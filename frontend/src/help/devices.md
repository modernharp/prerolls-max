# Which apps play intros

Even with everything set up right, some apps skip intros. This list was checked in November 2026. If your app isn't listed, test in a web browser first: if the intro plays there, the app is the reason.

## Plex

| App | Plays intros? |
|---|---|
| Web browser (app.plex.tv), Plex desktop app | Yes |
| Roku, smart TVs | Usually |
| 2026 apps for Apple TV, iPhone, iPad, Android TV, Fire TV and Shield | Only after a change: in the app's settings, set **Cinema trailers to play before movies** to **1** |
| Casting, DLNA, Plexamp, downloads, Infuse | No |

Plex plays intros before movies only, and the same intro list is used for everyone.

## Jellyfin (with the Prerolls Max plugin)

| App | Plays intros? |
|---|---|
| Web browser, Jellyfin Media Player | Yes, movies and episodes |
| Android | Yes |
| Android TV | Movies only, from the start |
| Roku (official app) | Turn on **Cinema Mode**. Plays only the first intro, so [combine several into one](help:media-tools). |
| Kodi (Jellyfin add-ons) | Yes |
| Swiftfin, Infuse, Jellyfin MPV Shim | No |
| Samsung TV | No |

## Emby (needs Emby Premiere)

| App | Plays intros? |
|---|---|
| Web browser, phone and tablet apps | Yes, with **Cinema Intros** on in the app |
| Android TV, Fire TV | Movies only |
| Roku | Turn on **Cinema Intros** in the app. It can be unreliable. |
| Samsung TV | Often not. Some show "No compatible streams"; an H.264 MP4 intro sometimes helps. |
| Infuse | No |

## On every server

- Intros play only when you start from the beginning, never when you resume.
- No intro plays between episodes that play on their own, one after another.

Home warns you when it spots an app that skipped an intro. See [Missed-intro check](help:missed-intros). Not sure what applies to you? Try the [troubleshooter](app:/help/troubleshoot).
