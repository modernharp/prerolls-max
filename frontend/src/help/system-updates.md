# System and updates

[Settings, Advanced, System and updates](app:/settings/advanced/system) shows which version you have, checks for a newer one, lists the tools Prerolls Max uses, and makes a diagnostics file for bug reports.

## Updates

Press **Check for updates** to compare your version with the newest release. **Check automatically** sets how often it looks by itself.

If the page says update checks are off, this copy doesn't know where new releases are published. Whoever set it up can set `PMAX_UPDATE_REPO` to the GitHub repository that publishes Prerolls Max releases, then restart it.

How you install an update depends on how you run Prerolls Max:

- **Docker:** get the new image and recreate the container, for example with `docker compose pull` and then `docker compose up -d`. Your settings and videos stay in the `/data` folder.
- **Windows installer:** the page can install the update for you.

## Tools

- **FFmpeg** reads video lengths, makes thumbnails, and powers the video maker and the loudness and TV-friendly tools.
- **yt-dlp** downloads movie trailers. **Deno** and **Node.js** help it with YouTube.

A red cross means that part won't work until the tool is installed. The Docker image includes all of them.

## Diagnostics

**Download diagnostics** saves a zip file with recent logs and settings, for a bug report. Passwords, tokens and API keys are left out. Attach it to your bug report, along with the text from [Report a problem](app:/help/report).

## Restarting

Prerolls Max can't restart itself from the web page. Restart it where it runs:

- **Docker:** restart the container.
- **Windows:** use the Prerolls Max icon in the system tray.
- **Linux:** restart its service.
