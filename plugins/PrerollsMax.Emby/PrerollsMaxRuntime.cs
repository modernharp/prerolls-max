using System.Net;
using MediaBrowser.Controller.Library;
using MediaBrowser.Model.Logging;
using MediaBrowser.Model.Tasks;
using PrerollsMax.Shared;

namespace PrerollsMax.Emby;

/// <summary>
/// The plugin's long-lived parts, shared by the intro provider, the scheduled task
/// and the settings endpoint. Emby has no plugin service registration, so this is
/// a process-wide singleton created on first use.
/// </summary>
public sealed class PrerollsMaxRuntime
{
    private const string RefreshIntrosTaskKey = "RefreshIntros";

    private static readonly object CreateLock = new();
    private static PrerollsMaxRuntime? _instance;

    // Emby has no IHttpClientFactory; one long-lived client with pooled connections
    // that are renewed every few minutes (so DNS changes are noticed).
    private static readonly HttpClient Http = new(new SocketsHttpHandler
    {
        PooledConnectionLifetime = TimeSpan.FromMinutes(5),
        AutomaticDecompression = DecompressionMethods.GZip | DecompressionMethods.Deflate,
    })
    {
        Timeout = Timeout.InfiniteTimeSpan,
    };

    private readonly ILogger _logger;
    private readonly ITaskManager _taskManager;
    private ILibraryManager? _libraryManager;
    private readonly SemaphoreSlim _prefetchLock = new(1, 1);
    private DateTime _lastPrefetch = DateTime.MinValue;
    private DateTime _lastRefreshQueued = DateTime.MinValue;
    private int _refreshWaiting;
    private int _tidyWaiting;
    private int _tidyTries;

    private PrerollsMaxRuntime(ILogManager logManager, ITaskManager taskManager)
    {
        _logger = logManager.GetLogger("PrerollsMax");
        _taskManager = taskManager;
        var log = new Log(_logger);
        var client = new PrerollsMaxClient(() => Http, log, "emby", Plugin.PluginVersion);
        // Emby plays only files it has registered: keep a renamed intro's old copy
        // (still registered) until the next tidy-up, after Emby has the new one.
        Picker = new IntroPicker(client, new IntroCache(Plugin.CacheDirectory, log, keepOldCopies: true), log);
        Picker.Cache.Playable = file => _libraryManager?.FindByPath(file, false) is not null;
    }

    public IntroPicker Picker { get; }

    public BingeTracker Binges { get; } = new();

    public ILogger Logger => _logger;

    public static PrerollsMaxRuntime Get(ILogManager logManager, ITaskManager taskManager, ILibraryManager? libraryManager = null)
    {
        lock (CreateLock)
        {
            _instance ??= new PrerollsMaxRuntime(logManager, taskManager);
            _instance._libraryManager ??= libraryManager;
            return _instance;
        }
    }

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
    /// Download every intro that could play, tidy the folder, and if anything
    /// changed, have Emby register the new files ("Refresh Custom Intros"), since
    /// Emby only plays intros it has registered.
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
            var before = Snapshot();
            var maxBytes = Math.Max(256, Plugin.Instance?.Configuration.MaxCacheMegabytes ?? 2048) * 1024L * 1024L;
            var removed = await Picker.PrefetchAsync(settings, maxBytes, ct).ConfigureAwait(false);
            var forgotten = Forget(removed);
            var unregistered = CachedFiles().Any(f => _libraryManager?.FindByPath(f, false) is null);
            if (!before.SetEquals(Snapshot()) || forgotten > 0 || unregistered)
            {
                QueueIntroRefresh();
            }

            _tidyTries = unregistered ? _tidyTries + 1 : 0;
            if (unregistered && _tidyTries <= 5 && Interlocked.Exchange(ref _tidyWaiting, 1) == 0)
            {
                // Older copies stay until Emby has registered the new files; look again
                // once its refresh has had time to run, so they don't linger.
                _ = Task.Run(async () =>
                {
                    await Task.Delay(TimeSpan.FromSeconds(90)).ConfigureAwait(false);
                    Interlocked.Exchange(ref _tidyWaiting, 0);
                    await PrefetchAsync(true, CancellationToken.None).ConfigureAwait(false);
                });
            }
        }
        catch (Exception ex)
        {
            _logger.Warn("Prerolls Max: downloading intros ahead failed: {0}", ex.Message);
        }
        finally
        {
            _prefetchLock.Release();
        }
    }

    public void PrefetchInBackground() => _ = Task.Run(() => PrefetchAsync(false, CancellationToken.None));

    /// <summary>
    /// The cached video files, for Emby's "Refresh Custom Intros". Each is named
    /// after its intro, which is the name Emby shows for it.
    /// </summary>
    public IEnumerable<string> CachedFiles() => Picker.Cache.NamedVideos();

    /// <summary>
    /// Remove Emby's items for files the cache deleted (old versions, old names, files
    /// from version 2.0), so no item is left pointing at a file that isn't there.
    /// Returns how many were removed.
    /// </summary>
    public int Forget(IEnumerable<string> files)
    {
        var library = _libraryManager;
        if (library is null)
        {
            return 0;
        }

        var count = 0;
        foreach (var file in files)
        {
            try
            {
                var item = library.FindByPath(file, false);
                if (item is not null)
                {
                    library.DeleteItem(item, new DeleteOptions { DeleteFileLocation = false });
                    count++;
                }
            }
            catch (Exception ex)
            {
                _logger.Debug("Prerolls Max: couldn't remove the Emby item for {0}: {1}", file, ex.Message);
            }
        }

        if (count > 0)
        {
            _logger.Info("Prerolls Max: removed {0} old intro item(s) from Emby.", count);
        }

        return count;
    }

    /// <summary>Show the intro's name from Prerolls Max on its Emby item.</summary>
    public void Name(MediaBrowser.Controller.Entities.BaseItem item, string name)
    {
        if (string.IsNullOrWhiteSpace(name) || string.Equals(item.Name, name, StringComparison.Ordinal))
        {
            return;
        }

        try
        {
            item.Name = name;
            item.UpdateToRepository(ItemUpdateType.MetadataEdit);
        }
        catch (Exception ex)
        {
            _logger.Debug("Prerolls Max: couldn't rename the Emby item for {0}: {1}", name, ex.Message);
        }
    }

    /// <summary>Ask Emby to run "Refresh Custom Intros" (at most once a minute).</summary>
    public void QueueIntroRefresh()
    {
        var wait = TimeSpan.FromMinutes(1) - (DateTime.UtcNow - _lastRefreshQueued);
        if (wait > TimeSpan.Zero)
        {
            // Asked again within the minute (a second download finished just after the
            // first): run once more when the minute is up instead of dropping it, or
            // the newer intro stays unregistered and Emby plays nothing in its place.
            if (Interlocked.Exchange(ref _refreshWaiting, 1) == 0)
            {
                _ = Task.Run(async () =>
                {
                    await Task.Delay(wait).ConfigureAwait(false);
                    Interlocked.Exchange(ref _refreshWaiting, 0);
                    QueueIntroRefresh();
                });
            }

            return;
        }

        try
        {
            var worker = _taskManager.ScheduledTasks.FirstOrDefault(t =>
                string.Equals(t.ScheduledTask?.Key, RefreshIntrosTaskKey, StringComparison.OrdinalIgnoreCase));
            if (worker is null)
            {
                _logger.Warn("Prerolls Max: Emby's \"Refresh Custom Intros\" task wasn't found, so new intros are registered at Emby's next scheduled refresh.");
                return;
            }

            _lastRefreshQueued = DateTime.UtcNow;
            _taskManager.QueueScheduledTask(worker.ScheduledTask, new TaskOptions());
            _logger.Info("Prerolls Max: asked Emby to register the downloaded intros.");
        }
        catch (Exception ex)
        {
            _logger.Warn("Prerolls Max: couldn't start \"Refresh Custom Intros\": {0}", ex.Message);
        }
    }

    private HashSet<string> Snapshot() => new(CachedFiles(), StringComparer.Ordinal);

    private sealed class Log : IPluginLog
    {
        private readonly ILogger _logger;

        public Log(ILogger logger) => _logger = logger;

        public void Debug(string message) => _logger.Debug("{0}", message);

        public void Info(string message) => _logger.Info("{0}", message);

        public void Warn(string message) => _logger.Warn("{0}", message);
    }
}
