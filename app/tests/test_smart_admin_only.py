"""Smart-feature routes that read server folders, replace files or change
settings are for admins; reading stays open to everyone signed in.

These run the real app, like test_first_run_and_roles.py.
"""
from fastapi.testclient import TestClient

from backend import main, models, smart_settings
from backend.database import SessionLocal
from tests.test_first_run_and_roles import _make_user, _setup, _sign_in, fresh  # noqa: F401

ADMIN_ONLY = (
    ("POST", "/api/watch-folders", {"json": {"path": "/tmp", "mode": "link"}}),
    ("PUT", "/api/watch-folders/1", {"json": {"path": "/tmp", "mode": "link"}}),
    ("DELETE", "/api/watch-folders/1", {}),
    ("POST", "/api/watch-folders/1/check", {}),
    ("PUT", "/api/smart-settings", {"json": {"history_retention_days": 30}}),
    ("DELETE", "/api/stats", {}),
    ("POST", "/api/media/loudness/normalize", {"json": {"preroll_ids": [999999], "mode": "replace"}}),
)

OPEN_READS = ("/api/watch-folders", "/api/smart-settings", "/api/stats/recent", "/api/stats/summary",
              "/api/health/intros", "/api/rules", "/api/exclusions", "/api/weights")


def _forget_smart_settings():
    db = SessionLocal()
    try:
        db.query(models.FeatureSetting).delete()
        db.commit()
    finally:
        db.close()
    smart_settings.clear_cache()


def test_a_signed_in_viewer_cant_use_the_admin_routes(fresh):
    _setup(fresh, "admin", "admin pass 1")
    _make_user(fresh, "viewer")
    viewer = _sign_in("viewer", "another pass")
    for method, path, kw in ADMIN_ONLY:
        r = viewer.request(method, path, **kw)
        assert r.status_code == 403, (method, path, r.status_code, r.text)
        body = r.json()
        assert body["error"]["code"] == "admin_required"
        assert body["detail"].startswith("Only an admin can")
    for path in OPEN_READS:
        assert viewer.get(path).status_code == 200, path


def test_a_viewer_may_still_start_media_jobs_that_keep_the_originals(fresh):
    _setup(fresh, "admin", "admin pass 1")
    _make_user(fresh, "viewer")
    viewer = _sign_in("viewer", "another pass")
    # Past the admin check: the intro doesn't exist, so it's a form problem, not a 403.
    r = viewer.post("/api/media/loudness/normalize", json={"preroll_ids": [999999], "mode": "new_version"})
    assert r.status_code == 422 and "preroll_ids" in r.json()["error"]["fields"], r.text
    r = viewer.post("/api/media/versions", json={"preroll_ids": [999999], "profiles": ["1080p"]})
    assert r.status_code == 422 and "preroll_ids" in r.json()["error"]["fields"], r.text


def test_an_admin_and_a_full_access_key_get_through(fresh):
    _setup(fresh, "admin", "admin pass 1")
    try:
        assert fresh.put("/api/smart-settings", json={"history_retention_days": 30}).status_code == 200
        assert fresh.delete("/api/stats").status_code == 200
        # A missing folder is a form problem, not a permissions one.
        r = fresh.post("/api/watch-folders", json={"path": "/no/such/folder/here", "mode": "link"})
        assert r.status_code == 422 and "path" in r.json()["error"]["fields"]
        assert fresh.post("/api/watch-folders/999999/check").status_code == 404
        r = fresh.post("/api/media/loudness/normalize", json={"preroll_ids": [999999], "mode": "replace"})
        assert r.status_code == 422 and "preroll_ids" in r.json()["error"]["fields"]

        full = fresh.post("/api/keys?name=automation&permissions=full").json()["key"]
        read = fresh.post("/api/keys?name=dashboard&permissions=read").json()["key"]
        anon = TestClient(main.app, raise_server_exceptions=False)
        assert anon.delete("/api/stats", headers={"X-Api-Key": full}).status_code == 200
        assert anon.delete("/api/stats", headers={"X-Api-Key": read}).status_code in (401, 403)
        # Nobody signed in at all: refused.
        assert anon.delete("/api/stats").status_code == 401
    finally:
        _forget_smart_settings()


def test_with_login_off_they_work_like_the_other_admin_routes(fresh):
    _setup(fresh, "admin", "admin pass 1")
    assert fresh.put("/auth/settings", json={"auth_enabled": False}).status_code == 200
    anon = TestClient(main.app, raise_server_exceptions=False)
    try:
        # Same as /auth/users or /browse-folders with login off: open.
        assert anon.get("/auth/users").status_code == 200
        assert anon.put("/api/smart-settings", json={"history_retention_days": 30}).status_code == 200
        assert anon.delete("/api/stats").status_code == 200
        assert anon.post("/api/watch-folders/999999/check").status_code == 404
    finally:
        _forget_smart_settings()
