# What each server can do

Plex, Jellyfin and Emby handle intros in different ways, so some options work better on one than another.

- **Plex** has one intro list for the whole server. Prerolls Max changes that list when a schedule starts or ends. That's reliable for dates and holidays. But Plex picks the intro before it knows which movie is starting, so choices by genre, rating or person can only follow the movie already playing, and apply to the next one someone starts. Plex never plays intros before TV episodes.
- **Jellyfin and Emby** ask the Prerolls Max plugin before every movie or episode, so the right intro is picked each time. Emby also needs Emby Premiere.
- **On every server**, intros don't play when you resume a movie.

Next to options in Prerolls Max you'll see a badge for each server:

- **Works:** the server does this itself.
- **Needs plugin:** works once the Prerolls Max plugin is installed. It changes to **Works (plugin)** once the plugin is working.
- **Next play only:** Prerolls Max does its best by changing Plex's list before the next play. With several people watching at once, it can't be exact.
- **Not possible:** the server can't do this at all.

Tap a badge to see why. Here's the full list for your servers:
