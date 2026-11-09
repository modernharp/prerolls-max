# Play a test

**Play a test** asks a media server, in its own words, what it would play before a movie. Nothing starts playing on your TV, and the test isn't counted in What Played.

Press **Play a test** on a server's card on [Media Servers](app:/servers), or open **Or let Prerolls Max ask the server** in the setup guide. Then:

1. Pick the media server (each one is listed by its name).
2. Pick a movie from that server's library. Type part of a title and press **Search** to find one.
3. Press **Ask … what it would play**.

You get a plain answer, such as: *Before "Night of the Test", Living room will play: Pumpkin Intro, Ghost Intro.*

## How it asks

- **Plex**: Prerolls Max asks Plex to get the movie ready to play, the same way an app does when you press Play, and reads which intros Plex puts in front of it. When your intros are set to pick one at random, another test can show a different one.
- **Jellyfin and Emby**: Prerolls Max asks for the movie's intros the way the Jellyfin and Emby apps do. The Prerolls Max plugin on that server then asks Prerolls Max, exactly as it would for a real playback.

## When the answer is "no intro"

The answer says why, in order of what's most likely:

- **The server is switched off** on Media Servers, so Prerolls Max leaves it alone.
- **Nothing is set to play**: no schedule is on and there are no default intros. Turn one on under [Schedules](app:/schedules).
- **The plugin isn't installed or set up** (Jellyfin, Emby): follow the plugin steps on the server's card.
- **This movie never gets intros**: it's on the [never-play list](app:/schedules/never-play), or it has a no-intro tag.
- **Plex skipped them for this movie**: the movie's library may have Cinema Trailers turned off in Plex (the library's Edit, then Advanced), or Plex can't see the files. **Test connection** on its card checks the files, and its [folder mapping](help:folder-mapping) fixes most of these.
- **Emby is still getting them ready**: Emby only plays intros the plugin has downloaded and registered. New ones take a minute or two. Emby also needs Emby Premiere for intros.

If the test shows your intros but an app still skips them, the app is the reason: see [Which apps play intros](help:devices).
