"""Shared fixtures for the media-server tests: a clean server list, a settings
row put back afterwards, and an in-memory secret store."""
import pytest

from backend import admin_guard, models, secure_store
from backend.database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)

SETTING_COLUMNS = ("plex_url", "plex_token", "jellyfin_url", "emby_url", "path_mappings", "plex_server_machine_id",
                   "plex_server_name", "auth_enabled")


@pytest.fixture
def secrets(monkeypatch):
    store = {}
    monkeypatch.setattr(secure_store, "get_secret", lambda name: store.get(name))
    monkeypatch.setattr(secure_store, "has_secret", lambda name: name in store)
    monkeypatch.setattr(secure_store, "set_secret", lambda name, value: store.__setitem__(name, value) or True)
    monkeypatch.setattr(secure_store, "delete_secret", lambda name: store.pop(name, None) is not None)
    return store


@pytest.fixture
def server_db(secrets):
    """A session with no media servers and a settings row whose server fields are restored afterwards."""
    db = SessionLocal()
    setting = db.query(models.Setting).first()
    if setting is None:
        setting = models.Setting()
        db.add(setting)
        db.commit()
    saved = {c: getattr(setting, c, None) for c in SETTING_COLUMNS}
    for column in SETTING_COLUMNS:
        setattr(setting, column, None)
    db.query(models.MediaServer).delete()
    db.query(models.APIKey).filter(models.APIKey.name.like("% Plugin (Auto)%")).delete(synchronize_session=False)
    db.commit()
    db.secrets = secrets
    try:
        yield db
    finally:
        db.rollback()
        db.query(models.MediaServer).delete()
        db.query(models.APIKey).filter(models.APIKey.name.like("% Plugin (Auto)%")).delete(synchronize_session=False)
        setting = db.query(models.Setting).first()
        for column, value in saved.items():
            setattr(setting, column, value)
        db.commit()
        db.close()


@pytest.fixture
def as_admin():
    before = admin_guard._check
    admin_guard.configure(lambda request, db, action=None, **kw: None)
    yield
    admin_guard._check = before


def add(db, kind, name, url, token="t" * 20, enabled=True, **fields):
    from backend import media_servers as ms
    row = models.MediaServer(type=kind, name=name, url=url, enabled=enabled, **fields)
    db.add(row)
    db.flush()
    ms.set_secret(row, token)
    ms.mirror(db)
    db.commit()
    return row
