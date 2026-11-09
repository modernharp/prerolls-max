# Adding intro videos

An intro video (people also call it a preroll) is a short clip that plays before a movie. Yours live on [Intro Videos](app:/videos).

## Adding videos

Press **Add videos**, or drag files onto the page. First pick the collection they go into.

- **Formats:** MP4, MKV, MOV, WebM, AVI, M4V, TS and MPEG. MP4 with H.264 video and AAC sound plays on every server and every app.
- **Size:** up to 500 MB each. Most intros are a few MB.
- **Length:** anything works, but 10 to 30 seconds is usual.

### From this computer

Every file gets its own line in the list, with a progress bar while it uploads. A file that can't be added says **Not added** and why: it isn't a video, it's over 500 MB, or Prerolls Max opened it and found it isn't a real video (a picture renamed to `.mp4`, say). Those files are never sent, and the **Upload** button only counts the ones that can go. Press **×** to take a file off the list, or **Clear list** to start again.

If a file doesn't get through because the connection dropped, it stays in the list and goes again the next time you press **Upload**.

### From a web link

Choose **From a web link** and paste a link to one video file, like `https://example.com/intro.mp4`. Prerolls Max downloads it in the background and adds it the same way as an upload, with the same checks. You can watch the progress in the window.

The link has to be the file itself:

- Pages on YouTube, Vimeo, TikTok, Instagram and similar sites don't work. Downloading from them is against their terms. If you have the rights to a video, download it yourself and upload the file.
- Streams (links ending in `.m3u8` or `.mpd`) and links that open a web page don't work either. On a download page, copy the link the download button uses.

For safety, Prerolls Max won't fetch a link that points into your own network, like `http://192.168.1.20/intro.mp4`. Otherwise anyone who can add videos could use it to look around your network. To use a NAS or another computer at home, an admin can turn on **Allow links to my home network** in [Settings](app:/settings), under Playback.

### Videos you already have

Prerolls Max compares what's inside each new video with the videos you have; the file name doesn't matter. When a new file is exactly the same as one in your library, its line says **Already in your library as "Pumpkin Intro"** and offers two buttons:

- **Skip** leaves it out. Closing the window does the same.
- **Add anyway** adds it a second time, for example to keep a copy in another collection's folder.

Prerolls Max keeps the uploaded copy for 15 minutes while you decide, so **Add anyway** doesn't send it again. Links work the same way.

[Watch folders](help:watch-folders) skip exact copies on their own, and the folder's card says how many. Community downloads you already have are skipped too.

To add videos from a folder without uploading them one by one, use [watch folders](help:watch-folders).

## Collections

A collection is a group of intro videos, like "Everyday", "Halloween" or "Kids". Schedules and rules play collections, so put each video in at least one. A video can be in several.

- On the **Collections** tab, press **New collection** to make one. The pencil renames it.
- To change which collections a video is in, press the pencil on the video.
- Deleting a collection keeps its videos. Any schedule that played it is turned off, and you're told which before you confirm.

A collection can also say **Don't repeat an intro within (hours)**. See [How often and no repeats](help:weights-and-cooldowns).

## Editing a video

Press the pencil on a video to change:

- **Name:** the name shown in Prerolls Max. The file keeps its own name.
- **Collections:** which collections it's in.
- **How often:** from 1 (rarely) to 10 (often), when intros are picked at random.

## Fixing videos

Tick some videos and the bar at the bottom offers tools to even out loudness, make TV-friendly versions and combine several into one. See [Even loudness, TV-friendly versions and combined videos](help:media-tools).

If a card says **The video file is missing from disk**, the file was moved or deleted outside Prerolls Max, or the drive it's on isn't connected.

## Deleting videos

Deleted videos go to Trash for 30 days. Press **Undo** on the message that appears, or restore them later from Trash. Trash is in [Settings](app:/settings#advanced) once **Show advanced options** is on.

## Getting free intros

The **Get more from Community** tab lists free intros from Prerolls.me and Prerolls.uk. See [Community intros](help:community).
