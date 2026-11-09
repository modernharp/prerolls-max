# Connecting Plex

Plex doesn't need a plugin. Prerolls Max fills in Plex's own intro setting for you and keeps it up to date.

## Sign in with Plex (easiest)

1. On [Media Servers](app:/servers), press **Connect Plex**.
2. Press **Sign in with Plex**. A Plex window opens.
3. Sign in to Plex there. Your password goes to Plex, never to Prerolls Max.
4. Come back to Prerolls Max. It finds your server and checks the connection.

If no window opens, your browser blocked the pop-up. Press **Open the Plex sign-in page** instead. If you take longer than 10 minutes, the sign-in times out; just start again.

## Other ways: address and token

Open **Other ways to connect**, then fill in:

- **Plex address:** like `http://192.168.1.10:32400`. Port 32400 is added if you leave it out. If Prerolls Max runs in Docker, use the computer's network address (like `192.168.1.10`), not `localhost`. Inside a container, `localhost` means the container itself.
- **Plex token:** a long code that lets Prerolls Max talk to Plex. To find it, open Plex in a web browser, open any movie, choose **Get Info**, then **View XML**. The address of the page that opens ends with `X-Plex-Token=` followed by the token. Copy everything after the `=`.

## Settings Plex needs

- **Enable Cinema Trailers** must be on for each movie library. In Plex, edit the library, then open **Advanced**.
- In each Plex app, **Cinema trailers to play before movies** must not be 0.
- On the 2026 Plex apps for Apple TV, iPhone, iPad, Android TV and Fire TV, set it to **1**. Otherwise these apps skip intros. Plex says it's working on a fix.

## Test the connection

Press **Test connection** on the Plex card. Each check gets a tick or tells you what to fix. The last check makes sure Plex can open your intro files.

## Plex can't find the files

Prerolls Max doesn't send videos to Plex. It sends the **path** to each file, and Plex opens the file itself. If either one runs in Docker, they may see the intro folder under different paths. For example, Prerolls Max sees it as `/data/prerolls` and Plex as `/media/prerolls`.

If the test finds this, set up [folder mapping](help:folder-mapping). It has a full example.

## What Plex can't do

- Plex plays intros before movies only, never before TV episodes.
- Plex has one intro list for the whole server. Everyone watching at the same time gets intros from the same list, so Plex can't play a different intro per person, genre or title.
- Intros don't play when you resume a movie.
- Casting, DLNA, Plexamp, downloads and Infuse never play intros.

[What each server can do](help:what-servers-can-do) compares Plex with Jellyfin and Emby.
