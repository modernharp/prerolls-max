using System.Collections.Concurrent;

namespace PrerollsMax.Shared;

/// <summary>
/// Whether an episode starts a viewing session ("first episode of a binge") for
/// one person: no other episode of the same series was started within the window.
/// Asking again about the same episode inside the window gives the same answer, so
/// a client that asks twice for one playback doesn't lose the intro.
/// </summary>
public sealed class BingeTracker
{
    private readonly ConcurrentDictionary<string, (DateTime Last, string FirstEpisode)> _seen = new(StringComparer.Ordinal);

    /// <param name="userId">Who is watching.</param>
    /// <param name="seriesId">The series.</param>
    /// <param name="episodeId">The episode about to play.</param>
    /// <param name="window">How long a pause still counts as the same session.</param>
    /// <param name="otherEpisodePlayedAt">
    /// What the media server knows: when this person last played another episode of
    /// the series (UTC), or null if never or unknown.
    /// </param>
    public bool IsFirst(string userId, string seriesId, string episodeId, TimeSpan window, DateTime? otherEpisodePlayedAt = null)
    {
        var now = DateTime.UtcNow;
        var key = userId + "|" + seriesId;
        var recentByServer = otherEpisodePlayedAt.HasValue && now - otherEpisodePlayedAt.Value < window;
        var first = true;
        _seen.AddOrUpdate(
            key,
            _ =>
            {
                first = !recentByServer;
                return (now, first ? episodeId : string.Empty);
            },
            (_, old) =>
            {
                if (now - old.Last >= window)
                {
                    first = !recentByServer;
                    return (now, first ? episodeId : string.Empty);
                }

                first = string.Equals(old.FirstEpisode, episodeId, StringComparison.Ordinal);
                return (now, old.FirstEpisode);
            });

        if (_seen.Count > 5000)
        {
            foreach (var (k, v) in _seen)
            {
                if (now - v.Last > window)
                {
                    _seen.TryRemove(k, out _);
                }
            }
        }

        return first;
    }
}
