# Rules: different intros for different titles

A rule says "when this kind of title starts, play these intros". Rules work on Jellyfin and Emby, with the Prerolls Max plugin. Some rules people make:

- **Kids:** anything rated kids-safe gets one intro from the *Kids* collection.
- **80s horror:** a horror movie from the 1980s gets the *VHS* intros, in order.
- **Dad's films:** when Dad watches something from the *Films* library, two random intros from *Cinema* play.

Make them on **When They Play**, under the **Rules** tab.

## Which rule wins

Every time something starts, Prerolls Max checks four things, in this order:

1. The never-play list. A title on it gets no intro at all. See [TV shows, kids and the never-play list](tv-and-kids.md).
2. Your rules, from the top of the list down. The first rule that matches picks the intros.
3. Your schedules, if no rule matched.
4. Your default intros, if no schedule is on.

So the order of your rules matters. Put the most specific ones at the top. A rule with nothing filled in under "When" matches everything, so if you have one, keep it at the bottom.

## When: what a rule looks for

Everything you fill in must be true. A list matches if any entry in it does, so "Genres: Animation, Family" matches a title with either genre. Anything you leave empty is ignored.

| Condition | Matches when |
|---|---|
| Before | It's a movie, a TV episode, or either. |
| Only the first episode of a binge | It's the first episode someone starts after a break. See [TV shows, kids and the never-play list](tv-and-kids.md). |
| Genres | The title has one of these genres. "Sci-Fi" also matches "Science Fiction". |
| Kids-safe titles | The title's age rating is on your kids-safe list. |
| Age ratings | The title has one of these ratings, like G, PG-13, TV-Y7 or 12A. "pg 13" and "US-PG-13" both count as PG-13. |
| Decades, From the year, To the year | The title came out in one of these decades, or between the two years. |
| Libraries | The title is in one of these libraries on your media server. |
| Who's watching | One of these people is watching, by their Jellyfin or Emby user name. |

## Play: what a rule plays

A rule plays **a collection** or **videos I choose**. You also pick **how many**, and whether they play **at random** or **in order**. A random rule can also say **Don't repeat an intro within** a number of hours. See [How often and no repeats](weights-and-cooldowns.md).

## Kids-safe

To begin with, kids-safe means G and PG for US movies; TV-Y, TV-Y7, TV-G and TV-PG for US TV; and U and PG in the UK. Change the list in Settings, Playback.

Titles with no rating, or rated *Not Rated* or *Unrated*, don't count unless you turn on **Treat unrated titles as kids-safe**. An unrated title could be a home video, or it could be a director's cut. It's better for a kids' rule to miss a cartoon than to play before the wrong film.

## Try it

**Try it**, below the list of rules, answers "what would happen for this title?". Type a title, genres, an age rating, a year, a library or who's watching, then press **Show what would play**:

> Matches 'Kids' because the movie is rated PG, which is kids-safe. It plays 1 of these 2 at random.

It also says why each rule above it didn't match ("the movie is Crime, not Horror"), and what the schedules would do when nothing matches. Trying never changes what plays next.

## Where rules work

| | Plex | Jellyfin | Emby |
|---|---|---|---|
| Rules | No | Yes, for every play | Yes, for every play |
| Needs | | The Prerolls Max plugin | The Prerolls Max plugin and Emby Premiere |

Plex picks its intro before it knows which movie is starting, and it has one intro list for everyone, so rules can't work there. On Plex, the closest thing is a playlist step with "Only play this in some cases". It follows the movie already playing, so it affects the next play, not this one. Playlist steps can use the same conditions (genre, rating, kids-safe, year, library, person, first episode).
