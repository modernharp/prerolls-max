"""Build info, update source and port: nothing tied to one GitHub account."""
import importlib
import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

from backend import build_info, port_config

ROOT = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture
def info_file(tmp_path, monkeypatch):
    path = tmp_path / "build_info.json"
    monkeypatch.setenv("PMAX_BUILD_INFO", str(path))
    monkeypatch.delenv("PMAX_UPDATE_REPO", raising=False)
    yield path
    monkeypatch.delenv("PMAX_BUILD_INFO", raising=False)
    monkeypatch.delenv("PMAX_UPDATE_REPO", raising=False)
    _brand()


def _brand():
    build_info.load(refresh=True)
    from backend import brand
    return importlib.reload(brand)


def test_repository_comes_from_build_info(info_file):
    info_file.write_text(json.dumps({"repository": "someone/prerolls-max"}))
    brand = _brand()
    assert brand.UPDATE_REPO == "someone/prerolls-max"
    assert brand.PROJECT_URL == "https://github.com/someone/prerolls-max"
    assert brand.release_api_url() == "https://api.github.com/repos/someone/prerolls-max/releases/latest"
    assert brand.user_agent_comment("x") == " (+https://github.com/someone/prerolls-max; x)"


def test_no_build_info_means_updates_off(info_file):
    brand = _brand()
    assert brand.UPDATE_REPO == ""
    assert brand.PROJECT_URL == ""
    assert brand.release_api_url() is None
    assert brand.user_agent_comment() == ""
    assert brand.user_agent_comment("x") == " (x)"


def test_env_overrides_and_can_switch_off(info_file, monkeypatch):
    info_file.write_text(json.dumps({"repository": "someone/prerolls-max"}))
    monkeypatch.setenv("PMAX_UPDATE_REPO", "other/fork")
    assert _brand().UPDATE_REPO == "other/fork"
    monkeypatch.setenv("PMAX_UPDATE_REPO", "off")
    assert _brand().UPDATE_REPO == ""


@pytest.mark.parametrize("value", ["", "nope", "a/b/c", "../x", "https://evil.example/x/y", "a b/c"])
def test_rejects_values_that_are_not_a_repository(info_file, value):
    info_file.write_text(json.dumps({"repository": value}))
    assert _brand().UPDATE_REPO == ""


def test_broken_file_is_ignored(info_file):
    info_file.write_text("{not json")
    assert _brand().UPDATE_REPO == ""


# The only GitHub repositories shipped code may name: NeXroll (credit) and the
# YouTube token provider it downloads. Everything else comes from build_info.json.
ALLOWED_GITHUB = {"JFLXCLOUD/NeXroll", "Brainicism/bgutil-ytdlp-pot-provider"}


def test_no_account_is_hard_coded_in_shipped_code():
    shipped = [ROOT / "app" / "backend", ROOT / "app" / "scripts", ROOT / "packaging", ROOT / "plugins",
               ROOT / "Dockerfile", ROOT / "docker-compose.yml", ROOT / "unraid", ROOT / "docker",
               ROOT / ".github", ROOT / "scripts"]
    pattern = re.compile(r"github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)")
    hits = []
    for base in shipped:
        files = [base] if base.is_file() else [p for p in base.rglob("*") if p.is_file()]
        for path in files:
            if path.suffix in {".png", ".ico", ".dll", ".zip", ".pyc"} or "bin" in path.parts or "obj" in path.parts:
                continue
            for repo in pattern.findall(path.read_text(encoding="utf-8", errors="ignore")):
                repo = repo.removesuffix(".git")
                if repo not in ALLOWED_GITHUB and not repo.startswith(("rhysd/actionlint", "repos/")):
                    hits.append(f"{path.relative_to(ROOT)}: {repo}")
    assert hits == []


def test_write_build_info_script(tmp_path):
    out = tmp_path / "build_info.json"
    env = dict(os.environ, GITHUB_REPOSITORY="Some-Owner/prerolls-max", GITHUB_SHA="abc123")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "write_build_info.py"), "--out", str(out)],
                   check=True, env=env, capture_output=True)
    data = json.loads(out.read_text())
    assert data["repository"] == "Some-Owner/prerolls-max"
    assert data["commit"] == "abc123"
    assert data["image"] == "ghcr.io/some-owner/prerolls-max"
    from backend import version
    assert data["version"] == version.__version__


def test_port_order(tmp_path):
    """One port setting: PMAX_PORT, else startup.json in the data folder (which
    Settings and the Windows installer write), else 9393."""
    env = {"PMAX_DB_DIR": str(tmp_path)}
    assert port_config.configured_port(env) == (9393, "default")
    port_config.save_port(9494, env)
    assert port_config.configured_port(env) == (9494, "settings")
    assert port_config.configured_port(dict(env, PMAX_PORT="9500")) == (9500, "environment")
    port_config.save_port(None, env)
    assert port_config.configured_port(env) == (9393, "default")


def test_installer_writes_the_same_port_file():
    nsi = (ROOT / "packaging" / "windows" / "installer.nsi").read_text(encoding="utf-8")
    assert port_config.FILE_NAME in nsi and "Prerolls Max\\startup.json" in nsi.replace("/", "\\")
    for script in ("tray_app.py", "windows_service.py"):
        assert "port_config.configured_port" in (ROOT / "app" / "scripts" / script).read_text(encoding="utf-8")


def test_versions_agree():
    """app/version.py, the backend fallback and the frontend package agree."""
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "bump_version.py"), "--check"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_release_helpers(tmp_path):
    from xml.dom import minidom

    notes = subprocess.run([sys.executable, str(ROOT / "scripts" / "release_notes.py"), "1.0.0",
                            "--repository", "Some-One/prerolls-max"],
                           capture_output=True, text=True, check=True).stdout
    assert "Prerolls Max replaces NeXroll" in notes
    assert "ghcr.io/some-one/prerolls-max:1.0.0" in notes
    assert "https://some-one.github.io/prerolls-max/jellyfin/manifest.json" in notes
    subprocess.run([sys.executable, str(ROOT / "scripts" / "render_templates.py"), "--repository",
                    "Some-One/prerolls-max", "--out", str(tmp_path)], check=True, capture_output=True)
    xml = (tmp_path / "unraid" / "prerolls-max.xml").read_text()
    assert "<Repository>ghcr.io/some-one/prerolls-max:latest</Repository>" in xml
    assert "{{" not in xml
    minidom.parseString(xml.encode())
