"""The smart features are wired into the real app."""
from backend import main


def test_new_routes_are_served():
    paths = set(main.app.openapi()["paths"])
    for path in ("/api/rules", "/api/rules/preview", "/api/rules/order", "/api/exclusions", "/api/smart-settings",
                 "/api/ratings", "/api/weights", "/api/collections/{collection_id}/cooldown", "/api/watch-folders",
                 "/api/watch-folders/{folder_id}/check", "/api/stats/recent", "/api/stats/top",
                 "/api/stats/never-played", "/api/stats/summary", "/api/health/intros", "/api/media/status",
                 "/api/media/info/{preroll_id}", "/api/media/loudness", "/api/media/loudness/check",
                 "/api/media/loudness/normalize", "/api/media/versions", "/api/media/combine"):
        assert path in paths, path


def test_the_plugin_route_uses_the_rule_set_and_records_history():
    deps = main._plugin_v2_deps()
    assert deps.smart_intros is not None and deps.on_answer is not None
    assert deps.rule_pool is not None and deps.binge_hours() >= 1
