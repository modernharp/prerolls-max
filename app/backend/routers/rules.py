"""Rule sets, the never-play list and the smart-feature settings.

    GET    /api/rules                 -> {rules: [Rule], fallback}
    POST   /api/rules                 RuleIn -> Rule
    GET    /api/rules/{id}            -> Rule
    PUT    /api/rules/{id}            RuleIn -> Rule
    DELETE /api/rules/{id}            -> {deleted: true}
    PUT    /api/rules/order           {ids: [..]} -> {rules: [Rule]}
    POST   /api/rules/preview         {item: {...}} -> which rule matches and what plays, in words

    GET    /api/exclusions            -> {items: [..], auto_tags: {...}}
    POST   /api/exclusions            {kind: item|title|tag, value, note?}
    DELETE /api/exclusions/{id}

    GET    /api/smart-settings        -> every setting (smart_settings.DEFAULTS)
    PUT    /api/smart-settings        changes some of them (admins)
    GET    /api/ratings               -> rating families for pickers, with kids-safe marks

Rule = {id, name, enabled, position, when, play, summary, plays, problem}
"""
from __future__ import annotations

import json
import logging
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend import intro_rules, models, smart_settings, unique_names
from backend.admin_guard import admin
from backend.database import SessionLocal
from backend.errors import AppError, bad_input, not_found
from backend.ratings import families_for_ui, rating_key
from backend.sequence_conditions import decade_of
from backend.validation import Name, clean_name

logger = logging.getLogger("prerollsmax.rules")

router = APIRouter(tags=["Rules"])

MAX_RULES = 200


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

def _texts(values, what: str, limit: int = 50) -> list:
    out = []
    for value in values or []:
        text = clean_name(str(value), what=what, max_len=100)
        if text.lower() not in [o.lower() for o in out]:
            out.append(text)
    if len(out) > limit:
        raise ValueError(f"Choose {limit} or fewer.")
    return out


class RuleWhen(BaseModel):
    model_config = ConfigDict(extra="ignore")

    genres: List[str] = Field(default_factory=list)
    ratings: List[str] = Field(default_factory=list)
    kids_safe: bool = False
    decades: List[str] = Field(default_factory=list)
    year_from: Optional[int] = Field(None, ge=1880, le=2200)
    year_to: Optional[int] = Field(None, ge=1880, le=2200)
    libraries: List[str] = Field(default_factory=list)
    users: List[str] = Field(default_factory=list)
    media_type: Literal["movie", "episode", "any"] = "any"
    first_episode_only: bool = False

    @field_validator("genres")
    @classmethod
    def _genres(cls, v):
        return _texts(v, "genre")

    @field_validator("libraries")
    @classmethod
    def _libraries(cls, v):
        return _texts(v, "library name")

    @field_validator("users")
    @classmethod
    def _users(cls, v):
        return _texts(v, "user name")

    @field_validator("ratings")
    @classmethod
    def _ratings(cls, v):
        out = []
        for value in v or []:
            key = rating_key(value)
            if not key or len(key) > 20:
                raise ValueError("Use age ratings like G, PG-13 or TV-Y7.")
            if key not in out:
                out.append(key)
        return out[:50]

    @field_validator("decades", mode="before")
    @classmethod
    def _decades(cls, v):
        out = []
        for value in v or []:
            decade = decade_of(value)
            if decade is None:
                raise ValueError("Use decades like 1980s or 1990.")
            if f"{decade}s" not in out:
                out.append(f"{decade}s")
        return out

    @model_validator(mode="after")
    def _years(self):
        if self.year_from and self.year_to and self.year_to < self.year_from:
            raise ValueError("The last year must be the same as or after the first year.")
        if self.first_episode_only and self.media_type == "movie":
            raise ValueError("\"First episode only\" needs the rule to cover episodes.")
        return self


class RulePlay(BaseModel):
    model_config = ConfigDict(extra="ignore")

    collection_id: Optional[int] = Field(None, ge=1)
    preroll_ids: List[int] = Field(default_factory=list, max_length=100)
    count: Optional[int] = Field(None, ge=1, le=20)
    order: Literal["random", "in_order"] = "random"
    cooldown_hours: int = Field(0, ge=0, le=720)

    @model_validator(mode="after")
    def _source(self):
        if not self.collection_id and not self.preroll_ids:
            raise ValueError("Choose a collection or some intro videos to play.")
        if self.collection_id and self.preroll_ids:
            raise ValueError("Choose a collection or intro videos, not both.")
        if any(i < 1 for i in self.preroll_ids):
            raise ValueError("That list has an intro video that doesn't exist.")
        return self


class RuleIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: Name
    enabled: bool = True
    when: RuleWhen = Field(default_factory=RuleWhen)
    play: RulePlay
    position: Optional[int] = Field(None, ge=0, le=MAX_RULES)


class RuleOrder(BaseModel):
    model_config = ConfigDict(extra="ignore")
    ids: List[int] = Field(..., max_length=MAX_RULES)


class SampleItem(BaseModel):
    """What the plugin would send about the title (CONTRACTS.md section 7)."""

    model_config = ConfigDict(extra="ignore")

    item_type: Literal["Movie", "Episode", "movie", "episode"] = "Movie"
    item_name: str = Field("", max_length=300)
    item_id: str = Field("", max_length=100)
    series_name: str = Field("", max_length=300)
    series_id: str = Field("", max_length=100)
    genres: List[str] = Field(default_factory=list, max_length=50)
    tags: List[str] = Field(default_factory=list, max_length=100)
    official_rating: str = Field("", max_length=40)
    year: Optional[int] = Field(None, ge=1880, le=2200)
    library_name: str = Field("", max_length=200)
    library_id: str = Field("", max_length=100)
    user_name: str = Field("", max_length=200)
    user_id: str = Field("", max_length=100)
    first_in_session: Optional[bool] = None


class PreviewIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    item: SampleItem = Field(default_factory=SampleItem)


class ExclusionIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: Literal["item", "title", "tag"]
    value: str = Field(..., min_length=1, max_length=300)
    note: Optional[str] = Field(None, max_length=300)

    @field_validator("value")
    @classmethod
    def _value(cls, v):
        return clean_name(v, what="value", max_len=300)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rows(db) -> list:
    return db.query(models.IntroRule).order_by(models.IntroRule.position, models.IntroRule.id).all()


def _check_play_targets(db, play: RulePlay) -> None:
    if play.collection_id:
        if db.query(models.Category).filter(models.Category.id == play.collection_id).first() is None:
            raise bad_input("That collection doesn't exist anymore.", field="play.collection_id",
                            hint="Pick another collection.")
    if play.preroll_ids:
        found = {p.id for p in db.query(models.Preroll.id).filter(models.Preroll.id.in_(play.preroll_ids)).all()}
        missing = [i for i in play.preroll_ids if i not in found]
        if missing:
            raise bad_input("Some of those intro videos don't exist anymore.", field="play.preroll_ids",
                            hint="Refresh the page and choose them again.")


def present(db, row) -> dict:
    rule = intro_rules.rule_dict(row)
    play = rule["play"]
    collection_name = None
    if play.get("collection_id"):
        collection = db.query(models.Category).filter(models.Category.id == play["collection_id"]).first()
        collection_name = collection.name if collection else None
    plays, _collection, problem = intro_rules.candidates(db, play)
    rule.update({
        "summary": intro_rules.describe_when(rule["when"]) + " " + intro_rules.describe_play(play, collection_name),
        "collection_name": collection_name,
        "plays": [{"id": p.id, "name": intro_rules._label(p)} for p in plays[:50]],
        "problem": problem,
    })
    return rule


def _get_row(db, rule_id: int):
    row = db.query(models.IntroRule).filter(models.IntroRule.id == rule_id).first()
    if row is None:
        raise not_found("That rule")
    return row


def _renumber(db, rows: list) -> None:
    for index, row in enumerate(rows):
        row.position = index


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

FALLBACK_NOTE = ("When no rule matches, your schedules decide. Rules need the Prerolls Max Intros plugin on Jellyfin "
                 "or Emby; Plex picks its intro before it knows the movie, so rules don't apply there.")


@router.get("/api/rules")
def list_rules(db=Depends(get_db)):
    return {"rules": [present(db, r) for r in _rows(db)], "fallback": FALLBACK_NOTE}


@router.post("/api/rules")
def create_rule(body: RuleIn, db=Depends(get_db)):
    rows = _rows(db)
    if len(rows) >= MAX_RULES:
        raise AppError(f"You can have up to {MAX_RULES} rules.", status=409, code="too_many_rules",
                       hint="Delete rules you no longer use.")
    unique_names.check_unique(db, "rule", body.name)
    _check_play_targets(db, body.play)
    row = models.IntroRule(name=body.name, enabled=body.enabled,
                           when_json=json.dumps(body.when.model_dump()),
                           play_json=json.dumps(body.play.model_dump()))
    db.add(row)
    position = len(rows) if body.position is None else min(body.position, len(rows))
    rows.insert(position, row)
    _renumber(db, rows)
    db.commit()
    db.refresh(row)
    return present(db, row)


@router.put("/api/rules/order")
def order_rules(body: RuleOrder, db=Depends(get_db)):
    rows = _rows(db)
    by_id = {r.id: r for r in rows}
    if set(body.ids) != set(by_id) or len(body.ids) != len(by_id):
        raise bad_input("The new order has to list every rule once.", field="ids",
                        hint="Refresh the page and try again.")
    _renumber(db, [by_id[i] for i in body.ids])
    db.commit()
    return {"rules": [present(db, r) for r in _rows(db)]}


@router.get("/api/rules/{rule_id}")
def get_rule(rule_id: int, db=Depends(get_db)):
    return present(db, _get_row(db, rule_id))


@router.put("/api/rules/{rule_id}")
def update_rule(rule_id: int, body: RuleIn, db=Depends(get_db)):
    row = _get_row(db, rule_id)
    unique_names.check_rename(db, "rule", row.name, body.name, row.id)
    _check_play_targets(db, body.play)
    row.name = body.name
    row.enabled = body.enabled
    row.when_json = json.dumps(body.when.model_dump())
    row.play_json = json.dumps(body.play.model_dump())
    if body.position is not None:
        rows = [r for r in _rows(db) if r.id != row.id]
        rows.insert(min(body.position, len(rows)), row)
        _renumber(db, rows)
    db.commit()
    db.refresh(row)
    return present(db, row)


@router.delete("/api/rules/{rule_id}")
def delete_rule(rule_id: int, db=Depends(get_db)):
    row = _get_row(db, rule_id)
    db.delete(row)
    db.flush()
    _renumber(db, _rows(db))
    db.commit()
    return {"deleted": True}


def _facts(item: SampleItem) -> dict:
    data = item.model_dump()
    data["item_type"] = "Episode" if item.item_type.lower() == "episode" else "Movie"
    return data


def _schedules_now(db) -> str:
    setting = db.query(models.Setting).first()
    if setting is None:
        return "Nothing is set up yet."
    parts = []
    schedule_id = getattr(setting, "active_schedule_id", None)
    if schedule_id:
        schedule = db.query(models.Schedule).filter(models.Schedule.id == schedule_id).first()
        if schedule is not None:
            parts.append(f"the schedule '{schedule.name}' is on")
    category_id = getattr(setting, "active_category", None)
    if category_id and not parts:
        category = db.query(models.Category).filter(models.Category.id == category_id).first()
        if category is not None:
            parts.append(f"the collection '{category.name}' is playing")
    if getattr(setting, "filler_active", None) and not parts:
        parts.append("your default intros are playing")
    return ("Right now " + parts[0] + ".") if parts else "Right now no schedule is on, so nothing would play."


@router.post("/api/rules/preview")
def preview_rules(body: PreviewIn, db=Depends(get_db)):
    """Which rule a title would match and what would play, in plain words.

    Nothing is recorded and no rotation moves.
    """
    facts = _facts(body.item)
    settings = smart_settings.get_all(db)
    exclusions = [{"kind": e.kind, "value": e.value} for e in db.query(models.IntroExclusion).all()]
    excluded = intro_rules.exclusion_reason(exclusions, facts, settings)
    rules = [intro_rules.rule_dict(r) for r in _rows(db)]
    if excluded:
        return {"excluded": True, "matched": None, "explanation": excluded, "would_play": [], "pool": [],
                "count": 0, "order": None, "checks": [], "fallback": None}
    rule, explanation, checks = intro_rules.first_match(rules, facts, settings)
    if rule is None:
        return {"excluded": False, "matched": None, "explanation": explanation, "would_play": [], "pool": [],
                "count": 0, "order": None, "checks": checks, "fallback": _schedules_now(db)}
    rows, problem = intro_rules.choose(db, rule, dry_run=True)
    play = rule.get("play") or {}
    order = play.get("order") or "random"
    count = play.get("count") or (len(rows) if order == "in_order" else 1)
    listed = [{"id": p.id, "name": intro_rules._label(p)} for p in rows]
    if problem:
        explanation += f" But it can't play anything: {problem} So your schedules decide instead."
    elif order == "random":
        explanation += f" It plays {count} of these {len(listed)} at random."
    else:
        explanation += f" It plays {'these' if len(listed) > 1 else 'this'} in order."
    return {"excluded": False, "matched": {"id": rule.get("id"), "name": rule.get("name")},
            "explanation": explanation, "would_play": listed if order == "in_order" else [],
            "pool": listed if order == "random" else [], "count": count, "order": order,
            "checks": checks, "fallback": _schedules_now(db) if problem else None}


# ---------------------------------------------------------------------------
# Never-play list
# ---------------------------------------------------------------------------

def _exclusion(row) -> dict:
    labels = {"item": "Item id", "title": "Title", "tag": "Tag"}
    return {"id": row.id, "kind": row.kind, "kind_label": labels.get(row.kind, row.kind), "value": row.value,
            "note": row.note, "created_at": row.created_at.isoformat() + "Z" if row.created_at else None}


@router.get("/api/exclusions")
def list_exclusions(db=Depends(get_db)):
    settings = smart_settings.get_all(db)
    rows = db.query(models.IntroExclusion).order_by(models.IntroExclusion.kind, models.IntroExclusion.value).all()
    return {"items": [_exclusion(r) for r in rows],
            "auto_tags": {"enabled": bool(settings.get("honor_no_intro_tags", True)),
                          "tags": settings.get("no_intro_tags") or [],
                          "note": "Jellyfin and Emby items tagged with one of these never get intros. "
                                  "Plex can't skip intros for one title."}}


@router.post("/api/exclusions")
def add_exclusion(body: ExclusionIn, db=Depends(get_db)):
    existing = (db.query(models.IntroExclusion)
                .filter(models.IntroExclusion.kind == body.kind).all())
    if any(e.value.strip().lower() == body.value.strip().lower() for e in existing):
        raise AppError("That's already on the never-play list.", status=409, code="already_excluded",
                       fields={"value": "That's already on the never-play list."})
    if db.query(models.IntroExclusion).count() >= 5000:
        raise AppError("The never-play list is full (5,000 entries).", status=409, code="too_many_exclusions",
                       hint="Tag the titles with no-intro in Jellyfin or Emby instead.")
    row = models.IntroExclusion(kind=body.kind, value=body.value, note=(body.note or "").strip() or None)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _exclusion(row)


@router.delete("/api/exclusions/{exclusion_id}")
def delete_exclusion(exclusion_id: int, db=Depends(get_db)):
    row = db.query(models.IntroExclusion).filter(models.IntroExclusion.id == exclusion_id).first()
    if row is None:
        raise not_found("That entry")
    db.delete(row)
    db.commit()
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@router.get("/api/smart-settings")
def get_smart_settings(db=Depends(get_db)):
    return smart_settings.get_all(db)


@router.put("/api/smart-settings", dependencies=[Depends(admin("change these settings"))])
def put_smart_settings(body: smart_settings.SmartSettingsUpdate, db=Depends(get_db)):
    changes = body.model_dump(exclude_none=True)
    values = smart_settings.save(db, changes)
    out = dict(values)
    if "binge_window_hours" in changes:
        from backend import plugin_push
        out["plugins_updated"] = plugin_push.push_binge_window(int(changes["binge_window_hours"]))
    return out


@router.get("/api/ratings")
def get_ratings(db=Depends(get_db)):
    settings = smart_settings.get_all(db)
    return {"families": families_for_ui(bool(settings.get("unrated_is_kids_safe")), settings.get("kids_safe_ratings")),
            "kids_safe": settings.get("kids_safe_ratings"),
            "unrated_is_kids_safe": bool(settings.get("unrated_is_kids_safe"))}
