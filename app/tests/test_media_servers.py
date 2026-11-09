"""The media server list: migration from one server per type, the settings
row mirror for older code, plugin linking, and backups."""
import json

from backend import media_servers as ms, media_servers_backup, models, sequence_conditions
from tests.media_server_fixtures import add, as_admin, secrets, server_db  # noqa: F401 (fixtures)


def _setting(db):
    return db.query(models.Setting).first()


# -- migration ---------------------------------------------------------------------

def test_a_single_server_database_becomes_rows_once(server_db):
    s = _setting(server_db)
    s.plex_url, s.plex_server_name, s.plex_server_machine_id = "http://plex:32400", "Den", "abc123"
    s.jellyfin_url, s.emby_url = "http://jf:8096", "http://emby:8096"
    s.path_mappings = json.dumps([{"local": "/data/prerolls", "plex": "/prerolls"}])
    server_db.commit()
    server_db.secrets.update({"plex_token": "plex-secret-123", "jellyfin_api_key": "j" * 32, "emby_api_key": "e" * 32})

    assert ms.sync_from_settings(server_db) is True
    rows = ms.ordered(server_db)
    assert [(r.type, r.name, r.url, r.is_primary) for r in rows] == [
        ("plex", "Den", "http://plex:32400", True), ("jellyfin", "Jellyfin", "http://jf:8096", True),
        ("emby", "Emby", "http://emby:8096", True)]
    plex = rows[0]
    assert plex.server_identifier == "abc123"
    assert ms.mappings(plex) == [{"local": "/data/prerolls", "plex": "/prerolls"}]
    assert ms.get_secret(plex) == "plex-secret-123" and ms.get_secret(rows[1]) == "j" * 32

    assert ms.sync_from_settings(server_db) is False  # idempotent
    assert len(ms.ordered(server_db)) == 3


def test_a_plex_token_kept_in_the_old_column_is_moved_too(server_db):
    s = _setting(server_db)
    s.plex_url, s.plex_token = "http://plex:32400", "column-token-1"
    server_db.commit()
    ms.sync_from_settings(server_db)
    assert ms.get_secret(ms.ordered(server_db, "plex")[0]) == "column-token-1"
    assert _setting(server_db).plex_token is None
    assert server_db.secrets["plex_token"] == "column-token-1"


def test_an_old_endpoint_changing_the_address_moves_the_first_server(server_db):
    first = add(server_db, "jellyfin", "Living room", "http://jf1:8096", token="a" * 20)
    add(server_db, "jellyfin", "Bedroom", "http://jf2:8096", token="b" * 20)
    s = _setting(server_db)
    assert s.jellyfin_url == "http://jf1:8096" and server_db.secrets["jellyfin_api_key"] == "a" * 20
    s.jellyfin_url = "http://jf3:8096"  # what POST /jellyfin/connect does
    server_db.secrets["jellyfin_api_key"] = "c" * 20
    server_db.commit()
    ms.sync_from_settings(server_db)
    server_db.refresh(first)
    assert first.url == "http://jf3:8096" and ms.get_secret(first) == "c" * 20
    assert [r.name for r in ms.ordered(server_db, "jellyfin")] == ["Living room", "Bedroom"]


def test_the_old_disconnect_promotes_the_next_server(server_db):
    add(server_db, "jellyfin", "Living room", "http://jf1:8096", token="a" * 20)
    add(server_db, "jellyfin", "Bedroom", "http://jf2:8096", token="b" * 20)
    assert ms.forget_primary(server_db, "jellyfin") == "Living room"
    s = _setting(server_db)
    assert s.jellyfin_url == "http://jf2:8096" and server_db.secrets["jellyfin_api_key"] == "b" * 20
    assert [r.name for r in ms.ordered(server_db)] == ["Bedroom"]


def test_switching_the_first_server_off_mirrors_the_next(server_db):
    first = add(server_db, "plex", "Den", "http://p1:32400", token="p" * 20,
                path_mappings=json.dumps([{"local": "/a", "plex": "/x"}]))
    add(server_db, "plex", "Loft", "http://p2:32401", token="q" * 20,
        path_mappings=json.dumps([{"local": "/a", "plex": "/y"}]))
    first.enabled = False
    ms.mirror(server_db)
    server_db.commit()
    s = _setting(server_db)
    assert s.plex_url == "http://p2:32401" and json.loads(s.path_mappings)[0]["plex"] == "/y"
    for row in ms.ordered(server_db):
        row.enabled = False
    ms.mirror(server_db)
    server_db.commit()
    assert _setting(server_db).plex_url is None
    assert ms.sync_from_settings(server_db) is False and len(ms.ordered(server_db)) == 2  # nothing removed


def test_names_default_friendly_and_ignore_case(server_db):
    assert ms.default_name(server_db, "jellyfin") == "Jellyfin"
    add(server_db, "jellyfin", "Jellyfin", "http://jf1:8096")
    assert ms.default_name(server_db, "jellyfin") == "Jellyfin 2"
    assert ms.name_taken(server_db, "  jellyFIN ") and not ms.name_taken(server_db, "Jellyfin 2")


def test_plex_targets_put_the_first_server_first_with_its_own_mappings(server_db):
    add(server_db, "plex", "Den", "http://p1:32400", token="p" * 20,
        path_mappings=json.dumps([{"local": "/data", "plex": "/prerolls"}]))
    add(server_db, "plex", "Loft", "http://p2:32401", token="q" * 20,
        path_mappings=json.dumps([{"local": "/data", "plex": "/media/intros"}]))
    add(server_db, "plex", "Off", "http://p3:32402", enabled=False)
    targets = ms.plex_targets(server_db)
    assert [(t.name, t.primary, t.mappings[0]["plex"]) for t in targets] == [
        ("Den", True, "/prerolls"), ("Loft", False, "/media/intros")]
    assert targets[1].token == "q" * 20


# -- plugins -----------------------------------------------------------------------

def test_plugins_are_linked_by_key_then_server_id_then_address(server_db):
    one = add(server_db, "jellyfin", "Living room", "http://192.168.1.5:8096", server_identifier="aaaa-1111")
    two = add(server_db, "jellyfin", "Bedroom", "http://192.168.1.6:8096", plugin_key_id=77)
    assert ms.link_plugin(server_db, "jellyfin", "", 77, "").id == two.id
    assert ms.link_plugin(server_db, "jellyfin", "AAAA1111", None, "").id == one.id
    assert ms.link_plugin(server_db, "jellyfin", "", None, "192.168.1.6").id == two.id
    assert ms.link_plugin(server_db, "jellyfin", "zzzz", None, "10.0.0.9") is None
    assert ms.link_plugin(server_db, "emby", "zzzz", None, "") is None


def test_an_unknown_plugin_links_to_the_only_server_and_is_remembered(server_db):
    row = add(server_db, "emby", "Emby", "http://emby:8096")
    assert ms.link_plugin(server_db, "emby", "e-server-9", 12, "172.17.0.4").id == row.id
    server_db.refresh(row)
    assert row.server_identifier == "e-server-9" and row.plugin_key_id == 12


def test_server_rules_can_name_one_server(server_db, monkeypatch):
    den = add(server_db, "jellyfin", "Den", "http://jf1:8096")
    loft = add(server_db, "jellyfin", "Loft", "http://jf2:8096")
    plex = add(server_db, "plex", "Living room Plex", "http://p1:32400")
    monkeypatch.setattr(sequence_conditions, "server_lookup", ms.lookup)
    met = sequence_conditions.server_rule_met
    assert met([f"server:{den.id}"], "jellyfin", den.id) is True
    assert met([f"server:{den.id}"], "jellyfin", loft.id) is False
    assert met(["emby", f"server:{loft.id}"], "jellyfin", loft.id) is True
    assert met([f"server:{plex.id}"], "plex", None) is True  # Plex writes one list for its servers
    assert met([f"server:{den.id}"], None, None) is None
    text = sequence_conditions.describe_condition({"rules": [{"kind": "server", "values": [f"server:{loft.id}"]}]})
    assert "playing on Loft" in text


# -- backups -----------------------------------------------------------------------

def test_backup_round_trip_keeps_servers_and_skips_keyless_ones(server_db):
    add(server_db, "plex", "Den", "http://p1:32400", token="p" * 20,
        path_mappings=json.dumps([{"local": "/a", "plex": "/x"}]))
    add(server_db, "jellyfin", "Loft", "http://jf2:8096", token="j" * 20, enabled=False)
    with_keys = media_servers_backup.export(server_db, True)
    without = media_servers_backup.export(server_db, False)
    assert with_keys[0]["token"] == "p" * 20 and all(e["token"] == "" for e in without)
    assert without[0]["mappings"] == [{"local": "/a", "plex": "/x"}]

    skipped = []
    data = {"media_servers": without + [{"type": "emby", "name": "New", "url": "http://e:8096", "token": ""},
                                        {"type": "emby", "name": "Bad", "url": "ftp://nope", "token": "x" * 20}]}
    assert media_servers_backup.restore(server_db, data, skipped) == 2
    rows = ms.ordered(server_db)
    assert [(r.name, r.enabled) for r in rows] == [("Den", True), ("Loft", False)]
    assert ms.get_secret(rows[0]) == "p" * 20  # kept: same address
    assert any("New" in s for s in skipped) and any("web address" in s for s in skipped)
    assert _setting(server_db).plex_url == "http://p1:32400"


def test_a_backup_without_a_server_list_leaves_it_alone(server_db):
    add(server_db, "plex", "Den", "http://p1:32400")
    assert media_servers_backup.restore(server_db, {"settings": {}}, []) == 0
    assert len(ms.ordered(server_db)) == 1
