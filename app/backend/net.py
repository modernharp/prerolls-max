"""Guards for outgoing requests.

Two kinds of addresses reach the network from Prerolls Max:

1. Media servers and *arr apps the user configured. These are usually on the
   home network, so private addresses are allowed, but they must be valid web
   addresses (see validation.clean_server_url).
2. Fixed internet services (community libraries, holiday API, GitHub). These
   must only ever go to their own hosts, whatever a request or a saved setting
   says. Use :func:`require_host` before every fetch so a changed setting or
   a crafted ID can't make the server fetch another site (SSRF).
"""

from __future__ import annotations

from typing import Iterable
from urllib.parse import urlsplit


class BlockedAddress(ValueError):
    """The address isn't one this feature is allowed to contact."""


def host_of(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def require_host(url: str, allowed_hosts: Iterable[str], *, https_only: bool = True) -> str:
    """Return ``url`` if it points at one of ``allowed_hosts``, else raise.

    ``allowed_hosts`` are exact host names; subdomains must be listed too.
    """
    allowed = {h.lower().strip(".") for h in allowed_hosts}
    try:
        parts = urlsplit(url)
    except ValueError:
        raise BlockedAddress("That address isn't valid.")
    if parts.scheme not in (("https",) if https_only else ("http", "https")):
        raise BlockedAddress("Only secure (https) addresses are allowed here.")
    host = (parts.hostname or "").lower()
    if not host or host not in allowed:
        raise BlockedAddress(f"{host or 'That address'} isn't one of the allowed sites.")
    if parts.username or parts.password:
        raise BlockedAddress("Addresses with a user name or password aren't allowed here.")
    return url
