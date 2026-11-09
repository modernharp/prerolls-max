"""First-run setup, the login gate and admin-only actions (CONTRACTS.md §4).

A fresh NeXroll install was open to anyone on the network: login was off,
the factory reset only checked roles when login was on, and any signed-in
account could manage users and API keys. These run the real app.
"""
import pytest
from fastapi.testclient import TestClient

from backend import auth_gate, main, models
from backend.database import SessionLocal


def _wipe_accounts():
    db = SessionLocal()
    try:
        db.query(models.Session).delete()
        db.query(models.APIKey).delete()
        db.query(models.AuthAuditLog).delete()
        db.query(models.User).delete()
        setting = db.query(models.Setting).first()
        if setting is not None:
            setting.auth_enabled = False
            setting.auth_allow_registration = False
        db.commit()
    finally:
        db.close()
    main._auth_gate_invalidate()
    main._login_rate_limit.clear()


@pytest.fixture
def fresh():
    _wipe_accounts()
    yield TestClient(main.app, raise_server_exceptions=False)
    _wipe_accounts()


def _setup(client, username="admin", password="correct horse"):
    r = client.post("/auth/setup", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r


def _make_user(client, username, role="user", password="another pass"):
    r = client.post("/auth/users", json={"username": username, "password": password, "role": role})
    assert r.status_code == 200, r.text


def _sign_in(username, password):
    c = TestClient(main.app, raise_server_exceptions=False)
    r = c.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return c


# --- first run ---------------------------------------------------------------

def test_a_fresh_install_asks_for_setup_and_refuses_everything_else(fresh):
    status = fresh.get("/auth/status").json()
    assert status["setup_required"] is True and status["users_exist"] is False
    for method, path in (("GET", "/categories"), ("GET", "/settings"), ("POST", "/schedules"),
                         ("POST", "/admin/factory-reset"), ("GET", "/api/keys"), ("POST", "/auth/register"),
                         ("GET", "/onboarding/status"), ("GET", "/static/prerolls/x/y.mp4")):
        r = fresh.request(method, path, json={})
        assert r.status_code == 401, (method, path, r.status_code)
        body = r.json()
        assert body["error"]["code"] == "setup_required"
        assert body["detail"] == body["error"]["message"]
    assert fresh.get("/health").status_code == 200


def test_setup_routes_the_plugin_and_interface_files_stay_open():
    assert auth_gate.is_setup_exempt("GET", "/auth/status")
    assert auth_gate.is_setup_exempt("POST", "/auth/setup")
    assert auth_gate.is_setup_exempt("GET", "/plugin/intros")
    assert auth_gate.is_setup_exempt("GET", "/")
    assert auth_gate.is_setup_exempt("GET", "/assets/index-abc123.js")
    assert auth_gate.is_setup_exempt("GET", "/icons/icon-192.png")
    assert auth_gate.is_setup_exempt("OPTIONS", "/categories")
    assert auth_gate.is_setup_exempt("GET", "/some/route", frontend_file=True)
    assert not auth_gate.is_setup_exempt("POST", "/assets/x.js")
    assert not auth_gate.is_setup_exempt("GET", "/static/prerolls/Halloween/a.mp4")
    assert not auth_gate.is_setup_exempt("GET", "/categories")
    assert not auth_gate.is_setup_exempt("POST", "/auth/register")


def test_frontend_file_check_stays_inside_the_folder(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("x")
    (tmp_path.parent / "secret.txt").write_text("x")
    assert auth_gate.is_frontend_file(str(tmp_path), "/assets/app.js")
    assert not auth_gate.is_frontend_file(str(tmp_path), "/assets")
    assert not auth_gate.is_frontend_file(str(tmp_path), "/../secret.txt")
    assert not auth_gate.is_frontend_file(None, "/assets/app.js")


def test_setup_creates_an_admin_turns_login_on_and_signs_in(fresh):
    r = _setup(fresh, "Admin", "  spaces ok  ")
    assert r.json()["user"]["role"] == "admin" and r.json()["user"]["username"] == "admin"
    assert "pmax_session" in r.cookies
    status = fresh.get("/auth/status").json()
    assert status["setup_required"] is False and status["auth_enabled"] is True
    assert status["authenticated"] is True
    assert fresh.get("/categories").status_code == 200
    # Without the cookie: login required, in the shared error format.
    anon = TestClient(main.app, raise_server_exceptions=False)
    r = anon.get("/categories")
    assert r.status_code == 401 and r.json()["error"]["code"] == "login_required"


def test_setup_only_works_once(fresh):
    _setup(fresh)
    r = TestClient(main.app, raise_server_exceptions=False).post(
        "/auth/setup", json={"username": "intruder", "password": "intruder pass"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_set_up"


@pytest.mark.parametrize("body,field", [
    ({"username": "ab", "password": "longenough"}, "username"),
    ({"username": "bad name", "password": "longenough"}, "username"),
    ({"username": "admin", "password": "short"}, "password"),
    ({"username": "admin", "password": "x" * 80}, "password"),
    ({"password": "longenough"}, "username"),
    ({"username": "admin", "password": "Password1"}, "password"),
    ({"username": "admin", "password": "12345678"}, "password"),
])
def test_setup_explains_what_to_fix(fresh, body, field):
    r = fresh.post("/auth/setup", json=body)
    assert r.status_code == 422
    assert field in r.json()["error"]["fields"]
    assert fresh.get("/auth/status").json()["setup_required"] is True


# --- roles -------------------------------------------------------------------

def test_only_admins_manage_accounts_keys_and_security(fresh):
    _setup(fresh, "admin", "admin pass 1")
    _make_user(fresh, "viewer")
    viewer = _sign_in("viewer", "another pass")
    assert viewer.get("/categories").status_code == 200
    for method, path, kw in (
        ("GET", "/auth/users", {}),
        ("POST", "/auth/users", {"json": {"username": "sneaky", "password": "sneaky pass", "role": "admin"}}),
        ("GET", "/api/keys", {}),
        ("POST", "/api/keys?name=mine", {}),
        ("PUT", "/auth/settings", {"json": {"auth_enabled": False}}),
        ("GET", "/auth/audit-logs", {}),
        ("POST", "/browse-folders", {"json": {"path": "/"}}),
        ("POST", "/restore/database", {"json": {"categories": []}}),
        ("POST", "/admin/factory-reset", {"json": {"confirm": "RESET"}}),
    ):
        r = viewer.request(method, path, **kw)
        assert r.status_code == 403, (method, path, r.status_code, r.text)
        assert r.json()["error"]["code"] == "admin_required"
    assert fresh.get("/auth/users").status_code == 200
    assert fresh.post("/browse-folders", json={"path": "/"}).status_code == 200


def test_the_factory_reset_needs_an_admin_even_with_login_off(fresh):
    _setup(fresh, "admin", "admin pass 1")
    assert fresh.put("/auth/settings", json={"auth_enabled": False}).status_code == 200
    anon = TestClient(main.app, raise_server_exceptions=False)
    assert anon.get("/categories").status_code == 200  # login off: the rest is open
    r = anon.post("/admin/factory-reset", json={"confirm": "RESET"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "login_required"
    # An admin still gets through to the confirmation check.
    r = fresh.post("/admin/factory-reset", json={"confirm": "nope"})
    assert r.status_code == 422 and "confirm" in r.json()["error"]["fields"]
    # Signing in works with login off, for exactly this.
    admin = _sign_in("admin", "admin pass 1")
    assert admin.post("/admin/factory-reset", json={"confirm": "nope"}).status_code == 422


def test_api_keys_only_work_in_the_header(fresh):
    _setup(fresh)
    full = fresh.post("/api/keys?name=automation&permissions=full").json()["key"]
    read = fresh.post("/api/keys?name=dashboard&permissions=read").json()["key"]
    anon = TestClient(main.app, raise_server_exceptions=False)
    assert anon.get("/categories", headers={"X-Api-Key": read}).status_code == 200
    assert anon.get(f"/categories?api_key={read}").status_code == 401
    assert anon.get("/external/status", headers={"X-Api-Key": read}).status_code == 200
    r = anon.get(f"/external/status?api_key={read}")
    assert r.status_code == 401
    # A read key can't change anything; a full key can, and counts as admin.
    assert anon.post("/categories", headers={"X-Api-Key": read}, json={"name": "X"}).status_code == 401
    assert anon.get("/auth/users", headers={"X-Api-Key": full}).status_code == 200
    assert anon.get("/auth/users", headers={"X-Api-Key": read}).status_code == 403
    assert anon.get("/api/keys/validate", headers={"X-Api-Key": read}).json()["valid"] is True


def test_api_key_names_are_unique_and_checked(fresh):
    _setup(fresh)
    assert fresh.post("/api/keys?name=Home%20Assistant").status_code == 200
    r = fresh.post("/api/keys?name=home%20assistant")
    assert r.status_code == 409 and "Home Assistant" in r.json()["detail"]
    assert fresh.post("/api/keys?name=x&permissions=admin").status_code == 422
    assert fresh.post("/api/keys?name=%20%20").status_code == 422


def test_the_last_admin_cant_be_removed_or_turned_off(fresh):
    _setup(fresh, "admin", "admin pass 1")
    _make_user(fresh, "second", role="admin")
    second = _sign_in("second", "another pass")
    users = {u["username"]: u["id"] for u in second.get("/auth/users").json()["users"]}
    assert second.delete(f"/auth/users/{users['admin']}").status_code == 200
    r = second.delete(f"/auth/users/{users['second']}")
    assert r.status_code == 400 and r.json()["error"]["code"] == "cannot_delete_self"
    key = second.post("/api/keys?name=ops").json()["key"]
    r = TestClient(main.app, raise_server_exceptions=False).delete(
        f"/auth/users/{users['second']}", headers={"X-Api-Key": key})
    assert r.status_code == 400 and r.json()["error"]["code"] == "last_admin"


def test_duplicate_user_names_get_a_friendly_conflict(fresh):
    _setup(fresh, "admin")
    _make_user(fresh, "kid")
    r = fresh.post("/auth/users", json={"username": "KID", "password": "kid pass 22"})
    assert r.status_code == 409 and r.json()["error"]["fields"]["username"]


def test_wrong_password_message_is_plain(fresh):
    _setup(fresh, "admin", "admin pass 1")
    r = TestClient(main.app, raise_server_exceptions=False).post(
        "/auth/login", json={"username": "admin", "password": "nope"})
    assert r.status_code == 401
    assert r.json()["detail"] == "That user name and password don't match."


def test_new_passwords_only_need_eight_characters_and_not_a_common_one(fresh):
    # No upper case, digits or symbols needed (CONTRACTS.md section 4).
    _setup(fresh, "admin", "admin pass 1")
    r = fresh.post("/auth/users", json={"username": "kid", "password": "lowercase"})
    assert r.status_code == 200, r.text
    r = fresh.post("/auth/users", json={"username": "kid2", "password": "iloveyou"})
    assert r.status_code == 422
    assert "common" in r.json()["error"]["fields"]["password"]
