# Prerolls Max: contracts between the parts

This file is the source of truth for how the parts talk to each other while
they're built in parallel. Change it before you change behaviour.

## 1. Errors (every endpoint)

Implemented in `app/backend/errors.py`. Every non-2xx response is:

```json
{
  "detail": "Plex didn't answer at http://192.168.1.5:32400.",
  "error": {
    "code": "plex_unreachable",
    "message": "Plex didn't answer at http://192.168.1.5:32400.",
    "hint": "Check that Plex is running and that the address is right.",
    "fields": {"url": "The address must start with http:// or https://."},
    "request_id": "a1b2c3d4"
  }
}
```

- `detail` is always a string, the same as `error.message`.
- `fields` appears only for form problems: field name to a message for that field. Nested fields use dots (`items.0.id`).
- Raise `AppError` or a helper from `errors.py` (`bad_input`, `not_found`, `conflict`, `unreachable`, `rejected_credentials`). Never put `str(e)` in a response; log it.
- Messages say what happened in plain words. Hints say what to do next. No jargon, no stack traces, no internal IDs ("Category 12"); use names.

## 2. Input checks

`app/backend/validation.py` has pydantic field types and `clean_*` functions:
`ServerUrl`, `Token`, `ApiKey`, `Name`, `FileName`, `FolderPath`, `TimeHHMM`,
`DateValue`, `DateTimeValue`, `HexColor`. Use them in request models, with
`Field(ge=, le=)` for numbers and `Literal[...]` for choices. Request models
should set `model_config = ConfigDict(extra="ignore")` unless unknown keys
are dangerous (settings), then `extra="forbid"`.

The web interface checks the same rules before sending, using the same
messages (`frontend/src/lib/validate.ts`), so people see problems as they type.

## 3. Outgoing requests

`app/backend/net.py`: `require_host(url, allowed_hosts)` before fetching any
fixed internet service (community libraries, holidays, GitHub). Media server
and *arr addresses are user-configured and may be private; validate them with
`clean_server_url` when saved.

## 4. Login and first run

- `GET /auth/status` adds `"setup_required": true` when no user account exists.
- `POST /auth/setup` takes `{username, password, display_name?}`. It only works while `setup_required` is true. It creates an admin, turns login on, and signs the browser in. The password needs at least 8 characters and can't be one of the 20 most common passwords (`COMMON_PASSWORDS` in `main.py`, mirrored in `validate.ts`). No upper case, digits or symbols are required. The same rule applies wherever a new password is set.
- While setup is required, every API route except `/auth/status`, `/auth/setup`, `/health`, the static interface and `/plugin/*` returns 401 with code `setup_required`.
- Existing installs that already have users keep their login on/off choice. If login is off, the interface shows a banner.
- Plugin routes (`/plugin/*`) need an API key whenever login is on. `?api_key=` in the URL is no longer accepted; use the `X-Api-Key` header.

## 5. Community libraries (new API)

Two sources, both always available, listed in this order:

| id | name | id prefix |
|---|---|---|
| `prerollsme` | Prerolls.me | `pm:` + slug |
| `prerollsuk` | Prerolls.uk (Typical Nerds) | `tn:` + path |

A person can pick items from both and download them together.

```
GET  /api/community/sources
  -> [{id, name, site_url, description, item_count, downloadable_count,
       last_refreshed (ISO or null), refreshing: bool,
       terms: {summary, url, needs_acceptance: bool, accepted: bool},
       error: null | {message, hint}}]

GET  /api/community/items?source=prerollsme|prerollsuk&q=&category=&tag=
       &duration=lt10|10-20|20-30|30plus&downloadable=true&sort=newest|popular|shortest|az
       &page=1&limit=24   (limit 1-100)
  -> {items: [Item], page, limit, total, total_pages}

Item = {
  id, source, title, description, category: {slug, name} | null, tags: [],
  creator: {name, url} | null, duration_seconds | null,
  width | null, height | null, size_bytes | null,
  thumbnail_url | null,      # same-origin: /api/community/thumb?id=...
  preview_url | null,        # direct video URL or same-origin proxy
  embed_url | null,          # YouTube/Vimeo embed for watch-only items
  page_url,                  # the item's page on the source site
  downloadable: bool,        # false for YouTube/Vimeo items
  platforms: ["plex","jellyfin","emby"],
  in_library: {preroll_id, name} | null
}

GET  /api/community/categories?source=   -> [{slug, name, count}]
GET  /api/community/thumb?id=             -> image (cached on disk)
POST /api/community/sources/{id}/refresh  -> {job_id}
POST /api/community/sources/{id}/accept-terms -> source
POST /api/community/download  {item_ids: [id], collection_id?: int, new_collection_name?: str}
  -> {job_id}
GET  /api/jobs/{job_id}
  -> {id, kind, state: queued|running|done|failed, progress: 0-100,
      message, done: int, total: int, errors: [{item_id, message}], result}
```

The old `/community-prerolls/*` routes keep working for scripts but must not
fetch any host except the two sources' own.

As implemented (additions only; everything above holds):

- `source` is required on `/items` and `/categories`. Without `q` the default
  sort is `newest`; with `q`, best match first. Prerolls.uk has no download
  counts, so `popular` keeps its own order there.
- Extra query params: `platform=plex|jellyfin|emby`, `include_ai=true`
  (Prerolls.uk's AI folder is left out unless asked for or `category=ai`).
- Extra Item fields: `attribution` ("by X · via Prerolls.me"), `published_at`,
  `hosted_on` and `watch_url` (Prerolls.me), `versions: [{id, platform, title,
  size_bytes, duration_seconds}]` (Prerolls.uk platform versions folded into one row).
- `GET /api/community/preview?id=`: streams a Prerolls.uk video (Range works);
  for Prerolls.me it redirects to the video's own address. Prerolls.uk items
  have no thumbnail (`thumbnail_url: null`).
- Prerolls.uk before acceptance: 403 `terms_not_accepted`. Before its first
  refresh: `/items` answers 409 `needs_refresh`. The refresh job's `result`
  carries `lengths_job_id` (reading video lengths runs as a second job).
- Download job `result`: `{added: [{item_id, preroll_id, name, title}],
  skipped: [...already in the library], collection: {id, name}, applied}`.
  At most 100 ids per request; YouTube/Vimeo items come back as per-item errors.

## 6. What each server can do

```
GET /api/capabilities
  -> {servers: [{type: "plex"|"jellyfin"|"emby", connected: bool, version,
       features: {<feature>: {level: "native"|"plugin"|"emulated"|"none",
                              note: "plain sentence"}}}]}
```

Feature keys: `random`, `sequence`, `random_in_groups`, `folders`, `genre_rules`,
`rating_rules`, `per_user`, `per_library`, `episodes`, `first_episode_only`,
`time_of_day`, `dates`, `trailers`, `on_resume`, `client_notes`.

The interface shows a small badge on every option that depends on these:
"Works", "Next play only", "Needs plugin", "Not possible on Plex".

Several servers of one type (section 10): each type entry adds `instances:
[{id, type, name, enabled, connected, version, plugin?}]`, and the answer has
the same list at the top level as `instances`. A type is `connected` when any
of its servers is; its `plugin` is a working one when any has checked in.

## 10. Media servers (several of each type)

```
GET    /api/servers?check=          -> {servers: [Server]}   (check=true asks each server, a few seconds)
POST   /api/servers                 {type: plex|jellyfin|emby, name?, url, token} -> Server
GET    /api/servers/{id}?check=     -> Server
PUT    /api/servers/{id}            {name?, url?, token?, enabled?} -> Server
DELETE /api/servers/{id}            -> {deleted: true, name}
POST   /api/servers/{id}/test       -> {steps: [{id, title, state: ok|warn|fail|skipped, detail, link: {to, label}|null}], server}
GET    /api/servers/{id}/plugin     -> as GET /jellyfin/plugin/detect, for this server
POST   /api/servers/{id}/plugin     {nexroll_url} -> as POST /jellyfin/plugin/configure
GET    /api/servers/{id}/folder-mapping           -> {server, primary, mappings: [{local, plex}]}  (Plex only, else 409)
PUT    /api/servers/{id}/folder-mapping           {mappings} -> same   (paths checked like watch folders)
POST   /api/servers/{id}/folder-mapping/detect    -> as POST /settings/path-mappings/detect
GET    /api/servers/{id}/movies?q=  -> {items: [{id, title, year}]}
POST   /api/servers/{id}/play-test  {item_id} -> {server: {id, name, type}, movie: {id, title}, ok,
                                       items: [{title, preroll_id}], summary, reasons: [{title, detail, link}]}

Server = {id, type, type_label, name, url, enabled, primary, version, has_key,
          plugin_key: {id, name, active} | null, created_at,
          mappings (Plex), last_apply (Plex): {state: ok|failed|waiting, message, at, missing} | null,
          status (with check): {connected, reachable, signed_in, message, hint, version, server_name}}
```

- Changing anything is admin only (section 9's check). The token is never sent back.
- Names are unique ignoring case and spacing (409 `server_name_taken`, field `name`). New names default to the type, then "Jellyfin 2", "Jellyfin 3".
- A new address or token is checked before it is saved: 502 `<type>_unreachable` (field `url`) or `<type>_auth_failed` (field `token`), in plain words. The same server twice (same address, or the same Plex machine id / Jellyfin or Emby server id) is 409 `server_already_added`.
- Storage: table `media_servers`; each token in the secure store as `media_server_<id>`. The first switched-on server of each type is the *primary*: it is mirrored into the settings row (`plex_url`, `jellyfin_url`, `emby_url`, `path_mappings`, and the old secret names), so the old `/plex/*`, `/jellyfin/*`, `/emby/*` routes keep working on it. What those routes write is adopted back (a new address or token changes the primary; `/<type>/disconnect` removes it and the next one takes its place). On start, a single-server or NeXroll database becomes rows.
- Plex: every switched-on Plex server gets the same list whenever the scheduler writes one, each translated through its own folder mapping, with its own path check and playback guard. A server that was busy or down is retried about every two minutes; every five minutes each list is read back and rewritten if someone changed it. `last_apply` says how it went for that server.
- Jellyfin and Emby: a `/plugin/v2/intros` request is matched to its server by the plugin's API key, then the `server_id` it sends, then the address it calls from, then "the only server of that type"; a match fills in the key and server id it didn't know. A switched-off server is answered with no items (`intentional_empty: false`). Play history and missed-intro checks carry the server's name (`server_name`); missed-intro warnings name the server when there are several of a type. "Play a test" requests are not recorded.
- Playlist `server` rules take types or `server:<id>`; on Plex a named Plex server counts as every Plex server (they share one list).
- Backups: `media_servers: [{type, name, url, enabled, server_identifier, mappings, token}]` (`token` empty when fetched with an API key). Restore replaces the list only when the backup has a non-empty one; a server with no token in the backup keeps this install's token for the same address, or is left out and named in `skipped`.
- `/plex/tv/connect` takes `add_server: true, name` to add the account's next Plex server instead of replacing the first.

## 7. Plugin protocol v2 (Jellyfin and Emby)

```
GET /plugin/v2/intros
Headers: X-Api-Key (required when login is on), X-PrerollsMax-Plugin: jellyfin/1.0.0
Query: item_id, item_type=Movie|Episode, user_id, user_name, library_id,
       library_name, genres (comma list, URL-encoded), tags, official_rating,
       year, series_id, season, episode, is_first_in_session (0/1),
       client, device_id, server_id, audio (e.g. "TrueHD Atmos 7.1"),
       video (e.g. "2160p HDR10")
-> {mode: "exact", items: [{id, name, path, stream_url, version, duration_seconds}],
    reason: "Plain sentence for logs", intentional_empty: false, cache_seconds}
```

The plugin sends everything it knows, so the server never has to call back
into Jellyfin or Emby during playback. v1 `/plugin/intros` stays for old
plugins.

Details (implemented in `app/backend/routers/plugin_v2.py` and `plugins/Shared`):

- Extra query fields: `item_name`, `series_name`, `path` (the media file, for
  file-name rules), `tmdb_id`, `audio_default` (codec of the default audio
  track) and `audio_codecs` (comma list of every audio track's codec).
  Episodes send the series' genres, tags and rating when they have none.
- `all=1` (with `item_type`) asks for every intro that could play now, so the
  plugin can download them ahead; the answer has `mode: "pool"` and
  `cache_seconds: 1800`. A playback answer has `mode: "exact"` and
  `cache_seconds: 0`.
- `stream_url` is relative (`/plugin/stream?p=&e=&t=`); the plugin joins it to
  the Prerolls Max address it was configured with and sends `X-Api-Key` when
  downloading. Links expire after an hour.
- Item ids on Emby are Emby's numeric `InternalId`s; on Jellyfin, Guids
  without dashes.
- `is_first_in_session`: the plugin decides from its own memory plus the
  user's play history (gap set on the plugin page, default 4 hours). If it
  doesn't send it for an episode, Prerolls Max works it out the same way from
  the requests it has seen.
- Errors use section 1. The endpoint never answers 404 (plugins read 404 as
  "older Prerolls Max" and fall back to v1). 401 codes: `plugin_key_required`
  (login on, no key), `plugin_key_rejected` (wrong or expired key); 400
  `api_key_in_url` for `?api_key=`.
- The plugin waits at most its timeout (default 3 s). If Prerolls Max is down
  it plays the last non-empty list it received ("last known good"); intros
  still downloading play from the next playback on.
- `intentional_empty: true` means zero intros on purpose: the title is on the
  never-play list or has a no-intro tag. The plugin plays nothing and keeps
  its last known good list. Any empty answer (also "nothing is set to play")
  plays nothing and never replaces that list; only a non-empty answer does.
  Pool answers (`all=1`) always say `false`.

Rule kinds that use these facts (`sequence_conditions.py`): `rating`, `user`,
`library`, `first_in_session`, alongside `media_type`, `genre`, `tag`,
`file_name`, `audio_format`. On Plex they are unknown, so they count as not
met and the block's Otherwise plays.

## 8. Words in the interface

| Use | Not |
|---|---|
| Intro video | preroll (the word "preroll" may appear in help text) |
| Collection | category |
| When they play / schedule | schedule rule, cron |
| Default intros | filler |
| Movie trailers | NeX-Up |
| Playlist (Advanced) | sequence |
| If schedules overlap | priority / blend / exclusive |
| Media server | Plex/Jellyfin/Emby connector |
| Video maker | generator studio |

## 9. Smart features

User-facing explanations: `docs/features/*.md`. All routes use section 1
errors; jobs report through `GET /api/jobs/{id}` (section 5).

Admin only (an admin account or a full-access API key, the same check as the
other admin routes; with login off they are open like those): `POST`/`PUT`/
`DELETE /api/watch-folders...` and `POST /api/watch-folders/{id}/check` (they
read server folders), `POST /api/media/loudness/normalize` with
`mode: "replace"`, `PUT /api/smart-settings` and `DELETE /api/stats`. Anyone
else signed in gets 403 `admin_required`; nobody signed in, 401
`login_required`. Every read, and the media jobs that keep the originals, stay
open to everyone signed in.

New `/api/capabilities` feature keys (section 6): `rule_sets`, `year_rules`,
`kids_safe`, `exclude_titles`, `weights_cooldowns`, `play_history`,
`missed_intro_check`, `combined_file`, `loudness`, `matching_versions`,
`watch_folders`. Plex: `rule_sets` and `exclude_titles` are `none`;
`kids_safe`, `year_rules`, `weights_cooldowns`, `play_history`,
`missed_intro_check` are `emulated`; the file tools are `native`.

New rule kinds for Playlist (Advanced) conditions: `kids_safe`
(`unrated_is_safe`, optional `ratings`) and `year` (`decades`, `from`, `to`).

### Rules (Jellyfin/Emby, checked before schedules)

```
GET    /api/rules            -> {rules: [Rule], fallback: "plain sentence"}
POST   /api/rules            RuleIn -> Rule        (position optional, default last)
GET    /api/rules/{id}       -> Rule
PUT    /api/rules/{id}       RuleIn -> Rule
DELETE /api/rules/{id}       -> {deleted: true}
PUT    /api/rules/order      {ids: [every rule id]} -> {rules}
POST   /api/rules/preview    {item: {item_type: Movie|Episode, item_name, item_id, series_name, series_id,
                              genres[], tags[], official_rating, year, library_name, library_id,
                              user_name, user_id, first_in_session}}
  -> {excluded, matched: {id, name} | null, explanation, would_play: [{id, name}] (in_order),
      pool: [{id, name}] (random), count, order, checks: [{rule_id, name, matched, why}], fallback}

RuleIn = {name, enabled, position?,
  when: {genres[], ratings[], kids_safe: bool, decades["1980s"], year_from, year_to,
         libraries[], users[], media_type: movie|episode|any, first_episode_only: bool},
  play: {collection_id | preroll_ids[], count (1-20, null = 1 random / all in order),
         order: random|in_order, cooldown_hours (0-720)}}
Rule = RuleIn + {id, summary, collection_name, plays: [{id, name}], problem: null | "sentence"}
```

`kids_safe: false` means "doesn't matter", not "not kids-safe".

```
GET    /api/exclusions       -> {items: [{id, kind, kind_label, value, note, created_at}],
                                 auto_tags: {enabled, tags[], note}}
POST   /api/exclusions       {kind: item|title|tag, value, note?}   409 already_excluded
DELETE /api/exclusions/{id}
GET    /api/ratings          -> {families: [{id, name, ratings: [{value, label, kids_safe}]}],
                                 kids_safe[], unrated_is_kids_safe}
GET    /api/smart-settings   -> {binge_window_hours 4, kids_safe_ratings[], unrated_is_kids_safe,
                                 honor_no_intro_tags, no_intro_tags[], history_enabled,
                                 history_retention_days 90, backup_includes_history false,
                                 loudness_target_lufs -23, loudness_tolerance_lu 2, watch_sessions}
PUT    /api/smart-settings   any subset (extra keys refused) -> all + plugins_updated[] when the
                             binge gap changed: [{server, updated, message}]
```

`/plugin/v2/intros` checks the never-play list (ids, titles, tags, and
`no-intro`/`nointro` tags) and then the rules; `reason` explains the match
("Matches 'Kids' because the movie is rated PG, which is kids-safe."). Pool
requests (`all=1`) include every enabled rule's intros.

### Weights, cooldowns, watch folders

```
GET  /api/weights?collection_id=    -> {items: [{preroll_id, name, weight, last_played, resting_until}],
                                        cooldown_hours, collection, note}
PUT  /api/weights                   {items: [{preroll_id, weight 1-10}]} -> {updated}
PUT  /api/collections/{id}/cooldown {cooldown_hours 0-720} -> {collection_id, name, cooldown_hours, summary}

GET    /api/watch-folders           -> [{id, path, collection_id, collection_name, mode: link|copy,
                                         recursive, enabled, exists, imported_count, last_checked_at,
                                         problem, waiting: [{name, seconds, why}]}]
POST   /api/watch-folders           {path, collection_id?, mode, recursive, enabled}
PUT    /api/watch-folders/{id}      same body
DELETE /api/watch-folders/{id}
POST   /api/watch-folders/{id}/check -> {imported: [{preroll_id, name}], waiting, errors[], note}
```

### Backups

`GET /backup/database` (schema_version 6) adds `intro_rules` (in order: `{name,
enabled, position, when, play}` with the old collection and intro ids),
`intro_exclusions`, `watch_folders` (`{path, collection_id, collection_name,
mode, recursive, enabled, imported_count, imported_keys}`), `smart_settings`
(only the ones changed from the defaults), `play_history_included` and, only
when `backup_includes_history` is on, `play_history`. Intro rows carry `weight`
and collection rows `cooldown_hours`. The system ZIP's database file has the
play history tables (`intro_plays`, `playback_checks`) emptied unless that
setting is on.

`POST /restore/database` replaces each of these parts only when the backup has
it (older backups leave them alone), points rules and watch folders at the new
collection and intro ids, and checks every entry the way the API does (watch
folder paths through `clean_folder_path`). Entries it can't use are left out
and named in `skipped`; `smart_features` counts what came back.
`POST /restore/files` checks the restored database's watch folders the same
way and adds `skipped` too.

### Play history and missed intros

```
GET    /api/stats/recent?limit&server&user&client&days -> {items: [Play], history_enabled, retention_days, note}
GET    /api/stats/top?days=30&order=most|least&limit   -> {items: [{preroll_id, name, plays, last_played}]}
GET    /api/stats/never-played?days                    -> {items: [{preroll_id, name, collections, added}]}
GET    /api/stats/summary?days=30                      -> {total_plays, by_user, by_server, by_client, by_day}
DELETE /api/stats                                      -> {removed}
GET    /api/health/intros?days=7  -> {status: ok|info|warning|unknown, message, playbacks, with_intros,
                                      watching: {plex|jellyfin|emby: {ok, message, seconds_ago}},
                                      warnings: [{id, severity: warning|info, server, client, title,
                                                  reason, fix, count, last_seen, examples}]}
Play = {id, played_at, preroll_id, name, server_type, server_name, user_name, client, device,
        item_name, item_type, source: plugin|plex_sessions, rule_name}
```

### Media tools (jobs)

```
GET  /api/media/status                -> {ffmpeg, tonemap, profiles, frame_rates}
GET  /api/media/info/{preroll_id}     -> {format, width, height, hdr, ..., matches_1080p_sdr, advice,
                                          versions: [{id, name, label, enabled}], version_of}
GET  /api/media/loudness              -> {target_lufs, tolerance_lu, median_lufs, counts,
                                          outliers[], items: [{preroll_id, name, lufs, peak, lra,
                                          checked_at, status: unchecked|ok|loud|quiet|peaks|silent, label}]}
POST /api/media/loudness/check        {preroll_ids?: [], only_unchecked?} -> {job_id}
POST /api/media/loudness/normalize    {preroll_ids, target_lufs?, mode: new_version|replace,
                                       use_instead: true} -> {job_id}
POST /api/media/versions              {preroll_ids, profiles: ["1080p"|"720p"|"2160p"], frame_rate,
                                       use_instead: true, skip_matching: true} -> {job_id}
POST /api/media/combine               {preroll_ids[] | sequence_id, name, profile, frame_rate,
                                       match_loudness: true, collection_id?} -> {job_id}
```

Job results: loudness check `{checked}`; normalize `{target_lufs, mode, items:
[{preroll_id, name, new_preroll_id, before_lufs, after_lufs, original_in_trash?}]}`;
versions `{made: [{preroll_id, name, profile, new_preroll_id, format, was,
tone_mapped}], skipped: [{..., why}], note}`; combine `{preroll_id, name, path,
duration_seconds, format, parts[], note}`. Per-item problems are in the job's
`errors`. `use_instead` moves the new version into the original's collections
and switches the original off (`enabled: false`); new prerolls carry
`version_of` and `version_label`.

## 10. Names and adding videos

- **One name each.** Schedules, playlists and rules need a name no other item of
  the same kind has (case and extra spaces ignored, `backend/unique_names.py`).
  Saving a taken name: 409 `name_taken`, `fields.name` = "There's already a
  schedule called 'Halloween'. Pick another name." An edit that keeps the item's
  own name is never refused (old databases can hold two). Imports and restores
  add " (2)", " (3)" instead and list the renames: `renamed: [sentences]` in
  `POST /restore/database` and `/sequences/import-bundle-confirm`;
  `/sequences/import` offers `suggested_name`.
- **Built-in collections.** The collections Prerolls Max fills itself carry
  `Category.system_key` (`backend/system_collections.py`): `movie_trailers`
  ("Movie trailers"), `tv_trailers` ("TV trailers"), `video_maker` ("Video
  maker") and `coming_soon_lists` ("Coming Soon Lists"). Code finds them by key,
  never by name. On every start and at the end of `POST /restore/database`,
  rows without a key are tagged by NeXroll's names ("NeX-Up Movie Trailers",
  "NeX-Up TV Trailers", "NeX-Up Prerolls") and renamed, unless the person
  already has a collection with the new name (ignoring case): then it becomes
  "Movie trailers (built-in)". Backups carry `system_key` on each category;
  `.nexseq` imports read the old names as the new ones. `POST
  /nexup/sequence/create` numbers a taken playlist name (" (2)") and lists it
  in `renamed`, like the imports.
- **Duplicates.** `POST /prerolls/upload` with form field `if_duplicate=ask`:
  a file whose SHA-256 matches a library video is not added; the answer is
  `{uploaded: false, duplicate: true, token, existing: {id, name}, message,
  keep_minutes: 15}`. `POST /prerolls/upload/staged/{token}` `{action: "add" |
  "skip"}` adds the parked copy (the upload's answer) or drops it; an expired
  token is 410 `staged_expired`. Without `if_duplicate` uploads behave as
  before. Watch folders skip exact duplicates and report `duplicate_count`.
- **Web links.** `POST /api/library/from-link` `{url, collection_id?}` ->
  `{job_id}`; the job's `result` is the upload answer above (or a duplicate).
  `backend/link_fetch.py` holds the rules (http/https only, every address and
  redirect checked, private addresses only with the admin setting
  `links_allow_home_network`); `frontend/src/lib/videoLink.ts` mirrors the
  link check and its messages.
- **Plugin cache (plugin 2.1).** Each intro is kept as
  `intro_cache/<12 hex>-<8 hex>/<Safe Name>.<ext>` (intro id and version, then
  its name), so servers list it by name. 2.0's `<24 hex>-<12 hex>.<ext>` files
  are moved on upgrade and their library items removed.

## 11. Moving from NeXroll

Prerolls Max replaces NeXroll; the interface says so in Settings, the first-run
guide and Help (`moving-from-nexroll`). Routes in `app/backend/routers/nexroll_migrate.py`:

```
GET  /api/migrate/nexroll          (admin) -> {found: [{path, folder, modified}], platform, library_dir,
                                               import: {last: Report | null, waiting: {count, folder, examples}},
                                               alongside: Alongside}
POST /api/migrate/nexroll/scan     (admin) {path?}           -> {job_id, path}   nexroll.db, copied read-only
POST /api/migrate/nexroll/upload   (admin) multipart file    -> {job_id}         NeXroll .json or full .zip
POST /api/migrate/nexroll/fetch    (admin) {url, api_key?}   -> {job_id}         NeXroll's GET /backup/database,
                                    X-Api-Key header; address and key are checked first (fields url, api_key)
     job result: {source_id, preview: {counts, servers, keys, missing, names_taken, library_empty,
                  suggested_mode, skipped, left_behind}}   (source kept for an hour; 410 source_expired)
POST /api/migrate/nexroll/import   (admin) {source_id, mode: replace|merge, include_keys, confirm_replace}
     -> {job_id}; replace without confirm_replace is 409 confirm_replace.
     Report = {mode, added, matched, renamed[], skipped[], notes[], keys_imported[], videos_copied,
               settings: replaced|kept, missing: {count, ids, folder, folder_exists_here, examples}, message}
POST /api/migrate/nexroll/relink   (admin) {from_folder, to_folder} -> {relinked, still_missing, examples, message}
GET  /api/migrate/nexroll/detect?refresh= -> {alongside, summary, servers, warnings: [{id, severity, server,
                                              title, message, fix, help}]}
POST /api/migrate/nexroll/detect/dismiss  {id}   (hidden for a day)
PUT  /api/migrate/nexroll/alongside (admin) {mode?: replace|alongside, nexroll_servers?: [id], port?, clear_port?}
     -> Alongside = {mode, servers: [{id, name, type, manager}], summary, conflicts[],
                     port: {running, configured, source: environment|settings|default, saved, in_docker,
                            restart_needed}}
PUT  /api/servers/{id}/manager     (admin) {manager: prerollsmax|nexroll} -> {id, name, managed_by, alongside}
```

- NeXroll's user accounts and API keys never come over; Prerolls Max keeps its own `auth_*` settings.
  Merge joins collections by name, reuses videos by path or fingerprint, and names clashing schedules
  and playlists "Name (2)" (section 10). Replace uses `POST /restore/database`.
- Media servers in NeXroll's settings become rows (section 10) when no server has that address.
- Imported videos whose files aren't reachable are listed in `nexroll_import.json` next to the database,
  and the library clean-up leaves them alone until they are relinked.
- `Server` (section 10) adds `managed_by: prerollsmax|nexroll`. A server left to NeXroll (only in
  `alongside` mode, `coexist.json` next to the database): its Plex intro list is never written or
  checked, and `/plugin/v2/intros` answers `items: []` with `intentional_empty: true`.
- Port: `PMAX_PORT`, then `startup.json` next to the database (`{"port": n}`), then 9393. A taken
  port at start prints one plain line ("Port 9393 is already in use, probably by NeXroll...").
