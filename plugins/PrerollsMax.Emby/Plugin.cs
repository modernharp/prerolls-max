using MediaBrowser.Common.Configuration;
using MediaBrowser.Common.Plugins;
using MediaBrowser.Model.Drawing;
using MediaBrowser.Model.Plugins;
using MediaBrowser.Model.Serialization;

namespace PrerollsMax.Emby;

/// <summary>Prerolls Max Intros for Emby.</summary>
public class Plugin : BasePlugin<PluginConfiguration>, IHasWebPages, IHasThumbImage
{
    /// <summary>The plugin's id. Different from the NeXroll plugin's, so both can be installed.</summary>
    public static readonly Guid PluginId = new("2fea54cd-3c4a-4307-ab53-5e25a07a24ec");

    public Plugin(IApplicationPaths applicationPaths, IXmlSerializer xmlSerializer)
        : base(applicationPaths, xmlSerializer)
    {
        Instance = this;
    }

    public static Plugin? Instance { get; private set; }

    public override string Name => "Prerolls Max Intros";

    public override Guid Id => PluginId;

    public override string Description => "Plays intro videos chosen by Prerolls Max before movies and episodes.";

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

    public ImageFormat ThumbImageFormat => ImageFormat.Png;

    public Stream? GetThumbImage()
        => GetType().Assembly.GetManifestResourceStream(GetType().Namespace + ".thumb.png");

    public IEnumerable<PluginPageInfo> GetPages()
    {
        return new[]
        {
            new PluginPageInfo
            {
                Name = "PrerollsMaxIntros",
                EmbeddedResourcePath = GetType().Namespace + ".Configuration.configPage.html",
            },
            new PluginPageInfo
            {
                Name = "PrerollsMaxIntrosJs",
                EmbeddedResourcePath = GetType().Namespace + ".Configuration.configPage.js",
            },
        };
    }
}
