"""'Set up the plugin for me' must not say "Done" when the media server can't
reach Prerolls Max at the address the user gave (localhost from inside Docker
is the common case). After saving the settings, Prerolls Max asks the plugin's
own Test endpoint to call it back and returns that answer as `reach`.
"""
import pytest

from backend import main, models, secure_store
from backend.database import SessionLocal
from tests.test_interface_gaps import admin  # noqa: F401  (fixture)


class _Resp:
    def __init__(self, status, data=None):
        self.status_code = status
        self._data = data
        self.text = ""

    def json(self):
        if self._data is None:
            raise ValueError("no json")
        return self._data


def test_reach_check_reads_the_plugin_answer():
    ok = main._plugin_reach_check(lambda path: _Resp(200, {"Ok": True, "Message": "Connected."}))
    assert ok == {"ok": True, "message": "Connected."}
    bad = main._plugin_reach_check(lambda path: _Resp(200, {"Ok": False, "Message": "Couldn't reach Prerolls Max."}))
    assert bad == {"ok": False, "message": "Couldn't reach Prerolls Max."}


@pytest.mark.parametrize("post", [
    lambda path: _Resp(404),                       # an older plugin without the check
    lambda path: _Resp(200, {"something": 1}),     # not the plugin's answer
    lambda path: (_ for _ in ()).throw(OSError()),  # the media server went away
])
def test_reach_check_unknown_is_none(post):
    assert main._plugin_reach_check(post) is None


@pytest.fixture
def emby_connected(monkeypatch):
    db = SessionLocal()
    try:
        setting = db.query(models.Setting).first()
        old = setting.emby_url
        setting.emby_url = "http://emby:8096"
        db.commit()
    finally:
        db.close()
    monkeypatch.setattr(secure_store, "get_emby_api_key", lambda: "e" * 32)
    yield
    db = SessionLocal()
    try:
        db.query(models.Setting).first().emby_url = old
        db.commit()
    finally:
        db.close()


@pytest.mark.parametrize("plugin_ok", [True, False])
def test_emby_configure_reports_whether_the_plugin_can_call_back(admin, emby_connected, monkeypatch, plugin_ok):  # noqa: F811
    seen = []

    def fake_get(url, **kw):
        if url.endswith("/emby/Plugins"):
            return _Resp(200, [{"Id": main.PMAX_EMBY_PLUGIN_ID, "Name": "Prerolls Max Intros"}])
        return _Resp(200, {})

    def fake_post(url, **kw):
        seen.append((url, kw.get("json")))
        if url.endswith("/PrerollsMax/Test"):
            return _Resp(200, {"Ok": plugin_ok, "Message": "Connected." if plugin_ok else "Couldn't reach Prerolls Max at http://localhost:9393."})
        return _Resp(204)

    monkeypatch.setattr(main.requests, "get", fake_get)
    monkeypatch.setattr(main.requests, "post", fake_post)
    r = admin.post("/emby/plugin/configure", json={"nexroll_url": "http://localhost:9393/"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reach"]["ok"] is plugin_ok
    test_calls = [j for u, j in seen if u.endswith("/emby/PrerollsMax/Test")]
    assert test_calls and test_calls[0]["PrerollsMaxUrl"] == "http://localhost:9393"
    # the plugin is tested with the key it was just given, which the response never shows
    assert test_calls[0]["ApiKey"] and test_calls[0]["ApiKey"] not in r.text


# --- one auto key per media server ---------------------------------------------

def test_plugin_key_name_is_per_server():
    assert main._plugin_key_name("Jellyfin", "LIVING-ROOM", "http://x:8096") == "Jellyfin Plugin (Auto) · LIVING-ROOM"
    assert main._plugin_key_name("Emby", None, "http://192.168.1.5:8096/") == "Emby Plugin (Auto) · 192.168.1.5:8096"
    assert main._plugin_key_name("Jellyfin", "", "") == "Jellyfin Plugin (Auto)"


def _drop_auto_keys(db):
    db.query(models.APIKey).filter(models.APIKey.name.like("Jellyfin Plugin (Auto)%")).delete(synchronize_session=False)
    db.commit()


def test_setting_up_a_second_server_keeps_the_first_servers_key():
    db = SessionLocal()
    try:
        _drop_auto_keys(db)
        first_raw, _ = main._plugin_api_key(db, main._plugin_key_name("Jellyfin", "JF-A", ""), "x", {})
        second_raw, _ = main._plugin_api_key(db, main._plugin_key_name("Jellyfin", "JF-B", ""), "x", {"ApiKey": "stale"})
        assert first_raw != second_raw
        assert main.validate_api_key(first_raw, "read", db) is not None, "the first server's plugin must keep working"
        assert main.validate_api_key(second_raw, "read", db) is not None
        # Setting the first one up again keeps its key rather than making another.
        again, new = main._plugin_api_key(db, main._plugin_key_name("Jellyfin", "JF-A", ""), "x", {"ApiKey": first_raw})
        assert again == first_raw and new is None
    finally:
        _drop_auto_keys(db)
        db.close()


def test_a_working_key_from_before_per_server_names_is_kept():
    db = SessionLocal()
    try:
        _drop_auto_keys(db)
        legacy_raw, _ = main._plugin_api_key(db, "Jellyfin Plugin (Auto)", "x", {})
        raw, new = main._plugin_api_key(db, main._plugin_key_name("Jellyfin", "JF-A", ""), "x", {"ApiKey": legacy_raw})
        assert raw == legacy_raw and new is None
    finally:
        _drop_auto_keys(db)
        db.close()
