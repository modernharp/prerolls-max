"""Typed or bookmarked interface paths (/servers, /welcome) go to their /#/ page.

The interface uses hash routes, so a browser asking the server for /servers
used to get a JSON 404. A page load of a path no route knows is redirected to
/#/<path>; API calls, files and an endpoint's own 404 are not.
"""
import pytest
from fastapi.testclient import TestClient

from backend import main

HTML = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}


@pytest.fixture
def client():
    return TestClient(main.app, raise_server_exceptions=False, follow_redirects=False)


@pytest.mark.parametrize("path", ["/servers", "/welcome", "/help/troubleshoot",
                                  "/settings/advanced/system", "/schedules/rules/new", "/videos/all"])
def test_a_page_load_of_an_interface_path_goes_to_its_hash_route(client, path):
    r = client.get(path, headers=HTML)
    assert r.status_code == 307, r.text
    assert r.headers["location"] == "/#" + path


def test_the_query_string_comes_along(client):
    r = client.get("/servers?type=jellyfin", headers=HTML)
    assert r.headers["location"] == "/#/servers?type=jellyfin"


@pytest.mark.parametrize("path,headers", [
    ("/servers", {"Accept": "application/json"}),        # an API client
    ("/servers", {}),                                     # no Accept at all
    ("/missing-icon.png", HTML),                          # a file
    ("/api/not-a-thing", HTML),                           # the API
    ("/static/app/gone.js", HTML),
    ("/jellyfin/not-a-thing", HTML),
    ("/a.b/c d", HTML),                                   # not an interface path
])
def test_api_calls_and_files_are_not_redirected(client, path, headers):
    # A 404, or the sign-in check's 401 when the test database has no admin
    # or no session: either way JSON, never a redirect.
    r = client.get(path, headers=headers)
    assert r.status_code in (401, 404), r.text
    assert "location" not in r.headers
    assert r.json()["error"]["code"] in ("not_found", "setup_required", "login_required")


def test_existing_api_routes_answer_as_before(client):
    r = client.get("/health", headers=HTML)
    assert r.status_code == 200 and r.json()["status"] == "healthy"


def test_other_methods_are_not_redirected(client):
    r = client.post("/servers-nowhere", headers=HTML)
    assert r.status_code in (401, 404, 405)
    assert "location" not in r.headers
