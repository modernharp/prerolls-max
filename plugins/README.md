# Prerolls Max Intros (Jellyfin and Emby plugins)

Jellyfin and Emby have no setting of their own for intro videos. This small plugin asks Prerolls Max which intros to play each time a movie or episode starts, and hands the videos to the server. Plex doesn't need a plugin: Prerolls Max fills in Plex's own intro setting.

| Server | Download |
|---|---|
| Jellyfin 10.11 | `PrerollsMax.Jellyfin-10.11-<version>.zip` |
| Jellyfin 12 | `PrerollsMax.Jellyfin-12-<version>.zip` |
| Emby 4.9 and later | `PrerollsMax.Emby.dll` (also in `PrerollsMax.Emby-<version>.zip`) |

## Installing

The easy way is in the app: open **Media Servers**, connect Jellyfin or Emby, and follow the four plugin steps on its card. Prerolls Max picks the right download for your server, and **Set up the plugin for me** fills in the plugin's settings.

To install by hand:

- **Jellyfin:** unzip the package for your version (12 or 10.11) into a new folder called `PrerollsMax` inside Jellyfin's `plugins` folder (`/config/plugins` in Docker), then restart Jellyfin.
- **Emby:** copy `PrerollsMax.Emby.dll` straight into Emby's `plugins` folder (`/config/plugins` in Docker), not into a folder of its own, then restart Emby. Emby plays intros only with Emby Premiere, and with **Cinema Intros** on in the server's settings and in each app (Settings, Playback).

Then open the plugin's page (Dashboard, Plugins, Prerolls Max Intros). Enter the address the media server uses to reach Prerolls Max, and an API key from Prerolls Max (Settings, Advanced, API keys). Press **Test connection**.

In Docker, `localhost` inside the media server's container means that container, not your computer. Use your computer's network address, like `http://192.168.1.10:9393`. Emby's Docker image ignores `host.docker.internal`, so use the numbers there.

The plugins are named **Prerolls Max Intros** and have their own ids, so they can sit next to NeXroll's plugin while you move over. Once the new one works, remove the NeXroll plugin so intros aren't added twice.

## What the plugin does for you

- **It never holds up playback.** It waits at most 3 seconds for Prerolls Max (you can change this). Intros that aren't downloaded yet keep downloading in the background and play from the next movie on.
- **It keeps working if Prerolls Max is down.** It plays the last list of intros Prerolls Max sent, which it keeps on disk. A title that gets no intro on purpose (the never-play list, a `no-intro` tag) still gets none.
- **It tidies up after itself.** A scheduled task, "Download Prerolls Max intros", runs at startup and every 30 minutes. It downloads everything that could play and removes old versions, files unused for two weeks, and the oldest files beyond the size limit (2 GB unless you change it).
- **It knows the first episode of a binge.** An episode is first when the same person started no other episode of that show within the break set on the plugin page (4 hours unless you change it). Jellyfin also checks the person's play history; Emby uses what the plugin has seen since Emby started.

## For developers

| Folder | Server | .NET | Built against |
|---|---|---|---|
| `PrerollsMax.Jellyfin` (net9.0) | Jellyfin 10.11.x | 9 | `Jellyfin.Controller` 10.11.0 |
| `PrerollsMax.Jellyfin` (net10.0) | Jellyfin 12.x | 10 | `Jellyfin.Controller` 12.0.0 |
| `PrerollsMax.Emby` | Emby 4.9 and later | 8 | `MediaBrowser.Server.Core` 4.9.1.90 (nuget.org) |
| `Shared` | both | | compiled into each plugin |

Plugin ids: Jellyfin `c0a6ea94-7795-4b61-b964-4ddfb93ec8b0`, Emby `2fea54cd-3c4a-4307-ab53-5e25a07a24ec`. Each Jellyfin build targets the first release of its series. Jellyfin refuses a plugin built against a newer server than itself, so a 12.0.0 build loads on every 12.x.

### Building

Tests for the shared code (cache names, moving 2.0 files, tidying up): `dotnet test PrerollsMax.Shared.Tests`.

You need the .NET 10 SDK (it builds the .NET 8 and 9 targets too) and access to nuget.org. Nothing is copied out of a media server install and no DLLs are committed: Emby publishes its server libraries on NuGet (`MediaBrowser.Server.Core`), so the Emby plugin builds like the others.

```sh
./build.sh                                # packages land in ./out
DOTNET=/path/to/dotnet ./build.sh         # a dotnet that isn't on PATH
```

The version lives in one place, `Directory.Build.props` (`PrerollsMaxPluginVersion`). The assemblies, Jellyfin's `meta.json` and the `X-PrerollsMax-Plugin` header all take it from there. Bump it whenever plugin code changes. Builds are reproducible: the same sources give byte-identical zips.

CI: `.github/workflows/plugins.yml` builds and tests all three (called from `ci.yml` on every push and from `release.yml` for a release) and uploads the packages. The Docker image builds them in its `pluginbuild` stage and serves them from the Media Servers page (`/jellyfin/plugin/download?series=12|10.11`, `/emby/plugin/download`).

`jellyfin-repo/update_repository.py` publishes a release's Jellyfin packages into the plugin catalog. `release.yml` runs it and puts the catalogs on the `gh-pages` branch, so Jellyfin users add `https://<owner>.github.io/<repo>/jellyfin/manifest.json` (Jellyfin 12) or `.../jellyfin/manifest-10.11.json` (Jellyfin 10.11) under Dashboard, Plugins, Repositories.

### How they talk to Prerolls Max

Protocol v2 (`docs/dev/CONTRACTS.md` section 7): on each play the plugin calls `GET /plugin/v2/intros` with everything the server knows (type, genres, tags, age rating, user, library, series, season and episode, first episode of a sitting, audio and video, file path, TMDB id), so Prerolls Max never calls back into the media server while the player waits. If Prerolls Max answers 404 (an older version), the plugin uses v1 `/plugin/intros` for ten minutes.

- **Fallback list:** the last non-empty list is kept on disk and survives restarts. An answer marked `intentional_empty` plays nothing and leaves that list as it was.
- **Downloads** go to the plugin's data folder (`intro_cache`): one at a time per file, two at once overall, each into its own temporary name, renamed into place only when complete.
- **Names:** each intro has a folder of its own and its real name as the file name, for example `intro_cache/1a2b3c4d5e6f-0a1b2c3d/Pumpkin Intro.mp4`, because Emby (and some Jellyfin pages) show intros under their file name. The folder is a short id for the intro and its version, so two intros with the same name never collide and a regenerated video gets a new folder and is registered afresh. Names are made safe for Windows, macOS and Linux (no `<>:"/\|?*`, no reserved names like `CON`, at most 80 characters) and a name ending in a word like "Trailer" or "Sample" gets " (intro)" added, so the server doesn't take it for a movie extra. Jellyfin and Emby are also given the exact name from Prerolls Max for the item. Renaming an intro in Prerolls Max renames the file; nothing is downloaded again.
- **Moving from 2.0:** version 2.0 kept files as `intro_cache/<hash>-<hash>.mp4`, which Emby listed as "e8d13c0f…". At startup the intros in the last known good list move to their named files (so they play even if Prerolls Max is down), the rest when they're next needed, and the old files and their library items are removed. On Emby the old file stays (and keeps playing) until Emby has registered the new one, then goes.
- **Links** in v2 answers are relative to the address configured in the plugin (so a reverse-proxy path prefix works) and expire after an hour. The API key goes in the `X-Api-Key` header, never in the address.
- **Jellyfin** only plays intros that are library items, so each file is registered (one registration per file at a time). Removed files are removed from Jellyfin too.
- **Emby** only plays intros it registered through "Refresh Custom Intros". The plugin lists its downloads there and runs that task itself whenever its downloads change. It sends Emby's own numeric item ids. Older copies of an intro (a previous name or version) are kept, and play, until Emby has registered the new file; the plugin looks again 90 seconds after asking Emby to register, then removes them and their items.
- **First episode:** asking twice about the same episode gives the same answer.

### Checked against real servers

Smoke-tested in Docker (November 2026) against `jellyfin/jellyfin:10.11.0`, `jellyfin/jellyfin:latest` (12.4.0) and `emby/embyserver:latest` (4.10.2.0), with a tiny movie library and Prerolls Max running from source:

1. Start the server with the plugin in its plugins folder, finish the setup wizard through the API (`/Startup/Configuration`, `/Startup/User`, `/Startup/Complete`), and add a library.
2. Configure the plugin (`POST /Plugins/<id>/Configuration`) and call the Test endpoint (`POST /PrerollsMax/Test`).
3. Ask for intros: Jellyfin `GET /Items/<id>/Intros?userId=<user>`, Emby `GET /Users/<user>/Items/<id>/Intros`.
4. Point the plugin at an address that accepts connections and never answers: the call returns after the timeout with the last list.
5. Names and moving from 2.0 (Jellyfin 12.4.0 and Emby 4.10.2.0, plugin 2.1.0.0): run 2.0 until Emby lists its intros as `aed8ea18…`, swap in 2.1 and restart. Straight away both servers return the intros, named "Pumpkin: Night Intro?" (file `Pumpkin Night Intro.mp4`) and "Snow Globe"; Emby's old items are removed after it registers the new files, and Jellyfin's database has no items left at the old paths. Renaming an intro in Prerolls Max ("Snow Globe Party", "Coming Soon Trailer") showed the new name on both at the next play, with no playback missing its intro.
