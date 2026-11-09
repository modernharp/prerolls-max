"""The list of plugins that asked for intros survives a restart of Prerolls
Max. It used to live only in memory, so after every update or reboot the
Media Servers page said a working plugin "Needs setting up" and the capability
badges said "Needs plugin" until someone played a movie again."""
from backend.routers import plugin_v2


def test_plugins_seen_are_read_back_after_a_restart(tmp_path):
    path = str(tmp_path / plugin_v2.SEEN_FILE_NAME)
    old_path = plugin_v2._seen_state["path"]
    try:
        plugin_v2.reload_seen_for_tests(path)
        plugin_v2.note_plugin("jellyfin", version="2.0.0.0", protocol="v2", server_id="abc",
                              server_name="LIVING-ROOM", key_name="Jellyfin Plugin (Auto) · LIVING-ROOM", now=1000.0)
        plugin_v2.note_plugin("emby", version="2.0.0.0", protocol="v2", server_name="DEN", now=1010.0)

        plugin_v2.reload_seen_for_tests(path)  # as if Prerolls Max restarted
        rows = plugin_v2.seen_plugins(now=1100.0)
        assert [(r["server_type"], r["server_name"], r["plugin_version"]) for r in rows] == [
            ("emby", "DEN", "2.0.0.0"), ("jellyfin", "LIVING-ROOM", "2.0.0.0")]
        assert rows[1]["last_seen_seconds_ago"] == 100

        # Still forgotten after a week, as before.
        assert plugin_v2.seen_plugins(now=1000.0 + plugin_v2.SEEN_FOR_SECONDS + 20) == []
    finally:
        plugin_v2.reload_seen_for_tests(old_path)
        plugin_v2.reset_seen()


def test_a_damaged_file_only_costs_the_list(tmp_path):
    path = tmp_path / plugin_v2.SEEN_FILE_NAME
    path.write_text("{not json")
    old_path = plugin_v2._seen_state["path"]
    try:
        plugin_v2.reload_seen_for_tests(str(path))
        assert plugin_v2.seen_plugins() == []
        plugin_v2.note_plugin("jellyfin", version="2.0.0.0", server_name="A", now=5.0)
        assert plugin_v2.seen_plugins(now=6.0)[0]["server_name"] == "A"
    finally:
        plugin_v2.reload_seen_for_tests(old_path)
        plugin_v2.reset_seen()
