namespace PrerollsMax.Shared;

/// <summary>Logging the shared code can use on both Jellyfin and Emby.</summary>
public interface IPluginLog
{
    void Debug(string message);

    void Info(string message);

    void Warn(string message);
}

/// <summary>The settings the shared code needs, copied out of either plugin's configuration.</summary>
public sealed record ClientSettings
{
    /// <summary>Address of Prerolls Max, as the media server reaches it, e.g. http://192.168.1.5:9393.</summary>
    public string BaseUrl { get; init; } = string.Empty;

    /// <summary>The API key from Prerolls Max (Media Servers, or Settings, Advanced, API keys). Sent in the X-Api-Key header only.</summary>
    public string ApiKey { get; init; } = string.Empty;

    /// <summary>How long a playback may wait for Prerolls Max, in seconds.</summary>
    public int TimeoutSeconds { get; init; } = 3;

    /// <summary>Optional path prefix as Prerolls Max sees its files.</summary>
    public string PathPrefixFrom { get; init; } = string.Empty;

    /// <summary>The same folder as the media server sees it.</summary>
    public string PathPrefixTo { get; init; } = string.Empty;

    public string NormalizedBaseUrl => (BaseUrl ?? string.Empty).Trim().TrimEnd('/');

    public TimeSpan Timeout => TimeSpan.FromSeconds(Math.Clamp(TimeoutSeconds <= 0 ? 3 : TimeoutSeconds, 1, 30));
}

/// <summary>What is about to play. Everything Prerolls Max needs, so it never calls back during playback.</summary>
public sealed class IntroRequest
{
    public string ItemId { get; set; } = string.Empty;

    /// <summary>"Movie" or "Episode".</summary>
    public string ItemType { get; set; } = "Movie";

    public string ItemName { get; set; } = string.Empty;

    public string Path { get; set; } = string.Empty;

    public string UserId { get; set; } = string.Empty;

    public string UserName { get; set; } = string.Empty;

    public string LibraryId { get; set; } = string.Empty;

    public string LibraryName { get; set; } = string.Empty;

    public List<string> Genres { get; set; } = new();

    public List<string> Tags { get; set; } = new();

    public string OfficialRating { get; set; } = string.Empty;

    public int? Year { get; set; }

    public string SeriesId { get; set; } = string.Empty;

    public string SeriesName { get; set; } = string.Empty;

    public int? Season { get; set; }

    public int? Episode { get; set; }

    public bool? IsFirstInSession { get; set; }

    public string Client { get; set; } = string.Empty;

    public string DeviceId { get; set; } = string.Empty;

    public string ServerId { get; set; } = string.Empty;

    /// <summary>Readable audio, e.g. "TrueHD Atmos 7.1".</summary>
    public string Audio { get; set; } = string.Empty;

    /// <summary>Codec of the default audio track, e.g. "truehd".</summary>
    public string AudioDefault { get; set; } = string.Empty;

    /// <summary>Codecs of every audio track.</summary>
    public List<string> AudioCodecs { get; set; } = new();

    /// <summary>Readable video, e.g. "2160p HDR10".</summary>
    public string Video { get; set; } = string.Empty;

    public string TmdbId { get; set; } = string.Empty;
}

/// <summary>One intro to play.</summary>
public sealed class IntroEntry
{
    public string Id { get; set; } = string.Empty;

    public string Name { get; set; } = string.Empty;

    /// <summary>The file's path as Prerolls Max sees it.</summary>
    public string Path { get; set; } = string.Empty;

    /// <summary>Where to download it. Relative to the Prerolls Max address in v2.</summary>
    public string StreamUrl { get; set; } = string.Empty;

    /// <summary>Changes whenever the file is rewritten.</summary>
    public string Version { get; set; } = string.Empty;

    public double? DurationSeconds { get; set; }
}

/// <summary>Prerolls Max's answer for one playback.</summary>
public sealed class IntroAnswer
{
    public List<IntroEntry> Items { get; set; } = new();

    public string Mode { get; set; } = "exact";

    public string Reason { get; set; } = string.Empty;

    /// <summary>
    /// True when Prerolls Max chose no intros on purpose (the title is on the never-play
    /// list, or has a no-intro tag). Play nothing, and keep the last known good list.
    /// </summary>
    public bool IntentionalEmpty { get; set; }

    public int CacheSeconds { get; set; }

    /// <summary>"v2" or "v1" (an older Prerolls Max or NeXroll).</summary>
    public string Protocol { get; set; } = "v2";

    /// <summary>True when the list came from the last answer kept on disk because Prerolls Max did not answer.</summary>
    public bool FromLastKnownGood { get; set; }
}

/// <summary>Result of the settings page's Test button.</summary>
public sealed class ConnectionReport
{
    public bool Ok { get; set; }

    /// <summary>One or two plain sentences for the settings page.</summary>
    public string Message { get; set; } = string.Empty;

    public string ServerVersion { get; set; } = string.Empty;

    public bool Authenticated { get; set; }
}
