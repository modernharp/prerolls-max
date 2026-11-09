"""When what plays changes, Prerolls Max asks the Jellyfin and Emby plugins to
download the new intros right away (their Prefetch endpoint). Emby only plays
an intro it has registered, which the plugin does after downloading it; left
to the plugin's half-hourly refresh, the first movies after a schedule
switched started with no intro on Emby."""
import time

from backend import plugin_push


class _Resp:
    def __init__(self, status):
        self.status_code = status


def test_prefetch_calls_each_connected_plugin(monkeypatch):
    calls = []
    monkeypatch.setattr(plugin_push, "_servers", lambda: {
        "jellyfin": {"url": "http://jf:8096/", "token": "j" * 32},
        "emby": {"url": "http://emby:8096", "token": "e" * 32},
        "plex": {"url": "http://plex:32400", "token": "p"},
    })
    monkeypatch.setattr(plugin_push.requests, "post",
                        lambda url, **kw: calls.append((url, kw.get("headers"))) or _Resp(204))
    assert plugin_push.prefetch_now() == {"jellyfin": True, "emby": True}
    urls = [u for u, _ in calls]
    assert urls == ["http://jf:8096/PrerollsMax/Prefetch", "http://emby:8096/emby/PrerollsMax/Prefetch"]
    assert calls[1][1] == {"X-Emby-Token": "e" * 32}


def test_a_server_that_is_down_is_not_fatal(monkeypatch):
    monkeypatch.setattr(plugin_push, "_servers", lambda: {"emby": {"url": "http://emby:8096", "token": "e" * 32}})

    def boom(url, **kw):
        raise OSError("connection refused")

    monkeypatch.setattr(plugin_push.requests, "post", boom)
    assert plugin_push.prefetch_now() == {"emby": False}
    monkeypatch.setattr(plugin_push, "_servers", lambda: {})
    assert plugin_push.prefetch_now() == {}


def test_requests_close_together_make_one_call(monkeypatch):
    runs = []
    monkeypatch.setattr(plugin_push, "prefetch_now", lambda: runs.append(1) or {})
    with plugin_push._prefetch_lock:  # one left waiting by an earlier test
        if plugin_push._prefetch_timer is not None:
            plugin_push._prefetch_timer.cancel()
            plugin_push._prefetch_timer = None
    assert plugin_push.request_prefetch(delay=0.05) is True
    assert plugin_push.request_prefetch(delay=0.05) is False
    time.sleep(0.3)
    assert runs == [1]
    assert plugin_push.request_prefetch(delay=0.01) is True
    time.sleep(0.2)
    assert runs == [1, 1]


def test_a_schedule_change_asks_the_plugins(monkeypatch):
    from backend import scheduler as sched_mod
    asked = []
    monkeypatch.setattr(sched_mod, "_request_plugin_prefetch", lambda: asked.append(1))
    s = sched_mod.Scheduler.__new__(sched_mod.Scheduler)
    import threading
    s._schedule_check_lock = threading.Lock()
    s._applied_local_paths = set()

    def tick_same():
        return None

    def tick_changes():
        s._applied_local_paths = {"/prerolls/Halloween/Ghost Intro.mp4"}

    monkeypatch.setattr(s, "_check_and_execute_schedules_locked", tick_same, raising=False)
    s._check_and_execute_schedules()
    assert asked == []
    monkeypatch.setattr(s, "_check_and_execute_schedules_locked", tick_changes, raising=False)
    s._check_and_execute_schedules()
    assert asked == [1]
