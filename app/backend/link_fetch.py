"""Download one video file from a web link, safely.

Prerolls Max fetches the link itself, from the machine it runs on, so a link
must not be able to reach places the person couldn't reach from outside
(server-side request forgery). The rules:

- http and https only, no user name or password in the link.
- The host name is looked up first and every address it gives must be on the
  internet: loopback, private, link-local (cloud metadata), multicast and
  reserved addresses are refused. The connection then goes to the address
  that was checked, so a second lookup can't swap in another one. The
  admin-only setting "Allow links to my home network" lifts the block for
  private and loopback addresses (a NAS); link-local, multicast and reserved
  ones stay blocked.
- Redirects are followed by hand, at most ``MAX_REDIRECTS``, and each new
  address goes through the same checks.
- When the machine is set up to use a proxy (HTTPS_PROXY, HTTP_PROXY,
  NO_PROXY), requests go through it, like everything else Prerolls Max fetches.
  Addresses are still checked where they can be looked up here.
- The size is capped, connect and read time out, and the file streams to a
  temporary name that is only used once complete.
- Web pages, video sites (YouTube, Vimeo...) and streams (.m3u8, .mpd) are
  refused in plain words: they aren't video files.

``check_link`` is mirrored in the web page (frontend/src/lib/validate.ts) with
the same messages, so people see a problem as they paste.
"""
from __future__ import annotations

import ipaddress
import os
import re
import socket
import tempfile
import urllib.parse
import urllib.request
from email.message import Message
from typing import Callable, Optional

import urllib3

from backend.errors import AppError, bad_input

MAX_REDIRECTS = 5
MAX_URL_LENGTH = 2000
CONNECT_SECONDS = 10
READ_SECONDS = 30
CHUNK = 256 * 1024

# Sites whose links open a player page, not a file.
VIDEO_SITES = {
    "youtube.com": "YouTube", "youtu.be": "YouTube", "youtube-nocookie.com": "YouTube",
    "vimeo.com": "Vimeo", "tiktok.com": "TikTok", "instagram.com": "Instagram",
    "facebook.com": "Facebook", "fb.watch": "Facebook", "twitter.com": "X", "x.com": "X",
    "dailymotion.com": "Dailymotion", "twitch.tv": "Twitch", "reddit.com": "Reddit",
    "streamable.com": "Streamable", "rumble.com": "Rumble", "bilibili.com": "Bilibili",
}
STREAM_EXTENSIONS = (".m3u8", ".m3u", ".mpd", ".f4m", ".ism", ".isml")
STREAM_TYPES = ("application/vnd.apple.mpegurl", "application/x-mpegurl", "audio/mpegurl",
                "application/dash+xml", "vnd.ms-sstr+xml")
PAGE_TYPES = ("text/html", "application/xhtml+xml")
TYPE_EXTENSIONS = {
    "video/mp4": ".mp4", "video/x-m4v": ".m4v", "video/quicktime": ".mov", "video/webm": ".webm",
    "video/x-matroska": ".mkv", "video/matroska": ".mkv", "video/x-msvideo": ".avi", "video/avi": ".avi",
    "video/mp2t": ".ts", "video/mpeg": ".mpg", "video/x-ms-wmv": ".wmv", "video/x-flv": ".flv",
}


def _site(host: str) -> Optional[str]:
    host = host.lower().rstrip(".")
    for domain, name in VIDEO_SITES.items():
        if host == domain or host.endswith("." + domain):
            return name
    return None


def check_link(value) -> str:
    """The link, trimmed, or a plain 422 saying why it can't be used."""
    text = str(value or "").strip()
    if not text:
        raise bad_input("Paste a link to a video file.", field="url")
    if len(text) > MAX_URL_LENGTH:
        raise bad_input("That link is too long.", field="url")
    parts = urllib.parse.urlsplit(text)
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise bad_input("Use a link that starts with http:// or https://.", field="url")
    if parts.username or parts.password:
        raise bad_input("Links with a user name or password in them can't be used.", field="url",
                        hint="Use a link that opens the file without signing in.")
    site = _site(parts.hostname)
    if site:
        raise bad_input(
            f"That's a video page, not a video file. Prerolls Max can't download from {site}; "
            f"it's against {site}'s terms.", field="url",
            hint="Download the file yourself if you have the rights to it, then upload it.")
    if parts.path.lower().endswith(STREAM_EXTENSIONS):
        raise bad_input("That's a stream, not a file. Prerolls Max needs a link to one video file.",
                        field="url", hint="Look for a download link that ends in .mp4 or .mkv.")
    return text


# --- addresses ------------------------------------------------------------------

def _allowed(ip: ipaddress._BaseAddress, home_network: bool) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if ip.is_multicast or ip.is_unspecified or ip.is_link_local or ip.is_reserved:
        return False
    if ip.is_global:
        return True
    return home_network and (ip.is_private or ip.is_loopback)


def _blocked(host: str) -> AppError:
    return AppError(f"Prerolls Max won't download from {host}: that address is on your own network.",
                    status=422, code="link_private_address", fields={"url": "That address is on your own network."},
                    hint="To use a computer or NAS at home, an admin can turn on \"Allow links to my home "
                         "network\" in Settings, Playback.")


def pick_address(host: str, port: int, *, home_network: bool, resolve=socket.getaddrinfo,
                 via_proxy: bool = False) -> Optional[str]:
    """The checked address to connect to. None only when a proxy will look the
    name up itself (it couldn't be looked up here)."""
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        literal = None
    if literal is not None:
        if not _allowed(literal, home_network):
            raise _blocked(host)
        return str(literal)
    if host.lower().rstrip(".") in ("localhost",) or host.lower().endswith((".localhost", ".local", ".internal")):
        if not home_network:
            raise _blocked(host)
    try:
        infos = resolve(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError, OSError):
        if via_proxy:
            return None
        raise AppError(f"Prerolls Max couldn't find the site {host}.", status=422, code="link_unreachable",
                       fields={"url": "Check the link."}, hint="Check the link for typos, then try again.")
    addresses = []
    for info in infos:
        try:
            addresses.append(ipaddress.ip_address(info[4][0].split("%")[0]))
        except ValueError:
            continue
    if not addresses or not all(_allowed(a, home_network) for a in addresses):
        raise _blocked(host)
    return str(addresses[0])


# --- downloading --------------------------------------------------------------

def _proxy_for(url: str) -> Optional[str]:
    host = urllib.parse.urlsplit(url).hostname or ""
    if urllib.request.proxy_bypass(host):
        return None
    proxies = urllib.request.getproxies()
    return proxies.get(urllib.parse.urlsplit(url).scheme.lower())


def _ca_file() -> Optional[str]:
    for key in ("REQUESTS_CA_BUNDLE", "SSL_CERT_FILE", "CURL_CA_BUNDLE"):
        path = os.environ.get(key)
        if path and os.path.isfile(path):
            return path
    try:
        import certifi
        return certifi.where()
    except ImportError:
        return None


def _open(url: str, *, home_network: bool, resolve) -> urllib3.BaseHTTPResponse:
    parts = urllib.parse.urlsplit(url)
    scheme, host = parts.scheme.lower(), parts.hostname or ""
    port = parts.port or (443 if scheme == "https" else 80)
    timeout = urllib3.Timeout(connect=CONNECT_SECONDS, read=READ_SECONDS)
    headers = {"User-Agent": "Prerolls Max (intro video download)", "Accept": "video/*, */*;q=0.5"}
    proxy = _proxy_for(url)
    address = pick_address(host, port, home_network=home_network, resolve=resolve, via_proxy=bool(proxy))
    tls = {"cert_reqs": "CERT_REQUIRED", "ca_certs": _ca_file()} if scheme == "https" else {}
    if proxy:
        manager = urllib3.ProxyManager(proxy, timeout=timeout, retries=False, **tls)
        return manager.request("GET", url, headers=headers, redirect=False, preload_content=False)
    target = parts.path or "/"
    if parts.query:
        target += "?" + parts.query
    headers["Host"] = host if parts.port is None else f"{host}:{parts.port}"
    if scheme == "https":
        # Connect to the checked address, but check the certificate (and send
        # SNI) for the name in the link.
        pool = urllib3.HTTPSConnectionPool(address, port, timeout=timeout, retries=False, server_hostname=host,
                                           assert_hostname=host, **tls)
    else:
        pool = urllib3.HTTPConnectionPool(address, port, timeout=timeout, retries=False)
    return pool.urlopen("GET", target, headers=headers, redirect=False, preload_content=False)


def _status_problem(status: int) -> AppError:
    if status == 404 or status == 410:
        message = "There's no file at that link: the site says it can't find it."
    elif status in (401, 403):
        message = "The site won't let Prerolls Max download that file. It may need you to sign in."
    elif status == 429:
        message = "The site says too many downloads were asked for. Wait a while, then try again."
    else:
        message = f"The site didn't send the file (it answered with error {status})."
    return AppError(message, status=422, code="link_failed", fields={"url": message},
                    hint="Open the link in your browser to check it starts a download.")


def _filename(url: str, disposition: Optional[str], content_type: str) -> str:
    name = ""
    if disposition:
        msg = Message()
        msg["content-disposition"] = disposition
        name = msg.get_filename() or ""
    if not name:
        name = urllib.parse.unquote(os.path.basename(urllib.parse.urlsplit(url).path))
    name = re.sub(r'[\\/:*?"<>|,;\x00-\x1f]+', " ", os.path.basename(name.replace("\\", "/")))
    name = " ".join(name.split()).strip(" .")
    stem, ext = os.path.splitext(name)
    if not ext and content_type in TYPE_EXTENSIONS:
        ext = TYPE_EXTENSIONS[content_type]
    stem = (stem or "Video from a link")[:140].rstrip(" .")
    return stem + ext.lower()


def _is_page(head: bytes) -> bool:
    start = head.lstrip()[:200].lower()
    return start.startswith((b"<!doctype html", b"<html", b"<head", b"<?xml")) or b"<html" in start


def fetch(url: str, folder: str, *, max_bytes: int, home_network: bool = False,
          progress: Optional[Callable[[int, Optional[int]], None]] = None,
          resolve=socket.getaddrinfo) -> dict:
    """Download the video at ``url`` into ``folder``.

    Returns ``{"path", "filename", "size", "final_url"}``; raises AppError
    with a plain message for every way it can fail. The caller removes the
    file when done with it.
    """
    url = check_link(url)
    for _hop in range(MAX_REDIRECTS + 1):
        try:
            response = _open(url, home_network=home_network, resolve=resolve)
        except AppError:
            raise
        except urllib3.exceptions.SSLError as exc:
            raise AppError("The site's security certificate couldn't be checked, so nothing was downloaded.",
                           status=422, code="link_tls", fields={"url": "Check the link."}) from exc
        except (urllib3.exceptions.HTTPError, OSError) as exc:
            host = urllib.parse.urlsplit(url).hostname
            raise AppError(f"Prerolls Max couldn't reach {host}.", status=422, code="link_unreachable",
                           fields={"url": "The site didn't answer."},
                           hint="Check the link, and that this computer can reach the site.") from exc
        try:
            if response.status in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                if not location:
                    raise _status_problem(response.status)
                url = check_link(urllib.parse.urljoin(url, location))
                continue
            if response.status >= 400:
                raise _status_problem(response.status)
            return _save(response, url, folder, max_bytes=max_bytes, progress=progress)
        finally:
            response.release_conn()
    raise AppError("That link sends Prerolls Max from one address to another too many times.", status=422,
                   code="link_redirects", fields={"url": "Too many redirects."},
                   hint="Open it in your browser and copy the address of the file itself.")


def _save(response, url: str, folder: str, *, max_bytes: int, progress) -> dict:
    content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    if content_type in PAGE_TYPES:
        raise AppError("That link opens a web page, not a video file.", status=422, code="link_web_page",
                       fields={"url": "That's a web page."},
                       hint="On the page, look for a download button, and copy the link it uses.")
    if content_type in STREAM_TYPES:
        raise AppError("That's a stream, not a file. Prerolls Max needs a link to one video file.", status=422,
                       code="link_stream", fields={"url": "That's a stream."})
    from backend.uploads import human_size
    try:
        expected = int(response.headers.get("Content-Length") or 0) or None
    except ValueError:
        expected = None
    too_big = AppError(f"That video is too big. The limit is {human_size(max_bytes)}.", status=413,
                       code="too_large", fields={"url": "The file is too big."},
                       hint="Pick a smaller file, or make it smaller first.")
    if expected and expected > max_bytes:
        raise too_big
    filename = _filename(url, response.headers.get("Content-Disposition"), content_type)
    os.makedirs(folder, exist_ok=True)
    fd, part = tempfile.mkstemp(prefix=".link-", suffix=".part", dir=folder)
    size = 0
    try:
        with os.fdopen(fd, "wb") as out:
            head = b""
            for chunk in response.stream(CHUNK):
                if len(head) < 512:
                    head += chunk[: 512 - len(head)]
                    if len(head) >= 64 or len(chunk) < CHUNK:
                        if _is_page(head):
                            raise AppError("That link opens a web page, not a video file.", status=422,
                                           code="link_web_page", fields={"url": "That's a web page."})
                        if head.lstrip().startswith(b"#EXTM3U"):
                            raise AppError("That's a stream, not a file. Prerolls Max needs a link to one "
                                           "video file.", status=422, code="link_stream",
                                           fields={"url": "That's a stream."})
                size += len(chunk)
                if size > max_bytes:
                    raise too_big
                out.write(chunk)
                if progress:
                    progress(size, expected)
        if size == 0:
            raise AppError("The link gave an empty file.", status=422, code="empty_file",
                           fields={"url": "The file is empty."})
        final = os.path.join(folder, f".link-{os.path.basename(part)[6:-5]}-{filename}")
        os.replace(part, final)
    except BaseException:
        try:
            os.remove(part)
        except OSError:
            pass
        raise
    return {"path": final, "filename": filename, "size": size, "final_url": url}
