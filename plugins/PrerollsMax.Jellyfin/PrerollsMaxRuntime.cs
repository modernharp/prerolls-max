using System.Collections.Concurrent;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Library;
using MediaBrowser.Model.Entities;
using MediaBrowser.Model.IO;
using Microsoft.Extensions.Logging;
using PrerollsMax.Shared;

namespace PrerollsMax.Jellyfin;

/// <summary>
/// The plugin's long-lived parts: one HTTP client source, one intro folder, one
/// binge tracker. Registered as a singleton (see <see cref="ServiceRegistrator"/>).
/// </summary>
public sealed class PrerollsMaxRuntime
{
    public const string HttpClientName = "PrerollsMax";

    private readonly ILogger<PrerollsMaxRuntime> _logger;
    private readonly ILibraryManager _libraryManager;
    private readonly IFileSystem _fileSystem;
    private readonly Lazy<IntroPicker> _picker;
    private readonly ConcurrentDictionary<string, SemaphoreSlim> _registerLocks = new(StringComparer.Ordinal);
    private readonly SemaphoreSlim _prefetchLock = new(1, 1);
    private DateTime _lastPrefetch = DateTime.MinValue;

    public PrerollsMaxRuntime(
        IHttpClientFactory httpClientFactory,
        ILogger<PrerollsMaxRuntime> logger,
        ILibraryManager libraryManager,
        IFileSystem fileSystem)
    {
        _logger = logger;
        _libraryManager = libraryManager;
        _fileSystem = fileSystem;
        var log = new Log(logger);
        _picker = new Lazy<IntroPicker>(() =>
        {
            var client = new PrerollsMaxClient(() => httpClientFactory.CreateClient(HttpClientName), log, "jellyfin", Plugin.PluginVersion);
            return new IntroPicker(client, new IntroCache(Plugin.CacheDirectory, log), log);
        });
    }

    public IntroPicker Picker => _picker.Value;

    public BingeTracker Binges { get; } = new();

    /// <summary>The current settings, or null when the plugin isn't set up yet.</summary>
    public static ClientSettings? CurrentSettings()
    {
        var config = Plugin.Instance?.Configuration;
        if (config is null || string.IsNullOrWhiteSpace(config.PrerollsMaxUrl))
        {
            return null;
        }

        return new ClientSettings
        {
            BaseUrl = config.PrerollsMaxUrl,
            ApiKey = config.ApiKey,
            TimeoutSeconds = config.TimeoutSeconds,
            PathPrefixFrom = config.PathPrefixFrom,
            PathPrefixTo = config.PathPrefixTo,
        };
    }

    /// <summary>
    /// Download ahead and tidy the folder, at most every few minutes. Runs in the
    /// background after playbacks and from the scheduled task.
    /// </summary>
    public async Task PrefetchAsync(bool force, CancellationToken ct)
    {
        var settings = CurrentSettings();
        if (settings is null)
        {
            return;
        }

        if (!force && DateTime.UtcNow - _lastPrefetch < TimeSpan.FromMinutes(5))
        {
            return;
        }

        if (!await _prefetchLock.WaitAsync(0, ct).ConfigureAwait(false))
        {
            return;
        }

        try
        {
            _lastPrefetch = DateTime.UtcNow;
            var maxBytes = Math.Max(256, Plugin.Instance?.Configuration.MaxCacheMegabytes ?? 2048) * 1024L * 1024L;
            var removed = await Picker.PrefetchAsync(settings, maxBytes, ct).ConfigureAwait(false);
            // Jellyfin registers the moved files afresh (RegisterAsync); their old items go.
            Forget(removed.Concat(Picker.Cache.TakeGone()));
        }
        catch (Exception ex)
        {
            _logger.LogWarning("Prerolls Max: downloading intros ahead failed: {Message}", ex.Message);
        }
        finally
        {
            _prefetchLock.Release();
        }
    }

    /// <summary>Start <see cref="PrefetchAsync"/> without waiting for it.</summary>
    public void PrefetchInBackground() => _ = Task.Run(() => PrefetchAsync(false, CancellationToken.None));

    /// <summary>
    /// Make sure Jellyfin has the file as a video item; Jellyfin drops intros that
    /// aren't items. One registration per file at a time.
    /// </summary>
    public async Task<Guid?> RegisterAsync(string file, string name)
    {
        var gate = _registerLocks.GetOrAdd(file, _ => new SemaphoreSlim(1, 1));
        await gate.WaitAsync().ConfigureAwait(false);
        try
        {
            var resolved = _libraryManager.ResolvePath(_fileSystem.GetFileSystemInfo(file));
            if (resolved is not Video video)
            {
                _logger.LogWarning("Prerolls Max: Jellyfin doesn't see {File} as a video", file);
                return null;
            }

            var info = new FileInfo(file);
            var title = string.IsNullOrWhiteSpace(name) ? Path.GetFileNameWithoutExtension(file) : name;
            var existing = _libraryManager.GetItemById(video.Id);
            if (existing is Video)
            {
                if (!ChangedSinceRegistered(existing, info))
                {
                    if (!string.Equals(existing.Name, title, StringComparison.Ordinal))
                    {
                        // Renamed in Prerolls Max: show the new name in Jellyfin too.
                        existing.Name = title;
                        await existing.UpdateToRepositoryAsync(ItemUpdateType.MetadataEdit, CancellationToken.None).ConfigureAwait(false);
                    }

                    return video.Id;
                }

                // Rewritten in place (a mapped folder): register afresh so Jellyfin reads its length again.
                _libraryManager.DeleteItem(existing, new DeleteOptions { DeleteFileLocation = false });
            }

            video.Name = title;
            video.DateModified = info.LastWriteTimeUtc;
            _libraryManager.CreateItem(video, null);
            _logger.LogInformation("Prerolls Max: registered intro '{Name}' with Jellyfin", video.Name);
            return video.Id;
        }
        catch (Exception ex)
        {
            _logger.LogWarning("Prerolls Max: couldn't register {File} with Jellyfin: {Message}", file, ex.Message);
            return null;
        }
        finally
        {
            gate.Release();
        }
    }

    /// <summary>Remove the Jellyfin items of files the cache moved or deleted.</summary>
    public void Forget(IEnumerable<string> files)
    {
        foreach (var file in files)
        {
            try
            {
                var item = _libraryManager.FindByPath(file, false);
                if (item is not null)
                {
                    _libraryManager.DeleteItem(item, new DeleteOptions { DeleteFileLocation = false });
                }
            }
            catch (Exception ex)
            {
                _logger.LogDebug("Prerolls Max: couldn't remove the Jellyfin item for {File}: {Message}", file, ex.Message);
            }

            _registerLocks.TryRemove(file, out _);
        }
    }

    private static bool ChangedSinceRegistered(BaseItem existing, FileInfo file)
    {
        if (!file.Exists)
        {
            return false;
        }

        if (existing.Size is long size && size > 0 && size != file.Length)
        {
            return true;
        }

        var recorded = existing.DateModified.Kind == DateTimeKind.Local
            ? existing.DateModified.ToUniversalTime()
            : DateTime.SpecifyKind(existing.DateModified, DateTimeKind.Utc);
        return file.LastWriteTimeUtc > recorded.AddSeconds(1);
    }

    private sealed class Log : IPluginLog
    {
        private readonly ILogger _logger;

        public Log(ILogger logger) => _logger = logger;

        public void Debug(string message) => _logger.LogDebug("{Message}", message);

        public void Info(string message) => _logger.LogInformation("{Message}", message);

        public void Warn(string message) => _logger.LogWarning("{Message}", message);
    }
}
