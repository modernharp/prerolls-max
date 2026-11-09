# TV shows, kids and the never-play list

## Never play an intro before a title

Some things should start straight away: a concert film, home videos, a short you watch every week. Put them on the never-play list on [When They Play, Never play](app:/schedules/never-play). Under **Add to the list**, choose how to find it:

- **Title:** the title as your media server shows it. A show's title covers all its episodes.
- **Item id:** the id in the item's web address in Jellyfin or Emby. A show's id covers all its episodes too.
- **Tag:** any tag you use in Jellyfin or Emby, like *Concert*. Everything with that tag is skipped.

You can add a note to remember why it's there.

The never-play list is checked before any rule or schedule.

### The no-intro tag

For most titles you don't need the list at all. **In Jellyfin or Emby, add the tag `no-intro` (or `nointro`) to a movie or show**, and it never gets an intro. This is on from the start. To change the tags, or turn this off, open [Settings, Playback](app:/settings#playback).

## Only before the first episode of a binge

An intro before every episode gets old fast. A [rule](help:rules) or a playlist step can play intros only before the **first episode someone starts after a break**.

The break is 4 hours unless you change **Break between episodes (hours)** in [Settings, Playback](app:/settings#playback). If the same person started an episode of the same show less than 4 hours ago, this one isn't the first. When you change the break, Prerolls Max also updates the plugin on each connected Jellyfin and Emby server, so they agree.

Jellyfin and Emby never play intros between episodes that play on their own, one after another. Intros only come before an episode someone picked.

## Different intros for each person

A rule can match **who's watching**, by their Jellyfin or Emby user name. Give the kids' accounts their own rule, or keep the cinema-style intros for the grown-ups.

## Kids-safe intros

Make a rule with **Kids-safe titles** turned on, set it to play your kids' collection, and move it to the top of the list. Titles rated G, PG, TV-Y, TV-Y7, TV-G, TV-PG or U match. Unrated titles don't, unless you say so in Settings. See [Rules](help:rules) for how to change the list.

## Where these work

| | Plex | Jellyfin | Emby |
|---|---|---|---|
| First episode of a binge | No. Plex never plays intros before episodes. | Yes | Yes. The Android TV and Fire TV app plays intros before movies only. |
| A different intro for each person | Only roughly, for the next play, while one person is watching | Yes | Yes |
| Kids-safe | Only in playlist steps, for the next play | Yes | Yes |
| Never-play list and `no-intro` tag | No | Yes | Yes |

Plex can't skip intros for one title, or pick one per person. The nearest thing is turning **Cinema Trailers** off for a whole library in Plex, in that library's settings. People do this for a *Concerts* or *Kids* library.
