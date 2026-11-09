# Questions people ask

## Does it cost anything?

No. Prerolls Max is free and open source.

## Do I need Plex Pass?

No. Plex plays your own intro videos without Plex Pass. Plex Pass only matters if you want Plex's own trailers for new releases.

## Do I need Emby Premiere?

Yes. Emby plays intros through its Cinema Intros feature, and that needs Premiere.

## Why does everyone get the same intro on Plex?

Plex has one intro list for the whole server, not one per person. Prerolls Max changes that list when a schedule starts or ends. If two people start a movie at the same time, they get intros from the same list.

## Can intros play before TV episodes?

On Jellyfin and Emby, yes, with the Prerolls Max plugin. They play before the episode you pick, not between episodes that play on their own. On Plex, no: Plex plays intros before movies only.

## Can I play a different intro for each genre, age rating or person?

On Jellyfin and Emby, yes, using [rules](help:rules). The right intro is picked for each play. On Plex, no: Plex picks its intro before it knows which movie is starting, and it has one list for everyone.

## Why didn't the intro play when I carried on watching?

No media server plays an intro when you resume a movie. Start it from the beginning.

## Why does my Roku play only the first intro?

The official Jellyfin app on Roku plays only the first intro in the list. [Combine your intros into one video](help:media-tools) and it plays them all.

## Which video format should I use?

MP4 with H.264 video and AAC sound plays everywhere. Most intros are 10 to 30 seconds long. If an intro is 4K or HDR and your movies aren't, make a [TV-friendly version](help:media-tools).

## Where are my intro videos stored?

In Prerolls Max's intro folder. With Docker, that's the folder you mounted at `/data/prerolls`. Turn on Advanced in Settings, then open **Storage** to see the exact path.

## I deleted a video by mistake

Press **Undo** on the message that appears straight after. Later, turn on **Show advanced options** in [Settings](app:/settings#advanced), open **Trash**, and restore it. Deleted videos stay in Trash for 30 days.

## I forgot my password

On the sign-in page, press **Forgot your password?**. For safety, you can only reset it on the computer that runs Prerolls Max.

## Is it safe to turn sign-in off?

Only on a network you trust completely. With sign-in off, anyone who can reach Prerolls Max can change or delete your intros.

## I used NeXroll. Can I keep my setup?

Yes. Your schedules, collections and settings come across, and the old words have new names: categories are now collections, filler is default intros, sequences are playlists, and NeX-Up is movie trailers. See [Moving from NeXroll](help:settings) in the Settings article.

## Something else is wrong

Try the [troubleshooter](app:/help/troubleshoot), or [report a problem](app:/help/report).
