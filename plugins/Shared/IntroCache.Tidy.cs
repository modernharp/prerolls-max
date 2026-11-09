namespace PrerollsMax.Shared;

/// <summary>Keeping the intro folder tidy and within its size limit.</summary>
public sealed partial class IntroCache
{
    /// <summary>
    /// Remove what isn't needed: older versions of intros in <paramref name="keep"/>,
    /// files unused for <paramref name="unusedFor"/>, files left by version 2.0 of the
    /// plugin, then the least recently used until the folder fits in
    /// <paramref name="maxBytes"/>. Never removes a file in <paramref name="keep"/> or one
    /// being downloaded. Returns the removed paths, so the media server can forget them
    /// too (moved files: <see cref="TakeMoves"/>).
    /// </summary>
    public IReadOnlyList<string> Prune(IEnumerable<IntroEntry> keep, long maxBytes, TimeSpan unusedFor)
    {
        var removed = new List<string>();
        if (!Directory.Exists(_dir))
        {
            return removed;
        }

        var keepFiles = new HashSet<string>(keep.Select(FileFor), StringComparer.Ordinal);
        var current = new HashSet<string>(keepFiles.Select(f => CacheNames.KeyOfFile(_dir, f)), StringComparer.Ordinal);
        foreach (var lkg in _lastKnownGood.Values)
        {
            foreach (var e in lkg)
            {
                // A remembered list may name a version that has since been replaced;
                // the replacement stands in for it (AnyCopy finds it by key).
                var file = FileFor(e);
                if (!current.Contains(CacheNames.KeyOfFile(_dir, file)))
                {
                    keepFiles.Add(file);
                }
            }
        }

        var keepKeys = new HashSet<string>(keepFiles.Select(f => CacheNames.KeyOfFile(_dir, f)), StringComparer.Ordinal);
        // Intros whose current file the server can't play yet: their older copies stay.
        var waiting = Playable is null
            ? new HashSet<string>(StringComparer.Ordinal)
            : new HashSet<string>(keepFiles.Where(f => File.Exists(f) && !Playable(f)).Select(f => CacheNames.KeyOfFile(_dir, f)),
                StringComparer.Ordinal);
        var now = DateTime.UtcNow;
        var candidates = new List<(string Path, DateTime Used, long Size)>();
        long total = 0;

        foreach (var file in Directory.EnumerateFiles(_dir, "*", SearchOption.AllDirectories))
        {
            if (file.EndsWith(PartSuffix, StringComparison.Ordinal))
            {
                // Left behind by a crash or a stopped server.
                if (now - File.GetLastWriteTimeUtc(file) > TimeSpan.FromHours(1) && TryDelete(file))
                {
                    removed.Add(file);
                }

                continue;
            }

            if (!IsVideo(file))
            {
                continue;
            }

            long size;
            try
            {
                size = new FileInfo(file).Length;
            }
            catch (IOException)
            {
                continue;
            }

            if (keepFiles.Contains(file) || _inflight.ContainsKey(file))
            {
                total += size;
                continue;
            }

            var used = _lastUsed.TryGetValue(file, out var u) ? u : File.GetLastWriteTimeUtc(file);
            if (waiting.Contains(CacheNames.KeyOfFile(_dir, file)))
            {
                total += size;
                continue;
            }

            if (CacheNames.IsLegacy(_dir, file) || keepKeys.Contains(CacheNames.KeyOfFile(_dir, file)) || now - used > unusedFor)
            {
                // A file from version 2.0 (anything still needed was moved to its named
                // file above), an older version of something current, or nothing has
                // asked for it in a while.
                if (TryDelete(file))
                {
                    removed.Add(file);
                    _lastUsed.TryRemove(file, out _);
                }

                continue;
            }

            total += size;
            candidates.Add((file, used, size));
        }

        foreach (var (file, _, size) in candidates.OrderBy(c => c.Used))
        {
            if (total <= maxBytes)
            {
                break;
            }

            if (TryDelete(file))
            {
                removed.Add(file);
                _lastUsed.TryRemove(file, out _);
                total -= size;
            }
        }

        RemoveEmptyFolders();
        SaveIndex();
        if (removed.Count > 0)
        {
            _log.Info($"Prerolls Max: removed {removed.Count} intro file(s) no longer needed from {_dir}.");
        }

        return removed;
    }

    private void RemoveEmptyFolders()
    {
        try
        {
            foreach (var folder in Directory.EnumerateDirectories(_dir))
            {
                if (!Directory.EnumerateFileSystemEntries(folder).Any())
                {
                    Directory.Delete(folder);
                }
            }
        }
        catch (Exception)
        {
            // Tidying only; next time.
        }
    }
}
