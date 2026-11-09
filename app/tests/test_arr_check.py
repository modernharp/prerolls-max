"""Connecting Radarr or Sonarr: tested against the real apps, the old check
accepted Sonarr's address and key in the Radarr form ("Connected to Sonarr"),
and anything that answered 401 (Plex, Prerolls Max itself) was reported as
"Radarr turned down the API key"."""

import asyncio
from unittest.mock import patch

import httpx

from backend.radarr_connector import RadarrConnector
from backend.sonarr_connector import SonarrConnector


def run(connector, handler):
    real_client = httpx.AsyncClient
    with patch("backend.arr_check.httpx.AsyncClient",
               lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs)):
        return asyncio.run(connector.test_connection())


def arr(app_name, key="right", version="6.4.4"):
    def handler(request):
        if request.url.path == "/ping":
            return httpx.Response(200, json={"status": "OK"})
        if request.headers.get("X-Api-Key") != key:
            return httpx.Response(401, json={"message": "Unauthorized"})
        return httpx.Response(200, json={"appName": app_name, "instanceName": app_name, "version": version})
    return handler


def test_radarr_connects():
    r = run(RadarrConnector("http://radarr.test", "right"), arr("Radarr"))
    assert r["success"] and r["appName"] == "Radarr" and r["version"] == "6.4.4"


def test_sonarr_address_in_the_radarr_form_is_refused():
    r = run(RadarrConnector("http://sonarr.test", "right"), arr("Sonarr", version="4.0.20"))
    assert not r["success"]
    assert r["message"] == "That address is Sonarr, not Radarr. Add it under Sonarr (TV shows) instead."


def test_radarr_address_in_the_sonarr_form_is_refused():
    r = run(SonarrConnector("http://radarr.test", "right"), arr("Radarr"))
    assert not r["success"]
    assert "Radarr, not Sonarr" in r["message"] and "Radarr (movies)" in r["message"]


def test_another_arr_app_is_named():
    r = run(RadarrConnector("http://lidarr.test", "right"), arr("Lidarr"))
    assert not r["success"]
    assert r["message"].startswith("That address is Lidarr, not Radarr.") and "7878" in r["message"]


def test_wrong_key_on_real_radarr():
    r = run(RadarrConnector("http://radarr.test", "wrong"), arr("Radarr"))
    assert not r["success"]
    assert "turned down the API key" in r["message"]


def test_some_other_app_answering_401_is_not_called_a_wrong_key():
    def plex_like(request):
        return httpx.Response(401, text="<html>Unauthorized</html>")
    r = run(RadarrConnector("http://plex.test:32400", "whatever"), plex_like)
    assert not r["success"]
    assert "isn't Radarr" in r["message"] and "7878" in r["message"]
    assert "API key" not in r["message"]


def test_a_web_page_is_not_radarr():
    r = run(SonarrConnector("http://router.test", "k"), lambda request: httpx.Response(200, text="<html>Router</html>"))
    assert not r["success"] and "isn't Sonarr" in r["message"]


def test_server_error_message_has_no_status_codes():
    r = run(RadarrConnector("http://radarr.test", "right"), lambda request: httpx.Response(500, text="boom"))
    assert not r["success"]
    assert "HTTP" not in r["message"] and "500" not in r["message"]


def test_nothing_there():
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)
    r = run(RadarrConnector("http://127.0.0.1:1", "k"), refuse)
    assert not r["success"] and "didn't answer" in r["message"]
