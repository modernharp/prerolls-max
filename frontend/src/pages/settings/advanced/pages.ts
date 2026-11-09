// The pages the Advanced switch reveals.
export interface AdvancedPageInfo {
  slug: string;
  title: string;
  summary: string;
  ready: boolean;
  /** Help article for the "?" button. */
  help?: string;
}

export const ADVANCED_PAGES: AdvancedPageInfo[] = [
  { slug: "playlists", title: "Playlists", summary: "Build an ordered list of intros, like a cinema pre-show.", ready: true, help: "playlists" },
  { slug: "trailers", title: "Movie trailers", summary: "Trailers for upcoming movies before the film, like at the cinema.", ready: true, help: "movie-trailers" },
  { slug: "video-maker", title: "Video maker", summary: "Make a short intro from your own words and pictures. It goes straight into your library.", ready: true, help: "video-maker" },
  { slug: "folder-mapping", title: "Folder mapping", summary: "Tell Prerolls Max where your media server sees the intro folder.", ready: true, help: "folder-mapping" },
  { slug: "storage", title: "Storage", summary: "Where intro videos are kept, and how much space they use.", ready: true, help: "storage" },
  { slug: "scaling", title: "Video scaling", summary: "Smaller copies of intros for viewers away from home.", ready: true, help: "video-scaling" },
  { slug: "trash", title: "Trash", summary: "Deleted intro videos, kept for 30 days.", ready: true, help: "settings#trash" },
  { slug: "api-keys", title: "API keys", summary: "Keys that let other apps and the plugins talk to Prerolls Max.", ready: true, help: "settings#api-keys" },
  { slug: "logs", title: "Logs", summary: "What Prerolls Max has been doing, for tracking down problems.", ready: true, help: "settings#logs" },
  { slug: "system", title: "System and updates", summary: "Version, updates and the tools Prerolls Max uses.", ready: true, help: "system-updates" },
];
