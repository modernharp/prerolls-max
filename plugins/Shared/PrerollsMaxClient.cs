using System.Globalization;
using System.Net;
using System.Text;
using System.Text.Json;

namespace PrerollsMax.Shared;

/// <summary>Prerolls Max said no to the API key.</summary>
public sealed class PrerollsMaxRejectedException : Exception
{
    public PrerollsMaxRejectedException(string message) : base(message)
    {
    }
}

/// <summary>Prerolls Max did not answer, answered too slowly, or answered with an error.</summary>
public sealed class PrerollsMaxUnavailableException : Exception
{
    public PrerollsMaxUnavailableException(string message, Exception? inner = null) : base(message, inner)
    {
    }
}

/// <summary>
/// Talks to Prerolls Max: plugin protocol v2 (<c>/plugin/v2/intros</c>), falling
/// back to v1 (<c>/plugin/intros</c>) when the server is older and answers 404.
/// The API key only ever goes in the X-Api-Key header.
/// </summary>
public sealed class PrerollsMaxClient
{
    private static readonly TimeSpan V1Memory = TimeSpan.FromMinutes(10);

    private readonly Func<HttpClient> _httpClient;
    private readonly IPluginLog _log;
    private readonly string _serverType;
    private readonly string _pluginVersion;
    private DateTime _useV1Until = DateTime.MinValue;

    /// <param name="httpClient">Gives an HttpClient (IHttpClientFactory where the server has one).</param>
    /// <param name="log">Where to log.</param>
    /// <param name="serverType">"jellyfin" or "emby".</param>
    /// <param name="pluginVersion">This plugin's version.</param>
    public PrerollsMaxClient(Func<HttpClient> httpClient, IPluginLog log, string serverType, string pluginVersion)
    {
        _httpClient = httpClient;
        _log = log;
        _serverType = serverType;
        _pluginVersion = pluginVersion;
    }

    /// <summary>What the X-PrerollsMax-Plugin header says, e.g. "jellyfin/2.0.0.0".</summary>
    public string PluginHeader => $"{_serverType}/{_pluginVersion}";

    /// <summary>The intros for one playback.</summary>
    public async Task<IntroAnswer> GetIntrosAsync(ClientSettings settings, IntroRequest request, CancellationToken ct)
    {
        if (DateTime.UtcNow >= _useV1Until)
        {
            var v2 = await SendAsync(settings, settings.NormalizedBaseUrl + "/plugin/v2/intros?" + BuildQuery(request), ct)
                .ConfigureAwait(false);
            if (v2.Status != HttpStatusCode.NotFound)
            {
                return Interpret(v2, settings, "v2");
            }

            _log.Info("Prerolls Max: this server doesn't know plugin protocol v2 yet; using v1 for 10 minutes.");
            _useV1Until = DateTime.UtcNow + V1Memory;
        }

        var query = new StringBuilder();
        Add(query, "media_type", request.ItemType);
        Add(query, "item_id", request.ItemId);
        if (request.Genres.Count > 0)
        {
            Add(query, "genres", string.Join(",", request.Genres));
        }

        var v1 = await SendAsync(settings, settings.NormalizedBaseUrl + "/plugin/intros?" + query, ct).ConfigureAwait(false);
        return Interpret(v1, settings, "v1");
    }

    /// <summary>Every intro that could play now, so the plugin can download them before anyone presses play.</summary>
    public async Task<IntroAnswer> GetPoolAsync(ClientSettings settings, string itemType, CancellationToken ct)
    {
        var query = new StringBuilder();
        Add(query, "all", "1");
        Add(query, "item_type", itemType);
        if (DateTime.UtcNow >= _useV1Until)
        {
            var v2 = await SendAsync(settings, settings.NormalizedBaseUrl + "/plugin/v2/intros?" + query, ct).ConfigureAwait(false);
            if (v2.Status != HttpStatusCode.NotFound)
            {
                return Interpret(v2, settings, "v2");
            }

            _useV1Until = DateTime.UtcNow + V1Memory;
        }

        var v1Query = new StringBuilder();
        Add(v1Query, "media_type", itemType);
        Add(v1Query, "item_id", "0");
        Add(v1Query, "all", "1");
        var v1 = await SendAsync(settings, settings.NormalizedBaseUrl + "/plugin/intros?" + v1Query, ct).ConfigureAwait(false);
        return Interpret(v1, settings, "v1");
    }

    /// <summary>Download one intro into <paramref name="destination"/>.</summary>
    public async Task DownloadAsync(ClientSettings settings, IntroEntry entry, string destination, CancellationToken ct)
    {
        var url = ResolveStreamUrl(settings.NormalizedBaseUrl, entry.StreamUrl);
        if (string.IsNullOrEmpty(url))
        {
            throw new PrerollsMaxUnavailableException($"Prerolls Max sent no download link for '{entry.Name}'.");
        }

        using var message = NewRequest(HttpMethod.Get, url, settings);
        using var response = await _httpClient().SendAsync(message, HttpCompletionOption.ResponseHeadersRead, ct)
            .ConfigureAwait(false);
        if (response.StatusCode is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden)
        {
            throw new PrerollsMaxRejectedException(
                $"Prerolls Max refused to send '{entry.Name}' (HTTP {(int)response.StatusCode}). The link may have expired; it is asked for again on the next play.");
        }

        if (!response.IsSuccessStatusCode)
        {
            throw new PrerollsMaxUnavailableException($"Prerolls Max couldn't send '{entry.Name}' (HTTP {(int)response.StatusCode}).");
        }

        await using var output = new FileStream(destination, FileMode.CreateNew, FileAccess.Write, FileShare.None, 81920, useAsync: true);
        await response.Content.CopyToAsync(output, ct).ConfigureAwait(false);
        await output.FlushAsync(ct).ConfigureAwait(false);
    }

    /// <summary>The settings page's Test button. Always returns; never throws.</summary>
    public async Task<ConnectionReport> TestAsync(string baseUrl, string apiKey, CancellationToken ct)
    {
        var settings = new ClientSettings { BaseUrl = baseUrl ?? string.Empty, ApiKey = apiKey ?? string.Empty, TimeoutSeconds = 10 };
        var url = settings.NormalizedBaseUrl;
        if (string.IsNullOrWhiteSpace(url))
        {
            return new ConnectionReport { Message = "Type the Prerolls Max address first, for example http://192.168.1.5:9393." };
        }

        if (!Uri.TryCreate(url, UriKind.Absolute, out var parsed) || (parsed.Scheme != "http" && parsed.Scheme != "https"))
        {
            return new ConnectionReport { Message = $"\"{url}\" isn't a web address. It should start with http:// or https://, for example http://192.168.1.5:9393." };
        }

        Response answer;
        try
        {
            answer = await SendAsync(settings, url + "/plugin/health", ct).ConfigureAwait(false);
        }
        catch (PrerollsMaxUnavailableException ex)
        {
            var hint = parsed.IsLoopback
                ? " This address points at the media server itself; if Prerolls Max runs in another container or computer, use that computer's network address."
                : " Check the address and that Prerolls Max is running.";
            return new ConnectionReport { Message = ex.Message + hint };
        }

        if (answer.Status is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden)
        {
            return new ConnectionReport
            {
                Message = string.IsNullOrWhiteSpace(apiKey)
                    ? "Prerolls Max answered, but it needs an API key because login is on. In Prerolls Max, open Media Servers and press \"Set up the plugin for me\"."
                    : "Prerolls Max answered, but it didn't accept this API key. It may have been deleted or expired. In Prerolls Max, open Media Servers and press \"Set up the plugin for me\"."
            };
        }

        if (answer.Status == HttpStatusCode.NotFound)
        {
            return new ConnectionReport { Message = "Something answered at this address, but it isn't Prerolls Max. Check the port number." };
        }

        if ((int)answer.Status >= 400)
        {
            return new ConnectionReport { Message = $"Prerolls Max answered with an error (HTTP {(int)answer.Status}). Its log has the details." };
        }

        try
        {
            using var doc = JsonDocument.Parse(answer.Body);
            var root = doc.RootElement;
            var app = Str(root, "app");
            var authed = Bool(root, "authenticated") ?? false;
            var version = Str(root, "version");
            if (!string.IsNullOrEmpty(app) && !app.Contains("Prerolls", StringComparison.OrdinalIgnoreCase)
                && !app.Contains("NeXroll", StringComparison.OrdinalIgnoreCase))
            {
                return new ConnectionReport { Message = "Something answered at this address, but it isn't Prerolls Max." };
            }

            var named = string.IsNullOrEmpty(version) ? "Prerolls Max" : $"Prerolls Max {version}";
            return new ConnectionReport
            {
                Ok = true,
                Authenticated = authed,
                ServerVersion = version,
                Message = authed
                    ? $"Connected to {named}, and it accepted the API key. Intros will play."
                    : $"Connected to {named}. No API key is set; that works only while login is off in Prerolls Max."
            };
        }
        catch (JsonException)
        {
            return new ConnectionReport { Message = "Something answered at this address, but it isn't Prerolls Max. Check the port number." };
        }
    }

    /// <summary>
    /// Turns the link Prerolls Max sent into one this server can fetch. v2 sends
    /// "/plugin/stream?...", relative to the configured address, so a reverse proxy
    /// prefix (https://example.com/prerolls) is kept. v1 sent a full URL built from
    /// whatever address the request arrived on; its path is moved onto the configured
    /// address too.
    /// </summary>
    public static string ResolveStreamUrl(string baseUrl, string streamUrl)
    {
        if (string.IsNullOrWhiteSpace(streamUrl))
        {
            return string.Empty;
        }

        baseUrl = (baseUrl ?? string.Empty).TrimEnd('/');
        var marker = streamUrl.IndexOf("/plugin/stream", StringComparison.Ordinal);
        if (marker >= 0 && !string.IsNullOrEmpty(baseUrl))
        {
            return baseUrl + streamUrl[marker..];
        }

        if (streamUrl.StartsWith('/'))
        {
            return baseUrl + streamUrl;
        }

        return streamUrl;
    }

    /// <summary>The v2 query string, in the order CONTRACTS.md lists it.</summary>
    public static string BuildQuery(IntroRequest r)
    {
        var q = new StringBuilder();
        Add(q, "item_id", r.ItemId);
        Add(q, "item_type", r.ItemType);
        Add(q, "item_name", r.ItemName);
        Add(q, "user_id", r.UserId);
        Add(q, "user_name", r.UserName);
        Add(q, "library_id", r.LibraryId);
        Add(q, "library_name", r.LibraryName);
        if (r.Genres.Count > 0)
        {
            Add(q, "genres", string.Join(",", r.Genres.Select(g => g.Replace(",", " "))));
        }

        if (r.Tags.Count > 0)
        {
            Add(q, "tags", string.Join(",", r.Tags.Select(t => t.Replace(",", " "))));
        }

        Add(q, "official_rating", r.OfficialRating);
        Add(q, "year", r.Year?.ToString(CultureInfo.InvariantCulture));
        Add(q, "series_id", r.SeriesId);
        Add(q, "series_name", r.SeriesName);
        Add(q, "season", r.Season?.ToString(CultureInfo.InvariantCulture));
        Add(q, "episode", r.Episode?.ToString(CultureInfo.InvariantCulture));
        if (r.IsFirstInSession.HasValue)
        {
            Add(q, "is_first_in_session", r.IsFirstInSession.Value ? "1" : "0");
        }

        Add(q, "client", r.Client);
        Add(q, "device_id", r.DeviceId);
        Add(q, "server_id", r.ServerId);
        Add(q, "audio", r.Audio);
        Add(q, "audio_default", r.AudioDefault);
        if (r.AudioCodecs.Count > 0)
        {
            Add(q, "audio_codecs", string.Join(",", r.AudioCodecs));
        }

        Add(q, "video", r.Video);
        Add(q, "path", r.Path);
        Add(q, "tmdb_id", r.TmdbId);
        return q.ToString();
    }

    private static void Add(StringBuilder q, string name, string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return;
        }

        if (q.Length > 0)
        {
            q.Append('&');
        }

        q.Append(name).Append('=').Append(Uri.EscapeDataString(value.Trim()));
    }

    private sealed record Response(HttpStatusCode Status, string Body);

    private HttpRequestMessage NewRequest(HttpMethod method, string url, ClientSettings settings)
    {
        var message = new HttpRequestMessage(method, url);
        if (!string.IsNullOrWhiteSpace(settings.ApiKey))
        {
            message.Headers.TryAddWithoutValidation("X-Api-Key", settings.ApiKey.Trim());
        }

        message.Headers.TryAddWithoutValidation("X-PrerollsMax-Plugin", PluginHeader);
        // Read by v1 servers to list connected plugins.
        message.Headers.TryAddWithoutValidation("X-Plugin-Server-Type", _serverType == "emby" ? "Emby" : "Jellyfin");
        message.Headers.TryAddWithoutValidation("X-Plugin-Server-Version", _pluginVersion);
        try
        {
            message.Headers.TryAddWithoutValidation("X-Plugin-Server-Name", Environment.MachineName);
        }
        catch (InvalidOperationException)
        {
        }

        return message;
    }

    private async Task<Response> SendAsync(ClientSettings settings, string url, CancellationToken ct)
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(ct);
        timeout.CancelAfter(settings.Timeout);
        try
        {
            using var message = NewRequest(HttpMethod.Get, url, settings);
            using var response = await _httpClient().SendAsync(message, HttpCompletionOption.ResponseContentRead, timeout.Token)
                .ConfigureAwait(false);
            var body = await response.Content.ReadAsStringAsync(timeout.Token).ConfigureAwait(false);
            return new Response(response.StatusCode, body);
        }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested)
        {
            throw new PrerollsMaxUnavailableException(
                $"Prerolls Max didn't answer within {settings.Timeout.TotalSeconds:0} seconds at {settings.NormalizedBaseUrl}.");
        }
        catch (HttpRequestException ex)
        {
            throw new PrerollsMaxUnavailableException($"Couldn't reach Prerolls Max at {settings.NormalizedBaseUrl}.", ex);
        }
    }

    private static IntroAnswer Interpret(Response response, ClientSettings settings, string protocol)
    {
        if (response.Status is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden)
        {
            throw new PrerollsMaxRejectedException(
                string.IsNullOrWhiteSpace(settings.ApiKey) || response.Body.Contains("plugin_key_required", StringComparison.Ordinal)
                    ? "Prerolls Max needs an API key because login is on. In Prerolls Max, open Media Servers and press \"Set up the plugin for me\"."
                    : "Prerolls Max didn't accept the API key. In Prerolls Max, open Media Servers and press \"Set up the plugin for me\".");
        }

        if ((int)response.Status >= 400)
        {
            throw new PrerollsMaxUnavailableException(
                $"Prerolls Max answered with an error (HTTP {(int)response.Status}) at {settings.NormalizedBaseUrl}.");
        }

        try
        {
            return Parse(response.Body, protocol);
        }
        catch (JsonException ex)
        {
            throw new PrerollsMaxUnavailableException("Prerolls Max sent an answer this plugin can't read.", ex);
        }
    }

    /// <summary>Reads a v2 answer, or a v1 one (PascalCase, "Exact").</summary>
    public static IntroAnswer Parse(string body, string protocol = "v2")
    {
        using var doc = JsonDocument.Parse(body);
        var root = doc.RootElement;
        var answer = new IntroAnswer
        {
            Protocol = protocol,
            Mode = Str(root, "mode") is { Length: > 0 } mode ? mode : "exact",
            Reason = Str(root, "reason"),
            IntentionalEmpty = Bool(root, "intentional_empty") ?? false,
            CacheSeconds = (int)(Num(root, "cache_seconds") ?? 0),
        };

        if (Get(root, "items") is { ValueKind: JsonValueKind.Array } items)
        {
            foreach (var item in items.EnumerateArray())
            {
                if (item.ValueKind != JsonValueKind.Object)
                {
                    continue;
                }

                var entry = new IntroEntry
                {
                    Id = Str(item, "id"),
                    Name = Str(item, "name"),
                    Path = Str(item, "path"),
                    StreamUrl = Str(item, "stream_url") is { Length: > 0 } s ? s : Str(item, "streamurl"),
                    Version = Str(item, "version"),
                    DurationSeconds = Num(item, "duration_seconds"),
                };
                if (string.IsNullOrEmpty(entry.Name) && !string.IsNullOrEmpty(entry.Path))
                {
                    entry.Name = System.IO.Path.GetFileNameWithoutExtension(entry.Path.Replace('\\', '/'));
                }

                if (!string.IsNullOrEmpty(entry.Path) || !string.IsNullOrEmpty(entry.StreamUrl))
                {
                    answer.Items.Add(entry);
                }
            }
        }

        return answer;
    }

    private static JsonElement? Get(JsonElement obj, string name)
    {
        if (obj.ValueKind != JsonValueKind.Object)
        {
            return null;
        }

        foreach (var prop in obj.EnumerateObject())
        {
            if (string.Equals(prop.Name, name, StringComparison.OrdinalIgnoreCase))
            {
                return prop.Value;
            }
        }

        return null;
    }

    private static string Str(JsonElement obj, string name)
    {
        var value = Get(obj, name);
        return value is { ValueKind: JsonValueKind.String } v ? v.GetString() ?? string.Empty
            : value is { ValueKind: JsonValueKind.Number } n ? n.GetRawText() : string.Empty;
    }

    private static double? Num(JsonElement obj, string name)
    {
        var value = Get(obj, name);
        if (value is { ValueKind: JsonValueKind.Number } n && n.TryGetDouble(out var d))
        {
            return d;
        }

        return null;
    }

    private static bool? Bool(JsonElement obj, string name)
    {
        var value = Get(obj, name);
        return value?.ValueKind switch
        {
            JsonValueKind.True => true,
            JsonValueKind.False => false,
            _ => null,
        };
    }
}
