# Rules: different intros for different titles

A rule says "when this kind of title starts, play these intros". Rules work on Jellyfin and Emby. Some rules people make:

- **Kids:** anything rated kids-safe gets one intro from the *Kids* collection.
- **80s horror:** a horror movie from the 1980s gets the *VHS* intros, in order.
- **Dad's films:** when Dad watches something from the *Films* library, two random intros from *Cinema* play.

Make them on [When They Play, Rules](app:/schedules/rules). Press **New rule**. If you don't have any rules yet, **Make a Kids rule** starts you off with a ready-made one.

## Which rule wins

Every time something starts, Prerolls Max checks four things, in this order:

1. The [never-play list](help:never-play). A title on it gets no intro at all.
2. Your rules, from the top of the list down. The first rule that matches picks the intros.
3. Your [schedules](help:schedules), if no rule matched.
4. Your default intros, if no schedule is on.

So the order of your rules matters. Put the most specific ones at the top, using the arrows. A rule with nothing filled in under "When" matches everything, so if you have one, keep it at the bottom.

## When: what a rule looks for

Fill in only what matters. Everything you fill in must be true for the rule to match. A list matches if any entry in it does, so "Genres: Animation, Family" matches a title with either genre. Anything you leave empty is ignored.

| Condition | Matches when |
|---|---|
| Before | It's a movie, a TV episode, or either. |
| Only the first episode of a binge | It's the first episode someone starts after a break. See [TV shows, kids and the never-play list](help:never-play). |
| Genres | The title has one of these genres. "Sci-Fi" also matches "Science Fiction". |
| Kids-safe titles | The title's age rating is on your kids-safe list. |
| Age ratings | The title has one of these ratings. "pg 13" and "US-PG-13" both count as PG-13. |
| Decades, From the year, To the year | The title came out in one of these decades, or between the two years. |
| Libraries | The title is in one of these libraries on your media server. |
| Who's watching | One of these people is watching, by their Jellyfin or Emby user name. |

## Play: what a rule plays

A rule plays **a collection** or **videos I choose**. You also pick **how many**, and whether they play **at random** or **in order**. A random rule can also say **Don't repeat an intro within** a number of hours. See [How often and no repeats](help:weights-and-cooldowns).

If a rule has nothing it can play (its collection is empty, or its videos were deleted), the list says why, and that rule is skipped until you fix it.

To pause a rule without deleting it, open it and turn **On** off.

## Kids-safe

To begin with, kids-safe means:

- US movies: G and PG
- US TV: TV-Y, TV-Y7, TV-G and TV-PG
- UK: U and PG

Change the list in [Settings, Playback](app:/settings#playback).

Titles with no rating, or rated *Not Rated* or *Unrated*, don't count unless you turn on **Treat unrated titles as kids-safe**. An unrated title could be a home video, or it could be a director's cut. It's better for a kids' rule to miss a cartoon than to play before the wrong film.

## Try it

**Try it**, below the list, answers "what would happen for this title?". Type a title, its genres, age rating, year, library or who's watching, then press **Show what would play**. You get an answer like:

> Matches 'Kids' because the movie is rated PG, which is kids-safe. It plays 1 of these 2 at random.

Open **Why each rule did or didn't match** to see why the rules above it didn't match ("the movie is Crime, not Horror"). Trying never changes what plays next.

## Where rules work

| | Plex | Jellyfin | Emby |
|---|---|---|---|
| Rules | No | Yes, for every play | Yes, for every play |
| Needs | | The Prerolls Max plugin | The Prerolls Max plugin and Emby Premiere |

Plex picks its intro before it knows which movie is starting, and it has one intro list for everyone, so rules can't work there. On Plex, the closest thing is a [playlist](help:playlists) step with "Only play this in some cases". It follows the movie already playing, so it affects the next play, not this one.
