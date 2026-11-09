using System.Collections.Concurrent;
namespace PrerollsMax.Shared;

/// <summary>
/// The plugin's folder of downloaded intros.
///
/// - Each intro has a folder of its own and its real name as the file name
///   (see <see cref="CacheNames"/>), so the media server lists it as
///   "Pumpkin Intro" rather than a string of letters and numbers.
/// - Each version of a file gets its own folder, so a file Prerolls Max rewrites
///   (a regenerated Coming Soon list) is downloaded again and the media server
///   registers it afresh, with the right length.
/// - Downloads never run inside a playback for longer than the playback's time
///   budget: they keep going in the background and the next play uses them.
/// - One download per file at a time, each into its own temporary name, renamed
///   into place only when complete, so a half-written file is never played.
/// - The folder is kept to a size limit, and files nothing has asked for in a while
///   are removed.
/// - The last list Prerolls Max sent is kept on disk, so intros keep playing while
///   Prerolls Max is down or restarting.
/// - Files moved here (an intro renamed in Prerolls Max, or a file from version 2.0)
///   are handed to the media server (<see cref="TakeMoves"/>) so it can forget the
///   old library item. Emby can only play files it has registered, so for Emby the
///   old file is copied instead and stays (<see cref="CopiesOf"/>) until the next
///   tidy-up, by which time Emby has registered the new one.
/// </summary>
/// <summary>An intro file the cache moved: where it was, where it is, the intro's name.</summary>
public sealed record MovedIntro(string From, string To, string Name);

public sealed partial class IntroCache
{
    public static readonly string[] VideoExtensions = { ".mp4", ".mkv", ".m4v", ".mov", ".avi", ".wmv", ".webm", ".ts", ".mpg", ".mpeg" };

    private const string PartSuffix = ".part";
    private readonly string _dir;
    private readonly IPluginLog _log;
    private readonly SemaphoreSlim _downloadSlots = new(2, 2);
    private readonly ConcurrentDictionary<string, Task<string?>> _inflight = new(StringComparer.Ordinal);
    private readonly ConcurrentDictionary<string, DateTime> _lastUsed = new(StringComparer.Ordinal);
    private readonly ConcurrentDictionary<string, List<IntroEntry>> _lastKnownGood = new(StringComparer.OrdinalIgnoreCase);
    private readonly ConcurrentQueue<MovedIntro> _moves = new();
    private readonly object _diskLock = new();
    private readonly object _moveLock = new();
    private readonly bool _keepOldCopies;

    /// <param name="keepOldCopies">Copy rather than move a renamed or old-style file,
    /// keeping the old one (still registered with the server) until the next tidy-up.</param>
    public IntroCache(string directory, IPluginLog log, bool keepOldCopies = false)
    {
        _dir = directory;
        _log = log;
        _keepOldCopies = keepOldCopies;
        try
        {
            Directory.CreateDirectory(_dir);
        }
        catch (Exception ex)
        {
            _log.Warn($"Prerolls Max: couldn't create the intro folder {_dir}: {ex.Message}");
        }

        LoadIndex();
        LoadLastKnownGood();
        MoveLastKnownGoodToNamedFiles();
    }

    public string DirectoryPath => _dir;

    /// <summary>
    /// Whether the media server can play a file yet (Emby: it's registered). While a
    /// current file can't be played, older copies of the same intro are kept.
    /// Null: every file plays as soon as it's here (Jellyfin registers on demand).
    /// </summary>
    public Func<string, bool>? Playable { get; set; }

    /// <summary>Downloads that are still running.</summary>
    public int PendingDownloads => _inflight.Count;

    /// <summary>Where this version of the intro is kept, under its own name.</summary>
    public string FileFor(IntroEntry entry)
        => Path.Combine(_dir, CacheNames.Folder(entry), CacheNames.FileName(entry));

    /// <summary>The cached copy of exactly this version, or null.</summary>
    public string? Ready(IntroEntry entry)
    {
        var file = FileFor(entry);
        if (!File.Exists(file) && !Adopt(entry, file))
        {
            return null;
        }

        MarkUsed(file);
        return file;
    }

    /// <summary>The newest cached copy of any version of this intro, or null.</summary>
    public string? AnyCopy(IntroEntry entry)
    {
        try
        {
            var key = CacheNames.Key(entry);
            var newest = AllVideos()
                .Where(f => CacheNames.KeyOfFile(_dir, f) == key)
                .OrderByDescending(File.GetLastWriteTimeUtc)
                .FirstOrDefault();
            if (newest is not null)
            {
                MarkUsed(newest);
            }

            return newest;
        }
        catch (Exception)
        {
            return null;
        }
    }

    /// <summary>
    /// Start (or join) the download of one intro. The task finishes with the cached
    /// path, or null if the download failed. It is never cancelled by a playback giving
    /// up: callers wait for it only as long as they can afford.
    /// </summary>
    public Task<string?> EnsureAsync(IntroEntry entry, Func<string, CancellationToken, Task> download)
    {
        var target = FileFor(entry);
        if (File.Exists(target) || Adopt(entry, target))
        {
            MarkUsed(target);
            return Task.FromResult<string?>(target);
        }

        // The download starts only once its task is in _inflight. Starting it inside
        // GetOrAdd's factory let a quick download finish, and try to remove itself,
        // before GetOrAdd had added it, leaving a finished task in _inflight for good
        // (PendingDownloads never reached 0 and that file was never tidied up).
        var started = new TaskCompletionSource<string?>(TaskCreationOptions.RunContinuationsAsynchronously);
        var task = _inflight.GetOrAdd(target, started.Task);
        if (ReferenceEquals(task, started.Task))
        {
            _ = Task.Run(async () =>
            {
                try
                {
                    started.SetResult(await DownloadAsync(entry, target, download).ConfigureAwait(false));
                }
                catch (Exception e)
                {
                    _inflight.TryRemove(target, out _);
                    started.SetException(e);
                }
            });
        }

        return task;
    }

    /// <summary>
    /// Files moved since the last call (old path, new path), so the media server can
    /// point the library item at the new file or drop it.
    /// </summary>
    public IReadOnlyList<MovedIntro> TakeMoves()
    {
        var list = new List<MovedIntro>();
        while (_moves.TryDequeue(out var move))
        {
            list.Add(move);
        }

        return list;
    }

    /// <summary>Every cached file of this intro (any version or name), newest first.</summary>
    public IReadOnlyList<string> CopiesOf(IntroEntry entry)
    {
        try
        {
            var key = CacheNames.Key(entry);
            return AllVideos().Where(f => CacheNames.KeyOfFile(_dir, f) == key)
                .OrderByDescending(File.GetLastWriteTimeUtc).ToList();
        }
        catch (Exception)
        {
            return Array.Empty<string>();
        }
    }

    /// <summary>The old paths of files moved since the last call.</summary>
    public IReadOnlyList<string> TakeGone() => TakeMoves().Select(m => m.From).ToList();

    /// <summary>
    /// Use a copy that's already here instead of downloading: the same version kept
    /// under the intro's old name (it was renamed in Prerolls Max), or a file from
    /// version 2.0 of the plugin kept straight in the cache folder.
    /// </summary>
    private bool Adopt(IntroEntry entry, string target)
    {
        try
        {
            var folder = Path.GetDirectoryName(target)!;
            var source = Directory.Exists(folder)
                ? Directory.EnumerateFiles(folder).FirstOrDefault(f => IsVideo(f) && !CacheNames.PathsEqual(f, target))
                : null;
            var legacy = CacheNames.Legacy(_dir, entry);
            source ??= File.Exists(legacy) ? legacy : null;
            if (source is null)
            {
                return false;
            }

            lock (_moveLock)
            {
                if (File.Exists(target))
                {
                    return true;
                }

                Directory.CreateDirectory(folder);
                if (_keepOldCopies)
                {
                    var part = target + "." + Guid.NewGuid().ToString("N")[..8] + PartSuffix;
                    File.Copy(source, part);
                    File.Move(part, target);
                }
                else
                {
                    File.Move(source, target);
                    _lastUsed.TryRemove(source, out _);
                    _moves.Enqueue(new MovedIntro(source, target, entry.Name));
                }
            }

            _log.Info($"Prerolls Max: intro '{entry.Name}' now kept as {Path.GetFileName(folder)}/{Path.GetFileName(target)}.");
            return true;
        }
        catch (Exception ex)
        {
            _log.Debug($"Prerolls Max: couldn't reuse the copy of '{entry.Name}' already here ({ex.Message}); downloading it.");
            return false;
        }
    }

    /// <summary>
    /// The intros in the last known good lists, moved to their named files at startup
    /// (version 2.0 kept them under hash names), so they keep playing even while
    /// Prerolls Max can't be reached.
    /// </summary>
    private void MoveLastKnownGoodToNamedFiles()
    {
        var moved = 0;
        foreach (var entry in _lastKnownGood.Values.SelectMany(l => l))
        {
            var target = FileFor(entry);
            if (!File.Exists(target) && File.Exists(CacheNames.Legacy(_dir, entry)) && Adopt(entry, target))
            {
                moved++;
            }
        }

        if (moved > 0)
        {
            _log.Info($"Prerolls Max: moved {moved} intro(s) to files named after them.");
            SaveIndex();
        }
    }

    private async Task<string?> DownloadAsync(IntroEntry entry, string target, Func<string, CancellationToken, Task> download)
    {
        var part = target + "." + Guid.NewGuid().ToString("N")[..8] + PartSuffix;
        try
        {
            await _downloadSlots.WaitAsync().ConfigureAwait(false);
            try
            {
                if (File.Exists(target))
                {
                    MarkUsed(target);
                    return target;
                }

                Directory.CreateDirectory(Path.GetDirectoryName(target)!);
                using var cts = new CancellationTokenSource(TimeSpan.FromMinutes(15));
                await download(part, cts.Token).ConfigureAwait(false);
                if (new FileInfo(part).Length == 0)
                {
                    throw new IOException("the download was empty");
                }

                try
                {
                    File.Move(part, target);
                }
                catch (IOException) when (File.Exists(target))
                {
                    // Someone else finished first; theirs is as good.
                }

                MarkUsed(target);
                _log.Info($"Prerolls Max: downloaded intro '{entry.Name}' ({new FileInfo(target).Length:N0} bytes).");
                return target;
            }
            finally
            {
                _downloadSlots.Release();
            }
        }
        catch (Exception ex)
        {
            _log.Warn($"Prerolls Max: couldn't download intro '{entry.Name}': {ex.Message}");
            return null;
        }
        finally
        {
            TryDelete(part);
            _inflight.TryRemove(target, out _);
        }
    }

    /// <summary>Every cached video, in the per-intro folders (not version 2.0's files).</summary>
    public IReadOnlyList<string> NamedVideos()
    {
        try
        {
            return Directory.Exists(_dir)
                ? Directory.EnumerateFiles(_dir, "*", SearchOption.AllDirectories)
                    .Where(f => IsVideo(f) && !CacheNames.IsLegacy(_dir, f)).ToList()
                : new List<string>();
        }
        catch (Exception)
        {
            return new List<string>();
        }
    }

    public static bool IsVideo(string file)
        => !file.EndsWith(PartSuffix, StringComparison.Ordinal)
           && VideoExtensions.Contains(Path.GetExtension(file).ToLowerInvariant());

    private IEnumerable<string> AllVideos()
        => Directory.Exists(_dir)
            ? Directory.EnumerateFiles(_dir, "*", SearchOption.AllDirectories).Where(IsVideo)
            : Enumerable.Empty<string>();

    private void MarkUsed(string file) => _lastUsed[file] = DateTime.UtcNow;

    private static bool TryDelete(string file)
    {
        try
        {
            if (File.Exists(file))
            {
                File.Delete(file);
                return true;
            }
        }
        catch (IOException)
        {
            // Playing right now (Windows locks it); it goes on a later prune.
        }
        catch (UnauthorizedAccessException)
        {
        }

        return false;
    }
}
