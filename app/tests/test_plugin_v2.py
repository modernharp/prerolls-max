"""Plugin protocol v2 (/plugin/v2/intros) and the rules it makes possible.

The plugin sends what is about to play; Prerolls Max must answer from that
alone (no calls back into Jellyfin/Emby), require the API key in the header
while login is on, and hand out short-lived links relative to its address.
"""
import datetime
import types
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import errors
from backend.routers import plugin_v2
from backend.sequence_conditions import PlaybackContext, condition_holds, describe_condition, evaluate_rule


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def first(self):
        return self.rows[0] if self.rows else None

    def filter(self, *_):
        return self

    def all(self):
        return self.rows


class FakeDb:
    def __init__(self, setting):
        self.setting = setting

    def query(self, model):
        return FakeQuery([self.setting] if model is SettingModel else [])


class SettingModel:
    pass


class Key:
    id = 3
    name = "Jellyfin Plugin (Auto)"


@pytest.fixture(autouse=True)
def clean():
    plugin_v2.reset_seen()
    yield
    plugin_v2.reset_seen()
    plugin_v2.configure(None)


def make_client(login_on=False, paths=("/prerolls/a.mp4", "/prerolls/b.mp4"), mode="sequential"):
    calls = []
    clients = {}
    db = FakeDb(types.SimpleNamespace(auth_enabled=login_on, plugin_random_count=1))

    def get_db():
        yield db

    def resolve(db_, **kw):
        calls.append(kw)
        return {"paths": list(paths), "mode": mode}

    plugin_v2.configure(plugin_v2.Deps(
        get_db=get_db,
        resolve_intros=resolve,
        play_list=lambda setting, p, m, rotation: list(p),
        validate_api_key=lambda value, perm, db_: Key() if value == "good-key" else None,
        sign_stream_path=lambda path, expires: f"sig{expires}",
        file_version=lambda path: "10-20",
        plugin_clients=clients,
        setting_model=SettingModel,
    ))
    app = FastAPI()
    errors.install(app)
    app.include_router(plugin_v2.router)
    return TestClient(app), calls, clients


PLUGIN = {"X-PrerollsMax-Plugin": "jellyfin/2.0.0.0"}


def test_answers_with_relative_short_lived_links_and_versions():
    client, _, _ = make_client()
    answer = client.get("/plugin/v2/intros?item_type=Movie&item_id=abc", headers=PLUGIN)
    assert answer.status_code == 200
    body = answer.json()
    assert body["mode"] == "exact" and body["cache_seconds"] == 0
    assert [i["path"] for i in body["items"]] == ["/prerolls/a.mp4", "/prerolls/b.mp4"]
    item = body["items"][0]
    assert item["name"] == "a" and item["version"] == "10-20" and item["id"]
    assert item["stream_url"].startswith("/plugin/stream?")
    expires = int(parse_qs(urlparse(item["stream_url"]).query)["e"][0])
    assert 0 < expires - datetime.datetime.now().timestamp() <= plugin_v2.STREAM_LINK_SECONDS + 5
    assert "in order" in body["reason"]


def test_everything_the_plugin_sends_reaches_the_rules_without_lookups():
    client, calls, _ = make_client()
    query = ("item_type=Episode&item_id=e1&user_id=u1&user_name=Kid&library_id=l1&library_name=Kids%20TV"
             "&genres=Animation,Family&tags=4K&official_rating=TV-Y&series_id=s1&season=1&episode=2"
             "&is_first_in_session=0&audio_default=truehd&audio_codecs=truehd,ac3&path=%2Fm%2Fx.mkv&tmdb_id=99")
    assert client.get("/plugin/v2/intros?" + query, headers=PLUGIN).status_code == 200
    kw = calls[0]
    facts = kw["facts"]
    assert kw["media_type"] == "Episode" and kw["genres"] == ["Animation", "Family"] and kw["server_type"] == "jellyfin"
    assert facts["tags"] == ["4K"] and facts["official_rating"] == "TV-Y" and facts["user_name"] == "Kid"
    assert facts["library_name"] == "Kids TV" and facts["first_in_session"] is False and facts["path"] == "/m/x.mkv"
    assert facts["audio"] == {"default": "truehd", "formats": ["ac3", "truehd"], "complete": True}
    assert facts["tmdb_id"] == "99"


def test_first_in_session_is_worked_out_when_the_plugin_does_not_say():
    client, calls, _ = make_client()
    base = "/plugin/v2/intros?item_type=Episode&user_id=u9&series_id=s9&item_id="
    client.get(base + "ep1", headers=PLUGIN)
    client.get(base + "ep2", headers=PLUGIN)
    client.get(base + "ep1", headers=PLUGIN)
    assert [c["facts"]["first_in_session"] for c in calls] == [True, False, True]


def test_binge_sessions_restart_after_a_break():
    binges = plugin_v2.BingeSessions()
    assert binges.is_first("u", "s", "e1", 3600, now=0)
    assert not binges.is_first("u", "s", "e2", 3600, now=1000)
    assert binges.is_first("u", "s", "e3", 3600, now=1000 + 3601)
    assert binges.is_first("other", "s", "e3", 3600, now=1000 + 3602)


def test_pool_request_lists_everything_for_the_cache():
    client, calls, _ = make_client(mode="shuffle")
    body = client.get("/plugin/v2/intros?all=1&item_type=Movie", headers=PLUGIN).json()
    assert body["mode"] == "pool" and body["cache_seconds"] == plugin_v2.POOL_CACHE_SECONDS
    assert calls[0]["whole_pool"] is True and len(body["items"]) == 2


def test_login_on_needs_a_key_in_the_header():
    client, _, clients = make_client(login_on=True)
    missing = client.get("/plugin/v2/intros?item_type=Movie", headers=PLUGIN)
    assert missing.status_code == 401 and missing.json()["error"]["code"] == "plugin_key_required"
    assert "login is on" in missing.json()["detail"]
    wrong = client.get("/plugin/v2/intros?item_type=Movie", headers={**PLUGIN, "X-Api-Key": "nope"})
    assert wrong.status_code == 401 and wrong.json()["error"]["code"] == "plugin_key_rejected"
    ok = client.get("/plugin/v2/intros?item_type=Movie", headers={**PLUGIN, "X-Api-Key": "good-key"})
    assert ok.status_code == 200
    assert clients["Jellyfin Plugin (Auto)"]["protocol"] == "v2"


def test_a_key_in_the_address_is_refused_even_with_login_off():
    client, _, _ = make_client()
    answer = client.get("/plugin/v2/intros?item_type=Movie&api_key=good-key", headers=PLUGIN)
    assert answer.status_code == 400 and answer.json()["error"]["code"] == "api_key_in_url"


def test_the_plugin_is_remembered_for_capabilities():
    client, _, _ = make_client()
    client.get("/plugin/v2/intros?item_type=Movie&server_id=srv1", headers={"X-PrerollsMax-Plugin": "emby/2.0.0.0"})
    rows = plugin_v2.seen_plugins("emby")
    assert rows[0]["plugin_version"] == "2.0.0.0" and rows[0]["protocol"] == "v2" and rows[0]["server_id"] == "srv1"
    assert plugin_v2.seen_plugins("jellyfin") == []


def test_never_answers_404_so_plugins_do_not_fall_back_to_v1():
    client, _, _ = make_client(paths=())
    answer = client.get("/plugin/v2/intros", headers=PLUGIN)
    assert answer.status_code == 200 and answer.json()["items"] == []
    assert answer.json()["reason"] == "Nothing is set to play right now, so no intros."


def test_unconfigured_module_says_it_is_starting():
    plugin_v2.configure(None)
    app = FastAPI()
    errors.install(app)
    app.include_router(plugin_v2.router)
    answer = TestClient(app).get("/plugin/v2/intros")
    assert answer.status_code == 503 and answer.json()["error"]["code"] == "starting"


# --- The rules v2 makes possible --------------------------------------------

def ctx(**kw):
    return PlaybackContext(now=datetime.datetime(2026, 11, 8, 20, 0), **kw)


def rule(kind, *values, negate=False, **extra):
    return {"kind": kind, "values": list(values), "negate": negate, **extra}


def test_rating_rules_ignore_spelling_and_country_prefixes():
    assert evaluate_rule(rule("rating", "PG-13"), ctx(official_rating="pg 13")) is True
    assert evaluate_rule(rule("rating", "12"), ctx(official_rating="DE-12")) is True
    assert evaluate_rule(rule("rating", "TV-Y", "G"), ctx(official_rating="TV-MA")) is False
    assert evaluate_rule(rule("rating", "G"), ctx()) is None  # Plex: unknown, so not met


def test_user_and_library_rules_match_names_or_ids():
    assert evaluate_rule(rule("user", "kid"), ctx(user_name="Kid", user_id="u1")) is True
    assert evaluate_rule(rule("user", "u1"), ctx(user_name="Kid", user_id="u1")) is True
    assert evaluate_rule(rule("user", "dad"), ctx(user_name="Kid")) is False
    assert evaluate_rule(rule("library", "kids movies"), ctx(library_name="Kids Movies")) is True
    assert evaluate_rule(rule("library", "Films"), ctx()) is None


def test_first_episode_rule_and_its_negation():
    first = {"match": "all", "rules": [{"kind": "first_in_session"}]}
    later = {"match": "all", "rules": [{"kind": "first_in_session", "negate": True}]}
    assert condition_holds(first, ctx(first_in_session=True))
    assert not condition_holds(first, ctx(first_in_session=False))
    assert condition_holds(later, ctx(first_in_session=False))
    # Unknown (Plex, old plugin) is never met, negated or not.
    assert not condition_holds(first, ctx()) and not condition_holds(later, ctx())


def test_new_rules_read_plainly_in_logs():
    text = describe_condition({"rules": [rule("rating", "G", "PG"), rule("user", "Kid"),
                                         rule("library", "Kids"), {"kind": "first_in_session"}]})
    assert text == "rated G or PG and watched by Kid and from the library Kids and the first episode of a sitting"


def test_playback_context_with_facts_never_calls_the_media_server(monkeypatch):
    from backend import media_audio, media_genres, scheduler

    def boom(*a, **kw):
        raise AssertionError("called back into the media server")

    monkeypatch.setattr(media_genres, "item_details", boom)
    monkeypatch.setattr(media_audio, "item_audio", boom)
    monkeypatch.setattr(scheduler, "_localized_now", lambda db: datetime.datetime(2026, 11, 8, 20, 0))
    facts = {"official_rating": "PG", "user_name": "Kid", "first_in_session": True, "tmdb_id": "42",
             "audio": {"default": "ac3", "formats": ["ac3"], "complete": True}}
    context = scheduler.playback_context(None, media_type="Movie", item_id="x", server_type="jellyfin",
                                         genres=[], tags=[], facts=facts)
    assert context.genres() == [] and context.tags() == [] and context.file_path() is None
    assert context.tmdb_id() == "42" and context.audio()["default"] == "ac3"
    assert context.official_rating == "PG" and context.user_name == "Kid" and context.first_in_session is True
