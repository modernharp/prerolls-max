"""Weighted random picks and "don't repeat within N hours" (weighting.py)."""
import collections
import datetime
import os
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import errors, models, weighting
from backend.routers import automation as automation_routes
from backend.shuffle_bag import clear_shuffle_bags
from backend.timeutil import utcnow
from tests.smart_fixtures import collection, preroll, smart_db  # noqa: F401
from tests.test_multi_server_apply import MultiServerFixture

NOW = datetime.datetime(2026, 11, 8, 20, 0)


def item(i, weight=5, path=None):
    return types.SimpleNamespace(id=i, weight=weight, path=path or f"/p/{i}.mp4")


@pytest.fixture(autouse=True)
def fresh():
    clear_shuffle_bags()
    yield
    clear_shuffle_bags()


def test_equal_weights_keep_the_no_repeat_rotation():
    pool = [item(i) for i in range(5)]
    first_round = [weighting.pick("bag", pool, 1, now=NOW)[0].id for _ in pool]
    assert sorted(first_round) == [0, 1, 2, 3, 4]


def test_heavier_intros_play_proportionally_more_often():
    pool = [item(1, weight=10), item(2, weight=5), item(3, weight=1)]
    picks = collections.Counter(weighting.pick("w", pool, 1, now=NOW)[0].id for _ in range(1600))
    assert picks == {1: 1000, 2: 500, 3: 100}


def test_a_multi_pick_never_repeats_an_intro_in_one_playback():
    pool = [item(1, weight=10), item(2, weight=1), item(3, weight=1)]
    for _ in range(50):
        ids = [p.id for p in weighting.pick("multi", pool, 2, now=NOW)]
        assert len(set(ids)) == 2


def test_cooldown_leaves_recent_intros_out_while_others_can_play():
    pool = [item(1), item(2), item(3)]
    last = {1: NOW - datetime.timedelta(hours=1), 2: NOW - datetime.timedelta(hours=30)}
    picks = {weighting.pick(("cool", n), pool, 1, last_played=last, cooldown_hours=24, now=NOW)[0].id
             for n in range(30)}
    assert 1 not in picks and picks <= {2, 3}


def test_when_everything_is_resting_the_longest_rested_plays():
    pool = [item(1), item(2)]
    last = {1: NOW - datetime.timedelta(hours=1), 2: NOW - datetime.timedelta(hours=5)}
    assert [p.id for p in weighting.pick("all", pool, 1, last_played=last, cooldown_hours=24, now=NOW)] == [2]


def test_plex_list_repeats_heavier_intros():
    pool = [item(1, weight=10), item(2, weight=5), item(3, weight=5)]
    entries = weighting.plex_entries(pool, random_mode=True)
    assert [p.id for p in entries] == [1, 2, 3, 1]
    # In-order lists and unweighted lists are left exactly as they were.
    assert weighting.plex_entries(pool, random_mode=False) == pool
    plain = [item(1), item(2)]
    assert weighting.plex_entries(plain, random_mode=True) == plain


def test_plex_list_scales_down_to_fit_and_drops_resting_intros():
    pool = [item(i, weight=10 if i == 0 else 1, path="/" + "x" * 200) for i in range(20)]
    entries = weighting.plex_entries(pool, random_mode=True, max_chars=6000)
    assert sum(len(p.path) + 1 for p in entries) <= 6000 and entries.count(pool[0]) > 1
    last = {0: NOW - datetime.timedelta(hours=1)}
    rested = weighting.plex_entries(pool[:3], random_mode=True, cooldown_hours=12, last_played=last, now=NOW)
    assert pool[0] not in rested and len(rested) == 2


def test_sequence_random_blocks_use_weights_and_the_collection_cooldown(smart_db, tmp_path):
    from backend.scheduler import resolve_category_sequence_block
    group = collection(smart_db)
    heavy = preroll(smart_db, str(tmp_path / "heavy.mp4"), group, weight=10)
    light = preroll(smart_db, str(tmp_path / "light.mp4"), group, weight=1)
    picks = collections.Counter(
        resolve_category_sequence_block({"type": "random", "category_id": group.id}, smart_db,
                                        rotation_key=("t", "w"))[0].id for _ in range(400))
    assert picks[heavy.id] > picks[light.id]
    group.cooldown_hours = 48
    smart_db.add(models.PlayEvent(preroll_id=heavy.id, played_at=utcnow()))
    smart_db.commit()
    picked = {resolve_category_sequence_block({"type": "random", "category_id": group.id}, smart_db,
                                              rotation_key=("t", "c"))[0].id for _ in range(20)}
    assert picked == {light.id}


def test_plugin_random_category_uses_weights(smart_db, tmp_path):
    group = collection(smart_db)
    a = preroll(smart_db, str(tmp_path / "a.mp4"), group, weight=10)
    b = preroll(smart_db, str(tmp_path / "b.mp4"), group, weight=1)
    picks = collections.Counter(weighting.sample_paths(("plugin", "category", group.id), [a.path, b.path], 1,
                                                       category_id=group.id)[0] for _ in range(300))
    assert picks[a.path] > picks[b.path] > 0


def test_weights_and_cooldown_api(smart_db, tmp_path):
    app = FastAPI()
    errors.install(app)
    app.include_router(automation_routes.router)
    client = TestClient(app)
    group = collection(smart_db, "T-Weights")
    a = preroll(smart_db, str(tmp_path / "a.mp4"), group)
    saved = client.put("/api/weights", json={"items": [{"preroll_id": a.id, "weight": 9}]})
    assert saved.json() == {"updated": 1}
    too_heavy = client.put("/api/weights", json={"items": [{"preroll_id": a.id, "weight": 11}]})
    assert too_heavy.status_code == 422 and too_heavy.json()["error"]["fields"]["items.0.weight"] == "Use 10 or less."
    cooldown = client.put(f"/api/collections/{group.id}/cooldown", json={"cooldown_hours": 24}).json()
    assert cooldown["summary"] == "An intro from 'T-Weights' won't play again within 24 hours while another one can."
    one = client.put(f"/api/collections/{group.id}/cooldown", json={"cooldown_hours": 1}).json()
    assert one["summary"] == "An intro from 'T-Weights' won't play again within 1 hour while another one can."
    client.put(f"/api/collections/{group.id}/cooldown", json={"cooldown_hours": 24})
    smart_db.add(models.PlayEvent(preroll_id=a.id, played_at=utcnow()))
    smart_db.commit()
    listed = client.get(f"/api/weights?collection_id={group.id}").json()
    assert listed["cooldown_hours"] == 24 and listed["items"][0]["weight"] == 9
    assert listed["items"][0]["resting_until"] is not None
    assert client.put("/api/collections/999999/cooldown", json={"cooldown_hours": 1}).status_code == 404


class PlexListWeights(MultiServerFixture):
    """The random list written to Plex repeats heavier intros, and the check that
    re-applies a changed list expects the same thing (no endless rewrites)."""

    def setUp(self):
        super().setUp()
        os.environ["PMAX_ALLOW_MIDPLAYBACK_PREROLL_WRITES"] = "1"
        self.addCleanup(os.environ.pop, "PMAX_ALLOW_MIDPLAYBACK_PREROLL_WRITES", None)
        self.heavy = os.path.join(self.temp_dir.name, "heavy.mp4")
        with open(self.heavy, "wb") as handle:
            handle.write(b"x")
        with self.Session() as db:
            db.add(models.Preroll(filename="heavy.mp4", path=self.heavy, category_id=self.category_id,
                                  enabled=True, weight=10))
            db.commit()
        self._configure(plex_url="http://plex:32400", plex_token="t")

    def test_a_heavier_intro_is_listed_twice(self):
        result, connector = self._apply()
        written = connector.set_preroll.call_args[0][0].split(";")
        assert result.plex is True
        assert written.count(self.heavy) == 2 and len(written) == 3

    def test_the_weighted_list_is_what_the_check_expects(self):
        with self.Session() as db:
            prerolls = scheduler_prerolls(db, self.category_id)
            weighted = self.scheduler._plex_weighted(db, prerolls, self.category_id, True)
        assert [os.path.basename(p.path) for p in weighted].count("heavy.mp4") == 2
        with self.Session() as db:
            assert self.scheduler._plex_weighted(db, prerolls, self.category_id, False) == prerolls


def scheduler_prerolls(db, category_id):
    from backend.scheduler import prerolls_for_category_query
    return prerolls_for_category_query(db, category_id).order_by(models.Preroll.id).all()
