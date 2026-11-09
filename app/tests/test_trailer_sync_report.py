"""What "Get trailers now" says when it finishes. Against real Radarr and
Sonarr, every YouTube download hit "Sign in to confirm you're not a bot" and
the page said nothing at all; with Radarr switched off it said nothing either."""

from backend import trailer_sync_report as report


def summary(kind="radarr", **results):
    results.setdefault("read_any", True)
    return report.summarize(kind, results)


def test_youtube_wall_is_explained_with_where_to_fix_it():
    results = {"read_any": True, "checked": 6, "downloaded": 0}
    for _ in range(6):
        report.count_failure(results, {"error": "YOUTUBE_BOT_BLOCK", "message": "YOUTUBE_BOT_BLOCK: ..."})
    s = report.summarize("radarr", results)
    assert not s["success"] and s["trouble"]
    assert s["message"] == "YouTube refused to hand over 6 trailers. It wants proof that this server isn't a robot."
    assert "If downloads fail" in s["hint"] and "Get trailers now" in s["hint"]


def test_every_radarr_off():
    s = summary(read_any=False, failed_servers=["Radarr", "Radarr 4K"])
    assert not s["success"]
    assert s["message"] == "Prerolls Max couldn't reach Radarr and Radarr 4K, so it didn't look for new trailers."
    assert "keep playing" in s["hint"]


def test_one_radarr_off_and_some_downloaded():
    s = summary(downloaded=2, checked=5, failed_servers=["Radarr 4K"])
    assert s["success"] and s["trouble"]
    assert s["message"] == "Downloaded 2 trailers. Radarr 4K didn't answer, so its movies were skipped this time."


def test_choices_are_not_failures():
    results = {"read_any": True, "checked": 3}
    for code in ("TOO_LONG", "NO_LANGUAGE_MATCH"):
        report.count_failure(results, {"error": code})
    s = report.summarize("radarr", results)
    assert s["success"] and not s["trouble"]
    assert "download" in s["message"].lower()


def test_other_kinds_of_failure():
    results = {"read_any": True, "checked": 4}
    report.count_failure(results, {"error": "VIDEO_UNAVAILABLE"})
    report.count_failure(results, {"error": "DOWNLOAD_FAILED"})
    report.count_failure(results, None)
    s = report.summarize("radarr", results)
    assert "1 trailer is no longer on YouTube." in s["message"]
    assert "2 trailers couldn't be downloaded." in s["message"]
    assert "Logs" in s["hint"]


def test_nothing_new_and_limit_reached():
    assert summary(checked=0)["message"] == "Radarr has nothing coming out in the days you look ahead."
    assert summary(checked=4)["message"].startswith("Nothing new to download.")
    assert "Most trailers to keep" in summary(checked=4, limit_reached=True)["message"]


def test_tv_needs_a_tmdb_key():
    s = summary("sonarr", checked=3, skipped_no_trailer=3, tmdb_key_rejected=True)
    assert not s["success"]
    assert "TMDB turned down the key" in s["message"]
    assert "Your own TMDB key" in s["hint"]


def test_tv_no_trailer_yet():
    s = summary("sonarr", checked=3, skipped_no_trailer=3)
    assert s["message"] == "No trailer was found for 3 shows yet."


def test_no_raw_error_text():
    s = summary(sync_error=True, errors=["Traceback: KeyError 'x'"])
    assert "Traceback" not in s["message"] and "KeyError" not in s["message"]
    assert s["message"] == "The check stopped partway."


def test_old_saved_errors_read_plainly():
    old = ("YouTube requires a Proof-of-Origin (PO) token and the token provider isn't active. Install the "
           "YouTube downloader (Node + PO-token provider) on the System page, then retry. Age-restricted trailers "
           "can also use cookies at /data/prerolls/nexup_trailers/library/youtube_cookies.txt.")
    plain = report.plain_error(old)
    assert "Proof-of-Origin" not in plain and "System page" not in plain and "/data" not in plain
    assert "If downloads fail" in plain


def test_raw_downloader_output_is_dropped():
    old = ("This trailer can't be downloaded because YouTube reports the source video as unavailable. "
           "[YouTube: ERROR: [youtube] QftAW9TTmuQ: This video is not available]")
    plain = report.plain_error(old)
    assert "ERROR" not in plain and "QftAW9TTmuQ" not in plain
    assert plain == "YouTube says this trailer is private, removed or blocked in your country."


def test_own_sentences_are_kept():
    assert report.plain_error("No usable trailer could be downloaded.") == "No usable trailer could be downloaded."
    assert report.plain_error(None) is None
