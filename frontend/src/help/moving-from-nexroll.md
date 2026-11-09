# Moving from NeXroll

Prerolls Max started as a copy of NeXroll 2.4.0, and it **replaces** NeXroll. Use one or the other, not both.

Running both causes trouble. Plex has one intro list per server and both apps write to it, so they keep overwriting each other and you can't tell which intros will play. On Jellyfin and Emby each app has its own plugin, and with both plugins installed every movie gets two sets of intros. Both apps also use port 9393 unless you change it.

Your collections, intro videos, schedules and playlists can come with you, and so can your media servers, usually with their keys.

## Back up NeXroll first

In NeXroll, open **Settings > Backup & Restore** and press **Download Database Backup** and **Download System Backup**. The first is a small .json file with your settings; the second is a .zip with your videos too. Keep both until Prerolls Max works the way you want. Prerolls Max can import either one.

## Stop NeXroll

How you stop it depends on how you installed it.

- **Windows service:** press Windows+R, type `services.msc` and press Enter. Right-click **NeXroll Background Service** and choose **Stop**. Then double-click it and set **Startup type** to **Disabled**, or it starts again with Windows.
- **Windows tray app:** right-click the NeXroll icon next to the clock, choose **Stop Service**, then **Exit**. Remove NeXroll from **Settings > Apps > Startup** as well.
- **Docker:** run `docker stop nexroll`, then `docker update --restart=no nexroll` so it stays stopped. With Docker Compose, run `docker compose down` in NeXroll's folder. Keep its data volume, because Prerolls Max can read it.
- **Unraid:** on the **Docker** tab, click the NeXroll icon and choose **Stop**, then switch its **Autostart** off.

Leave uninstalling NeXroll until your import has worked.

## Remove the NeXroll plugin

Jellyfin and Emby keep running NeXroll's plugin until you remove it, and it adds intros of its own.

- **Jellyfin:** go to **Dashboard > Plugins**, open **NeXroll Intros**, press **Uninstall** and restart Jellyfin.
- **Emby:** in the server dashboard, open **Plugins**, pick **NeXroll Intros**, uninstall it and restart Emby.

Home tells you if a server still has it.

## Install Prerolls Max

Prerolls Max uses port 9393 by default, the same as NeXroll, so the address you're used to keeps working once NeXroll is stopped. For another port, set `PMAX_PORT`. In Docker, change the port mapping instead, like `9494:9393`.

If NeXroll still holds the port when Prerolls Max starts, Prerolls Max stops and says so: "Port 9393 is already in use, probably by NeXroll."

`NEXROLL_` environment variables keep working. Prerolls Max reads them as `PMAX_`.

## Bring your setup over

On its very first start, Prerolls Max copies NeXroll's database when it finds one in its own data folder (on Windows, also in NeXroll's). To bring it over later, or from somewhere else, open [Settings > Moving from NeXroll](app:/settings#nexroll). There are three ways in:

- **Found on this computer.** Prerolls Max looks in NeXroll's usual folders. In Docker, add NeXroll's old data volume to the Prerolls Max container (for example as `/nexroll`) and type that path. NeXroll's file is only read, never changed.
- **Upload a NeXroll backup.** Either file from NeXroll's **Settings > Backup & Restore**. The .zip brings the videos along.
- **From a running NeXroll.** Type its address. If NeXroll's sign-in is on, make a key in NeXroll under **Settings > API Keys** (read only is enough) and paste it in.

Each way shows what it found before anything changes: how many collections, videos and schedules there are, and whether Prerolls Max can see the video files. Then you pick:

- **Replace** swaps what's in Prerolls Max for NeXroll's setup. Use it on a fresh install.
- **Merge** adds what's missing. A collection with the same name is joined, and a video that's already here isn't added twice. A schedule or playlist whose name is taken comes in as "Name (2)", and the report lists each one.

NeXroll's user accounts and API keys stay behind. Prerolls Max has its own sign-in, and you make new keys for your scripts in Prerolls Max. Media server keys come along when NeXroll's data has them, unless you switch that off.

### When videos are missing

Say NeXroll kept your videos in `D:\Prerolls` and Prerolls Max runs in Docker. Prerolls Max can't see that folder, and the report tells you. Type where the videos are now, like `/media/prerolls`, and press **Find them**. Prerolls Max looks for each file in the same place under the new folder, then by its name. The missing videos stay in your library until then.

## Install the Prerolls Max plugin

On Jellyfin and Emby, install **Prerolls Max Intros** from the Media Servers page. It does the job NeXroll's plugin did, but asks Prerolls Max. See [Connecting Jellyfin](help:connect-jellyfin) or [Connecting Emby](help:connect-emby).

## Test it

On [Media Servers](app:/servers), press **Play a test** on each server. The server says what it would play before a movie. Then play a real movie. You should see one set of intros.

## Running both

Most people shouldn't. It's worth it if you want to try Prerolls Max on one server before moving the rest, or NeXroll looks after a server you don't want to touch yet.

It only works when each media server is managed by one app:

1. In Prerolls Max, choose **Keep NeXroll running too** in [Settings > Moving from NeXroll](app:/settings#nexroll).
2. Give Prerolls Max another port, like 9494, and restart it. In Docker, change the port mapping instead.
3. In the table, set each server to **Prerolls Max** or **NeXroll**. The switch on each server card does the same.
4. In NeXroll, disconnect the servers Prerolls Max now manages.

On a server left to NeXroll, Prerolls Max never writes Plex's intro list, and its plugin adds nothing. The risks: if both apps manage one Plex server they take turns writing its list, and if a Jellyfin or Emby server has both plugins and both apps manage it, intros play twice. Prerolls Max can't see what NeXroll does, so check Home now and then. It shows who manages what and warns you when something looks wrong.

When you're ready to move the rest, switch back to **Replace NeXroll**, stop NeXroll and remove its plugin.
