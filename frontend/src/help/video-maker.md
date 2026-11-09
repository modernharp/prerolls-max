# Video maker

The video maker turns your own words into a short intro video, with your colours, a logo, a picture behind the text and music if you like. It's under [Settings, Advanced, Video maker](app:/settings/advanced/video-maker). Turn on **Show advanced options** in Settings first.

## Making a video

1. Under **Start from**, pick **Welcome**, **Coming soon**, **Announcement** or **QR code**.
2. Change the text. The preview updates as you type and plays on a loop.
3. Pick colours, or a ready-made colour set. Add a **Logo** or a **Picture behind** the text if you want.
4. Set the **Length (seconds)**, from 3 to 30, and pick the **Music**.
5. Type a name under **Save it as**, then press **Make the video**.

The page records the animation in your browser, which takes as long as the video, then Prerolls Max turns it into an MP4. A progress bar shows both parts. Keep the page open until it's done. The new video is then in [Your videos](app:/videos), ready to put in a collection or a playlist.

## QR codes

The QR code template shows a code people can scan with their phone, for example to request a movie. Type the web address under **Link the code opens**. The code in the preview is the same one that ends up in the video, so you can test it by scanning your screen.

## Music

- **No music:** silent.
- **The built-in fanfare:** a short piece that comes with Prerolls Max.
- **Your own music:** upload an MP3, M4A, WAV, FLAC or OGG file. It plays under the intro and fades out at the end.

## If it doesn't work

- The video maker needs FFmpeg. If it's missing, the page says so. [System and updates](app:/settings/advanced/system) shows whether it's installed. The Docker image includes it.
- Made videos are kept in the same folder as movie trailers. If you haven't picked one, the page offers the suggested folder.
