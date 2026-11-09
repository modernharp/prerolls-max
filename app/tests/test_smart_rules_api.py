"""The rule-set API and the rules end to end through /plugin/v2/intros.

A kids rule must win for a PG movie, an excluded title must get no intros,
items tagged no-intro too, and anything no rule matches falls back to the
schedules. Every answer is recorded for play history and the missed-intro check.
"""
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import errors, features, models, smart_settings
from backend.database import SessionLocal
from backend.routers import plugin_v2, rules
from tests.smart_fixtures import collection, preroll, smart_db  # noqa: F401


@pytest.fixture
def api(smart_db):
    app = FastAPI()
    errors.install(app)
    app.include_router(rules.router)
    return TestClient(app), smart_db


@pytest.fixture
def library(smart_db, tmp_path):
    kids = collection(smart_db, "T-Kids intros")
    grown = collection(smart_db, "T-Grown-up intros")
    k1 = preroll(smart_db, str(tmp_path / "kids-1.mp4"), kids, display_name="Cartoon intro")
    k2 = preroll(smart_db, str(tmp_path / "kids-2.mp4"), kids)
    g1 = preroll(smart_db, str(tmp_path / "grown-1.mp4"), grown)
    return types.SimpleNamespace(kids=kids, grown=grown, k1=k1, k2=k2, g1=g1)


def kids_rule(collection_id, **extra):
    return {"name": "Kids", "when": {"kids_safe": True, "media_type": "movie"},
            "play": {"collection_id": collection_id, "count": 1, "order": "random"}, **extra}


# --- CRUD ---------------------------------------------------------------------

def test_create_list_update_order_delete(api, library):
    client, _ = api
    created = client.post("/api/rules", json=kids_rule(library.kids.id))
    assert created.status_code == 200, created.text
    rule = created.json()
    assert rule["summary"] == "When a movie and rated kids-safe. Plays 1 intro at random from 'T-Kids intros'."
    assert {p["name"] for p in rule["plays"]} == {"Cartoon intro", "kids-2"} and rule["problem"] is None

    second = client.post("/api/rules", json={"name": "80s", "when": {"decades": ["80s"]},
                                             "play": {"preroll_ids": [library.g1.id], "order": "in_order"},
                                             "position": 0}).json()
    listed = client.get("/api/rules").json()
    assert [r["name"] for r in listed["rules"]] == ["80s", "Kids"]
    assert second["when"]["decades"] == ["1980s"] and "schedules decide" in listed["fallback"]

    reordered = client.put("/api/rules/order", json={"ids": [rule["id"], second["id"]]}).json()
    assert [r["name"] for r in reordered["rules"]] == ["Kids", "80s"]

    changed = client.put(f"/api/rules/{rule['id']}", json=kids_rule(library.kids.id, name="Kids only", enabled=False))
    assert changed.json()["name"] == "Kids only" and changed.json()["enabled"] is False

    assert client.delete(f"/api/rules/{second['id']}").json() == {"deleted": True}
    missing = client.get(f"/api/rules/{second['id']}")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "not_found"


def test_rule_input_is_checked_in_plain_words(api, library):
    client, _ = api
    no_source = client.post("/api/rules", json={"name": "x", "play": {}})
    assert no_source.status_code == 422
    assert no_source.json()["error"]["fields"]["play"] == "Choose a collection or some intro videos to play."
    bad_decade = client.post("/api/rules", json={**kids_rule(library.kids.id), "when": {"decades": ["soon"]}})
    assert bad_decade.json()["error"]["fields"]["when.decades"] == "Use decades like 1980s or 1990."
    bad_media = client.post("/api/rules", json={**kids_rule(library.kids.id), "when": {"media_type": "song"}})
    assert "Pick one of" in bad_media.json()["error"]["fields"]["when.media_type"]
    gone = client.post("/api/rules", json=kids_rule(999999))
    assert gone.status_code == 422 and gone.json()["error"]["fields"]["play.collection_id"].startswith("That collection")
    first_ep = client.post("/api/rules", json={**kids_rule(library.kids.id),
                                               "when": {"media_type": "movie", "first_episode_only": True}})
    assert "needs the rule to cover episodes" in first_ep.json()["detail"]
    order = client.put("/api/rules/order", json={"ids": [12345]})
    assert order.status_code == 422 and "every rule once" in order.json()["detail"]


def test_preview_says_why_in_plain_words(api, library):
    client, _ = api
    client.post("/api/rules", json={"name": "Horror", "when": {"genres": ["Horror"]},
                                    "play": {"collection_id": library.grown.id}})
    client.post("/api/rules", json=kids_rule(library.kids.id))
    answer = client.post("/api/rules/preview", json={"item": {"item_name": "Toy Story", "official_rating": "G",
                                                              "genres": ["Animation"]}}).json()
    assert answer["matched"]["name"] == "Kids"
    assert answer["explanation"] == ("Matches 'Kids' because it's a movie and the movie is rated G, which is "
                                     "kids-safe. It plays 1 of these 2 at random.")
    assert answer["checks"][0]["why"] == "Doesn't match: the movie is Animation, not Horror."
    assert {p["name"] for p in answer["pool"]} == {"Cartoon intro", "kids-2"}

    nothing = client.post("/api/rules/preview", json={"item": {"official_rating": "R"}}).json()
    assert nothing["matched"] is None and nothing["explanation"] == "No rule matches, so your schedules decide."
    assert nothing["fallback"].startswith(("Right now", "Nothing is set up"))


def test_never_play_list_api_and_preview(api, library):
    client, _ = api
    added = client.post("/api/exclusions", json={"kind": "title", "value": "  The Room ", "note": "No"})
    assert added.status_code == 200 and added.json()["value"] == "The Room"
    duplicate = client.post("/api/exclusions", json={"kind": "title", "value": "the room"})
    assert duplicate.status_code == 409 and duplicate.json()["error"]["code"] == "already_excluded"
    wrong = client.post("/api/exclusions", json={"kind": "studio", "value": "x"})
    assert wrong.status_code == 422
    listed = client.get("/api/exclusions").json()
    assert [i["value"] for i in listed["items"]] == ["The Room"] and listed["auto_tags"]["enabled"] is True
    preview = client.post("/api/rules/preview", json={"item": {"item_name": "The Room"}}).json()
    assert preview["excluded"] is True and preview["explanation"] == "No intros: 'The Room' is on your never-play list."
    assert client.delete(f"/api/exclusions/{added.json()['id']}").json() == {"deleted": True}


def test_smart_settings_round_trip_and_checks(api, monkeypatch):
    client, _ = api
    from backend import plugin_push
    monkeypatch.setattr(plugin_push, "push_binge_window", lambda hours: [{"server": "jellyfin", "updated": True}])
    defaults = client.get("/api/smart-settings").json()
    assert defaults["binge_window_hours"] == 4 and defaults["history_retention_days"] == 90
    assert defaults["loudness_target_lufs"] == -23.0 and defaults["unrated_is_kids_safe"] is False
    saved = client.put("/api/smart-settings", json={"binge_window_hours": 6, "kids_safe_ratings": ["g", "tv y"],
                                                    "history_retention_days": 30}).json()
    assert saved["binge_window_hours"] == 6 and saved["kids_safe_ratings"] == ["G", "TV-Y"]
    assert saved["plugins_updated"][0]["updated"] is True
    assert features.binge_hours() == 6
    bad = client.put("/api/smart-settings", json={"binge_window_hours": 100})
    assert bad.status_code == 422 and bad.json()["error"]["fields"]["binge_window_hours"] == "Use 48 or less."
    unknown = client.put("/api/smart-settings", json={"plex_token": "x"})
    assert unknown.status_code == 422
    families = client.get("/api/ratings").json()
    assert families["kids_safe"] == ["G", "TV-Y"]


# --- end to end through the plugin -------------------------------------------

def plugin_client(schedule_paths=("/schedule/a.mp4",)):
    calls = []

    def get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def resolve(db, **kw):
        calls.append(kw)
        return {"paths": list(schedule_paths), "mode": "sequential"}

    plugin_v2.configure(plugin_v2.Deps(
        get_db=get_db, resolve_intros=resolve, play_list=lambda setting, p, m, rotation: list(p),
        validate_api_key=lambda *a: None, sign_stream_path=lambda path, expires: "sig",
        file_version=lambda path: "1-2", plugin_clients={}, setting_model=models.Setting,
        preroll_model=models.Preroll, smart_intros=features.smart_intros, rule_pool=features.rule_pool,
        on_answer=features.on_answer, binge_hours=features.binge_hours))
    app = FastAPI()
    errors.install(app)
    app.include_router(plugin_v2.router)
    return TestClient(app), calls


@pytest.fixture
def plugin(smart_db):
    plugin_v2.reset_seen()
    yield plugin_client
    plugin_v2.configure(None)
    plugin_v2.reset_seen()


HEADERS = {"X-PrerollsMax-Plugin": "jellyfin/2.0.0"}


def test_a_kids_rule_wins_through_the_plugin(api, library, plugin):
    client, db = api
    client.post("/api/rules", json=kids_rule(library.kids.id))
    pclient, calls = plugin()
    body = pclient.get("/plugin/v2/intros?item_type=Movie&item_id=m1&item_name=Toy%20Story&official_rating=PG"
                       "&user_name=Kid&client=Jellyfin%20Web", headers=HEADERS).json()
    assert body["reason"] == "Matches 'Kids' because it's a movie and the movie is rated PG, which is kids-safe."
    assert len(body["items"]) == 1 and body["items"][0]["id"] in (str(library.k1.id), str(library.k2.id))
    assert calls == []  # the schedules weren't asked

    plays = db.query(models.PlayEvent).all()
    assert len(plays) == 1 and plays[0].rule_name == "Kids" and plays[0].user_name == "Kid"
    assert plays[0].server_type == "jellyfin" and plays[0].client == "Jellyfin Web"
    check = db.query(models.PlaybackCheck).one()
    assert check.outcome == "intros" and check.intro_count == 1 and check.item_id == "m1"


def test_rules_that_do_not_match_fall_back_to_schedules(api, library, plugin):
    client, db = api
    client.post("/api/rules", json=kids_rule(library.kids.id))
    pclient, calls = plugin()
    body = pclient.get("/plugin/v2/intros?item_type=Movie&item_id=m2&official_rating=R", headers=HEADERS).json()
    assert [i["path"] for i in body["items"]] == ["/schedule/a.mp4"] and len(calls) == 1
    assert body["intentional_empty"] is False


def test_an_excluded_title_and_a_no_intro_tag_get_nothing(api, library, plugin):
    client, db = api
    client.post("/api/rules", json={"name": "Everything", "play": {"collection_id": library.grown.id}})
    client.post("/api/exclusions", json={"kind": "item", "value": "abc"})
    pclient, calls = plugin()
    excluded = pclient.get("/plugin/v2/intros?item_type=Movie&item_id=abc&item_name=Live%20Concert",
                           headers=HEADERS).json()
    assert excluded["items"] == [] and excluded["reason"] == "No intros: 'Live Concert' is on your never-play list."
    tagged = pclient.get("/plugin/v2/intros?item_type=Movie&item_id=x&item_name=Doc&tags=4K,no-intro",
                         headers=HEADERS).json()
    assert tagged["items"] == [] and tagged["reason"] == "No intros: 'Doc' has the tag 'no-intro'."
    # Deliberate, so the plugin keeps its fallback list (CONTRACTS.md section 7).
    assert excluded["intentional_empty"] is True and tagged["intentional_empty"] is True
    assert calls == []
    outcomes = sorted(c.outcome for c in db.query(models.PlaybackCheck).all())
    assert outcomes == ["excluded", "excluded"] and db.query(models.PlayEvent).count() == 0


def test_pool_requests_include_every_rule_intro(api, library, plugin):
    client, _ = api
    client.post("/api/rules", json=kids_rule(library.kids.id))
    pclient, _calls = plugin()
    body = pclient.get("/plugin/v2/intros?all=1&item_type=Movie", headers=HEADERS).json()
    paths = [i["path"] for i in body["items"]]
    assert "/schedule/a.mp4" in paths and library.k1.path in paths and library.k2.path in paths


def test_first_episode_rule_and_the_binge_gap_setting(api, library, plugin):
    client, db = api
    client.post("/api/rules", json={"name": "First episode", "when": {"media_type": "episode",
                                                                      "first_episode_only": True},
                                    "play": {"preroll_ids": [library.g1.id], "order": "in_order"}})
    smart_settings.save(db, {"binge_window_hours": 2})
    pclient, calls = plugin(schedule_paths=())
    base = "/plugin/v2/intros?item_type=Episode&user_id=u1&series_id=s1&item_id="
    first = pclient.get(base + "e1", headers=HEADERS).json()
    second = pclient.get(base + "e2", headers=HEADERS).json()
    assert [i["path"] for i in first["items"]] == [library.g1.path]
    assert second["items"] == [] and len(calls) == 1
    assert second["intentional_empty"] is False  # nothing set to play isn't a deliberate "none"
    told = pclient.get(base + "e3&is_first_in_session=1", headers=HEADERS).json()
    assert len(told["items"]) == 1


def test_a_rule_whose_collection_is_empty_falls_back(api, library, plugin, tmp_path):
    client, db = api
    empty = collection(db, "T-Empty")
    client.post("/api/rules", json={"name": "Empty", "play": {"collection_id": empty.id}})
    pclient, calls = plugin()
    body = pclient.get("/plugin/v2/intros?item_type=Movie&item_id=z", headers=HEADERS).json()
    assert [i["path"] for i in body["items"]] == ["/schedule/a.mp4"] and len(calls) == 1
    listed = client.get("/api/rules").json()["rules"][0]
    assert listed["problem"] == "'T-Empty' has no intro videos whose files are there."
