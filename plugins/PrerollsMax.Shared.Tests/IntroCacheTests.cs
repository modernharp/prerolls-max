using PrerollsMax.Shared;

namespace PrerollsMax.Shared.Tests;

public sealed class IntroCacheTests : IDisposable
{
    private readonly string _dir = Path.Combine(Path.GetTempPath(), "pmax-cache-" + Guid.NewGuid().ToString("N")[..8]);

    public void Dispose()
    {
        if (Directory.Exists(_dir))
        {
            Directory.Delete(_dir, true);
        }
    }

    private sealed class QuietLog : IPluginLog
    {
        public void Debug(string message)
        {
        }

        public void Info(string message)
        {
        }

        public void Warn(string message)
        {
        }
    }

    private static IntroEntry Intro(string name, string version = "v1", string path = "/prerolls/Halloween/pumpkin.mp4")
        => new() { Id = "7", Name = name, Path = path, Version = version, StreamUrl = "/plugin/stream?p=x" };

    private static Task Write(string path, CancellationToken _)
    {
        File.WriteAllText(path, "video bytes");
        return Task.CompletedTask;
    }

    [Theory]
    [InlineData("Pumpkin Intro", "Pumpkin Intro")]
    [InlineData("  Spooky: Night? <2>  ", "Spooky Night 2")]
    [InlineData("a/b\\c|d*e", "a b c d e")]
    [InlineData("...hidden.", "hidden")]
    [InlineData("", "Intro")]
    [InlineData("CON", "CON (intro)")]
    [InlineData("Coming Soon Trailer", "Coming Soon Trailer (intro)")]
    [InlineData("Halloween-sample", "Halloween-sample (intro)")]
    [InlineData("Kids Night", "Kids Night")]
    public void Names_are_safe_on_every_file_system_and_read_as_videos_of_their_own(string name, string expected)
        => Assert.Equal(expected, CacheNames.SafeName(name));

    [Fact]
    public void Long_names_are_cut_at_a_whole_character()
    {
        var name = CacheNames.SafeName(new string('é', 70) + "🎃🎃🎃🎃🎃🎃🎃🎃🎃🎃🎃🎃🎃🎃🎃🎃🎃🎃🎃🎃");
        Assert.True(System.Text.Encoding.UTF8.GetByteCount(name) <= 180);
        Assert.False(char.IsHighSurrogate(name[^1]));
    }

    [Fact]
    public async Task An_intro_is_kept_in_its_own_folder_under_its_own_name()
    {
        var cache = new IntroCache(_dir, new QuietLog());
        var file = await cache.EnsureAsync(Intro("Pumpkin: Intro"), Write);
        Assert.NotNull(file);
        Assert.Equal("Pumpkin Intro.mp4", Path.GetFileName(file));
        Assert.Matches("^[0-9a-f]{12}-[0-9a-f]{8}$", Path.GetFileName(Path.GetDirectoryName(file)));
        Assert.Equal(new[] { file }, cache.NamedVideos());

        // Two intros with the same name don't collide.
        var other = await cache.EnsureAsync(Intro("Pumpkin: Intro", path: "/prerolls/Other/pumpkin.mp4"), Write);
        Assert.NotEqual(file, other);
        Assert.Equal(2, cache.NamedVideos().Count);
    }

    [Fact]
    public async Task A_renamed_intro_is_moved_not_downloaded_again_and_its_old_path_is_reported()
    {
        var cache = new IntroCache(_dir, new QuietLog());
        var first = await cache.EnsureAsync(Intro("Pumpkin"), Write);
        var downloads = 0;
        var renamed = await cache.EnsureAsync(Intro("Pumpkin Party"), (p, t) =>
        {
            downloads++;
            return Write(p, t);
        });
        Assert.Equal(0, downloads);
        Assert.Equal("Pumpkin Party.mp4", Path.GetFileName(renamed));
        Assert.False(File.Exists(first));
        var move = Assert.Single(cache.TakeMoves());
        Assert.Equal((first, renamed, "Pumpkin Party"), (move.From, move.To, move.Name));
        Assert.Empty(cache.TakeGone());
    }

    [Fact]
    public async Task Files_from_version_2_move_to_named_files_at_startup_and_leftovers_are_tidied()
    {
        Directory.CreateDirectory(_dir);
        var remembered = Intro("Snow Globe", path: "/prerolls/snow.mp4");
        var forgotten = Intro("Old One", path: "/prerolls/old.mp4");
        File.WriteAllText(CacheNames.Legacy(_dir, remembered), "snow");
        File.WriteAllText(CacheNames.Legacy(_dir, forgotten), "old");
        // The last list Prerolls Max sent names the snow globe.
        var seed = new IntroCache(_dir, new QuietLog());
        seed.SaveLastKnownGood("Movie", new[] { remembered });

        var cache = new IntroCache(_dir, new QuietLog());
        var moved = cache.FileFor(remembered);
        Assert.True(File.Exists(moved));
        Assert.Equal("snow", File.ReadAllText(moved));
        Assert.Equal("Snow Globe.mp4", Path.GetFileName(moved));
        Assert.Equal(cache.Ready(remembered), moved);
        // Emby lists only the named files, never the old hash names.
        Assert.Equal(new[] { moved }, cache.NamedVideos());

        // Moved: the media server is told where it went.
        Assert.Equal(new[] { CacheNames.Legacy(_dir, remembered) }, cache.TakeGone());
        var removed = cache.Prune(new[] { remembered }, long.MaxValue, TimeSpan.FromDays(14));
        Assert.Contains(CacheNames.Legacy(_dir, forgotten), removed);  // left over: deleted
        Assert.False(File.Exists(CacheNames.Legacy(_dir, forgotten)));
        Assert.True(File.Exists(moved));
        await Task.CompletedTask;
    }

    [Fact]
    public async Task For_Emby_a_renamed_intro_is_copied_and_the_old_copy_stays_until_the_tidy_up()
    {
        var cache = new IntroCache(_dir, new QuietLog(), keepOldCopies: true);
        var first = await cache.EnsureAsync(Intro("Pumpkin"), Write);
        var renamed = await cache.EnsureAsync(Intro("Pumpkin Party"), Write);
        Assert.True(File.Exists(first) && File.Exists(renamed));
        Assert.Empty(cache.TakeMoves());
        Assert.Equal(new[] { first, renamed }.OrderBy(x => x), cache.CopiesOf(Intro("Pumpkin Party")).OrderBy(x => x));

        // Not until the server can play the new file.
        cache.Playable = f => f != renamed;
        Assert.Empty(cache.Prune(new[] { Intro("Pumpkin Party") }, long.MaxValue, TimeSpan.FromDays(14)));
        Assert.True(File.Exists(first));
        cache.Playable = _ => true;
        var removed = cache.Prune(new[] { Intro("Pumpkin Party") }, long.MaxValue, TimeSpan.FromDays(14));
        Assert.Equal(new[] { first! }, removed);
        Assert.True(File.Exists(renamed));
    }

    [Fact]
    public void For_Emby_files_from_version_2_are_copied_at_startup_and_removed_by_the_tidy_up()
    {
        Directory.CreateDirectory(_dir);
        var remembered = Intro("Snow Globe", path: "/prerolls/snow.mp4");
        File.WriteAllText(CacheNames.Legacy(_dir, remembered), "snow");
        new IntroCache(_dir, new QuietLog()).SaveLastKnownGood("Movie", new[] { remembered });
        var cache = new IntroCache(_dir, new QuietLog(), keepOldCopies: true);
        Assert.True(File.Exists(cache.FileFor(remembered)));
        Assert.True(File.Exists(CacheNames.Legacy(_dir, remembered))); // still registered, still plays
        var removed = cache.Prune(new[] { remembered }, long.MaxValue, TimeSpan.FromDays(14));
        Assert.Equal(new[] { CacheNames.Legacy(_dir, remembered) }, removed);
    }

    [Fact]
    public async Task An_old_version_is_used_while_a_new_one_downloads_and_removed_once_it_is_in()
    {
        var cache = new IntroCache(_dir, new QuietLog());
        var v1 = await cache.EnsureAsync(Intro("Pumpkin", "v1"), Write);
        Assert.Equal(v1, cache.AnyCopy(Intro("Pumpkin", "v2")));
        var v2 = await cache.EnsureAsync(Intro("Pumpkin", "v2"), Write);
        var removed = cache.Prune(new[] { Intro("Pumpkin", "v2") }, long.MaxValue, TimeSpan.FromDays(14));
        Assert.Contains(v1, removed);
        Assert.False(Directory.Exists(Path.GetDirectoryName(v1)));
        Assert.True(File.Exists(v2));
    }

    [Fact]
    public async Task Finished_downloads_never_stay_pending()
    {
        // A download that finished before it was registered used to stay "pending"
        // forever, and its file was never tidied up.
        var cache = new IntroCache(_dir, new QuietLog());
        for (var i = 0; i < 200; i++)
        {
            await cache.EnsureAsync(Intro("Pumpkin", "v" + i), Write);
            Assert.Equal(0, cache.PendingDownloads);
        }
    }
}
