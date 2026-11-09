"""First run on Windows picks up NeXroll's database from NeXroll's own data
folder (%ProgramData%\\NeXroll or %LOCALAPPDATA%\\NeXroll), since Prerolls Max
keeps its data under a different folder name. The NeXroll file is copied,
never moved or changed."""
import os
import sqlite3
import sys

from backend import database
from backend.brand import DB_FILENAME, LEGACY_DB_FILENAME


def _make_nexroll_db(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE prerolls (id INTEGER PRIMARY KEY, filename TEXT)")
    con.execute("INSERT INTO prerolls (filename) VALUES ('Ghost Intro.mp4')")
    con.commit()
    con.close()


def test_windows_candidates_include_nexroll_data_folders(tmp_path):
    env = {"ProgramData": str(tmp_path / "pd"), "LOCALAPPDATA": str(tmp_path / "la")}
    found = database._legacy_db_candidates(str(tmp_path / "new"), platform="win32", environ=env)
    assert os.path.join(env["ProgramData"], "NeXroll", LEGACY_DB_FILENAME) in found
    assert os.path.join(env["LOCALAPPDATA"], "NeXroll", LEGACY_DB_FILENAME) in found
    # Not on other systems
    assert not any("NeXroll" in p for p in database._legacy_db_candidates(str(tmp_path), platform="linux", environ=env))


def test_first_run_copies_the_nexroll_database_from_localappdata(tmp_path, monkeypatch):
    la = tmp_path / "la"
    old = la / "NeXroll" / LEGACY_DB_FILENAME
    _make_nexroll_db(str(old))
    before = old.read_bytes()
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("PMAX_DB_PATH", raising=False)
    monkeypatch.setenv("PMAX_DB_DIR", str(tmp_path / "new"))
    monkeypatch.setenv("ProgramData", str(tmp_path / "pd-empty"))
    monkeypatch.setenv("LOCALAPPDATA", str(la))
    path = database._resolve_db_path()
    assert path == str(tmp_path / "new" / DB_FILENAME)
    con = sqlite3.connect(path)
    try:
        assert con.execute("SELECT filename FROM prerolls").fetchall() == [("Ghost Intro.mp4",)]
    finally:
        con.close()
    assert old.read_bytes() == before, "the NeXroll file must not change"


def test_an_existing_prerolls_max_database_is_never_replaced(tmp_path, monkeypatch):
    _make_nexroll_db(str(tmp_path / "pd" / "NeXroll" / LEGACY_DB_FILENAME))
    new_dir = tmp_path / "new"
    new_dir.mkdir()
    (new_dir / DB_FILENAME).write_bytes(b"")
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("PMAX_DB_PATH", raising=False)
    monkeypatch.setenv("PMAX_DB_DIR", str(new_dir))
    monkeypatch.setenv("ProgramData", str(tmp_path / "pd"))
    assert database._resolve_db_path() == str(new_dir / DB_FILENAME)
    assert (new_dir / DB_FILENAME).read_bytes() == b""
