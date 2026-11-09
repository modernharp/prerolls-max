# Watch folders

A watch folder adds new intro videos for you. Pick a folder and a collection on **Intro Videos**, **Add automatically**, and any new video that lands in that folder is added to the collection on its own. It's useful for a download folder, or a shared folder someone else fills. Only an admin can set one up.

## Two ways to add

- **Use them where they are** (the default): the file stays in your folder and Prerolls Max plays it from there. Your media server has to see that folder too.
- **Copy into the library:** a copy goes into the collection's folder in the Prerolls Max library. Your original stays where it is. A file with exactly the same contents as one already in the library is skipped.

## Files that are still arriving

Prerolls Max looks every 30 seconds. It adds a file only once the file has **stopped changing for about 20 seconds** and can be opened as a video. A file still copying over the network, or still downloading, shows under **Waiting** until it's done. Partial downloads (`.part`, `.crdownload`, `.!qB` and similar) and hidden files are never touched.

A file that still can't be opened as a video after several tries is left alone, and the page says which one.

Each file is only added once. If you delete it from the library later, it doesn't come back.

## Good to know

- The folder must be a full path as Prerolls Max sees it. In Docker, add the folder to the container first (for example `- /mnt/user/downloads/intros:/downloads/intros` under `volumes:`) and use the path inside the container, `/downloads/intros`.
- The Prerolls Max library folder is already checked for new files every few minutes, so it can't be a watch folder.
- Deleting a watch folder leaves the folder, its files and the intros already added alone.

## When new videos start playing

| | Plex | Jellyfin | Emby |
|---|---|---|---|
| A new intro plays | The next time Prerolls Max updates Plex's intro list | From the next play | From the next play, once the plugin has downloaded it |

If you use files where they are and Plex sees the folder under a different path, set up **Folder mapping** (Settings, Advanced).
