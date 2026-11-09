# Movie trailers

Prerolls Max can play trailers for movies that are coming soon before your film, the way a cinema does. Radarr tells it which movies are coming, and the trailers come from YouTube. NeXroll called this NeX-Up.

It's under [Settings, Advanced, Movie trailers](app:/settings/advanced/trailers). Turn on **Show advanced options** in Settings first.

## Setting it up

1. Connect **Radarr**. You need its address (usually ending in port 7878) and its API key. In Radarr, the key is under **Settings**, then **General**.
2. Under **Trailer settings**, pick a folder for the trailers. **Use the suggested folder** puts them next to your intro videos, where your media server can already see them.
3. Turn on **Download trailers for upcoming movies**.
4. Press **Get trailers now**. A progress bar shows each trailer as it downloads, and a message at the end says what happened. After that, Prerolls Max checks once a day.
5. Add a **Movie trailers** step to a [playlist](help:playlists), and use that playlist in a schedule or as your default intros.

If you put Sonarr's address in the Radarr box (or the other way round), Prerolls Max says so and doesn't connect. Each one has its own section.

Sonarr works the same way for new TV seasons. It's optional. If you have more than one Radarr, for example a separate one for 4K, press **Add another Radarr**. A movie that's on both only counts once.

## The settings

The page has how many days ahead to look, how many trailers to keep, and how many to play before each movie. Old trailers are deleted after the number of days you set, counted from the movie's release date, so a trailer never disappears before the film is out. Set it to 0 to keep trailers until you delete them.

A Movie trailers step in a playlist can play only some age ratings, for example only G and PG trailers before family films.

## When Radarr is off

If Radarr doesn't answer, the page says so instead of listing movies, and **Get trailers now** doesn't change anything. Trailers you already have keep playing. With two Radarrs, the page names the one that didn't answer and shows the other one's movies.

## If downloads fail

YouTube sometimes stops a server from downloading until it proves it isn't a robot. When that happens, **Get trailers now** says "YouTube refused to hand over" some trailers. It happens more on servers in data centres and on some home connections. Open **If downloads fail** on the Movie trailers page. There are two fixes:

- **Upload cookies.txt.** Sign in to YouTube in your web browser, save its cookies with a "cookies.txt" browser extension, and upload the file here. The cookies run out after a while; if downloads stop again, export them again.
- **Start the helper.** The helper answers YouTube's robot check for you. It needs Node.js. The Docker image comes with both. Elsewhere, press **Install the helper** first; it downloads from GitHub.

Then press **Try a test download**. It tries a real trailer, not just any YouTube video, because YouTube can let some videos through and still refuse trailers.

## Your own TMDB key

TV show trailers are looked up on The Movie Database (TMDB). The shared key Prerolls Max came with no longer works, so TV show trailers need a free key of your own. Make one at themoviedb.org, paste it under **Your own TMDB key**, and press **Test**. Movie trailers don't need it, because Radarr already knows each movie's trailer.

## Coming soon video

**Coming soon video** makes a 10-second video that lists up to eight movies and shows coming soon, with their dates. It goes into your intro videos in the "Coming Soon Lists" collection. Turn on **Make it again after each check** to keep it up to date, and use a **Coming soon video** step in a playlist to play it.

## Trailers for movies you have

This plays trailers for movies already in your library, from a **Trailers for movies you have** playlist step. Prerolls Max uses trailer files that sit next to your movies, named like `Sintel (2010)-trailer.mp4` or kept in a `Trailers` folder, and can download the rest from YouTube.

If Radarr runs in Docker or on another computer, it may see your movies under a different path, like `/movies`. Fill in **Radarr's movie folder** and **The same folder for Prerolls Max** so Prerolls Max can find the trailer files.
