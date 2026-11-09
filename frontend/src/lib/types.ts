// Shapes of what the server sends back. Only the fields this interface uses.

export interface AuthUser {
  id: number;
  username: string;
  display_name: string | null;
  role: "admin" | "user" | string;
}

export interface AuthStatus {
  auth_enabled: boolean;
  authenticated: boolean;
  user: AuthUser | null;
  display_name: string | null;
  users_exist: boolean;
  allow_registration: boolean;
  is_local: boolean;
  /** New (CONTRACTS §4). Missing on older servers. */
  setup_required?: boolean;
}

export interface OnboardingStatus {
  onboarding_complete: boolean;
  needs_onboarding: boolean;
  has_server: boolean;
  preroll_count: number;
  is_docker: boolean;
}

export interface CategoryRef {
  id: number;
  name: string;
}

export interface Category extends CategoryRef {
  description: string | null;
  apply_to_plex: boolean;
  plex_mode: string;
  is_system?: boolean;
}

export interface Preroll {
  id: number;
  filename: string;
  display_name: string | null;
  path: string;
  thumbnail: string | null;
  tags: string | null;
  category_id: number | null;
  category: CategoryRef | null;
  categories: CategoryRef[];
  description: string | null;
  duration: number | null;
  file_size: number | null;
  managed: boolean;
  upload_date: string | null;
  file_exists?: boolean;
  /** Smart features (newer servers). Off when a version took its place. */
  enabled?: boolean;
  /** How often it's picked at random: 1 (rarely) to 10 (often), 5 normal. */
  weight?: number;
  loudness_lufs?: number | null;
  /** Set on a version made from another intro (loudness, TV-friendly). */
  version_of?: number | null;
  version_label?: string | null;
}

export interface Schedule {
  id: number;
  name: string;
  type: "daily" | "weekly" | "monthly" | "yearly" | "holiday" | "custom" | string;
  start_date: string;
  end_date: string | null;
  category_id: number | null;
  category: CategoryRef | null;
  playlist: boolean;
  is_active: boolean;
  next_run: string | null;
  recurrence_pattern: string | null;
  recurrence_error?: string | null;
  sequence: string | null;
  blend_enabled: boolean;
  priority: number;
  exclusive: boolean;
  holiday_name: string | null;
  holiday_country?: string | null;
  source_sequence_id?: number | null;
  color: string | null;
}

export interface ServerStatus {
  connected: boolean;
  url: string | null;
  error?: string;
  message?: string;
  name?: string;
  server_name?: string;
  version?: string;
}

export interface TrashEntry {
  id: string | number;
  name?: string;
  filename?: string;
  original_path?: string;
  deleted_at?: string;
  size?: number;
}

export interface FillerSettings {
  enabled: boolean;
  type: "category" | "sequence" | "coming_soon" | string;
  category_id: number | null;
  sequence_id: number | null;
  preroll_id: number | null;
}

export interface PathMapping {
  local: string;
  plex: string;
}

export interface ApiKey {
  id: number;
  name: string;
  key_prefix?: string;
  permissions?: string;
  created_at?: string;
  last_used_at?: string | null;
  expires_at?: string | null;
  is_active?: boolean;
}

export interface LogEntry {
  id: number;
  timestamp: string;
  level: string;
  category: string;
  message: string;
  request_id: string | null;
}
