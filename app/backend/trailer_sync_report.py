"""What "Get trailers now" tells the person when it finishes.

The movie and TV syncs return counters; before this, the page showed nothing
at all when every download failed (YouTube's "confirm you're not a bot" wall,
Radarr switched off, a dead TMDB key). summarize() turns the counters into one
plain message and, when something needs doing, a hint saying what.
"""
from __future__ import annotations

from typing import Optional

# download_trailer() error codes where YouTube itself refused this server.
YOUTUBE_REFUSED = {"YOUTUBE_BOT_BLOCK", "STALE_COOKIES", "AGE_RESTRICTED", "RATE_LIMITED"}
# Choices, not failures: the trailer is too long or not in the chosen language.
SKIPPED_ON_PURPOSE = {"TOO_LONG", "NO_LANGUAGE_MATCH"}

FIX_YOUTUBE = ("Open “If downloads fail” on this page to add YouTube cookies or start the helper, "
               "then press Get trailers now again.")


def count_failure(results: dict, result: Optional[dict]) -> str:
    """Count a failed download by kind. Returns the error code."""
    code = str((result or {}).get("error") or "DOWNLOAD_FAILED") if isinstance(result, dict) else "DOWNLOAD_FAILED"
    if code in SKIPPED_ON_PURPOSE:
        return code
    if code in YOUTUBE_REFUSED:
        results["youtube_refused"] = results.get("youtube_refused", 0) + 1
    elif code == "VIDEO_UNAVAILABLE":
        results["video_unavailable"] = results.get("video_unavailable", 0) + 1
    elif code != "TMDB_KEY_REJECTED":
        results["download_failed"] = results.get("download_failed", 0) + 1
    return code


def plain_error(text: Optional[str]) -> Optional[str]:
    """A saved download error as one plain sentence.

    Rows saved by older versions hold messages such as "YouTube requires a
    Proof-of-Origin (PO) token... on the System page" and raw yt-dlp output in
    "[YouTube: ERROR: ...]"; they stay in the database until the next retry.
    """
    if not text:
        return text
    low = text.lower()
    if any(s in low for s in ("proof-of-origin", "po-token", "po token", "not a robot", "not a bot",
                              "sign in to confirm", "demanded sign-in", "requiring sign-in")):
        return ("YouTube asked this server to prove it isn't a robot. Open If downloads fail on the Movie "
                "trailers page to upload YouTube cookies or start the helper.")
    if "age-restricted" in low:
        return "This trailer is age-restricted, so YouTube only shows it to a signed-in account."
    if any(s in low for s in ("unavailable", "not available", "private", "removed")):
        return "YouTube says this trailer is private, removed or blocked in your country."
    if "rate-limit" in low or "too many requests" in low:
        return "YouTube has had too many requests from this network for now. It's tried again later."
    # Drop raw downloader output and file paths; keep our own sentence.
    cut = text.split(" [YouTube:", 1)[0].strip()
    return cut if cut and "/" not in cut and "\\" not in cut else "The trailer didn't download. It's tried again later."


def _trailers(n: int) -> str:
    return f"{n} trailer" if n == 1 else f"{n} trailers"


def _names(names: list) -> str:
    names = [str(n) for n in names if n]
    if len(names) <= 1:
        return names[0] if names else ""
    return ", ".join(names[:-1]) + " and " + names[-1]


def summarize(kind: str, results: dict) -> dict:
    """{success, message, hint} for a finished movie ("radarr") or TV ("sonarr") sync."""
    app = "Radarr" if kind == "radarr" else "Sonarr"
    what = "movies" if kind == "radarr" else "shows"
    failed = list(results.get("failed_servers") or [])
    downloaded = int(results.get("downloaded") or 0)
    refused = int(results.get("youtube_refused") or 0)
    unavailable = int(results.get("video_unavailable") or 0)
    other = int(results.get("download_failed") or 0)
    no_trailer = int(results.get("skipped_no_trailer") or 0)
    sentences, hints = [], []

    if results.get("read_any") is False:
        return {
            "success": False,
            "message": f"Prerolls Max couldn't reach {_names(failed) or app}, so it didn't look for new trailers.",
            "hint": f"Check that {app} is running and that its address hasn't changed. "
                    "The trailers you already have keep playing.",
        }

    if downloaded:
        sentences.append(f"Downloaded {_trailers(downloaded)}.")
    if failed:
        sentences.append(f"{_names(failed)} didn't answer, so {'its' if len(failed) == 1 else 'their'} {what} were skipped this time.")
    if results.get("sync_error"):
        sentences.append("The check stopped partway.")
        hints.append("Settings, Logs has the details.")
    if refused:
        sentences.append(f"YouTube refused to hand over {_trailers(refused)}. "
                         "It wants proof that this server isn't a robot.")
        hints.append(FIX_YOUTUBE)
    if unavailable:
        sentences.append(f"{_trailers(unavailable).capitalize()} {'is' if unavailable == 1 else 'are'} no longer on YouTube.")
    if other:
        sentences.append(f"{_trailers(other).capitalize()} couldn't be downloaded.")
        hints.append("Try again later. Settings, Logs has the details.")
    if results.get("tmdb_key_rejected"):
        sentences.append("TMDB turned down the key, so trailers for new seasons couldn't be looked up."
                         if kind == "sonarr" else
                         "TMDB turned down the key, so some trailers couldn't be looked up.")
        hints.append("Add a free TMDB key of your own under “Your own TMDB key” on this page.")
    elif no_trailer and not downloaded and kind == "sonarr":
        sentences.append(f"No trailer was found for {no_trailer} {'show' if no_trailer == 1 else 'shows'} yet.")
    if not sentences:
        if results.get("limit_reached"):
            sentences.append("You have as many trailers as you set it to keep. Raise “Most trailers to keep” to get more.")
        elif int(results.get("checked") or 0) == 0:
            sentences.append(f"{app} has nothing coming out in the days you look ahead.")
        else:
            sentences.append("Nothing new to download. You already have every trailer that's out for the movies coming soon.")

    trouble = bool(refused or other or failed or results.get("tmdb_key_rejected") or results.get("sync_error"))
    return {
        "success": not trouble or bool(downloaded),
        "message": " ".join(sentences),
        "hint": " ".join(dict.fromkeys(hints)) or None,
        "trouble": trouble,
    }
