# Changelog

Prerolls Max is a fork of [NeXroll](https://github.com/JFLXCLOUD/NeXroll) 2.4.0.

## [1.0.0] - 2026-11-09

The first Prerolls Max release. Compared with NeXroll 2.4.0:

### New

- **Moving from NeXroll.** Prerolls Max replaces NeXroll, and says so in Settings, the first-run guide and Help. **Settings > Moving from NeXroll** brings a NeXroll setup over from its data folder, a NeXroll backup (.json or .zip) or a running NeXroll, shows what it found first, then replaces or merges; videos it can't see are found again by folder. Home and Media Servers warn while NeXroll still runs: its plugin on a Jellyfin or Emby server, Plex's intro list changed by something else, or NeXroll on port 9393. If the port is taken at start, Prerolls Max says so in one line. To keep both on purpose, pick another port and which app manages each server.
- **A new, simpler interface.** Seven sections: Home, Intro Videos, When They Play, Media Servers, What Played, Help and Settings. Pages most people never need (playlists, movie trailers, the video maker, folder mapping, logs) sit behind **Show advanced options**.
- **Help built in, and it works offline.** Step-by-step guides, a glossary, a "my intro isn't playing" troubleshooter and a Report a problem page.
- **A setup checklist on Home:** connect a server, add videos, choose when they play, play a test.
- **Sign in with Plex.** No more copying tokens by hand.
- **Prerolls Max plugins for Jellyfin (10.11 and 12) and Emby,** with four guided steps on Media Servers, including **Set up the plugin for me**.
- **Badges for what each server can do,** next to each option: Works, Needs plugin, Next play only, or Not possible.
- **Community intros from two libraries:** Prerolls.me first, Prerolls.uk below it. Pick from both at once. Every video is credited to its creator. YouTube and Vimeo videos are watch-only links.
- **Rules (Jellyfin and Emby):** different intros by genre, age rating, kids-safe rating, decade or year, library, or who's watching. **Try it** shows which rule would match a title, and why.
- **A never-play list,** and a `no-intro` tag you can add in Jellyfin or Emby.
- **Intros only before the first episode of a binge** (Jellyfin and Emby).
- **How often** (1 to 10) for each intro, and **Don't repeat an intro within** a number of hours for collections and rules.
- **Watch folders:** new videos dropped in a folder are added to a collection on their own.
- **What Played:** which intros played, before what, for whom and on which app.
- **Missed-intro check:** Home warns you when an app started a movie without its intro, and says how to fix that app.
- **Media tools:** check and even out loudness, make TV-friendly 1080p versions, and combine several intros, or a whole playlist, into one video for Roku.
- **More ways to schedule:** holidays that move (like Easter), certain dates every year, certain days of the month, and a month calendar that shows overlaps.
- **Default intros can be a playlist.**
- **A new playlist builder** with steps that can depend on the movie, and **What would play** to test it.
- **An admin account on first run,** more people with their own sign-in, and API keys that can be read-only or expire.

### Better

- **Plain error messages.** Every error says what happened and what to do next, with a short code you can search for in the logs. No more raw server errors.
- **Forms check what you type as you go,** and show every problem at once.
- **Plex's intro list is written once, plainly and safely,** even when several people are watching.
- **The Jellyfin and Emby plugins never hold up playback.** They wait at most 3 seconds, download intros in the background, and keep playing the last list if Prerolls Max is down.
- **Uploads stream straight to disk,** with a 500 MB limit per file and a check that each file is a video.
- **The Docker image runs as an ordinary user** (PUID and PGID, 1000 unless you set them), not as root.
- **Backups include rules, the never-play list, watch folders and the new settings.** Play history is left out unless you ask for it.
- **Made and converted videos only appear once they're complete,** and originals are never changed in place.
- **Movie trailers:** more than one Radarr (for example a 4K one), plain Radarr and Sonarr errors, and help when YouTube blocks downloads.

### Fixed

- Schedules starting at the wrong time. The schedule clock is now worked out in one tested place, and the app warns you when its time zone doesn't match yours.
- Jellyfin freezing at the start of a movie while the plugin downloaded intros one by one.
- Emby skipping new intros until someone ran a refresh by hand.
- The Emby plugin couldn't be rebuilt from source. All three plugins now build in CI.
- Stopping the Docker container no longer waits out a 10-second timeout.

### Removed

- **NeXroll's old interface,** its wiki copy and its Plex token helper scripts. The new interface replaces them.
- **The Apple Trailers lookup,** which Apple retired.
- **The old Prerolls.uk folder crawler,** replaced by the new Community libraries.
- **API keys in web addresses** (`?api_key=`). Send keys in the `X-Api-Key` header instead.
- **Sign-in off by default.** New installs make an admin account first. Existing installs keep their choice, with a banner when sign-in is off.
- **Update checks until a release source is set** with `PMAX_UPDATE_REPO`. The app says so instead of failing.

### Moving from NeXroll

- Stop NeXroll first. Both use port 9393, and both would change Plex's intro list.
- **Your NeXroll database is picked up on first start.** If `prerollsmax.db` doesn't exist yet and `nexroll.db` is in the same data folder, Prerolls Max copies it. The NeXroll file isn't changed.
- **NeXroll backups can be restored** under Settings, Backup and restore.
- **Settings that start with `NEXROLL_` still work.** The new names start with `PMAX_`, and win when both are set.
- **Playlists:** `.nexseq` files from NeXroll can be imported.
- **Jellyfin and Emby:** install the Prerolls Max plugin, then remove NeXroll's once the new one shows Working.
- **New names:** categories are now collections, filler is default intros, sequences are playlists, NeX-Up is movie trailers, and the generator is the video maker.
