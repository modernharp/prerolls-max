using MediaBrowser.Controller.Library;
using MediaBrowser.Model.Logging;
using MediaBrowser.Model.Tasks;

namespace PrerollsMax.Emby;

/// <summary>
/// Downloads the intros Prerolls Max may play and has Emby register them, so
/// playback never waits for a download. Runs at startup and every 30 minutes.
/// </summary>
public class PrefetchTask : IScheduledTask
{
    private readonly PrerollsMaxRuntime _runtime;

    public PrefetchTask(ILogManager logManager, ITaskManager taskManager, ILibraryManager libraryManager)
    {
        // The library is needed to remove items of files the cache moved (at startup,
        // version 2.0's hash-named files move to files named after their intro).
        _runtime = PrerollsMaxRuntime.Get(logManager, taskManager, libraryManager);
    }

    public string Name => "Download Prerolls Max intros";

    public string Key => "PrerollsMaxPrefetch";

    public string Description => "Downloads the intro videos Prerolls Max may play, registers them with Emby, and removes ones it no longer uses.";

    public string Category => "Prerolls Max";

    public async Task Execute(CancellationToken cancellationToken, IProgress<double> progress)
    {
        progress.Report(0);
        await _runtime.PrefetchAsync(true, cancellationToken).ConfigureAwait(false);
        progress.Report(100);
    }

    public IEnumerable<TaskTriggerInfo> GetDefaultTriggers()
    {
        return new[]
        {
            new TaskTriggerInfo { Type = TaskTriggerInfo.TriggerStartup },
            new TaskTriggerInfo { Type = TaskTriggerInfo.TriggerInterval, IntervalTicks = TimeSpan.FromMinutes(30).Ticks },
        };
    }
}
