using MediaBrowser.Model.Plugins;

namespace PrerollsMax.Jellyfin;

/// <summary>Settings for Prerolls Max Intros, edited on the plugin's page or pushed by Prerolls Max.</summary>
public class PluginConfiguration : BasePluginConfiguration
{
    /// <summary>Prerolls Max's address as this server reaches it, e.g. http://192.168.1.5:9393.</summary>
    public string PrerollsMaxUrl { get; set; } = string.Empty;

    /// <summary>API key from Prerolls Max (Media Servers, or Settings, Advanced, API keys). Needed when login is on there.</summary>
    public string ApiKey { get; set; } = string.Empty;

    /// <summary>Play intros before movies.</summary>
    public bool EnableForMovies { get; set; } = true;

    /// <summary>Play intros before episodes.</summary>
    public bool EnableForEpisodes { get; set; } = true;

    /// <summary>How long a playback may wait for Prerolls Max, in seconds (1-30).</summary>
    public int TimeoutSeconds { get; set; } = 3;

    /// <summary>Hours between episodes that still count as one viewing session.</summary>
    public int BingeWindowHours { get; set; } = 4;

    /// <summary>Largest size of the downloaded intro folder, in megabytes.</summary>
    public int MaxCacheMegabytes { get; set; } = 2048;

    /// <summary>Optional: the intro folder as Prerolls Max sees it (e.g. /data/prerolls).</summary>
    public string PathPrefixFrom { get; set; } = string.Empty;

    /// <summary>Optional: the same folder as this server sees it (e.g. /media/prerolls).</summary>
    public string PathPrefixTo { get; set; } = string.Empty;
}
