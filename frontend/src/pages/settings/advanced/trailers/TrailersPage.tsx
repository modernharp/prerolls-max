// Advanced > Movie trailers: trailers for upcoming movies, found through
// Radarr (and Sonarr for TV), downloaded ahead and played from a playlist step.
import { ErrorNotice, Loading } from "../../../../components/Notice";
import { SwitchRow } from "../../../../components/Controls";
import { ButtonLink } from "../../../../components/Button";
import { ArrSection } from "./ArrSection";
import { TmdbKey, TrailerOptions } from "./TrailerOptions";
import { DownloadedList, SyncButton, UpcomingList } from "./TrailerLists";
import { DownloadTroubleshooting } from "./DownloadTroubleshooting";
import { LibraryTrailers } from "./LibraryTrailers";
import { ComingSoonVideo } from "./ComingSoonVideo";
import { useSaveTrailerSettings, useTrailerSettings } from "./useTrailers";

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section className="card stack" aria-labelledby={id}>
      <h2 id={id}>{title}</h2>
      {children}
    </section>
  );
}

export function TrailersPage() {
  const settings = useTrailerSettings();
  const save = useSaveTrailerSettings();
  if (settings.isLoading) return <Loading />;
  if (settings.isError || !settings.data) return <ErrorNotice error={settings.error} onRetry={() => settings.refetch()} />;
  const s = settings.data;
  return (
    <div className="stack">
      <p className="muted">
        Prerolls Max can download trailers for movies that are coming soon, the way a cinema shows them before the film.
        Radarr says what's coming; the trailers come from YouTube. To play them, add a Movie trailers step to a playlist.
      </p>
      <Section id="tr-on" title="Turn on">
        <SwitchRow
          label="Download trailers for upcoming movies"
          description="Checks once a day and keeps the newest ones."
          checked={s.enabled}
          disabled={save.isPending}
          onChange={(enabled) => save.mutate({ enabled })}
        />
        {save.isError && <ErrorNotice error={save.error} />}
      </Section>
      <Section id="tr-radarr" title="Radarr (movies)">
        <ArrSection kind="radarr" connected={s.radarr_connected} url={s.radarr_url} />
      </Section>
      <Section id="tr-sonarr" title="Sonarr (TV shows)">
        <p className="muted small">Optional. Adds trailers for new seasons and shows.</p>
        <ArrSection kind="sonarr" connected={s.sonarr_connected} url={s.sonarr_url} />
        {s.sonarr_connected && (
          <SwitchRow label="Download TV show trailers too" checked={s.sonarr_enabled} onChange={(sonarr_enabled) => save.mutate({ sonarr_enabled })} />
        )}
      </Section>
      <Section id="tr-settings" title="Trailer settings">
        <TrailerOptions settings={s} />
      </Section>
      <Section id="tr-coming" title="Coming soon">
        <SyncButton settings={s} />
        <UpcomingList settings={s} />
      </Section>
      <Section id="tr-downloaded" title="Downloaded trailers">
        <DownloadedList />
        <div>
          <ButtonLink to="/settings/advanced/playlists/new" size="sm">
            Make a playlist with trailers
          </ButtonLink>
        </div>
      </Section>
      <Section id="tr-coming-video" title="Coming soon video">
        <ComingSoonVideo settings={s} />
      </Section>
      <Section id="tr-library" title="Trailers for movies you have">
        <LibraryTrailers />
      </Section>
      <details className="card details-card">
        <summary>
          <strong>If downloads fail</strong>
          <span className="muted small"> YouTube cookies and the YouTube helper</span>
        </summary>
        <DownloadTroubleshooting />
      </details>
      <details className="card details-card">
        <summary>
          <strong>Your own TMDB key</strong>
          <span className="muted small"> Needed for TV show trailers</span>
        </summary>
        <TmdbKey settings={s} />
      </details>
    </div>
  );
}
