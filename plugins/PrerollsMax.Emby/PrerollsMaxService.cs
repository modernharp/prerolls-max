using MediaBrowser.Controller.Net;
using MediaBrowser.Model.Logging;
using MediaBrowser.Model.Services;
using MediaBrowser.Model.Tasks;

namespace PrerollsMax.Emby;

/// <summary>The settings page's Test button: the values as typed, saved or not.</summary>
[Route("/PrerollsMax/Test", "POST", Summary = "Checks that Emby can reach Prerolls Max with this address and API key")]
[Authenticated(Roles = "admin")]
public class TestConnectionRequest : IReturn<object>
{
    public string PrerollsMaxUrl { get; set; } = string.Empty;

    public string ApiKey { get; set; } = string.Empty;
}

/// <summary>Download intros now (also runs every 30 minutes).</summary>
[Route("/PrerollsMax/Prefetch", "POST", Summary = "Downloads the intros Prerolls Max may play")]
[Authenticated(Roles = "admin")]
public class PrefetchRequest : IReturnVoid
{
}

/// <summary>
/// Endpoints for the settings page. Emby calls Prerolls Max itself, so the
/// browser needs no access to Prerolls Max and nothing depends on CORS.
/// </summary>
public class PrerollsMaxService : IService
{
    private readonly PrerollsMaxRuntime _runtime;

    public PrerollsMaxService(ILogManager logManager, ITaskManager taskManager)
    {
        _runtime = PrerollsMaxRuntime.Get(logManager, taskManager);
    }

    public async Task<object> Post(TestConnectionRequest request)
    {
        var report = await _runtime.Picker.Client.TestAsync(request.PrerollsMaxUrl, request.ApiKey, CancellationToken.None).ConfigureAwait(false);
        return new Dictionary<string, object>
        {
            ["Ok"] = report.Ok,
            ["Message"] = report.Message,
            ["ServerVersion"] = report.ServerVersion,
            ["Authenticated"] = report.Authenticated,
        };
    }

    public async Task Post(PrefetchRequest request)
    {
        await _runtime.PrefetchAsync(true, CancellationToken.None).ConfigureAwait(false);
    }
}
