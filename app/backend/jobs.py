"""Background jobs with progress the web interface can poll.

Long work (refreshing a community list, downloading a handful of intro videos)
runs on a small thread pool instead of inside a request. Starting it returns a
job id; ``GET /api/jobs/{id}`` says how far it got:

    {id, kind, state: queued|running|done|failed, progress: 0-100,
     message, done, total, errors: [{item_id, message}], result}

Jobs live in memory only. Finished ones are kept for an hour (at most
``MAX_KEPT``) so a page that reloads can still read the outcome.

A job function receives a :class:`JobContext` and reports through it. Errors
for single items go in ``ctx.error(item_id, message)`` and the job carries on;
an exception ends the job as failed. :class:`AppError` messages are shown as
they are, anything else becomes a generic sentence (details go to the log).
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
import queue
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter

from backend.errors import GENERIC_MESSAGE, AppError, not_found

logger = logging.getLogger("prerollsmax.jobs")

QUEUED, RUNNING, DONE, FAILED = "queued", "running", "done", "failed"
MAX_KEPT = 200
KEEP_FINISHED_SECONDS = 3600


class Job:
    def __init__(self, kind: str, total: int = 0, message: str = "Waiting to start", key: Optional[str] = None):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.key = key
        self.state = QUEUED
        self.progress = 0
        self.message = message
        self.done = 0
        self.total = total
        self.errors: List[Dict[str, Any]] = []
        self.result: Any = None
        self.created_at = time.time()
        self.finished_at: Optional[float] = None

    @property
    def finished(self) -> bool:
        return self.state in (DONE, FAILED)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "kind": self.kind, "state": self.state, "progress": self.progress,
            "message": self.message, "done": self.done, "total": self.total,
            "errors": [dict(e) for e in self.errors], "result": self.result,
        }


class JobContext:
    """What a job function uses to report progress. Thread-safe."""

    def __init__(self, job: Job, lock: threading.Lock):
        self._job = job
        self._lock = lock

    @property
    def job_id(self) -> str:
        return self._job.id

    def set_total(self, total: int) -> None:
        with self._lock:
            self._job.total = max(0, int(total))
            self._recompute()

    def advance(self, count: int = 1, message: Optional[str] = None) -> None:
        with self._lock:
            self._job.done += count
            if message is not None:
                self._job.message = message
            self._recompute()

    def report(self, *, progress: Optional[float] = None, message: Optional[str] = None,
               done: Optional[int] = None, total: Optional[int] = None) -> None:
        with self._lock:
            if total is not None:
                self._job.total = max(0, int(total))
            if done is not None:
                self._job.done = max(0, int(done))
            if message is not None:
                self._job.message = message
            if progress is not None:
                self._job.progress = int(min(99, max(self._job.progress, progress)))
            elif total is not None or done is not None:
                self._recompute()

    def error(self, item_id: Optional[str], message: str) -> None:
        with self._lock:
            self._job.errors.append({"item_id": item_id, "message": message})

    def _recompute(self) -> None:
        if self._job.total:
            self._job.progress = int(min(99, 100 * self._job.done / self._job.total))


class JobRunner:
    def __init__(self, max_workers: int = 3, log: Optional[Callable[[str, str], None]] = None):
        # Daemon threads, not a ThreadPoolExecutor: the app must be able to
        # stop while a long job (reading video lengths) is still going.
        self._queue: "queue.Queue" = queue.Queue()
        self._max_workers = max_workers
        self._workers: List[threading.Thread] = []
        self._idle = 0
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()
        self._log = log

    def _worker(self) -> None:
        while True:
            job, fn = self._queue.get()
            try:
                self._run(job, fn)
            finally:
                with self._lock:
                    self._idle += 1

    def _dispatch(self, job: Job, fn) -> None:
        with self._lock:
            if self._idle > 0:
                self._idle -= 1          # an idle worker will take it
            elif len(self._workers) < self._max_workers:
                t = threading.Thread(target=self._worker, name=f"job-{len(self._workers) + 1}", daemon=True)
                self._workers.append(t)
                t.start()
            # else: every worker is busy; it waits its turn in the queue
        self._queue.put((job, fn))

    def set_log(self, log: Callable[[str, str], None]) -> None:
        self._log = log

    def submit(self, kind: str, fn: Callable[[JobContext], Any], *, total: int = 0,
               message: str = "Waiting to start", key: Optional[str] = None) -> Job:
        """Queue ``fn(ctx)``. With ``key``, a job with that key that hasn't
        finished is returned instead of starting a second one."""
        with self._lock:
            self._prune()
            if key:
                running = next((j for j in self._jobs.values() if j.key == key and not j.finished), None)
                if running:
                    return running
            job = Job(kind, total=total, message=message, key=key)
            self._jobs[job.id] = job
        self._dispatch(job, fn)
        return job

    def _run(self, job: Job, fn: Callable[[JobContext], Any]) -> None:
        ctx = JobContext(job, self._lock)
        with self._lock:
            job.state = RUNNING
            if job.message == "Waiting to start":
                job.message = "Working"
        try:
            result = fn(ctx)
            with self._lock:
                job.result = result
                job.state = DONE
                job.progress = 100
                if job.message in ("Working", "Waiting to start"):
                    job.message = "Finished"
        except AppError as exc:
            with self._lock:
                job.state = FAILED
                job.message = exc.message
                if exc.hint:
                    job.result = {"hint": exc.hint}
        except Exception as exc:  # logged, never shown
            self._write_log(f"Job {job.kind} {job.id} failed: {type(exc).__name__}: {exc}")
            with self._lock:
                job.state = FAILED
                job.message = GENERIC_MESSAGE
        finally:
            with self._lock:
                job.finished_at = time.time()

    def _write_log(self, message: str) -> None:
        if self._log:
            try:
                self._log(message, "ERROR")
                return
            except Exception:
                pass
        logger.error(message)

    def _prune(self) -> None:
        now = time.time()
        old = [jid for jid, j in self._jobs.items()
               if j.finished and j.finished_at and now - j.finished_at > KEEP_FINISHED_SECONDS]
        for jid in old:
            del self._jobs[jid]
        finished = sorted((j for j in self._jobs.values() if j.finished), key=lambda j: j.finished_at or 0)
        while len(self._jobs) > MAX_KEPT and finished:
            del self._jobs[finished.pop(0).id]

    def get(self, job_id: str) -> Optional[dict]:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.to_dict() if job else None

    def active(self, key: str) -> Optional[dict]:
        with self._lock:
            job = next((j for j in self._jobs.values() if j.key == key and not j.finished), None)
            return job.to_dict() if job else None

    def latest(self, key: str) -> Optional[dict]:
        """The newest job with this key, finished or not."""
        with self._lock:
            found = [j for j in self._jobs.values() if j.key == key]
            return max(found, key=lambda j: j.created_at).to_dict() if found else None

    def wait(self, job_id: str, timeout: float = 30.0) -> Optional[dict]:
        """For tests and synchronous callers: poll until the job finishes."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            state = self.get(job_id)
            if state is None or state["state"] in (DONE, FAILED):
                return state
            time.sleep(0.01)
        return self.get(job_id)


runner = JobRunner(max_workers=4)

router = APIRouter(tags=["Jobs"])


@router.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    """How far a background job got."""
    state = runner.get(job_id)
    if state is None:
        raise not_found("That task", hint="It may have finished more than an hour ago, or Prerolls Max restarted.")
    return state
