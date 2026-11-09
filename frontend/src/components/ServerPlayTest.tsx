// "Play a test" that asks the server itself: pick a server and a movie, and
// Prerolls Max asks that server what it would play first (a Plex play queue,
// or the /Intros call Jellyfin and Emby apps make). Nothing starts playing.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Clapperboard, Search } from "lucide-react";
import { api } from "../lib/api";
import { useMediaServers, type Movie, type PlayTestResult } from "../lib/mediaServers";
import { Select } from "./Select";
import { TextField } from "./Field";
import { Button } from "./Button";
import { ErrorNotice, Loading, Notice } from "./Notice";

export function ServerPlayTest({ serverId: initial }: { serverId?: number }) {
  const servers = useMediaServers();
  const usable = (servers.data ?? []).filter((s) => s.enabled);
  const [serverId, setServerId] = useState(initial ? String(initial) : "");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [movieId, setMovieId] = useState("");

  useEffect(() => {
    if (!serverId && usable.length) setServerId(String(usable[0]?.id));
  }, [serverId, usable]);

  const server = usable.find((s) => String(s.id) === serverId);
  const movies = useQuery({
    queryKey: ["server-movies", serverId, query],
    enabled: Boolean(server),
    retry: false,
    queryFn: async () => (await api.get<{ items: Movie[] }>(`/api/servers/${serverId}/movies`, { q: query }, { timeoutMs: 30_000 })).items,
  });
  useEffect(() => {
    const first = movies.data?.[0];
    if (first && !movies.data?.some((m) => m.id === movieId)) setMovieId(first.id);
  }, [movies.data, movieId]);

  const ask = useMutation({
    mutationFn: () => api.post<PlayTestResult>(`/api/servers/${serverId}/play-test`, { item_id: movieId }, { timeoutMs: 60_000 }),
  });

  if (servers.isLoading) return <Loading label="Finding your media servers…" />;
  if (servers.isError) return <ErrorNotice error={servers.error} onRetry={() => servers.refetch()} />;
  if (!usable.length) return <p className="muted">Add a media server first, then come back to test it.</p>;

  return (
    <div className="stack">
      <Select
        label="Media server"
        value={serverId}
        onChange={(v) => {
          setServerId(v);
          setMovieId("");
          ask.reset();
        }}
        options={usable.map((s) => ({ value: String(s.id), label: s.name === s.type_label ? s.name : `${s.name} (${s.type_label})` }))}
      />
      <form
        className="input-row"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(search.trim());
        }}
      >
        <TextField label="Find a movie" placeholder="Part of the title" value={search} onChange={(e) => setSearch(e.target.value)} />
        <div className="align-end">
          <Button type="submit" icon={<Search size={16} aria-hidden="true" />}>Search</Button>
        </div>
      </form>
      {movies.isLoading && <Loading label={`Asking ${server?.name ?? "the server"} for its movies…`} />}
      {movies.isError && <ErrorNotice error={movies.error} onRetry={() => movies.refetch()} />}
      {movies.data && !movies.data.length && (
        <p className="muted">{query ? `No movie matches "${query}" on ${server?.name}.` : `${server?.name} has no movies yet.`}</p>
      )}
      {movies.data && movies.data.length > 0 && (
        <Select
          label="Movie"
          value={movieId}
          onChange={(v) => {
            setMovieId(v);
            ask.reset();
          }}
          options={movies.data.map((m) => ({ value: m.id, label: m.year ? `${m.title} (${m.year})` : m.title }))}
        />
      )}
      <div>
        <Button variant="primary" icon={<Clapperboard size={18} aria-hidden="true" />} disabled={!movieId} loading={ask.isPending}
          onClick={() => ask.mutate()}>
          Ask {server?.name ?? "the server"} what it would play
        </Button>
      </div>
      <div aria-live="polite">
        {ask.isError && <ErrorNotice error={ask.error} />}
        {ask.data && <PlayTestAnswer result={ask.data} />}
      </div>
    </div>
  );
}

function PlayTestAnswer({ result }: { result: PlayTestResult }) {
  if (!result.ok) return <Notice tone="error" title="The server didn't answer">{result.summary}</Notice>;
  if (result.items.length) {
    return (
      <Notice tone="success" title="It works">
        <p>{result.summary}</p>
      </Notice>
    );
  }
  return (
    <Notice tone="warning" title={result.summary}>
      {result.reasons.length > 0 && (
        <>
          <p>What to check:</p>
          <ul>
            {result.reasons.map((r) => (
              <li key={r.title}>
                <strong>{r.title}.</strong> {r.detail} {r.link && <Link to={r.link.to}>{r.link.label}</Link>}
              </li>
            ))}
          </ul>
        </>
      )}
    </Notice>
  );
}
