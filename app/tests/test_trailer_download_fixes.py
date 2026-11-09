"""Fixes from testing trailers against real Radarr, Sonarr and YouTube."""

from pathlib import Path

from backend.dynamic_preroll import DynamicPrerollGenerator
from backend.radarr_connector import TrailerDownloader


def test_library_trailers_use_the_uploaded_cookies(tmp_path):
    # "Upload cookies.txt" saves into the trailer folder; library trailers
    # download into its "library" subfolder and looked for cookies there.
    library = tmp_path / "library"
    d = TrailerDownloader(str(library), "720", cookies_dir=str(tmp_path))
    assert d.cookies_file == tmp_path / "youtube_cookies.txt"


def test_coming_soon_cookies_default_to_the_trailer_folder(tmp_path):
    assert TrailerDownloader(str(tmp_path)).cookies_file == tmp_path / "youtube_cookies.txt"


def test_long_titles_end_with_an_ellipsis():
    short = DynamicPrerollGenerator._shorten("The Hunger Games: Sunrise on the Reaping", 40)
    assert short == "The Hunger Games: Sunrise on the Reaping"
    cut = DynamicPrerollGenerator._shorten("The Hunger Games: Sunrise on the Reaping (Extended)", 40)
    assert cut.endswith("…") and len(cut) <= 40


def test_a_cut_never_leaves_a_lone_backslash(tmp_path):
    gen = DynamicPrerollGenerator(str(tmp_path))
    # The colon falls exactly where the old code cut the escaped text.
    title = "A" * 38 + ": Part Two"
    escaped = gen._escape_text(gen._shorten(title, 40))
    assert not escaped.endswith("\\")
    assert escaped.count("\\") == escaped.count("\\:")
