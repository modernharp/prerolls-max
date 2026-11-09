using System.Collections.Concurrent;
using System.Diagnostics;

namespace PrerollsMax.Shared;

/// <summary>One intro ready to hand to the media server.</summary>
public sealed record ReadyIntro(IntroEntry Entry, string File);

/// <summary>
/// Turns Prerolls Max's answer into files the media server can play, inside the
/// playback's time budget. Shared by the Jellyfin and Emby plugins.
/// </summary>
public sealed class IntroPicker
{
    private readonly PrerollsMaxClient _client;
    private readonly IntroCache _cache;
    private readonly IPluginLog _log;

    public IntroPicker(PrerollsMaxClient client, IntroCache cache, IPluginLog log)
    {
        _client = client;
        _cache = cache;
        _log = log;
    }

    public IntroCache Cache => _cache;

    public PrerollsMaxClient Client => _client;

    /// <summary>
    /// The intros for one playback, in order. Never takes much longer than the
    /// configured timeout: intros still downloading when the time is up are skipped
    /// this time and play from the next playback on.
    /// </summary>
    public async Task<IReadOnlyList<ReadyIntro>> PickAsync(ClientSettings settings, IntroRequest request, CancellationToken ct)
    {
        var clock = Stopwatch.StartNew();
        IReadOnlyList<IntroEntry> entries;
        try
        {
            var answer = await _client.GetIntrosAsync(settings, request, ct).ConfigureAwait(false);
            entries = answer.Items;
            // Only a real list becomes the fallback for when Prerolls Max is unreachable.
            // An empty answer (a never-play title, a no-intro tag, nothing set) plays
            // nothing now but must not wipe that list for every later playback.
            if (entries.Count > 0)
            {
                _cache.SaveLastKnownGood(request.ItemType, entries);
            }
            else if (answer.IntentionalEmpty)
            {
                _log.Debug("Prerolls Max: no intros for this one on purpose; the fallback list is kept.");
            }

            if (!string.IsNullOrWhiteSpace(answer.Reason))
            {
                _log.Debug($"Prerolls Max: {answer.Reason}");
            }
        }
        catch (PrerollsMaxRejectedException ex)
        {
            _log.Warn(ex.Message);
            return Array.Empty<ReadyIntro>();
        }
        catch (PrerollsMaxUnavailableException ex)
        {
            entries = _cache.LastKnownGood(request.ItemType);
            _log.Warn(ex.Message + " " + (entries.Count > 0
                ? $"Playing the {entries.Count} intro(s) it chose last time."
                : "No intros this time."));
        }

        if (entries.Count == 0)
        {
            return Array.Empty<ReadyIntro>();
        }

        var found = new string?[entries.Count];
        var waiting = new Dictionary<int, Task<string?>>();
        for (var i = 0; i < entries.Count; i++)
        {
            var entry = entries[i];
            var local = MapPath(entry.Path, settings);
            if (!string.IsNullOrEmpty(local) && !local.StartsWith(@"\\", StringComparison.Ordinal) && File.Exists(local))
            {
                found[i] = local;
                continue;
            }

            found[i] = _cache.Ready(entry);
            if (found[i] is null && !string.IsNullOrWhiteSpace(entry.StreamUrl))
            {
                waiting[i] = _cache.EnsureAsync(entry, (tmp, token) => _client.DownloadAsync(settings, entry, tmp, token));
            }
        }

        if (waiting.Count > 0)
        {
            var left = settings.Timeout - clock.Elapsed;
            if (left > TimeSpan.Zero)
            {
                try
                {
                    await Task.WhenAny(Task.WhenAll(waiting.Values), Task.Delay(left, ct)).ConfigureAwait(false);
                }
                catch (OperationCanceledException)
                {
                }
            }

            foreach (var (i, task) in waiting)
            {
                found[i] = task.IsCompletedSuccessfully ? task.Result : null;
                // A new version still downloading: the copy from before beats nothing.
                found[i] ??= _cache.AnyCopy(entries[i]);
            }

            var late = waiting.Count(kv => found[kv.Key] is null);
            if (late > 0)
            {
                _log.Info($"Prerolls Max: {late} intro(s) are still downloading and will play from the next playback on.");
            }
        }

        var ready = new List<ReadyIntro>();
        for (var i = 0; i < entries.Count; i++)
        {
            if (found[i] is { } file)
            {
                ready.Add(new ReadyIntro(entries[i], file));
            }
        }

        return ready;
    }

    /// <summary>
    /// Download every intro that could play now (movies and episodes), then tidy the
    /// folder. Returns the files removed, so the media server can forget them.
    /// </summary>
    public async Task<IReadOnlyList<string>> PrefetchAsync(ClientSettings settings, long maxBytes, CancellationToken ct)
    {
        var pool = new ConcurrentDictionary<string, IntroEntry>(StringComparer.Ordinal);
        var reachable = false;
        foreach (var kind in new[] { "Movie", "Episode" })
        {
            try
            {
                var answer = await _client.GetPoolAsync(settings with { TimeoutSeconds = 30 }, kind, ct).ConfigureAwait(false);
                reachable = true;
                foreach (var e in answer.Items)
                {
                    pool[_cache.FileFor(e)] = e;
                }
            }
            catch (Exception ex) when (ex is PrerollsMaxUnavailableException or PrerollsMaxRejectedException)
            {
                _log.Warn($"Prerolls Max: couldn't list intros to download ahead: {ex.Message}");
                break;
            }
        }

        if (!reachable)
        {
            return Array.Empty<string>();
        }

        var downloads = pool.Values
            .Where(e => string.IsNullOrEmpty(MapPath(e.Path, settings)) || !File.Exists(MapPath(e.Path, settings)))
            .Select(e => _cache.EnsureAsync(e, (tmp, token) => _client.DownloadAsync(settings, e, tmp, token)))
            .ToList();
        await Task.WhenAll(downloads).ConfigureAwait(false);
        return _cache.Prune(pool.Values, maxBytes, TimeSpan.FromDays(14));
    }

    /// <summary>
    /// Prerolls Max's path for a file, as this server sees it, using the optional
    /// prefix pair from the settings page.
    /// </summary>
    public static string MapPath(string path, ClientSettings settings)
    {
        if (string.IsNullOrWhiteSpace(path))
        {
            return string.Empty;
        }

        if (string.IsNullOrWhiteSpace(settings.PathPrefixFrom) || string.IsNullOrWhiteSpace(settings.PathPrefixTo))
        {
            return path;
        }

        var from = settings.PathPrefixFrom.Trim().TrimEnd('/', '\\').Replace('\\', '/');
        var to = settings.PathPrefixTo.Trim().TrimEnd('/', '\\');
        var normalized = path.Replace('\\', '/');
        if (!normalized.StartsWith(from + "/", StringComparison.OrdinalIgnoreCase)
            && !string.Equals(normalized, from, StringComparison.OrdinalIgnoreCase))
        {
            return path;
        }

        var rest = normalized[from.Length..];
        return to + (to.Contains('\\') ? rest.Replace('/', '\\') : rest);
    }
}
