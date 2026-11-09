# Missed-intro check

When an intro doesn't play, the app on your TV or phone is usually the reason, not the server. Prerolls Max watches what your media servers play. When a movie or episode starts **without** its intro, [Home](app:/) tells you which app it was, why it happened, and what to change. It looks at the last 7 days.

Some warnings you might see:

> **3 movie playbacks on Plex for Apple TV started without an intro.**
> Plex had intros set, but this app went straight to the movie. In that app's settings, set Cinema Trailers to 1 before movies, and turn Plex's own trailer sources off in Plex's server settings, so only your intro plays.

> **1 playback on Swiftfin iOS started without asking for intros.**
> Swiftfin doesn't play intros. Use the Jellyfin web app or Jellyfin Media Player on that device.

> **2 Jellyfin playbacks got no intros.**
> Prerolls Max had nothing set to play when these started. Turn on a schedule, set default intros, or add a rule that matches.

It also warns you when Jellyfin or Emby is connected but the Prerolls Max plugin hasn't asked for an intro all week. That usually means the plugin isn't installed, or can't reach Prerolls Max.

## Fixes by app

| App | What to do |
|---|---|
| Plex's 2026 apps for iPhone, iPad, Apple TV, Android TV and Fire TV | In the app's settings, set Cinema Trailers to "1 before movie". |
| Plex Web and the Plex desktop app | In Settings, Experience, set Cinema Trailers to at least 1. |
| Infuse, DLNA players, downloaded movies | These never play intros. |
| Swiftfin, Jellyfin MPV Shim | These don't play intros. Use the Jellyfin web app or Jellyfin Media Player. |
| Jellyfin or Emby on Roku | Turn on Cinema Mode (Jellyfin) or Cinema Intros (Emby) in the app. The Jellyfin Roku app plays only the first intro, so use a [combined video](help:media-tools). |
| Emby, any app | Turn on Cinema Intros in the app (Settings, Playback). Emby needs Premiere for this. |
| Samsung TV apps (Jellyfin, Emby) | These don't play intros. |

## What it notices

| | Plex | Jellyfin and Emby |
|---|---|---|
| Warns about | A movie watched from the start with no intro before it on the same player, or Plex's intro list being empty | A movie or episode started from the beginning that didn't ask the plugin for intros, or a time when Prerolls Max had nothing to play |
| How often it looks | Every 15 seconds | Every 30 seconds |
| Leaves out | Movies that were resumed or joined part way | Resumed movies, and episodes that played on their own after the last one |

To turn the check off, open [Settings, Playback](app:/settings#playback) and switch off **Spot intros that didn't play**.
