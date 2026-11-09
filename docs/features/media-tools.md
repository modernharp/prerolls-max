# Even loudness, TV-friendly versions and combined videos

Tick videos on **Intro Videos** and a bar appears at the bottom with four tools: **Check loudness**, **Even out loudness**, **Make TV-friendly version** and **Combine into one**. They run in the background with a progress bar, so you can close the window and come back later. They need FFmpeg, which the Docker image includes.

**Your originals are never changed in place.** New files only appear once they're complete. If you choose to replace a file, the original goes to Trash first (Settings, Advanced, Trash), and you can get it back for 30 days.

## Loudness

Intros come from everywhere, and some are much louder than the movie after them.

**Check loudness** measures each intro the way TV broadcasters do (the EBU R128 standard). Each video then shows **Loudness OK**, **Too loud**, **Too quiet** or **Clips** (its loudest moments distort). An intro more than 2 LU from your target is marked. 2 LU is about the difference you'd notice.

**Even out loudness** measures each intro, then turns it up or down in one steady step. The intro keeps its punch instead of getting squashed, and the picture isn't touched.

### Why -23 LUFS

Loudness is measured in LUFS; lower numbers are quieter. The target is **-23 LUFS**, the standard level for TV and close to how streaming services deliver films and series (-24 to -27). An intro at -23 sits right next to the movie.

You'll see -16 LUFS recommended "for streaming", but that's the level for phones and podcasts. An intro at -16 would be about 7 LU louder than the film after it. You can change the target in Settings, Playback, from -31 to -10.

### New version or replace

- **Make a new version** (the default): a new intro called "Name (Loudness -23 LUFS)" takes the original's place in its collections. The original stays in your library, switched off, so you can switch back.
- **Replace the file:** the file itself is replaced, and the original goes to Trash. Only an admin can do this.

## TV-friendly versions

A 4K HDR intro before an ordinary HD movie can make a TV flick into HDR mode and back, and makes the media server convert the intro while it plays. **Make TV-friendly version** makes a copy every app plays as it is:

- 1080p (or 720p, or 4K if you pick it), normal colour range (not HDR)
- H.264 video and stereo AAC sound at 48 kHz

HDR colours are converted so they still look right. Intros that already match are skipped. Like loudness, the new version takes the original's place in its collections unless you untick that.

A playlist step that names an intro directly keeps playing the original, so pick the new version in that step if you want it there.

## Combine into one video

Some apps play only the **first** intro in a list. The official Jellyfin app on Roku is the best-known one. **Combine into one** joins several intros, or a whole playlist, into one video with the same size and loudness throughout, and adds it to your library.

Random steps in a playlist are picked once, when the video is made. Make it again for a new mix. Steps with "Only play this in some cases" can't know the movie ahead of time, so their "Otherwise" choice is used.

## Where these work

The results are ordinary video files, so they work everywhere.

| | Plex | Jellyfin | Emby |
|---|---|---|---|
| Even loudness | Yes | Yes | Yes |
| TV-friendly versions | Yes | Yes | Yes |
| Combined video | Yes | Yes (needed for the Roku app) | Yes |
