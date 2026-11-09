# Settings

[Settings](app:/settings) has your account, backups, the time zone, playback options and the Advanced switch.

Looking for **Trash**, **API keys** or **Logs**? They're under Advanced, and each has its own section near the end of this page.

## Appearance

Choose **Light**, **Dark**, or **Same as my device**.

## Playback

Options for rules, TV shows and the tools that check your intros:

- **Break between episodes (hours):** how long someone has to stop watching a show before the next episode counts as "first". See [TV shows, kids and the never-play list](help:never-play).
- **Kids-safe:** which age ratings count as kids-safe, and whether unrated titles do.
- **Never play an intro:** the tags, like `no-intro`, that stop a title from getting an intro.
- **Play history:** whether Prerolls Max remembers what played, and for how long. See [What played](help:play-history).
- **Spot intros that didn't play:** the [missed-intro check](help:missed-intros).
- **Loudness:** the level that **Even out loudness** aims for. See [Even loudness](help:media-tools).

## Time zone

Schedules start and stop on Prerolls Max's clock. If that clock's time zone doesn't match the device you're using, you'll see a warning with a button to fix it.

## Account and sign-in

Keep **Ask for a password** on unless your network is completely private. With it off, anyone who can reach Prerolls Max can change or delete your intros.

**Changing your password** signs you out on your other devices. Passwords need at least 8 characters and can't be a well-known one like `password1`.

**Forgot your password?** On the sign-in page, open **Forgot your password?**. For safety, you can only set a new one on the computer that runs Prerolls Max. Open it there at `http://localhost:9393` (or whichever port you use).

### Other people

Admins can add people under **People who can sign in**. Press **Add person**, give them a user name and password, and tick **Admin** if they should be one.

- **Admin:** can change everything, including settings, watch folders and who can sign in.
- **Can change intros:** can upload videos and change collections, schedules and rules, but not settings.

The first account, made when you set up Prerolls Max, is always an admin.

## Backup and restore

A backup saves your collections, schedules, rules, never-play list, watch folders and settings.

- **Download settings backup** is a small `.json` file without the videos.
- **Download full backup (with videos)** is a `.zip` file with the videos too, so it can be large.

Play history is left out unless you turn on **Include play history in backups**. It can be long, and it says what people watched.

To restore, press **Choose backup file** and pick a `.json` or `.zip` file. Restoring replaces your current collections, schedules and settings with the ones in the backup. Download a backup first if you might want the current ones back. If some parts of the backup can't be used (for example, a watch folder that no longer exists), Prerolls Max lists them after restoring.

## Moving from NeXroll

Prerolls Max started as NeXroll, so it can read NeXroll's data. Stop NeXroll first: both use port 9393, and both would try to change Plex's intro list.

**With Docker:** point the Prerolls Max container at the same data folder NeXroll used (the one mounted at `/data`). On its first start, Prerolls Max finds `nexroll.db` there and copies it. Your NeXroll file isn't changed, so you can go back.

**On Windows, or anywhere else:** in NeXroll, download a backup. In Prerolls Max, open **Backup and restore**, press **Choose backup file**, and pick it. Full backups bring the videos too.

Then:

- **Jellyfin and Emby:** install the Prerolls Max plugin from [Media Servers](app:/servers). Once it shows **Working**, remove the old NeXroll plugin so the two don't both add intros.
- **Docker settings:** settings that start with `NEXROLL_` still work. The new names start with `PMAX_`.
- **Playlists:** NeXroll sequences come across as playlists. You can also import a `.nexseq` file on the Playlists page.

Some things have new names:

| NeXroll | Prerolls Max |
|---|---|
| Category | Collection |
| Filler | Default intros |
| Sequence | Playlist |
| NeX-Up | Movie trailers |
| Generator | Video maker |

## Advanced

Turn on **Show advanced options** to see more pages. Most people never need them.

- **Playlists:** a set order of intros, like a cinema pre-show. See [Playlists](help:playlists).
- **Movie trailers:** trailers for upcoming movies before the film. See [Movie trailers](help:movie-trailers).
- **Video maker:** make a short intro from text and pictures. See [Video maker](help:video-maker).
- **Folder mapping:** for when your media server sees the intro folder under another path. See [Folder mapping](help:folder-mapping).
- **Storage:** where intro videos are kept, and how much space they use. See [Storage](help:storage).
- **Video scaling:** smaller copies of intros for viewers away from home. See [Video scaling](help:video-scaling).
- **Trash**, **API keys** and **Logs:** see below.
- **System and updates:** your version, updates and diagnostics. See [System and updates](help:system-updates).

### Trash

Deleted videos stay in Trash for 30 days, then they're removed for good. Press **Restore** to bring one back, or **Empty trash** to remove them all now.

### API keys

An API key lets another app or script use Prerolls Max without your password. Press **New key**, give it a name you'll recognise, and choose:

- **What can it do?** **Only look (read)**, or **Look and change things**.
- **Stops working after:** never, or after 30 days, 90 days or a year.

Press **Make key** and copy it straight away. This is the only time the whole key is shown. The app sends it in the `X-Api-Key` header. Deleting a key stops anything using it at once.

You don't need to make keys for the Jellyfin and Emby plugins. **Set up the plugin for me** on Media Servers makes one for each.

### Logs

Logs show what Prerolls Max has been doing, newest first. If you saw an error code like `a1b2c3d4`, type it into the search box to find the exact entry. Pick **Errors only** to see just the problems.
