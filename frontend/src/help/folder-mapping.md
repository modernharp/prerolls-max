# Folder mapping

Most people don't need this. Read on if **Test connection** says your media server can't find the intro files. It mostly happens with Docker.

## Why it's needed

Prerolls Max doesn't send the video to Plex. It sends the **path** to the file, like `/data/prerolls/Halloween/pumpkin.mp4`, and Plex opens the file itself.

That only works if Plex sees the file at the same path. With Docker, it often doesn't. Each container is like a separate little computer with its own names for your folders.

## An example

Your intros are in `/home/me/prerolls` on your computer. Your Docker Compose file gives that folder to both containers, but under different names:

```yaml
services:
  prerolls-max:
    volumes:
      - /home/me/prerolls:/data/prerolls   # Prerolls Max sees /data/prerolls
  plex:
    volumes:
      - /home/me/prerolls:/media/prerolls  # Plex sees /media/prerolls
```

The part before the colon is the real folder on your computer. The part after it is what the container calls it.

| Container | Sees the intros at |
|---|---|
| Prerolls Max | `/data/prerolls` |
| Plex | `/media/prerolls` |

Same folder, two names. A folder mapping tells Prerolls Max: "when you talk to Plex, change `/data/prerolls` to `/media/prerolls`".

The simplest fix of all is giving both containers the same name for it. If Plex also used `/home/me/prerolls:/data/prerolls`, no mapping would be needed.

## Setting it up

1. Make sure the intro folder is added to **both** containers, as in the example. Plex can't see a folder that isn't given to its container. After changing the folders, run `docker compose up -d` so the change takes effect.
2. Turn on **Show advanced options** in [Settings](app:/settings#advanced), then open [Folder mapping](app:/settings/advanced/folder-mapping).
3. Press **Find it for me**. Prerolls Max asks Plex where it sees the folder and suggests a mapping. Press **Use this**, then **Save**.
4. If it can't find one, add a mapping yourself: what Prerolls Max sees on the left, what Plex sees on the right.
5. Go back to [Media Servers](app:/servers) and press **Test connection**.

## Windows and network shares

Paths must be full folder paths, like `D:\Prerolls` or `/mnt/prerolls`. Web or network addresses like `smb://nas/prerolls` don't work. Connect the share as a drive letter or a mounted folder first, then use that path.

## Jellyfin and Emby

The Prerolls Max plugin downloads intros from Prerolls Max itself, so Jellyfin and Emby rarely need a mapping.
