# Playlists

A playlist is a set order of things to play before a movie, like a cinema pre-show: a welcome video, two trailers, then a "turn off your phone" clip. Playlists are under [Settings, Advanced, Playlists](app:/settings/advanced/playlists). Turn on **Show advanced options** in Settings first.

Most people don't need a playlist. A schedule that plays a collection, or a [rule](help:rules), covers most cases.

## Making one

1. Press **New playlist** and give it a name.
2. Use **Add a step** for each thing that should play. Steps play from top to bottom. Use the arrows to move a step up or down.
3. Press **Save playlist**.

A step can play:

- some random videos from a collection (a different pick every time)
- videos you choose, in the order you add them
- videos from a collection, in order
- [movie trailers](help:movie-trailers) for upcoming movies, optionally only some age ratings
- trailers for movies you already have
- the coming soon video, which lists what's coming
- a short pause of black between videos

## Steps that only play sometimes

Turn on **Only play this in some cases** on a step to give it conditions under **Only if**. For example, a horror intro only when the genre is Horror, or a "lights down" video only after 8 pm. Conditions can check the genre, age rating, time of day, whether it's a movie or a TV episode, who's watching, the library, tags, the file name and the sound format. Choose whether **all** of them must be true or **any** of them.

**Otherwise** says what plays in that spot when the conditions aren't met. Leave it on **Play nothing in this spot** to skip it.

Plex picks its intros before it knows which movie is starting, so conditions about the movie can't be checked there. On Plex, those steps play their Otherwise choice instead. Time-of-day conditions work everywhere. Jellyfin and Emby check every condition before each movie, through the Prerolls Max plugin. The badges under the conditions show this for your servers.

## Checking what would play

**What would play**, at the bottom of a playlist, pretends something is starting now. Pick the server, a movie or a TV episode, and its genres, then press **Show what would play**. Each step says whether it plays, plays its Otherwise choice, or is skipped.

## Using a playlist

A playlist does nothing until something uses it:

- **In a schedule:** on [When They Play](app:/schedules), make a schedule and choose **A playlist** under **Play from**.
- **As your default intros,** at the bottom of When They Play.

When you change a playlist, schedules that use it change too. If you delete a playlist, those schedules keep playing the last version of it.

## Playlists on Roku

The official Jellyfin app on Roku plays only the first intro. To play a whole playlist there, [combine it into one video](help:media-tools).

## Sharing playlists

**Export** saves a playlist as a `.nexseq` file. **Import a .nexseq file** reads one, including files made in NeXroll. Prerolls Max matches the collections and videos it names with yours, by name. Anything it can't find is listed, and you can fix those steps after importing.
