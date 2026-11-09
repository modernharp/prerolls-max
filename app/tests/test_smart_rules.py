"""Smart rules: the rule-set matcher and the never-play list.

The same facts the plugin sends drive both the simple rule set
(intro_rules.py) and Playlist (Advanced) conditions (sequence_conditions.py).
"""
import pytest

from backend import intro_rules, ratings

SETTINGS = {"unrated_is_kids_safe": False, "kids_safe_ratings": list(ratings.DEFAULT_KIDS_SAFE),
            "honor_no_intro_tags": True, "no_intro_tags": ["no-intro", "nointro"]}


# --- the rule set -------------------------------------------------------------

def facts(**kw):
    base = {"item_type": "Movie", "item_name": "Some Film", "genres": [], "tags": [], "official_rating": "",
            "year": None, "library_name": "", "library_id": "", "user_name": "", "user_id": ""}
    base.update(kw)
    return base


def rule(name, **when):
    return {"id": hash(name) % 1000, "name": name, "enabled": True, "when": when, "play": {}}


def test_kids_rule_explains_itself():
    kids = rule("Kids", kids_safe=True)
    matched, text, _ = intro_rules.first_match([kids], facts(official_rating="PG"), SETTINGS)
    assert matched is kids
    assert text == "Matches 'Kids' because the movie is rated PG, which is kids-safe."


def test_first_matching_rule_wins_and_checks_say_why_others_did_not():
    horror = rule("Horror nights", genres=["Horror"], media_type="movie")
    kids = rule("Kids", kids_safe=True)
    matched, text, checks = intro_rules.first_match(
        [horror, kids], facts(genres=["Animation", "Family"], official_rating="G"), SETTINGS)
    assert matched is kids
    assert checks[0]["why"] == "Doesn't match: the movie is Animation and Family, not Horror."
    assert "rated G" in text


def test_every_condition_must_hold():
    combined = rule("80s horror for Sam", genres=["horror"], decades=["1980s"], users=["sam"], media_type="movie")
    ok, because, _ = intro_rules.match_when(combined["when"], facts(genres=["Horror"], year=1982, user_name="Sam"),
                                            SETTINGS)
    assert ok and because == ["it's a movie", "the movie is in the horror genre", "the movie came out in 1982",
                              "Sam is watching"]
    ok, _, why = intro_rules.match_when(combined["when"], facts(genres=["Horror"], year=1995, user_name="Sam"),
                                        SETTINGS)
    assert not ok and why == "the movie came out in 1995"
    ok, _, why = intro_rules.match_when(combined["when"], facts(genres=["Horror"], year=1982), SETTINGS)
    assert not ok and why == "nobody said who is watching"


def test_genre_aliases_match():
    ok, _, _ = intro_rules.match_when({"genres": ["Sci-Fi"]}, facts(genres=["Science Fiction"]), SETTINGS)
    assert ok


def test_unrated_titles_and_the_setting():
    when = {"kids_safe": True}
    ok, _, why = intro_rules.match_when(when, facts(official_rating=""), SETTINGS)
    assert not ok and "no age rating" in why
    ok, _, _ = intro_rules.match_when(when, facts(official_rating="NR"), {**SETTINGS, "unrated_is_kids_safe": True})
    assert ok


def test_ratings_list_and_library_and_user_ids():
    when = {"ratings": ["PG-13", "R"], "libraries": ["Films"], "users": ["u-1"]}
    ok, because, _ = intro_rules.match_when(
        when, facts(official_rating="pg 13", library_name="Films", user_id="u-1", user_name="Dad"), SETTINGS)
    assert ok and "the movie is rated pg 13" in because and "Dad is watching" in because
    ok, _, why = intro_rules.match_when(when, facts(official_rating="R", library_name="Kids"), SETTINGS)
    assert not ok and why == "it's in the Kids library"


def test_episodes_and_first_episode_only():
    when = {"media_type": "episode", "first_episode_only": True}
    episode = facts(item_type="Episode", first_in_session=True)
    ok, because, _ = intro_rules.match_when(when, episode, SETTINGS)
    assert ok and because == ["it's an episode", "it's the first episode of a sitting"]
    ok, _, why = intro_rules.match_when(when, {**episode, "first_in_session": False}, SETTINGS)
    assert not ok and why == "it isn't the first episode of this sitting"
    ok, _, why = intro_rules.match_when(when, facts(), SETTINGS)
    assert not ok and why == "it's a movie, not an episode"
    # "first episode only" leaves movies alone when the rule covers both.
    ok, _, _ = intro_rules.match_when({"first_episode_only": True}, facts(), SETTINGS)
    assert ok


def test_disabled_rules_and_empty_rules():
    off = {**rule("Off"), "enabled": False}
    everything = rule("Everything")
    matched, text, checks = intro_rules.first_match([off, everything], facts(), SETTINGS)
    assert matched is everything and checks[0]["why"] == "This rule is turned off."
    assert text == "Matches 'Everything' because it has no conditions, so it matches everything."
    assert intro_rules.first_match([], facts(), SETTINGS)[0] is None


def test_never_play_list_by_id_title_and_tag():
    rows = [{"kind": "item", "value": "abc-123"}, {"kind": "title", "value": "the room"},
            {"kind": "tag", "value": "Concert"}]
    assert intro_rules.exclusion_reason(rows, facts(item_id="ABC123"), SETTINGS) == \
        "No intros: 'Some Film' is on your never-play list."
    assert intro_rules.exclusion_reason(rows, facts(item_name="The  Room"), SETTINGS)
    assert intro_rules.exclusion_reason(rows, facts(tags=["concert"]), SETTINGS) == \
        "No intros: 'Some Film' has the tag 'concert'."
    # A whole series by its id or name.
    assert intro_rules.exclusion_reason(rows, facts(item_type="Episode", item_name="Pilot", series_id="abc-123"),
                                        SETTINGS)
    assert intro_rules.exclusion_reason(rows, facts(item_name="Other"), SETTINGS) is None


@pytest.mark.parametrize("listed,shown", [
    ("Night of the Test", "Night of the Test (1985)"),   # Jellyfin before metadata: folder name with year
    ("Night of the Test (1985)", "Night of the Test"),
    ("night of the test", "Night of the Test  (1985)"),
])
def test_never_play_title_matches_with_or_without_the_year(listed, shown):
    rows = [{"kind": "title", "value": listed}]
    assert intro_rules.exclusion_reason(rows, facts(item_name=shown), SETTINGS)


def test_never_play_title_does_not_drop_other_brackets():
    rows = [{"kind": "title", "value": "Alien"}]
    assert intro_rules.exclusion_reason(rows, facts(item_name="Alien (Director's Cut)"), SETTINGS) is None
    assert intro_rules.exclusion_reason(rows, facts(item_name="Aliens (1986)"), SETTINGS) is None


@pytest.mark.parametrize("tag", ["no-intro", "NoIntro", "no intro", "nointro"])
def test_no_intro_tags_are_honoured_automatically(tag):
    assert intro_rules.exclusion_reason([], facts(tags=["4K", tag]), SETTINGS) == \
        f"No intros: 'Some Film' has the tag '{tag}'."
    assert intro_rules.exclusion_reason([], facts(tags=[tag]), {**SETTINGS, "honor_no_intro_tags": False}) is None


def test_rule_summaries():
    assert intro_rules.describe_when({"kids_safe": True, "media_type": "movie"}) == "When a movie and rated kids-safe."
    assert intro_rules.describe_when({}) == "Always (no conditions)."
    assert intro_rules.describe_play({"count": 2, "order": "random", "cooldown_hours": 12}, "Kids") == \
        "Plays 2 intros at random from 'Kids', not repeating one within 12 hours."
    assert intro_rules.describe_play({"order": "in_order"}, None) == "Plays all of the chosen intros in order."
