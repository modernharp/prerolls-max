using MediaBrowser.Common.Configuration;
using MediaBrowser.Common.Plugins;
using MediaBrowser.Model.Plugins;
using MediaBrowser.Model.Serialization;

namespace PrerollsMax.Jellyfin;

/// <summary>Prerolls Max Intros for Jellyfin.</summary>
public class Plugin : BasePlugin<PluginConfiguration>, IHasWebPages
{
    /// <summary>The plugin's id. Different from the NeXroll plugin's, so both can be installed.</summary>
    public static readonly Guid PluginId = new("c0a6ea94-7795-4b61-b964-4ddfb93ec8b0");

    public Plugin(IApplicationPaths applicationPaths, IXmlSerializer xmlSerializer)
        : base(applicationPaths, xmlSerializer)
    {
        Instance = this;
    }

    public static Plugin? Instance { get; private set; }

    public override string Name => "Prerolls Max Intros";

    public override Guid Id => PluginId;

    public override string Description => "Plays intro videos chosen by Prerolls Max before movies and episodes.";

    /// <summary>This plugin's version, as Directory.Build.props sets it.</summary>
    public static string PluginVersion => typeof(Plugin).Assembly.GetName().Version?.ToString() ?? "0.0.0.0";

    /// <summary>Where downloaded intros are kept (absolute even when HOME is unset).</summary>
    public static string CacheDirectory
    {
        get
        {
            string? baseDir = null;
            try
            {
                baseDir = Instance?.DataFolderPath;
            }
            catch (Exception)
            {
            }

            if (string.IsNullOrWhiteSpace(baseDir) || !Path.IsPathRooted(baseDir))
            {
                baseDir = Path.Combine(Path.GetTempPath(), "PrerollsMax");
            }

            return Path.Combine(baseDir, "intro_cache");
        }
    }

    public IEnumerable<PluginPageInfo> GetPages()
    {
        return new[]
        {
            new PluginPageInfo
            {
                Name = "PrerollsMaxIntros",
                DisplayName = "Prerolls Max Intros",
                EmbeddedResourcePath = $"{GetType().Namespace}.Configuration.configPage.html",
            },
        };
    }
}
