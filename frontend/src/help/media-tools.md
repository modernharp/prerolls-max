# Even loudness, TV-friendly versions and combined videos

Tick videos on [Intro Videos](app:/videos) and a bar appears at the bottom with four tools: **Check loudness**, **Even out loudness**, **Make TV-friendly version** and **Combine into one**. They run in the background with a progress bar, so you can close the window and come back later.

**Your originals are never changed in place.** New files only appear once they're complete. If you choose to replace a file, the original goes to Trash first, and you can get it back for 30 days.

## Loudness

Intros come from everywhere, and some are much louder than the movie after them. **Check loudness** measures each intro the way TV broadcasters do. Each video then shows **Loudness OK**, **Too loud**, **Too quiet** or **Clips** (its loudest moments distort). Hold the pointer on the label, or tap it, to see the measured level.

**Even out loudness** measures each intro, then turns it up or down in one steady step. The intro keeps its punch instead of getting squashed, and the picture isn't touched.

### What the numbers mean

Loudness is measured in **LUFS**. Lower numbers are quieter: -23 is quieter than -16. A difference of 1 **LU** is a small step; 2 LU is about what you'd notice. An intro more than 2 LU away from your target is marked.

The target is **-23 LUFS**. That's the standard level for TV, and close to how streaming services deliver films and series (-24 to -27), so an intro at -23 sits right next to the movie. You'll see -16 LUFS recommended "for streaming", but that's the level for phones and podcasts. An intro at -16 would be about 7 LU louder than the film after it.

You can change the target in [Settings, Playback](app:/settings#playback), anywhere from -31 to -10.

### New version or replace

**Make a new version** is the default. A new intro called "Name (Loudness -23 LUFS)" takes the original's place in its collections. The original stays in your library, switched off, with the new version shown under it. You can switch back any time.

**Replace the file** saves space: it swaps the file itself and puts the original in Trash. Only an admin can do this.

## TV-friendly versions

A 4K or HDR intro before an ordinary HD movie can make a TV flick into HDR mode and back, and makes the media server convert the intro while it plays, which can stutter. **Make TV-friendly version** makes a copy that every app plays as it is: 1080p (or 720p, or 4K if you pick it), normal colour range (not HDR), H.264 video and stereo AAC sound. HDR colours are converted so they still look right. Intros that already match are skipped.

Like loudness, the new version takes the original's place in its collections unless you untick that. A playlist step that names an intro directly keeps playing the original, so pick the new version in that step if you want it there.

## Combine into one video

Some apps play only the **first** intro in a list. The official Jellyfin app on Roku is the best-known one. **Combine into one** joins several intros, or a whole [playlist](help:playlists), into one video with the same size and loudness throughout, and adds it to your library. Select at least two videos first, or pick a playlist.

Random steps in a playlist are picked once, when the video is made. Make it again for a new mix. Steps with "Only play this in some cases" can't know the movie ahead of time, so their "Otherwise" choice is used.

When it's done, put the combined video in the collection that your Roku viewers' schedule plays.

## Where these work

The results are ordinary video files, so they work the same on Plex, Jellyfin and Emby. The combined video matters most for Roku.

These tools need FFmpeg. The Docker image includes it. On other installs, [System and updates](app:/settings/advanced/system) shows whether it's installed.
