# Connecting Jellyfin

Jellyfin needs two things:

- an **API key**, so Prerolls Max can talk to Jellyfin
- the **Prerolls Max plugin**, so Jellyfin asks Prerolls Max which intro to play each time something starts

## 1. Make an API key

1. Open Jellyfin in your browser and sign in as an administrator.
2. Go to **Dashboard**, then **API Keys**, and press **+**.
3. Call it "Prerolls Max", then copy the key.

## 2. Connect

On [Media Servers](app:/servers), press **Connect Jellyfin**. Under **Jellyfin address**, type the address you use to open Jellyfin, like `http://192.168.1.10:8096`. Paste the key under **API key**.

If Prerolls Max runs in Docker, use the computer's network address, not `localhost`.

## 3. Install the plugin

After you connect, the Jellyfin card on [Media Servers](app:/servers) shows four steps. Each one turns green when it's done.

1. Press **Download the plugin for Jellyfin**. Prerolls Max picks the right one for your Jellyfin version (10.11 or 12).
2. Unzip it into a new folder called `PrerollsMax` inside Jellyfin's `plugins` folder:
   - Docker: `/config/plugins` (inside the folder you mapped to `/config`)
   - Linux: `/var/lib/jellyfin/plugins`
   - Windows: `%LOCALAPPDATA%\jellyfin\plugins`

   Restart Jellyfin, then press **I've restarted Jellyfin**.
3. Press **Set up the plugin for me**. Prerolls Max fills in the plugin's settings, including a key of its own. If Jellyfin runs in Docker or on another computer, first change the address to this computer's network address instead of `localhost`.
4. Play any movie in Jellyfin, then press **Check now**.

To fill in the plugin's page yourself instead (Jellyfin: **Dashboard**, **Plugins**, **Prerolls Max Intros**), make a key in Prerolls Max under **Settings, Advanced, API keys** and enter it with the address Jellyfin uses to reach Prerolls Max.

The card shows **Working** once the plugin has asked for an intro.

## Which apps play intros

| App | Plays intros? |
|---|---|
| Web browser, Jellyfin Media Player, Android, Kodi | Yes |
| Android TV | Movies only, from the start |
| Roku (official app) | Turn on **Cinema Mode** in the app. It plays only the first intro, so [combine several into one](help:media-tools). |
| Swiftfin, Infuse, Jellyfin MPV Shim | No |

In the web app and the others that play intros, **Cinema Mode** is on to begin with, and each device has its own switch. If one device skips intros, check it's still on.

See [Which apps play intros](help:devices) for every server.

## Episodes

Intros can play before TV episodes, but only before the episode someone picks, not between episodes that play on their own. To play them only before the first episode of a binge, see [TV shows, kids and the never-play list](help:never-play).

## Moving from NeXroll

If you used NeXroll's Jellyfin plugin, remove it once the Prerolls Max plugin shows **Working**, so the two don't both add intros.
