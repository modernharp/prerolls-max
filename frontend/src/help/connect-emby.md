# Connecting Emby

Emby plays intros through its **Cinema Intros** feature, which needs **Emby Premiere**. The Prerolls Max plugin tells Emby which intro to play each time something starts.

## 1. Make an API key

1. Open Emby in your browser and sign in as an administrator.
2. Go to **Settings**, then **API Keys**, and press **New API Key**.
3. Call it "Prerolls Max", then copy the key.

## 2. Connect

On [Media Servers](app:/servers), press **Connect Emby**. Under **Emby address**, type the address you use to open Emby, like `http://192.168.1.10:8096`. Paste the key under **API key**.

If Prerolls Max runs in Docker, use the computer's network address, not `localhost`.

## 3. Install the plugin

After you connect, the Emby card on [Media Servers](app:/servers) shows four steps. Each one turns green when it's done.

1. Press **Download the plugin for Emby**. You get one file, `PrerollsMax.Emby.dll`.
2. Copy it into Emby's `plugins` folder. Don't put it in a folder of its own.
   - Docker: `/config/plugins` (inside the folder you mapped to `/config`)
   - Linux: `/var/lib/emby/plugins`
   - Windows: `%APPDATA%\Emby-Server\programdata\plugins`

   Restart Emby, then press **I've restarted Emby**.
3. Press **Set up the plugin for me**. Prerolls Max fills in the plugin's settings, including a key of its own. If Emby runs in Docker or on another computer, first change the address to this computer's network address. (Emby's Docker image can't use `host.docker.internal`, so use the address with numbers, like `192.168.1.10`.)
4. Play any movie in Emby, then press **Check now**.

A brand-new intro can take up to a minute to start playing on Emby. Emby has to register it first; the plugin asks Emby to do that as soon as the download finishes. Until then, the movie plays without that intro (or with the previous copy, if the intro was only renamed or changed).

To fill in the plugin's page yourself instead (Emby: **Settings**, **Plugins**, **Prerolls Max Intros**), make a key in Prerolls Max under **Settings, Advanced, API keys** and enter it with the address Emby uses to reach Prerolls Max. In Emby's own pages, intros are listed under their names from Prerolls Max.

## 4. Turn on Cinema Intros

Emby only plays intros when all three of these are true:

- You have **Emby Premiere**.
- In Emby's server settings, **Cinema Intros** is on. Turn on intros for **episodes** too if you want them before TV shows.
- In **each** Emby app, **Settings**, then **Playback**, has **Cinema Intros** on. The Roku app has it off to begin with.

## Which apps play intros

| App | Plays intros? |
|---|---|
| Web browser, phone and tablet apps | Yes, with Cinema Intros on in the app |
| Android TV, Fire TV | Movies only |
| Roku | Turn on Cinema Intros in the app. It can be unreliable. |
| Samsung TV | Often not. Some show "No compatible streams"; an H.264 MP4 intro sometimes helps. |
| Infuse | No |

See [Which apps play intros](help:devices) for every server.

## Moving from NeXroll

If you used NeXroll's Emby plugin, remove it once the Prerolls Max plugin shows **Working**, so the two don't both add intros.
