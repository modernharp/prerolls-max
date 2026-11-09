# What played

[What Played](app:/played) shows which intros played, before which movie or episode, for whom and on which app. On a phone, open it from the link on Home.

At the top, pick a time (the last 7, 30 or 90 days, or the last year) and a server.

- **Recent plays** lists the newest first.
- **Played most** and **Played least** cover the time you picked.
- **Never played** lists intros with no play recorded. They're worth a look: maybe they're in a collection nothing plays, or they could use a higher **How often**.
- **By server**, **By person** and **By app** split the plays up.

## Keeping and clearing history

History older than **90 days** is forgotten on its own. To change that, or to turn history off, open [Settings, Playback](app:/settings#playback). Without history, What Played, the [missed-intro check](help:missed-intros) and "don't repeat within" can't work.

**Clear history** removes everything at once. Only an admin can do it. "Don't repeat within" uses this history, so after clearing it a recent intro may play again soon.

Backups leave play history out unless you turn on **Include play history in backups** in [Settings](app:/settings#backup).

## How plays are counted

| | Plex | Jellyfin | Emby |
|---|---|---|---|
| A play counts | When Plex shows the intro playing. Prerolls Max looks every 15 seconds, so an intro shorter than that can be missed. | When Jellyfin asks the plugin for intros as a movie or episode starts | When Emby asks the plugin for intros as a movie or episode starts |
| Who and which app | Yes | Yes | Yes |

On Jellyfin and Emby a play counts when the server asks for intros. An app that asks and then doesn't play them still counts, but that's rare. The [missed-intro check](help:missed-intros) finds apps that don't ask at all.
