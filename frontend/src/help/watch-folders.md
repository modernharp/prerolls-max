# Watch folders

A watch folder adds new intro videos for you. Pick a folder and a collection, and any new video that lands in that folder is added to the collection on its own. It's useful for a download folder, or a shared folder someone else fills.

## Setting one up

1. Open [Intro Videos, Add automatically](app:/videos/watch) and press **Watch a folder**.
2. Under **Folder**, type the folder's full path, like `/downloads/intros`.
3. Under **Add new videos to**, pick a collection.
4. Choose how they're added (see below), then press **Start watching**.

Only an admin can add, change or check watch folders.

## Two ways to add

**Use them where they are** is the default. The file stays in your folder and Prerolls Max plays it from there. Your media server has to be able to see that folder too.

**Copy into the library** puts a copy in the collection's folder inside the Prerolls Max library. Your original stays where it is.

Either way, a file with exactly the same contents as a video already in your library is left out, even if its name is different. The folder's card counts them, like **Skipped 1 duplicate**.

Turn on **Include folders inside it** to watch the folders inside the folder too.

## Files that are still arriving

Prerolls Max looks every 30 seconds. It adds a file only once the file has **stopped changing for about 20 seconds** and can be opened as a video. A file still copying over the network, or still downloading, shows under **Waiting** until it's done.

Partial downloads (`.part`, `.crdownload`, `.!qB` and similar) and hidden files are never touched. A file that still can't be opened as a video after several tries is left alone, and the folder shows which one.

Each file is only added once. If you delete it from the library later, it doesn't come back.

**Check now** looks straight away instead of waiting.

## Docker and paths

The path is the one Prerolls Max sees. In Docker, add the folder to the Prerolls Max container first, then use the path inside the container. For example, with this line under `volumes:` in your Docker Compose file:

```yaml
- /mnt/user/downloads/intros:/downloads/intros
```

you'd type `/downloads/intros` as the folder.

If you use files where they are, your media server must see that folder too. If it sees it under a different path, set up [folder mapping](help:folder-mapping).

The Prerolls Max library folder is already checked for new files every few minutes, so it can't be a watch folder.

## Stopping

Turn a watch folder off to pause it, or delete it to stop for good. Either way, the folder, its files and the intros already added stay as they are.

## When new videos start playing

| | Plex | Jellyfin | Emby |
|---|---|---|---|
| A new intro plays | The next time Prerolls Max updates Plex's intro list | From the next play | From the next play, once the plugin has downloaded it |
