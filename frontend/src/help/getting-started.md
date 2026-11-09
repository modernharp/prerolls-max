# Getting started

Prerolls Max plays a short video, an intro, before your movies. You choose the videos and when they play, and Prerolls Max tells your media server (Plex, Jellyfin or Emby) which one to use.

The first time you open Prerolls Max, it asks you to make an account. Pick a user name and a password of at least 8 characters, then press **Create account**. This account is the admin: it can change everything, including settings and who else can sign in.

After that, setup takes four steps. Home shows a **Finish setting up** checklist until you've done them all.

## 1. Connect your media server

Open [Media Servers](app:/servers) and press **Connect Plex**, **Connect Jellyfin** or **Connect Emby**.

- **Plex:** press **Sign in with Plex**. A Plex window opens. Sign in there, and Prerolls Max finds your server. See [Connecting Plex](help:connect-plex).
- **Jellyfin and Emby:** make an API key in the server's dashboard and paste it in. Then install the small Prerolls Max plugin; the page walks you through it. See [Connecting Jellyfin](help:connect-jellyfin) or [Connecting Emby](help:connect-emby).

Then press **Test connection**. Each check gets a tick, or tells you what to fix.

If Prerolls Max or your media server runs in Docker, read [Folder mapping](help:folder-mapping) too. It explains the most common Docker problem in one example.

## 2. Add intro videos

Open [Intro Videos](app:/videos). You can:

- **Add your own.** Press **Add videos**, or drag files onto the page. You can also paste a link to a video file. MP4 works on every server.
- **Get free ones.** Open the **Get more from Community** tab. See [Community intros](help:community).

Put each video in a **collection**, like "Everyday" or "Halloween". Schedules play collections, not single videos.

## 3. Choose when they play

Open [When They Play](app:/schedules) and press **New schedule**. You answer three questions:

1. Which collection plays, and whether to pick one at random or play them all.
2. When: every year between two dates, on a holiday, on certain days of the week, all the time, and a few more.
3. What happens if two schedules are on at the same time.

The box on the right says in plain words what will happen.

Also turn on **default intros** at the bottom of the page. They play whenever no schedule is on, so a movie never starts without one. See [Choosing when intros play](help:schedules).

## 4. Play a test

On Home, press **Start test** next to **Play a test**. Then open your media server in a web browser and play a movie from the beginning. Your intro should play first.

Test in a web browser before a TV or phone. Some TV and phone apps skip intros until you change a setting in the app. See [Which apps play intros](help:devices).

If nothing plays, open the [troubleshooter](app:/help/troubleshoot) or read [My intro isn't playing](help:intro-not-playing).

## Coming from NeXroll?

Your NeXroll schedules, collections and settings can come with you. See [Moving from NeXroll](help:settings) under Settings.
