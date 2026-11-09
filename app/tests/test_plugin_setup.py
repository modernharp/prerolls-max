"""Setting up the Prerolls Max Intros plugins from Prerolls Max, and handing them out.

main.py functions are lifted onto a bare namespace (main is not imported).
"""
import os
import re
import types
from pathlib import Path
from typing import Optional

import pytest

from tests.test_keyless_plugins import load_main_functions


def env(**extra):
    base = dict(os=os, re=re, sys=__import__("sys"), Path=Path, Optional=Optional, __file__="/app/backend/main.py",
                PMAX_EMBY_PLUGIN_ID="2fea54cd-3c4a-4307-ab53-5e25a07a24ec")
    base.update(extra)
    return base


def test_the_plugin_keeps_a_key_that_still_works():
    created = []

    class Record:
        name = "Jellyfin Plugin (Auto)"

    class FakeDb:
        def query(self, *_):
            raise AssertionError("no key should be created or retired")

    ns = load_main_functions({"_plugin_api_key"}, env(
        validate_api_key=lambda key, perm, db: Record() if key == "working-key" else None,
        models=types.SimpleNamespace(), _generate_api_key=lambda: created.append(1)))
    raw, new = ns["_plugin_api_key"](FakeDb(), "Jellyfin Plugin (Auto)", "x", {"ApiKey": "working-key"})
    assert raw == "working-key" and new is None and not created


def test_settings_pushed_to_the_plugin_keep_its_own_choices():
    ns = load_main_functions({"_plugin_settings", "_plugin_url_of"}, env())
    req = types.SimpleNamespace(path_prefix_from="", path_prefix_to="", enable_for_movies=True,
                                enable_for_episodes=False, timeout_seconds=99)
    merged = ns["_plugin_settings"]({"BingeWindowHours": 6, "MaxCacheMegabytes": 512, "NexrollUrl": "old",
                                     "MaxIntros": 1}, "http://pmax:9393/", "k", req)
    assert merged["PrerollsMaxUrl"] == "http://pmax:9393" and merged["ApiKey"] == "k"
    assert merged["BingeWindowHours"] == 6 and merged["MaxCacheMegabytes"] == 512
    assert merged["TimeoutSeconds"] == 30 and merged["EnableForEpisodes"] is False
    assert "NexrollUrl" not in merged and "MaxIntros" not in merged
    assert ns["_plugin_url_of"]({"NexrollUrl": "http://old"}) == "http://old"
    assert ns["_plugin_url_of"]({"PrerollsMaxUrl": "http://new", "NexrollUrl": "http://old"}) == "http://new"


def test_emby_finds_our_plugin_not_the_nexroll_one():
    ns = load_main_functions({"_find_emby_plugin"}, env())
    nexroll = {"Name": "NeXroll Intros", "Id": "a1b2c3d4-e5f6-7890-abcd-ae0c01200002"}
    ours = {"Name": "Prerolls Max Intros", "Id": "2fea54cd3c4a4307ab535e25a07a24ec"}
    assert ns["_find_emby_plugin"]([nexroll, ours]) is ours
    assert ns["_find_emby_plugin"]([nexroll]) is None
    assert ns["_find_emby_plugin"]([{"Name": "Prerolls Max Intros"}])["Name"] == "Prerolls Max Intros"


@pytest.mark.parametrize("version,series", [("12.4.0", "12"), ("12.0", "12"), ("10.11.3", "10.11"),
                                            ("10.10.7", None), ("", None), (None, None)])
def test_jellyfin_series(version, series):
    ns = load_main_functions({"_jellyfin_series"}, env())
    assert ns["_jellyfin_series"](version) == series


def test_the_newest_package_for_the_series_is_served(tmp_path, monkeypatch):
    for name in ("PrerollsMax.Jellyfin-12-2.9.0.0.zip", "PrerollsMax.Jellyfin-12-2.10.0.0.zip",
                 "PrerollsMax.Jellyfin-10.11-2.10.0.0.zip", "PrerollsMax.Emby.dll"):
        (tmp_path / name).write_bytes(b"x")
    ns = load_main_functions({"_plugin_package_dirs", "_version_key", "_resolve_jellyfin_plugin_zip",
                              "_resolve_emby_plugin_dll"}, env())
    monkeypatch.setenv("PMAX_PLUGIN_ZIP", str(tmp_path))
    monkeypatch.setenv("PMAX_EMBY_PLUGIN_DLL", str(tmp_path))
    assert Path(ns["_resolve_jellyfin_plugin_zip"]("12")).name == "PrerollsMax.Jellyfin-12-2.10.0.0.zip"
    assert Path(ns["_resolve_jellyfin_plugin_zip"]("10.11")).name == "PrerollsMax.Jellyfin-10.11-2.10.0.0.zip"
    assert Path(ns["_resolve_jellyfin_plugin_zip"](None)).name == "PrerollsMax.Jellyfin-12-2.10.0.0.zip"
    assert Path(ns["_resolve_emby_plugin_dll"]()).name == "PrerollsMax.Emby.dll"
