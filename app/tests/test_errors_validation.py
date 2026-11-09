"""The shared error format, input checks and outbound host guard."""

import datetime as dt
import re

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from backend import errors, net, validation as v


# --- errors -----------------------------------------------------------------

class Connect(BaseModel):
    url: v.ServerUrl
    token: v.Token
    name: v.Name


def _app():
    app = FastAPI()
    errors.install(app)

    @app.post("/connect")
    def connect(body: Connect):
        return {"url": body.url, "token": body.token, "name": body.name}

    @app.get("/app-error")
    def app_error():
        raise errors.unreachable("Plex", "http://10.0.0.5:32400")

    @app.get("/leaky")
    def leaky():
        raise HTTPException(500, detail="Failed: HTTPConnectionPool(host='x', port=1): Max retries exceeded")

    @app.get("/friendly")
    def friendly():
        raise HTTPException(400, detail="Pick at least one video.")

    @app.get("/boom")
    def boom():
        raise KeyError("secret_column")

    return app


@pytest.fixture
def client():
    return TestClient(_app(), raise_server_exceptions=False)


def test_validation_errors_name_each_field_in_plain_words(client):
    r = client.post("/connect", json={"url": "ftp://x", "token": "  ab cd  ", "name": ""})
    assert r.status_code == 422
    body = r.json()
    fields = body["error"]["fields"]
    assert fields["url"] == "The address must start with http:// or https://."
    assert "spaces" in fields["token"]
    assert fields["name"] == "Enter a name."
    assert body["detail"] == "3 fields need a fix before this can be saved."
    assert body["error"]["request_id"]


def test_a_field_called_path_keeps_its_name():
    # "path" is also where FastAPI says a value came from (the address); only
    # the first part of an error's location means that.
    assert errors.friendly_validation_fields([
        {"loc": ("body", "path"), "type": "missing", "msg": ""},
        {"loc": ("path", "preroll_id"), "type": "int_parsing", "msg": ""},
        {"loc": ("query", "query"), "type": "missing", "msg": ""},
    ]) == {"path": "This is required.", "preroll_id": "Enter a whole number.", "query": "This is required."}


def test_valid_input_is_cleaned(client):
    r = client.post("/connect", json={"url": "192.168.1.5:32400/", "token": ' "abcdef123456" ',
                                       "name": "  Living   room "})
    assert r.status_code == 200
    assert r.json() == {"url": "http://192.168.1.5:32400", "token": "abcdef123456", "name": "Living room"}


def test_app_error_has_message_hint_and_code(client):
    body = client.get("/app-error").json()
    assert body["detail"] == "Plex didn't answer at http://10.0.0.5:32400."
    assert body["error"]["code"] == "plex_unreachable"
    assert "running" in body["error"]["hint"]


def test_raw_exception_text_never_reaches_the_user(client):
    for path in ("/leaky", "/boom"):
        r = client.get(path)
        assert r.status_code == 500
        text = r.text
        assert "HTTPConnectionPool" not in text and "secret_column" not in text
        assert r.json()["detail"] == errors.GENERIC_MESSAGE
        assert r.json()["error"]["request_id"]


def test_friendly_http_exceptions_pass_through(client):
    r = client.get("/friendly")
    assert r.status_code == 400
    assert r.json()["detail"] == "Pick at least one video."
    assert r.headers["X-Request-ID"]


# --- validation -------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("http://plex:32400", "http://plex:32400"),
    ("HTTPS://Example.com/jellyfin/", "https://Example.com/jellyfin"),
    ("10.0.0.2:8096", "http://10.0.0.2:8096"),
])
def test_server_urls(raw, expected):
    assert v.clean_server_url(raw) == expected


@pytest.mark.parametrize("raw, words", [
    ("", "Enter the address"),
    ("http://", "computer name or IP"),
    ("http://host:99999", "between 1 and 65535"),
    ("javascript:alert(1)", "http:// or https://"),
    ("http://user:pw@host", "user name and password"),
    ("http://host/?token=1", "after ? or #"),
    ("http://my host", "spaces"),
])
def test_bad_server_urls(raw, words):
    with pytest.raises(ValueError, match=re.escape(words)):
        v.clean_server_url(raw)


def test_file_names_reject_plex_separators_and_windows_traps():
    assert v.clean_filename("Holiday Intro 2026.mp4") == "Holiday Intro 2026.mp4"
    for bad in ("a,b.mp4", "a;b.mp4", "../x.mp4", "con.mp4", "x."):
        with pytest.raises(ValueError):
            v.clean_filename(bad)
    assert v.plex_safe_filename("Cats, Dogs; Birds") == "Cats - Dogs - Birds"


def test_folder_paths():
    assert v.clean_folder_path("/data//prerolls/") == "/data/prerolls"
    assert v.clean_folder_path("D:\\Prerolls\\") == "D:\\Prerolls"
    for bad in ("prerolls", "smb://nas/share", "/data/../etc", "\x00"):
        with pytest.raises(ValueError):
            v.clean_folder_path(bad)


def test_times_and_dates():
    assert v.clean_time_hhmm("7:5") == "07:05"
    assert v.clean_time_hhmm("6:30 pm") == "18:30"
    assert v.clean_time_hhmm("12am") == "00:00"
    with pytest.raises(ValueError):
        v.clean_time_hhmm("25:00")
    assert v.parse_datetime("2026-12-24T18:30:00.000Z") == dt.datetime(2026, 12, 24, 18, 30)
    assert v.parse_datetime("2026-12-24") == dt.datetime(2026, 12, 24)
    with pytest.raises(ValueError, match="after"):
        v.check_date_range(dt.date(2026, 2, 1), dt.date(2026, 1, 1))


# --- net --------------------------------------------------------------------

def test_require_host_blocks_other_sites():
    ok = "https://www.prerolls.me/api/v1/catalog.json"
    assert net.require_host(ok, {"www.prerolls.me"}) == ok
    for bad in ("https://evil.example/x", "http://www.prerolls.me/x",
                "https://www.prerolls.me.evil.example/x", "https://user@www.prerolls.me/x"):
        with pytest.raises(net.BlockedAddress):
            net.require_host(bad, {"www.prerolls.me"})
