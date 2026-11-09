"""GET /api/capabilities: what each media server can do, honestly (CONTRACTS.md section 6)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers import capabilities, plugin_v2


@pytest.fixture(autouse=True)
def clean():
    plugin_v2.reset_seen()
    capabilities.clear_cache()
    yield
    plugin_v2.reset_seen()
    capabilities.clear_cache()


def versions(kind, url, token):
    return {"plex": ("1.42.2", True), "jellyfin": ("12.4.0", True), "emby": (None, False)}[kind]


def build(servers=None, **kw):
    servers = servers if servers is not None else {
        "plex": {"url": "http://plex:32400", "token": "t"},
        "jellyfin": {"url": "http://jf:8096", "token": "k"},
        "emby": {"url": "http://emby:8096", "token": "k"},
    }
    return {s["type"]: s for s in capabilities.build_capabilities(servers, version_of=versions, **kw)["servers"]}


def test_every_server_lists_every_feature_with_a_level_and_a_sentence():
    for server in build().values():
        assert set(server["features"]) == set(capabilities.FEATURES)
        for name, feature in server["features"].items():
            assert feature["level"] in capabilities.LEVELS, name
            assert feature["note"].endswith(".") and len(feature["note"]) > 20, name


def test_plex_is_honest_about_what_it_cannot_do():
    plex = build()["plex"]["features"]
    assert plex["episodes"] == {"level": "none", "note": "Plex only plays intros before movies."}
    assert plex["genre_rules"]["level"] == "emulated"
    assert plex["genre_rules"]["note"].startswith("Plex picks the intro before it knows the movie, "
                                                  "so genre rules apply from the next play")
    assert plex["per_user"]["level"] == "emulated" and plex["on_resume"]["level"] == "none"
    assert "2026" in plex["client_notes"]["note"] and "1 before movie" in plex["client_notes"]["note"]


def test_jellyfin_and_emby_do_it_exactly_through_the_plugin():
    servers = build()
    for kind in ("jellyfin", "emby"):
        features = servers[kind]["features"]
        for name in ("genre_rules", "rating_rules", "per_user", "per_library", "episodes", "first_episode_only"):
            assert features[name]["level"] == "plugin", (kind, name)
    assert "Swiftfin" in servers["jellyfin"]["features"]["client_notes"]["note"]
    assert "Premiere" in servers["emby"]["features"]["client_notes"]["note"]


def test_versions_and_connection_state():
    servers = build()
    assert servers["plex"]["version"] == "1.42.2" and servers["plex"]["connected"] is True
    assert servers["jellyfin"]["version"] == "12.4.0"
    assert servers["emby"]["configured"] is True and servers["emby"]["connected"] is False
    unset = build({"plex": {"url": "", "token": None}})
    assert unset["plex"]["configured"] is False and unset["jellyfin"]["connected"] is False


def test_plugin_state_comes_from_what_asked_for_intros():
    assert build()["jellyfin"]["plugin"]["connected"] is False
    plugin_v2.note_plugin("jellyfin", version="2.0.0.0", protocol="v2", server_id="abc")
    plugin_v2.note_plugin("emby", version="1.14.2.0", protocol="v1", server_name="NAS")
    servers = build()
    assert servers["jellyfin"]["plugin"]["version"] == "2.0.0.0" and servers["jellyfin"]["plugin"]["connected"]
    assert servers["emby"]["plugin"]["protocol"] == "v1" and "older plugin" in servers["emby"]["plugin"]["note"]


def test_plex_says_why_personal_rules_are_on_hold():
    state = {"applies": False, "reason": "2 people are watching on Plex at once, ..."}
    assert build(plex_state=state)["plex"]["personalization"] == state


def test_versions_are_cached():
    calls = []

    def counting(kind, url, token):
        calls.append(kind)
        return "1", True

    for _ in range(3):
        capabilities.server_version("plex", "http://p", "t", fetch=counting)
    assert calls == ["plex"]


def test_the_endpoint(monkeypatch):
    monkeypatch.setattr(capabilities, "_configured_servers", lambda: {})
    monkeypatch.setattr(capabilities, "_plex_state", lambda: None)
    app = FastAPI()
    app.include_router(capabilities.router)
    body = TestClient(app).get("/api/capabilities").json()
    assert [s["type"] for s in body["servers"]] == ["plex", "jellyfin", "emby"]
    assert all(s["connected"] is False for s in body["servers"])


def test_smart_features_are_reported_honestly_per_server():
    servers = build()
    plex = servers["plex"]["features"]
    assert plex["rule_sets"]["level"] == "none" and plex["exclude_titles"]["level"] == "none"
    assert "whole library" in plex["exclude_titles"]["note"]
    assert plex["kids_safe"]["level"] == "emulated" and plex["weights_cooldowns"]["level"] == "emulated"
    assert plex["play_history"]["level"] == "emulated" and "15 seconds" in plex["play_history"]["note"]
    for name in ("combined_file", "loudness", "matching_versions", "watch_folders"):
        assert plex[name]["level"] == "native", name
    for kind in ("jellyfin", "emby"):
        features = servers[kind]["features"]
        for name in ("rule_sets", "year_rules", "kids_safe", "exclude_titles", "weights_cooldowns", "play_history",
                     "missed_intro_check", "combined_file", "loudness", "matching_versions", "watch_folders"):
            assert features[name]["level"] == "plugin", (kind, name)
        assert "no-intro" in features["exclude_titles"]["note"]
    assert "Roku" in servers["jellyfin"]["features"]["combined_file"]["note"]
