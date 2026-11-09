import { Navigate, useParams } from "react-router-dom";
import { ArrowLeft, Construction } from "lucide-react";
import { usePrefs, setAdvanced } from "../../../lib/prefs";
import { PageHeader } from "../../../components/HelpPanel";
import { Button, ButtonLink } from "../../../components/Button";
import { EmptyState } from "../../../components/Notice";
import { ADVANCED_PAGES } from "./pages";
import { ApiKeysPage } from "./ApiKeysPage";
import { LogsPage } from "./LogsPage";
import { FolderMappingPage } from "./FolderMappingPage";
import { TrashPage } from "./TrashPage";
import { PlaylistsPage } from "./playlists/PlaylistsPage";
import { TrailersPage } from "./trailers/TrailersPage";
import { VideoMakerPage } from "./videoMaker/VideoMakerPage";
import { StoragePage } from "./StoragePage";
import { ScalingPage } from "./ScalingPage";
import { SystemPage } from "./SystemPage";

const PAGES: Record<string, () => React.ReactElement> = {
  "api-keys": ApiKeysPage,
  logs: LogsPage,
  "folder-mapping": FolderMappingPage,
  trash: TrashPage,
  playlists: PlaylistsPage,
  trailers: TrailersPage,
  "video-maker": VideoMakerPage,
  storage: StoragePage,
  scaling: ScalingPage,
  system: SystemPage,
};

export default function AdvancedPage() {
  const { page = "" } = useParams();
  const { advanced } = usePrefs();
  const info = ADVANCED_PAGES.find((p) => p.slug === page);
  if (!info) return <Navigate to="/settings#advanced" replace />;
  const Body = PAGES[page];
  return (
    <>
      <ButtonLink to="/settings#advanced" variant="ghost" size="sm" icon={<ArrowLeft size={16} aria-hidden="true" />}>
        Settings
      </ButtonLink>
      <PageHeader title={info.title} description={info.summary} helpSlug={info.help ?? "settings"} />
      {!advanced && (
        <div className="section">
          <EmptyState title="This is an advanced option" action={<Button onClick={() => setAdvanced(true)}>Show advanced options</Button>}>
            Turn on advanced options in Settings to use it.
          </EmptyState>
        </div>
      )}
      {advanced &&
        (Body ? (
          <Body />
        ) : (
          <EmptyState icon={<Construction size={40} />} title="Coming in a later update">
            {info.title} works in the server already, but this new interface doesn't have its page yet. Your existing{" "}
            {info.title.toLowerCase()} settings keep working in the meantime.
          </EmptyState>
        ))}
    </>
  );
}
