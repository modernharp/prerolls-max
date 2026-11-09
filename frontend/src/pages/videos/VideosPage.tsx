import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { Film, FolderInput, FolderOpen, Globe } from "lucide-react";
import { PageHeader } from "../../components/HelpPanel";
import { LibraryTab } from "./LibraryTab";
import { CollectionsTab } from "./CollectionsTab";
import { CommunityTab } from "./community/CommunityTab";
import { WatchFoldersTab } from "./watch/WatchFoldersTab";

// The "?" opens the guide for the tab you're on.
const TAB_HELP: Record<string, string> = { community: "community", watch: "watch-folders" };

export default function VideosPage() {
  const tab = useLocation().pathname.split("/")[2] ?? "";
  return (
    <>
      <PageHeader
        title="Intro Videos"
        description="The short videos that play before your movies."
        helpSlug={TAB_HELP[tab] ?? "intro-videos"}
      />
      <nav className="tabs-list" aria-label="Intro videos">
        <NavLink to="/videos" end className="tab">
          <Film size={18} aria-hidden="true" /> Your videos
        </NavLink>
        <NavLink to="/videos/collections" className="tab">
          <FolderOpen size={18} aria-hidden="true" /> Collections
        </NavLink>
        <NavLink to="/videos/community" className="tab">
          <Globe size={18} aria-hidden="true" /> Get more from Community
        </NavLink>
        <NavLink to="/videos/watch" className="tab">
          <FolderInput size={18} aria-hidden="true" /> Add automatically
        </NavLink>
      </nav>
      <Routes>
        <Route index element={<LibraryTab />} />
        <Route path="collections" element={<CollectionsTab />} />
        <Route path="community" element={<CommunityTab />} />
        <Route path="watch" element={<WatchFoldersTab />} />
      </Routes>
    </>
  );
}
