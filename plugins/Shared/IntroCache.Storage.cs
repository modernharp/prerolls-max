using System.Text.Json;

namespace PrerollsMax.Shared;

/// <summary>
/// What the cache keeps on disk besides the videos: when each file was last
/// used (for tidying) and the last list Prerolls Max sent (to play while it
/// can't be reached).
/// </summary>
public sealed partial class IntroCache
{
    private const string IndexFile = "cache-index.json";
    private const string LastKnownGoodFile = "last-known-good.json";

    private static readonly JsonSerializerOptions Json = new() { WriteIndented = false };

    /// <summary>Remember the list Prerolls Max sent for this kind of item.</summary>
    public void SaveLastKnownGood(string slot, IEnumerable<IntroEntry> entries)
    {
        var list = entries.ToList();
        _lastKnownGood[slot] = list;
        lock (_diskLock)
        {
            WriteAtomically(Path.Combine(_dir, LastKnownGoodFile), JsonSerializer.Serialize(_lastKnownGood, Json));
        }
    }

    /// <summary>The last list Prerolls Max sent for this kind of item, or an empty list.</summary>
    public IReadOnlyList<IntroEntry> LastKnownGood(string slot)
        => _lastKnownGood.TryGetValue(slot, out var list) ? list : Array.Empty<IntroEntry>();

    private void LoadIndex()
    {
        try
        {
            var path = Path.Combine(_dir, IndexFile);
            if (!File.Exists(path))
            {
                return;
            }

            // Names relative to the cache folder ("1a2b…-0a1b…/Pumpkin Intro.mp4"; version
            // 2.0 wrote bare file names, which are relative too).
            var data = JsonSerializer.Deserialize<Dictionary<string, DateTime>>(File.ReadAllText(path));
            foreach (var (name, used) in data ?? new())
            {
                _lastUsed[Path.Combine(_dir, name)] = DateTime.SpecifyKind(used, DateTimeKind.Utc);
            }
        }
        catch (Exception ex)
        {
            _log.Debug($"Prerolls Max: intro cache index not read ({ex.Message}); starting fresh.");
        }
    }

    private void SaveIndex()
    {
        try
        {
            var data = _lastUsed
                .Where(kv => File.Exists(kv.Key))
                .ToDictionary(kv => Path.GetRelativePath(_dir, kv.Key), kv => kv.Value);
            lock (_diskLock)
            {
                WriteAtomically(Path.Combine(_dir, IndexFile), JsonSerializer.Serialize(data, Json));
            }
        }
        catch (Exception ex)
        {
            _log.Debug($"Prerolls Max: intro cache index not saved: {ex.Message}");
        }
    }

    private void LoadLastKnownGood()
    {
        try
        {
            var path = Path.Combine(_dir, LastKnownGoodFile);
            if (!File.Exists(path))
            {
                return;
            }

            var data = JsonSerializer.Deserialize<Dictionary<string, List<IntroEntry>>>(File.ReadAllText(path));
            foreach (var (slot, list) in data ?? new())
            {
                _lastKnownGood[slot] = list ?? new List<IntroEntry>();
            }
        }
        catch (Exception ex)
        {
            _log.Debug($"Prerolls Max: last known intro list not read: {ex.Message}");
        }
    }

    private void WriteAtomically(string path, string content)
    {
        try
        {
            Directory.CreateDirectory(_dir);
            var temp = path + "." + Guid.NewGuid().ToString("N")[..8] + ".tmp";
            File.WriteAllText(temp, content);
            File.Move(temp, path, overwrite: true);
        }
        catch (Exception ex)
        {
            _log.Debug($"Prerolls Max: couldn't save {Path.GetFileName(path)}: {ex.Message}");
        }
    }
}
