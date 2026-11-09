"""The background job runner behind /api/jobs/{id}."""
import threading
import time

from backend.errors import GENERIC_MESSAGE, AppError
from backend.jobs import JobRunner


def test_a_job_reports_progress_errors_and_result():
    runner = JobRunner(max_workers=1)

    def work(ctx):
        ctx.set_total(4)
        for n in range(4):
            if n == 2:
                ctx.error("pm:b", "That one is on YouTube.")
            ctx.advance(message=f"Item {n + 1}")
        return {"added": 3}

    job = runner.submit("test.work", work)
    assert job.state in ("queued", "running", "done")
    out = runner.wait(job.id)
    assert out == {"id": job.id, "kind": "test.work", "state": "done", "progress": 100, "message": "Item 4",
                   "done": 4, "total": 4, "errors": [{"item_id": "pm:b", "message": "That one is on YouTube."}],
                   "result": {"added": 3}}


def test_progress_never_claims_100_before_the_end():
    runner = JobRunner(max_workers=1)
    seen = []
    gate = threading.Event()

    def work(ctx):
        ctx.report(total=2, done=2)
        seen.append(runner.get(ctx.job_id)["progress"])
        gate.wait(5)

    job = runner.submit("test", work)
    while not seen:
        time.sleep(0.001)
    assert seen == [99] and runner.get(job.id)["state"] == "running"
    gate.set()
    assert runner.wait(job.id)["progress"] == 100


def test_failures_say_what_happened_without_internals():
    logged = []
    runner = JobRunner(max_workers=1, log=lambda message, level: logged.append(message))

    def plain(ctx):
        raise AppError("Prerolls.me didn't answer.", hint="Try again later.")

    def broken(ctx):
        raise KeyError("secret internal detail")

    a = runner.wait(runner.submit("test", plain).id)
    assert (a["state"], a["message"], a["result"]) == ("failed", "Prerolls.me didn't answer.", {"hint": "Try again later."})
    b = runner.wait(runner.submit("test", broken).id)
    assert (b["state"], b["message"]) == ("failed", GENERIC_MESSAGE)
    assert "secret internal detail" not in str(b) and "secret internal detail" in logged[0]


def test_a_keyed_job_runs_once_at_a_time():
    runner = JobRunner(max_workers=2)
    gate = threading.Event()
    first = runner.submit("refresh", lambda ctx: gate.wait(5), key="refresh:x")
    second = runner.submit("refresh", lambda ctx: None, key="refresh:x")
    assert second.id == first.id and runner.active("refresh:x")["id"] == first.id
    gate.set()
    runner.wait(first.id)
    assert runner.active("refresh:x") is None and runner.latest("refresh:x")["id"] == first.id
    third = runner.submit("refresh", lambda ctx: None, key="refresh:x")
    assert third.id != first.id


def test_unknown_jobs_are_none():
    assert JobRunner().get("nope") is None
