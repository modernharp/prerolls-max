using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

namespace PrerollsMax.Shared;

/// <summary>
/// Where each intro lives in the plugin's folder, and what it's called there.
///
/// Media servers show an intro under its file name (Emby always, Jellyfin in
/// some pages), so each intro gets a folder of its own and its real name as the
/// file name: <c>&lt;cache&gt;/1a2b3c4d5e6f-0a1b2c3d/Pumpkin Intro.mp4</c>. The folder
/// name is a short id (which intro, which version), so two intros with the same
/// name never collide and a rewritten file gets a new folder.
///
/// Version 2.0 kept files as <c>&lt;cache&gt;/&lt;24 hex&gt;-&lt;12 hex&gt;.mp4</c>, which
/// Emby listed as "e8d13c0f…". <see cref="Legacy"/> finds those so they can be moved.
/// </summary>
public static partial class CacheNames
{
    public const int KeyLength = 12;
    private const int VersionLength = 8;
    private const int MaxNameChars = 80;
    private const int MaxNameBytes = 180;

    private static readonly HashSet<string> WindowsReserved = new(StringComparer.OrdinalIgnoreCase)
    {
        "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
    };

    /// <summary>Characters Windows, macOS or Linux don't allow in a file name.</summary>
    private static readonly char[] Forbidden = "<>:\"/\\|?*".ToCharArray();

    /// <summary>
    /// Endings Jellyfin and Emby read as "an extra of a movie" (a trailer, a sample...),
    /// which they'd treat differently from a video of its own.
    /// </summary>
    [GeneratedRegex(@"(^|[\s._-])(trailers?|samples?|behindthescenes|deleted|deletedscenes?|featurettes?|interviews?|scenes?|shorts?|clips?|others?|extras?|themes?|backdrops?)$", RegexOptions.IgnoreCase)]
    private static partial Regex ExtraSuffix();

    public static string Hash(string input)
        => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(input))).ToLowerInvariant();

    /// <summary>Which intro this is: its path on Prerolls Max, or its id.</summary>
    public static string Key(IntroEntry entry)
    {
        var identity = !string.IsNullOrWhiteSpace(entry.Path) ? entry.Path : entry.Id;
        return Hash(identity ?? string.Empty)[..KeyLength];
    }

    /// <summary>The folder for this version of the intro (relative to the cache).</summary>
    public static string Folder(IntroEntry entry)
        => string.IsNullOrWhiteSpace(entry.Version) ? Key(entry) : Key(entry) + "-" + Hash(entry.Version)[..VersionLength];

    /// <summary>The intro's file extension, from Prerolls Max's path (".mp4" when unknown).</summary>
    public static string Extension(IntroEntry entry)
    {
        var ext = System.IO.Path.GetExtension((entry.Path ?? string.Empty).Replace('\\', '/'));
        return string.IsNullOrEmpty(ext) || !IntroCache.VideoExtensions.Contains(ext.ToLowerInvariant()) ? ".mp4" : ext.ToLowerInvariant();
    }

    /// <summary>The file name: the intro's name, made safe for every file system.</summary>
    public static string FileName(IntroEntry entry) => SafeName(entry.Name) + Extension(entry);

    /// <summary>
    /// A name that works as a file name on Windows, macOS and Linux and that the
    /// media servers read as a video of its own. Keeps it recognisable.
    /// </summary>
    public static string SafeName(string? name)
    {
        var text = new StringBuilder();
        foreach (var c in (name ?? string.Empty).Normalize(NormalizationForm.FormC))
        {
            text.Append(char.IsControl(c) || Forbidden.Contains(c) ? ' ' : c);
        }

        var clean = Regex.Replace(text.ToString(), @"\s+", " ").Trim().TrimStart('.').Trim().TrimEnd('.', ' ');
        clean = Shorten(clean);
        if (clean.Length == 0)
        {
            clean = "Intro";
        }

        if (WindowsReserved.Contains(clean.Split('.')[0].Trim()) || ExtraSuffix().IsMatch(clean))
        {
            clean += " (intro)";
        }

        return clean;
    }

    /// <summary>Cuts a long name at a whole character, within the character and byte limits.</summary>
    private static string Shorten(string text)
    {
        if (text.Length == 0)
        {
            return text;
        }

        var info = new StringInfo(text);
        var length = Math.Min(info.LengthInTextElements, MaxNameChars);
        var cut = info.SubstringByTextElements(0, length);
        while (length > 1 && Encoding.UTF8.GetByteCount(cut) > MaxNameBytes)
        {
            length--;
            cut = info.SubstringByTextElements(0, length);
        }

        return cut.TrimEnd('.', ' ');
    }

    /// <summary>Where version 2.0 kept this intro (straight in the cache folder).</summary>
    public static string Legacy(string cache, IntroEntry entry)
    {
        var identity = !string.IsNullOrWhiteSpace(entry.Path) ? entry.Path : entry.Id;
        var name = Hash(identity ?? string.Empty)[..24];
        if (!string.IsNullOrWhiteSpace(entry.Version))
        {
            name += "-" + Hash(entry.Version)[..12];
        }

        return System.IO.Path.Combine(cache, name + Extension(entry));
    }

    /// <summary>
    /// Which intro a cached file belongs to: the folder's short id, or for an old
    /// file straight in the cache, the start of its name.
    /// </summary>
    public static string KeyOfFile(string cache, string file)
    {
        var parent = System.IO.Path.GetDirectoryName(file) ?? string.Empty;
        var id = PathsEqual(parent, cache)
            ? System.IO.Path.GetFileNameWithoutExtension(file)
            : System.IO.Path.GetFileName(parent);
        id = id.Split('-')[0];
        return id.Length > KeyLength ? id[..KeyLength] : id;
    }

    /// <summary>True for an old-style file kept straight in the cache folder.</summary>
    public static bool IsLegacy(string cache, string file)
        => PathsEqual(System.IO.Path.GetDirectoryName(file) ?? string.Empty, cache);

    public static bool PathsEqual(string a, string b)
        => string.Equals(System.IO.Path.GetFullPath(a).TrimEnd('/', '\\'), System.IO.Path.GetFullPath(b).TrimEnd('/', '\\'),
            OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal);
}
