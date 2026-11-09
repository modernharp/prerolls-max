# My intro isn't playing

The [troubleshooter](app:/help/troubleshoot) asks which server and app you use and checks your setup as it goes. This page lists the same problems, most common first. Each one says what you see, why it usually happens, and what to do.

Start with one test: play a movie from the beginning **in a web browser**. If the intro plays there, your setup works and the app on your TV or phone is the problem. If it doesn't play in the browser either, go to **It doesn't play anywhere** further down.

## It plays in the browser but not on my TV or phone

**Why:** some apps skip intros, or need a setting changed first.

**What to do:**

- **Plex on Apple TV, iPhone, iPad, Android TV or Fire TV (the 2026 apps):** these skip intros as they come. In the app's settings, set **Cinema trailers to play before movies** to **1**. Plex says it's working on a fix.
- **Plex by casting, DLNA, Plexamp, downloads or Infuse:** these never play intros. Nothing can change that.
- **Jellyfin on Swiftfin, Infuse or Jellyfin MPV Shim:** these don't play intros at all. Use the Jellyfin web app or Jellyfin Media Player on that device instead.
- **Jellyfin on Roku (the official app):** turn on **Cinema Mode** in the app's settings. It plays only the first intro, so if you want several, [combine them into one video](help:media-tools).
- **Emby, any app:** open the app's **Settings**, then **Playback**, and turn on **Cinema Intros**. Each app has its own switch. The Roku app has it off to begin with.
- **Emby or Jellyfin on a Samsung TV:** the Samsung apps often don't play intros. Emby sometimes shows "No compatible streams"; an H.264 MP4 intro sometimes fixes that.

[Which apps play intros](help:devices) has the full list. Home also warns you when it spots a movie that started without its intro. See [Missed-intro check](help:missed-intros).

## It didn't play when I carried on watching

**Why:** no media server plays an intro when you resume a movie or skip ahead. This isn't a fault.

**What to do:** start the movie from the beginning. Most apps offer this next to **Resume**.

## It plays before movies but not TV episodes

**Why:** it depends on the server.

- **Plex** plays intros before movies only. It can't play them before episodes.
- **Jellyfin** plays them before an episode you pick, but never between episodes that play on their own one after another. The Android TV app plays them before movies only.
- **Emby** needs intros for episodes turned on in the server's **Cinema Intros** settings. The Android TV and Fire TV app plays them before movies only.

**What to do:** on Jellyfin or Emby, check that a schedule, rule or default intros is set for episodes. To play intros only before the first episode of a binge, see [TV shows, kids and the never-play list](help:never-play).

## It doesn't play anywhere

### Nothing is set to play right now

**Why:** no schedule is on and default intros are off, so there's nothing to play.

**What to do:** look at **What plays before movies** on [Home](app:/). If it's empty, turn on **default intros** at the bottom of [When They Play](app:/schedules).

### The media server can't find the file

**Why:** this usually happens with Docker. Prerolls Max and Plex see your intro folder under different paths, so Plex looks in the wrong place.

**What to do:** press **Test connection** on [Media Servers](app:/servers). If the last check says the server can't find the files, set up [folder mapping](help:folder-mapping).

### Plex: cinema trailers are off for the library

**Why:** Plex plays intros only in libraries with **Enable Cinema Trailers** on.

**What to do:** in Plex, edit the movie library, open **Advanced**, and turn on **Enable Cinema Trailers**. Also check that **Cinema trailers to play before movies** isn't 0 in the app you use.

### Jellyfin or Emby: the plugin isn't installed or isn't working

**Why:** Jellyfin and Emby ask the Prerolls Max plugin which intro to play. Without it, nothing plays.

**What to do:** open [Media Servers](app:/servers). The card shows **Working** once the plugin has asked for an intro. If it doesn't, follow the four plugin steps on the card again, then play a movie and press **Check now**.

### Emby: Cinema Intros is off, or there's no Premiere

**Why:** Emby plays intros only with **Emby Premiere**, **Cinema Intros** on in the server's settings, and **Cinema Intros** on in each app.

**What to do:** check all three. See [Connecting Emby](help:connect-emby).

## The wrong intro plays

### Plex: everyone gets the same intro

**Why:** Plex has one intro list for the whole server. It can't pick a different intro for each person, each genre or each title.

**What to do:** nothing will make Plex do this. For a different intro per person or per kind of film, use Jellyfin or Emby with [rules](help:rules).

### An intro plays that shouldn't, or a title gets none

**Why:** Prerolls Max checks four things in order: the never-play list, then rules, then schedules, then default intros. The first match wins.

**What to do:** on Jellyfin or Emby, open [When They Play, Rules](app:/schedules/rules) and use **Try it** to see which rule picks the intro and why.

## Only the first intro plays

**Why:** the official Jellyfin app on Roku, and some other apps, play only the first intro in a list.

**What to do:** [combine your intros into one video](help:media-tools) and play that instead.

## Still stuck?

[Report a problem](app:/help/report). Say which server and app you use, and include the error code if you saw one (a short code like `a1b2c3d4`).
