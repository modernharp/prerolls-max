"""Keep the test run away from an installed Prerolls Max.

Without these, tests that touch the scheduler appended SCHEDULER lines to the
real %ProgramData%\\Prerolls Max\\logs\\app.log, and anything importing
backend.database opened the installed nexroll.db. An explicit
PMAX_DB_PATH / PMAX_LOG_DIR from the environment still wins.
"""
import os
import tempfile

_scratch = tempfile.mkdtemp(prefix="nexroll-tests-")
os.environ.setdefault("PMAX_LOG_DIR", os.path.join(_scratch, "logs"))
os.environ.setdefault("PMAX_DB_PATH", os.path.join(_scratch, "nexroll.db"))
# Tests that import backend.main keep its preroll and data folders here too.
os.environ.setdefault("PMAX_PREROLL_PATH", os.path.join(_scratch, "prerolls"))
os.environ.setdefault("PMAX_DB_DIR", _scratch)
