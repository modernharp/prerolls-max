using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using PrerollsMax.Shared;

namespace PrerollsMax.Jellyfin;

/// <summary>What the settings page's Test button sends: the values as typed, saved or not.</summary>
public class TestConnectionBody
{
    public string PrerollsMaxUrl { get; set; } = string.Empty;

    public string ApiKey { get; set; } = string.Empty;
}

/// <summary>
/// Endpoints for the plugin's settings page. Jellyfin calls Prerolls Max itself,
/// so the browser needs no access to Prerolls Max and nothing depends on CORS.
/// </summary>
[ApiController]
[Route("PrerollsMax")]
[Authorize(Policy = "RequiresElevation")]
public class PrerollsMaxController : ControllerBase
{
    private readonly PrerollsMaxRuntime _runtime;

    public PrerollsMaxController(PrerollsMaxRuntime runtime)
    {
        _runtime = runtime;
    }

    /// <summary>Check the address and key, and say what's wrong in plain words.</summary>
    [HttpPost("Test")]
    public async Task<ActionResult<ConnectionReport>> Test([FromBody] TestConnectionBody body, CancellationToken ct)
    {
        var report = await _runtime.Picker.Client.TestAsync(body.PrerollsMaxUrl, body.ApiKey, ct).ConfigureAwait(false);
        return Ok(report);
    }

    /// <summary>Download intros now (also runs every 30 minutes).</summary>
    [HttpPost("Prefetch")]
    public async Task<ActionResult> Prefetch(CancellationToken ct)
    {
        await _runtime.PrefetchAsync(true, ct).ConfigureAwait(false);
        return Ok(new { pending = _runtime.Picker.Cache.PendingDownloads });
    }
}
