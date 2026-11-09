# More than one media server

Prerolls Max works with as many media servers as you have, of any kind: a Plex in the living room and another at a friend's house, two Jellyfin servers, or Plex, Jellyfin and Emby side by side. Each one has its own card on [Media Servers](app:/servers).

## Add a server

1. On [Media Servers](app:/servers), press **Add a server**.
2. Pick the kind: Plex, Jellyfin or Emby.
3. Give it a name you'll recognise, like "Living room" or "Bedroom Jellyfin". Prerolls Max suggests one ("Jellyfin", then "Jellyfin 2"). Two servers can't have the same name.
4. Fill in the address and the token or API key, just like the first time. Prerolls Max checks that the server answers and takes the key before it adds it.

For Plex, **Sign in with Plex** adds the next server on your Plex account that isn't on the list yet. You can also type the address and paste a token under **Other ways to connect**.

## What each server gets

- **Plex**: every Plex server that's switched on gets the same intros whenever a schedule, playlist or default intros change. Each Plex server sees your intro folder in its own way, so each has its own [folder mapping](help:folder-mapping) (the **Change** link on its card). If one of them can't see some files, its card says so by name, for example "Loft couldn't see 2 of the 4 intro files".
- **Jellyfin and Emby**: each server needs the Prerolls Max Intros plugin, set up from its own card. Each plugin gets its own key, so setting up a second server never breaks the first. Both can play intros at the same time.
- A playlist step can play only on some servers: in its **Only if** rules, choose **The media server is** and pick a kind ("Any Jellyfin") or one server by name. On Plex every server gets one list, so naming a Plex server counts as every Plex server.

## Rename, switch off or disconnect

- **Edit** changes the name, the address or the key. A new address or key is checked before it's saved.
- **Switch off** keeps the server on the list but Prerolls Max stops looking after its intros: Plex keeps the list it has, and Jellyfin and Emby get no intros from Prerolls Max until you switch it on again.
- **Disconnect** removes the server after you confirm. For Jellyfin and Emby, its plugin's key stops working too. Your videos, collections and schedules stay.

## Good to know

- Home shows one line per server, and What Played and the missed-intro warnings name the server when you have several of one kind.
- The first server of each kind that's switched on is the one older scripts and the `/plex`, `/jellyfin` and `/emby` addresses act on.
- Backups include the server list. A backup downloaded with an API key leaves the tokens and keys out; a server without a key isn't restored, unless this install already has the key for the same address.
- To check a server, use **Test connection** on its card, or [Play a test](help:play-a-test).
