# What Played

The **What Played** page shows which intros played, before which movie or episode, for whom and on which app. Pick a time (the last 7, 30 or 90 days, or the last year) and a server at the top.

- **Recent plays:** the newest first.
- **Played most** and **Played least:** over the time you picked.
- **Never played:** intros with no play recorded. Check they're in a collection that plays, or give them a higher **How often**.
- **By server**, **By person** and **By app:** the plays split up.

History older than **90 days** is forgotten on its own. Change that, or turn history off, in Settings, Playback. Without history, What Played, the [missed-intro check](missed-intros.md) and "don't repeat within" can't work. **Clear history** removes everything at once; only an admin can do it.

Backups leave play history out unless you turn on **Include play history in backups** in Settings, because it says who watched what. Rules, the never-play list, watch folders, How often and "don't repeat within" are always in backups.

## How plays are counted

| | Plex | Jellyfin | Emby |
|---|---|---|---|
| A play counts | When Plex shows the intro playing. Prerolls Max looks every 15 seconds, so an intro shorter than that can be missed. | When Jellyfin asks the plugin for intros as a movie or episode starts | When Emby asks the plugin for intros as a movie or episode starts |
| Who and which app | Yes | Yes | Yes |

On Jellyfin and Emby a play counts when the server asks for intros. An app that asks and then doesn't play them still counts, but that's rare. The [missed-intro check](missed-intros.md) finds apps that don't ask at all.
