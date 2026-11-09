using MediaBrowser.Controller;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Entities.Movies;
using MediaBrowser.Controller.Entities.TV;
using MediaBrowser.Controller.Library;
using MediaBrowser.Controller.Session;
using MediaBrowser.Model.Entities;
using MediaBrowser.Model.Logging;
using MediaBrowser.Model.Tasks;
using PrerollsMax.Shared;

namespace PrerollsMax.Emby;

/// <summary>
/// Asks Prerolls Max which intros play before a movie or episode (protocol v2,
/// with everything Emby knows about it) and hands Emby the downloaded files.
/// Emby only plays intros it has registered, so the files are downloaded ahead
/// (see <see cref="PrefetchTask"/>) and listed in <see cref="GetAllIntroFiles"/>.
/// </summary>
public class IntroProvider : IIntroProvider
{
    private readonly ILibraryManager _libraryManager;
    private readonly ISessionManager _sessionManager;
    private readonly IServerApplicationHost _appHost;
    private readonly PrerollsMaxRuntime _runtime;

    public IntroProvider(
        ILogManager logManager,
        ITaskManager taskManager,
        ILibraryManager libraryManager,
        ISessionManager sessionManager,
        IServerApplicationHost appHost)
    {
        _libraryManager = libraryManager;
        _sessionManager = sessionManager;
        _appHost = appHost;
        _runtime = PrerollsMaxRuntime.Get(logManager, taskManager, libraryManager);
    }

    public string Name => "Prerolls Max Intros";

    /// <summary>
    /// Everything downloaded, for Emby's "Refresh Custom Intros". Never waits for a
    /// download: it lists what is there and starts a background download for next time.
    /// </summary>
    public IEnumerable<string> GetAllIntroFiles()
    {
        _runtime.PrefetchInBackground();
        return _runtime.CachedFiles();
    }

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
            var unregistered = 0;
            var intros = new List<IntroInfo>();
            foreach (var intro in ready)
            {
                var registered = _libraryManager.FindByPath(intro.File, false);
                if (registered is null)
                {
                    // Not registered yet (just renamed, or just downloaded): register it
                    // for next time, and play an older copy of the same intro that Emby
                    // has registered meanwhile.
                    unregistered++;
                    registered = _runtime.Picker.Cache.CopiesOf(intro.Entry)
                        .Select(f => _libraryManager.FindByPath(f, false))
                        .FirstOrDefault(i => i is not null);
                }

                if (registered is not null)
                {
                    _runtime.Name(registered, intro.Entry.Name);
                    intros.Add(new IntroInfo { ItemId = registered.InternalId, Path = registered.Path });
                }
                else
                {
                    intros.Add(new IntroInfo { Path = intro.File });
                }
            }

            if (unregistered > 0)
            {
                // Emby may skip intros it hasn't registered yet; register them for next time.
                _runtime.QueueIntroRefresh();
            }

            _runtime.Logger.Info("Prerolls Max: {0} intro(s) before {1} '{2}' for {3}", intros.Count, itemType, item.Name, user.Name);
            _runtime.PrefetchInBackground();
            return intros;
        }
        catch (Exception ex)
        {
            _runtime.Logger.Warn("Prerolls Max: no intros this time: {0}", ex.Message);
            return Enumerable.Empty<IntroInfo>();
        }
    }

    private IntroRequest Describe(BaseItem item, User user, string itemType, PluginConfiguration config)
    {
        var request = new IntroRequest
        {
            // Emby's own API addresses items by this number (InternalId), not the Guid.
            ItemId = item.InternalId.ToString(System.Globalization.CultureInfo.InvariantCulture),
            ItemType = itemType,
            ItemName = item.Name ?? string.Empty,
            Path = item.Path ?? string.Empty,
            UserId = user.Id.ToString("N"),
            UserName = user.Name ?? string.Empty,
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

        try
        {
            var tmdb = item.GetProviderId(MetadataProviders.Tmdb);
            request.TmdbId = tmdb ?? string.Empty;
        }
        catch (Exception)
        {
        }

        try
        {
            var library = _libraryManager.GetCollectionFolders(item).FirstOrDefault();
            if (library is not null)
            {
                request.LibraryId = library.InternalId.ToString(System.Globalization.CultureInfo.InvariantCulture);
                request.LibraryName = library.Name ?? string.Empty;
            }
        }
        catch (Exception)
        {
        }

        if (item is Episode episode)
        {
            request.SeriesId = episode.SeriesId.ToString(System.Globalization.CultureInfo.InvariantCulture);
            request.SeriesName = episode.SeriesName ?? string.Empty;
            request.Season = episode.ParentIndexNumber;
            request.Episode = episode.IndexNumber;
            var series = episode.Series;
            if (series is not null)
            {
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
            request.IsFirstInSession = _runtime.Binges.IsFirst(request.UserId, request.SeriesId, request.ItemId, window);
        }

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

            request.AudioCodecs = audio.Select(s => s.Codec ?? string.Empty).Where(c => c.Length > 0).Distinct(StringComparer.OrdinalIgnoreCase).ToList();
            var video = streams.FirstOrDefault(s => s.Type == MediaStreamType.Video);
            request.Video = video?.DisplayTitle ?? string.Empty;
        }
        catch (Exception)
        {
        }

        try
        {
            var session = _sessionManager.Sessions
                .Where(s => s.UserInternalId == user.InternalId)
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

        return request;
    }
}
