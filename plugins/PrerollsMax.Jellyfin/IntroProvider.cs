using Jellyfin.Data.Enums;
using Jellyfin.Database.Implementations.Entities;
using Jellyfin.Database.Implementations.Enums;
using MediaBrowser.Controller;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Entities.Movies;
using MediaBrowser.Controller.Entities.TV;
using MediaBrowser.Controller.Library;
using MediaBrowser.Controller.Session;
using MediaBrowser.Model.Entities;
using Microsoft.Extensions.Logging;
using PrerollsMax.Shared;

namespace PrerollsMax.Jellyfin;

/// <summary>
/// Asks Prerolls Max which intros play before a movie or episode, sending
/// everything Jellyfin knows about it (protocol v2), and hands Jellyfin the files.
/// Never waits longer than the configured timeout; if Prerolls Max is down, the
/// intros it chose last time play.
/// </summary>
public class IntroProvider : IIntroProvider
{
    private readonly ILogger<IntroProvider> _logger;
    private readonly ILibraryManager _libraryManager;
    private readonly IUserDataManager _userDataManager;
    private readonly ISessionManager _sessionManager;
    private readonly IServerApplicationHost _appHost;
    private readonly PrerollsMaxRuntime _runtime;

    public IntroProvider(
        ILogger<IntroProvider> logger,
        ILibraryManager libraryManager,
        IUserDataManager userDataManager,
        ISessionManager sessionManager,
        IServerApplicationHost appHost,
        PrerollsMaxRuntime runtime)
    {
        _logger = logger;
        _libraryManager = libraryManager;
        _userDataManager = userDataManager;
        _sessionManager = sessionManager;
        _appHost = appHost;
        _runtime = runtime;
    }

    public string Name => "Prerolls Max Intros";

    public async Task<IEnumerable<IntroInfo>> GetIntros(BaseItem item, User user)
    {
        var config = Plugin.Instance?.Configuration;
        var settings = PrerollsMaxRuntime.CurrentSettings();
        if (config is null || settings is null)
        {
            return Enumerable.Empty<IntroInfo>();
        }

        string itemType;
        if (item is Movie)
        {
            if (!config.EnableForMovies)
            {
                return Enumerable.Empty<IntroInfo>();
            }

            itemType = "Movie";
        }
        else if (item is Episode)
        {
            if (!config.EnableForEpisodes)
            {
                return Enumerable.Empty<IntroInfo>();
            }

            itemType = "Episode";
        }
        else
        {
            return Enumerable.Empty<IntroInfo>();
        }

        try
        {
            var request = Describe(item, user, itemType, config);
            var ready = await _runtime.Picker.PickAsync(settings, request, CancellationToken.None).ConfigureAwait(false);
            // Copies the cache just moved to their named files leave old items behind.
            _runtime.Forget(_runtime.Picker.Cache.TakeGone());
            var intros = new List<IntroInfo>();
            foreach (var intro in ready)
            {
                var id = await _runtime.RegisterAsync(intro.File, intro.Entry.Name).ConfigureAwait(false);
                intros.Add(id is Guid guid ? new IntroInfo { ItemId = guid } : new IntroInfo { Path = intro.File });
            }

            _logger.LogInformation(
                "Prerolls Max: {Count} intro(s) before {Type} '{Name}' for {User}",
                intros.Count, itemType, item.Name, user.Username);
            _runtime.PrefetchInBackground();
            return intros;
        }
        catch (Exception ex)
        {
            // A throwing provider would cost the other intro providers' intros too.
            _logger.LogWarning("Prerolls Max: no intros this time: {Message}", ex.Message);
            return Enumerable.Empty<IntroInfo>();
        }
    }

    private IntroRequest Describe(BaseItem item, User user, string itemType, PluginConfiguration config)
    {
        var request = new IntroRequest
        {
            ItemId = item.Id.ToString("N"),
            ItemType = itemType,
            ItemName = item.Name ?? string.Empty,
            Path = item.Path ?? string.Empty,
            UserId = user.Id.ToString("N"),
            UserName = user.Username ?? string.Empty,
            Genres = (item.Genres ?? Array.Empty<string>()).ToList(),
            Tags = (item.Tags ?? Array.Empty<string>()).ToList(),
            OfficialRating = item.OfficialRating ?? string.Empty,
            Year = item.ProductionYear,
        };

        try
        {
            request.ServerId = _appHost.SystemId;
        }
        catch (Exception)
        {
        }

        if (item.ProviderIds is not null && item.ProviderIds.TryGetValue("Tmdb", out var tmdb))
        {
            request.TmdbId = tmdb ?? string.Empty;
        }

        try
        {
            var library = _libraryManager.GetCollectionFolders(item).FirstOrDefault();
            if (library is not null)
            {
                request.LibraryId = library.Id.ToString("N");
                request.LibraryName = library.Name ?? string.Empty;
            }
        }
        catch (Exception ex)
        {
            _logger.LogDebug("Prerolls Max: library of {Name} not found: {Message}", item.Name, ex.Message);
        }

        if (item is Episode episode)
        {
            request.SeriesId = episode.SeriesId.ToString("N");
            request.SeriesName = episode.SeriesName ?? string.Empty;
            request.Season = episode.ParentIndexNumber;
            request.Episode = episode.IndexNumber;
            var series = episode.Series;
            if (series is not null)
            {
                // Episodes usually carry no genres or rating of their own.
                if (request.Genres.Count == 0)
                {
                    request.Genres = (series.Genres ?? Array.Empty<string>()).ToList();
                }

                if (request.Tags.Count == 0)
                {
                    request.Tags = (series.Tags ?? Array.Empty<string>()).ToList();
                }

                if (string.IsNullOrEmpty(request.OfficialRating))
                {
                    request.OfficialRating = series.OfficialRating ?? string.Empty;
                }
            }

            var window = TimeSpan.FromHours(Math.Clamp(config.BingeWindowHours <= 0 ? 4 : config.BingeWindowHours, 1, 48));
            request.IsFirstInSession = _runtime.Binges.IsFirst(
                request.UserId, request.SeriesId, request.ItemId, window, OtherEpisodePlayedAt(episode, user));
        }

        DescribeStreams(item, request);
        DescribeClient(user, request);
        return request;
    }

    /// <summary>When this person last played another episode of the series, from Jellyfin's play history.</summary>
    private DateTime? OtherEpisodePlayedAt(Episode episode, User user)
    {
        try
        {
            var recent = _libraryManager.GetItemList(new InternalItemsQuery(user)
            {
                IncludeItemTypes = new[] { BaseItemKind.Episode },
                AncestorIds = new[] { episode.SeriesId },
                Recursive = true,
                OrderBy = new[] { (ItemSortBy.DatePlayed, SortOrder.Descending) },
                Limit = 3,
            });
            DateTime? latest = null;
            foreach (var other in recent)
            {
                if (other.Id == episode.Id)
                {
                    continue;
                }

                var played = _userDataManager.GetUserData(user, other)?.LastPlayedDate;
                if (played.HasValue)
                {
                    var utc = played.Value.Kind == DateTimeKind.Local ? played.Value.ToUniversalTime() : DateTime.SpecifyKind(played.Value, DateTimeKind.Utc);
                    if (latest is null || utc > latest)
                    {
                        latest = utc;
                    }
                }
            }

            return latest;
        }
        catch (Exception ex)
        {
            _logger.LogDebug("Prerolls Max: play history not read: {Message}", ex.Message);
            return null;
        }
    }

    private static void DescribeStreams(BaseItem item, IntroRequest request)
    {
        try
        {
            var streams = item.GetMediaStreams() ?? new List<MediaStream>();
            var audio = streams.Where(s => s.Type == MediaStreamType.Audio).ToList();
            var main = audio.FirstOrDefault(s => s.IsDefault) ?? audio.FirstOrDefault();
            if (main is not null)
            {
                request.Audio = main.DisplayTitle ?? string.Empty;
                request.AudioDefault = main.Codec ?? string.Empty;
            }

            request.AudioCodecs = audio.Select(s => s.Codec).Where(c => !string.IsNullOrWhiteSpace(c)).Distinct(StringComparer.OrdinalIgnoreCase).ToList()!;
            var video = streams.FirstOrDefault(s => s.Type == MediaStreamType.Video);
            if (video is not null)
            {
                request.Video = video.DisplayTitle ?? string.Empty;
            }
        }
        catch (Exception)
        {
            // Streams are a nice-to-have; rules that need them treat "unknown" as not met.
        }
    }

    private void DescribeClient(User user, IntroRequest request)
    {
        try
        {
            var session = _sessionManager.Sessions
                .Where(s => s.UserId.Equals(user.Id))
                .OrderByDescending(s => s.LastActivityDate)
                .FirstOrDefault();
            if (session is not null)
            {
                request.Client = session.Client ?? string.Empty;
                request.DeviceId = session.DeviceId ?? string.Empty;
            }
        }
        catch (Exception)
        {
        }
    }
}
