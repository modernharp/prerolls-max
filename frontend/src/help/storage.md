# Storage

[Settings, Advanced, Storage](app:/settings/advanced/storage) shows where Prerolls Max keeps things and how much space each part uses: your intro videos, movie trailers and made videos, thumbnails, and the settings file.

## Moving your intro videos

Type the new folder's full path under **Move intro videos to another folder** and press **Move videos**. Every video moves there and your library follows. With a big library this takes a while, so leave the page open.

The path is the one Prerolls Max sees. In Docker, that's the path inside the container, like `/data/prerolls`, not the folder's name on your NAS. To use a new folder in Docker, add it to the container first.

After moving, check [Folder mapping](help:folder-mapping) if your media server sees the new folder under a different path.

## Warnings

If most videos can't be found, the page says the intro folder looks offline. That usually means a network drive or USB disk isn't connected. Connect it again and reload the page.

If only a few are missing, the page says how many. Their cards on Intro Videos say **The video file is missing from disk**, and you can delete them there.
