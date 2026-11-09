using MediaBrowser.Model.Tasks;

namespace PrerollsMax.Jellyfin;

/// <summary>
/// Downloads every intro that could play now, so the first playback doesn't
/// have to wait, and tidies the intro folder. Runs at startup and every 30 minutes.
/// </summary>
public class PrefetchTask : IScheduledTask
{
    private readonly PrerollsMaxRuntime _runtime;

    public PrefetchTask(PrerollsMaxRuntime runtime)
    {
        _runtime = runtime;
    }

    public string Name => "Download Prerolls Max intros";

    public string Key => "PrerollsMaxPrefetch";

    public string Description => "Downloads the intro videos Prerolls Max may play, and removes ones it no longer uses.";

    public string Category => "Prerolls Max";

    public async Task ExecuteAsync(IProgress<double> progress, CancellationToken cancellationToken)
    {
        progress.Report(0);
        await _runtime.PrefetchAsync(true, cancellationToken).ConfigureAwait(false);
        progress.Report(100);
    }

    public IEnumerable<TaskTriggerInfo> GetDefaultTriggers()
    {
        return new[]
        {
            new TaskTriggerInfo { Type = TaskTriggerInfoType.StartupTrigger },
            new TaskTriggerInfo { Type = TaskTriggerInfoType.IntervalTrigger, IntervalTicks = TimeSpan.FromMinutes(30).Ticks },
        };
    }
}
