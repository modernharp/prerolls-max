-- Schema real NeXroll 2.4.0 created on first start (dumped from its nexroll.db).
CREATE TABLE api_keys (
	id INTEGER NOT NULL, 
	name VARCHAR NOT NULL, 
	key_hash VARCHAR NOT NULL, 
	key_prefix VARCHAR(8) NOT NULL, 
	permissions VARCHAR, 
	expires_at DATETIME, 
	created_at DATETIME, 
	last_used_at DATETIME, 
	is_active BOOLEAN, 
	description TEXT, 
	PRIMARY KEY (id)
);
CREATE TABLE auth_audit_logs (
	id INTEGER NOT NULL, 
	timestamp DATETIME NOT NULL, 
	event_type VARCHAR NOT NULL, 
	username VARCHAR, 
	user_id INTEGER, 
	ip_address VARCHAR, 
	user_agent VARCHAR, 
	details VARCHAR, 
	PRIMARY KEY (id)
);
CREATE TABLE categories (
	id INTEGER NOT NULL, 
	name VARCHAR, 
	description TEXT, 
	plex_mode VARCHAR, 
	apply_to_plex BOOLEAN, 
	is_system BOOLEAN, 
	PRIMARY KEY (id)
);
CREATE TABLE coming_soon_trailers (
	id INTEGER NOT NULL, 
	radarr_movie_id INTEGER, 
	tmdb_id INTEGER, 
	imdb_id VARCHAR, 
	certification VARCHAR, 
	genres TEXT, 
	title VARCHAR, 
	year INTEGER, 
	overview TEXT, 
	release_date DATETIME, 
	release_type VARCHAR, 
	trailer_url VARCHAR, 
	local_path VARCHAR, 
	file_size_mb FLOAT, 
	duration_seconds INTEGER, 
	resolution VARCHAR, 
	poster_url VARCHAR, 
	fanart_url VARCHAR, 
	downloaded_at DATETIME, 
	status VARCHAR, 
	error_message TEXT, 
	is_enabled BOOLEAN, 
	monitored BOOLEAN, 
	excluded_from_list BOOLEAN, 
	play_count INTEGER, 
	last_played DATETIME, 
	created_at DATETIME, 
	updated_at DATETIME, 
	PRIMARY KEY (id)
);
CREATE TABLE coming_soon_tv_trailers (
	id INTEGER NOT NULL, 
	sonarr_series_id INTEGER, 
	tvdb_id INTEGER, 
	tmdb_id INTEGER, 
	imdb_id VARCHAR, 
	certification VARCHAR, 
	genres TEXT, 
	title VARCHAR, 
	year INTEGER, 
	season_number INTEGER, 
	overview TEXT, 
	network VARCHAR, 
	release_date DATETIME, 
	release_type VARCHAR, 
	trailer_url VARCHAR, 
	local_path VARCHAR, 
	file_size_mb FLOAT, 
	duration_seconds INTEGER, 
	resolution VARCHAR, 
	poster_url VARCHAR, 
	fanart_url VARCHAR, 
	downloaded_at DATETIME, 
	status VARCHAR, 
	error_message TEXT, 
	is_enabled BOOLEAN, 
	monitored BOOLEAN, 
	excluded_from_list BOOLEAN, 
	play_count INTEGER, 
	last_played DATETIME, 
	created_at DATETIME, 
	updated_at DATETIME, 
	PRIMARY KEY (id)
);
CREATE TABLE community_templates (
	id INTEGER NOT NULL, 
	name VARCHAR, 
	description TEXT, 
	author VARCHAR, 
	template_data TEXT, 
	category VARCHAR, 
	tags TEXT, 
	downloads INTEGER, 
	rating FLOAT, 
	created_at DATETIME, 
	is_public BOOLEAN, 
	PRIMARY KEY (id)
);
CREATE TABLE genre_maps (
	id INTEGER NOT NULL, 
	genre VARCHAR, 
	genre_norm VARCHAR, 
	category_id INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(category_id) REFERENCES categories (id)
);
CREATE TABLE holiday_presets (
	id INTEGER NOT NULL, 
	name VARCHAR, 
	description TEXT, 
	month INTEGER, 
	day INTEGER, 
	start_month INTEGER, 
	start_day INTEGER, 
	end_month INTEGER, 
	end_day INTEGER, 
	is_recurring BOOLEAN, 
	category_id INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(category_id) REFERENCES categories (id)
);
CREATE TABLE ignored_paths (
	id INTEGER NOT NULL, 
	path VARCHAR, 
	path_key VARCHAR, 
	filename VARCHAR, 
	reason VARCHAR, 
	created_at DATETIME, 
	PRIMARY KEY (id)
);
CREATE TABLE library_trailers (
	id INTEGER NOT NULL, 
	radarr_movie_id INTEGER, 
	tmdb_id INTEGER, 
	certification VARCHAR, 
	title VARCHAR, 
	year INTEGER, 
	genres TEXT, 
	added_to_library DATETIME, 
	source VARCHAR, 
	status VARCHAR, 
	error_message TEXT, 
	local_path VARCHAR, 
	trailer_url VARCHAR, 
	file_size_mb FLOAT, 
	duration_seconds INTEGER, 
	poster_url VARCHAR, 
	is_enabled BOOLEAN, 
	in_selection BOOLEAN, 
	downloaded_at DATETIME, 
	last_attempt_at DATETIME, 
	created_at DATETIME, 
	updated_at DATETIME, 
	PRIMARY KEY (id)
);
CREATE TABLE log_entries (
	id INTEGER NOT NULL, 
	timestamp DATETIME NOT NULL, 
	level VARCHAR NOT NULL, 
	category VARCHAR NOT NULL, 
	source VARCHAR, 
	message TEXT NOT NULL, 
	details TEXT, 
	request_id VARCHAR, 
	user_id INTEGER, 
	duration_ms INTEGER, 
	ip_address VARCHAR, 
	PRIMARY KEY (id)
);
CREATE TABLE navigation_favorites (
	scope VARCHAR NOT NULL, 
	page VARCHAR NOT NULL, 
	user_id INTEGER, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (scope, page), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE TABLE preroll_categories (
	preroll_id INTEGER NOT NULL, 
	category_id INTEGER NOT NULL, 
	PRIMARY KEY (preroll_id, category_id), 
	FOREIGN KEY(preroll_id) REFERENCES prerolls (id) ON DELETE CASCADE, 
	FOREIGN KEY(category_id) REFERENCES categories (id) ON DELETE CASCADE
);
CREATE TABLE prerolls (
	id INTEGER NOT NULL, 
	filename VARCHAR, 
	display_name VARCHAR, 
	path VARCHAR, 
	thumbnail VARCHAR, 
	tags TEXT, 
	category_id INTEGER, 
	description TEXT, 
	duration FLOAT, 
	file_size INTEGER, 
	managed BOOLEAN, 
	upload_date DATETIME, 
	community_preroll_id VARCHAR, 
	exclude_from_matching BOOLEAN, 
	file_hash VARCHAR, 
	enabled BOOLEAN, 
	PRIMARY KEY (id), 
	FOREIGN KEY(category_id) REFERENCES categories (id)
);
CREATE TABLE radarr_servers (
	id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, 
	name VARCHAR, 
	url VARCHAR NOT NULL, 
	api_key VARCHAR NOT NULL, 
	created_at DATETIME
);
CREATE TABLE saved_sequences (
	id INTEGER NOT NULL, 
	name VARCHAR, 
	description TEXT, 
	blocks TEXT, 
	created_at DATETIME, 
	updated_at DATETIME, 
	PRIMARY KEY (id)
);
CREATE TABLE schedules (
	id INTEGER NOT NULL, 
	name VARCHAR, 
	type VARCHAR, 
	start_date DATETIME, 
	end_date DATETIME, 
	category_id INTEGER, 
	fallback_category_id INTEGER, 
	playlist BOOLEAN, 
	is_active BOOLEAN, 
	last_run DATETIME, 
	next_run DATETIME, 
	recurrence_pattern VARCHAR, 
	preroll_ids TEXT, 
	sequence TEXT, 
	color VARCHAR, 
	blend_enabled BOOLEAN, 
	priority INTEGER, 
	"exclusive" BOOLEAN, 
	holiday_name VARCHAR, 
	holiday_country VARCHAR, 
	source_sequence_id INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(category_id) REFERENCES categories (id), 
	FOREIGN KEY(fallback_category_id) REFERENCES categories (id)
);
CREATE TABLE sessions (
	id INTEGER NOT NULL, 
	session_token VARCHAR NOT NULL, 
	user_id INTEGER NOT NULL, 
	created_at DATETIME, 
	expires_at DATETIME NOT NULL, 
	ip_address VARCHAR, 
	user_agent VARCHAR, 
	is_valid BOOLEAN, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE TABLE settings (
	id INTEGER NOT NULL, 
	plex_url VARCHAR, 
	plex_token VARCHAR, 
	jellyfin_url VARCHAR, 
	jellyfin_api_key VARCHAR, 
	emby_url VARCHAR, 
	emby_api_key VARCHAR, 
	community_fair_use_accepted BOOLEAN, 
	community_fair_use_accepted_at DATETIME, 
	community_server_url VARCHAR, 
	community_auto_refresh BOOLEAN, 
	plex_client_id VARCHAR, 
	plex_server_base_url VARCHAR, 
	plex_server_machine_id VARCHAR, 
	plex_server_name VARCHAR, 
	active_category INTEGER, 
	timezone VARCHAR, 
	last_backup_at VARCHAR, 
	onboarding_complete BOOLEAN, 
	onboarding_restart_requested BOOLEAN, 
	updated_at DATETIME, 
	override_expires_at DATETIME, 
	path_mappings TEXT, 
	last_schedule_fallback INTEGER, 
	genre_auto_apply BOOLEAN, 
	genre_priority_mode VARCHAR, 
	genre_override_ttl_seconds INTEGER, 
	dashboard_tile_order TEXT, 
	dashboard_layout TEXT, 
	last_seen_version VARCHAR, 
	verbose_logging BOOLEAN, 
	passive_mode BOOLEAN, 
	clear_when_inactive BOOLEAN, 
	playback_guard_minutes INTEGER, 
	nexup_enabled BOOLEAN, 
	nexup_radarr_url VARCHAR, 
	nexup_radarr_api_key VARCHAR, 
	nexup_storage_path VARCHAR, 
	plugin_random_count INTEGER, 
	nexup_quality VARCHAR, 
	nexup_days_ahead INTEGER, 
	nexup_max_trailers INTEGER, 
	nexup_max_storage_gb FLOAT, 
	nexup_trailers_per_playback INTEGER, 
	nexup_playback_order VARCHAR, 
	nexup_auto_refresh_hours INTEGER, 
	nexup_last_sync DATETIME, 
	nexup_category_id INTEGER, 
	nexup_download_delay INTEGER, 
	nexup_max_concurrent INTEGER, 
	nexup_bulk_warning_threshold INTEGER, 
	nexup_tmdb_api_key VARCHAR, 
	nexup_sonarr_enabled BOOLEAN, 
	nexup_sonarr_url VARCHAR, 
	nexup_sonarr_api_key VARCHAR, 
	nexup_tv_category_id INTEGER, 
	nexup_last_sonarr_sync DATETIME, 
	nexup_max_trailer_duration INTEGER, 
	nexup_trailer_language VARCHAR, 
	nexup_trailer_language_fallback VARCHAR, 
	nexup_include_unmonitored_movies BOOLEAN, 
	nexup_include_unmonitored_shows BOOLEAN, 
	nexup_release_date_preference VARCHAR, 
	nexup_dynamic_preroll_template VARCHAR, 
	nexup_dynamic_preroll_server_name VARCHAR, 
	nexup_dynamic_preroll_duration INTEGER, 
	nexup_dynamic_preroll_theme VARCHAR, 
	nexup_dynamic_preroll_custom_logo_path VARCHAR, 
	nexup_dynamic_preroll_language VARCHAR, 
	nexup_dynamic_preroll_resolution VARCHAR, 
	nexup_dynamic_preroll_frame_rate INTEGER, 
	nexup_dynamic_preroll_render_quality VARCHAR, 
	nexup_dynamic_preroll_font_scale FLOAT, 
	nexup_dynamic_preroll_font_family VARCHAR, 
	nexup_dynamic_preroll_title_color VARCHAR, 
	nexup_dynamic_preroll_subject_color VARCHAR, 
	nexup_dynamic_preroll_audio_mode VARCHAR, 
	nexup_dynamic_preroll_custom_audio_path VARCHAR, 
	nexup_dynamic_preroll_custom_headline VARCHAR, 
	nexup_dynamic_preroll_custom_subtext VARCHAR, 
	nexup_dynamic_preroll_qr_data VARCHAR, 
	nexup_dynamic_preroll_qr_caption VARCHAR, 
	nexup_dynamic_preroll_qr_dark VARCHAR, 
	nexup_dynamic_preroll_qr_light VARCHAR, 
	nexup_dynamic_preroll_qr_style VARCHAR, 
	nexup_dynamic_preroll_qr_logo BOOLEAN, 
	nexup_dynamic_preroll_qr_plate_color VARCHAR, 
	nexup_dynamic_preroll_qr_plate_opacity INTEGER, 
	nexup_dynamic_preroll_qr_plate_radius INTEGER, 
	nexup_coming_soon_list_auto_regen BOOLEAN, 
	nexup_coming_soon_list_layout VARCHAR, 
	nexup_coming_soon_list_source VARCHAR, 
	nexup_coming_soon_list_duration INTEGER, 
	nexup_coming_soon_list_max_items INTEGER, 
	nexup_coming_soon_list_bg_color VARCHAR, 
	nexup_coming_soon_list_text_color VARCHAR, 
	nexup_coming_soon_list_accent_color VARCHAR, 
	nexup_coming_soon_list_server_name VARCHAR, 
	nexup_coming_soon_list_auto_regen_layout VARCHAR, 
	nexup_coming_soon_list_include_audio BOOLEAN, 
	nexup_coming_soon_list_custom_audio_path VARCHAR, 
	nexup_coming_soon_list_custom_logo_path VARCHAR, 
	nexup_coming_soon_list_custom_backdrop_path VARCHAR, 
	nexup_coming_soon_list_backdrop_dim INTEGER, 
	nexup_dynamic_preroll_custom_backdrop_path VARCHAR, 
	nexup_dynamic_preroll_backdrop_dim INTEGER, 
	nexup_coming_soon_list_logo_mode VARCHAR, 
	nexup_coming_soon_list_language VARCHAR, 
	nexup_coming_soon_list_resolution VARCHAR, 
	nexup_coming_soon_list_frame_rate INTEGER, 
	nexup_coming_soon_list_render_quality VARCHAR, 
	nexup_coming_soon_list_theme VARCHAR, 
	nexup_coming_soon_list_qr_data VARCHAR, 
	nexup_coming_soon_list_font_scale FLOAT, 
	nexup_coming_soon_list_font_family VARCHAR, 
	nexup_coming_soon_list_auto_regen_log VARCHAR, 
	nexup_coming_soon_list_title_color VARCHAR, 
	nexup_coming_soon_list_date_color VARCHAR, 
	nexup_coming_soon_list_available_color VARCHAR, 
	nexup_coming_soon_list_heading_color VARCHAR, 
	nexup_coming_soon_available_days INTEGER, 
	nexup_coming_soon_max_available_now INTEGER, 
	nexup_trailer_retention_days INTEGER, 
	library_trailers_config TEXT, 
	auth_enabled BOOLEAN, 
	auth_session_timeout_hours INTEGER, 
	auth_allow_registration BOOLEAN, 
	auth_require_https BOOLEAN, 
	update_check_interval VARCHAR, 
	update_include_prerelease BOOLEAN, 
	update_last_check DATETIME, 
	update_dismissed_version VARCHAR, 
	update_auto_install BOOLEAN, 
	update_auto_hour INTEGER, 
	update_auto_delay_days INTEGER, 
	update_auto_last_attempt VARCHAR, 
	log_level VARCHAR, 
	log_retention_days INTEGER, 
	log_to_database BOOLEAN, 
	log_request_logging BOOLEAN, 
	log_scheduler_logging BOOLEAN, 
	log_api_logging BOOLEAN, 
	auto_scan_minutes INTEGER, 
	filler_enabled BOOLEAN, 
	filler_type VARCHAR, 
	filler_category_id INTEGER, 
	filler_sequence_id INTEGER, 
	filler_coming_soon_layout VARCHAR, 
	filler_dynamic_filename VARCHAR, 
	filler_preroll_id INTEGER, 
	filler_active VARCHAR, 
	applied_sequence_id INTEGER, 
	applied_sequence_name VARCHAR, 
	active_schedule_id INTEGER, 
	preroll_folder VARCHAR, 
	ignored_conflicts VARCHAR, genre_aggressive_intercept_enabled BOOLEAN DEFAULT 0, 
	PRIMARY KEY (id), 
	FOREIGN KEY(active_category) REFERENCES categories (id), 
	FOREIGN KEY(nexup_category_id) REFERENCES categories (id), 
	FOREIGN KEY(nexup_tv_category_id) REFERENCES categories (id), 
	FOREIGN KEY(filler_category_id) REFERENCES categories (id), 
	FOREIGN KEY(filler_sequence_id) REFERENCES saved_sequences (id)
);
CREATE TABLE sonarr_servers (
	id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, 
	name VARCHAR, 
	url VARCHAR NOT NULL, 
	api_key VARCHAR NOT NULL, 
	created_at DATETIME
);
CREATE TABLE users (
	id INTEGER NOT NULL, 
	username VARCHAR NOT NULL, 
	password_hash VARCHAR NOT NULL, 
	display_name VARCHAR, 
	email VARCHAR, 
	role VARCHAR, 
	is_active BOOLEAN, 
	created_at DATETIME, 
	last_login_at DATETIME, 
	failed_login_attempts INTEGER, 
	locked_until DATETIME, 
	PRIMARY KEY (id)
);
CREATE INDEX idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX idx_api_keys_prefix ON api_keys(key_prefix);
CREATE INDEX idx_auth_audit_event ON auth_audit_logs(event_type);
CREATE INDEX idx_auth_audit_timestamp ON auth_audit_logs(timestamp);
CREATE INDEX idx_auth_audit_username ON auth_audit_logs(username);
CREATE INDEX idx_log_category ON log_entries(category);
CREATE INDEX idx_log_level ON log_entries(level);
CREATE INDEX idx_log_request ON log_entries(request_id);
CREATE INDEX idx_log_timestamp ON log_entries(timestamp);
CREATE UNIQUE INDEX idx_sessions_token ON sessions(session_token);
CREATE INDEX idx_sessions_user ON sessions(user_id);
CREATE INDEX idx_tv_trailers_sonarr ON coming_soon_tv_trailers(sonarr_series_id);
CREATE INDEX idx_tv_trailers_title ON coming_soon_tv_trailers(title);
CREATE INDEX idx_tv_trailers_tvdb ON coming_soon_tv_trailers(tvdb_id);
CREATE UNIQUE INDEX idx_users_username ON users(username);
CREATE INDEX ix_api_keys_id ON api_keys (id);
CREATE INDEX ix_api_keys_key_hash ON api_keys (key_hash);
CREATE INDEX ix_auth_audit_logs_event_type ON auth_audit_logs (event_type);
CREATE INDEX ix_auth_audit_logs_id ON auth_audit_logs (id);
CREATE INDEX ix_auth_audit_logs_timestamp ON auth_audit_logs (timestamp);
CREATE INDEX ix_auth_audit_logs_username ON auth_audit_logs (username);
CREATE INDEX ix_categories_id ON categories (id);
CREATE UNIQUE INDEX ix_categories_name ON categories (name);
CREATE INDEX ix_coming_soon_trailers_id ON coming_soon_trailers (id);
CREATE INDEX ix_coming_soon_trailers_radarr_movie_id ON coming_soon_trailers (radarr_movie_id);
CREATE INDEX ix_coming_soon_trailers_title ON coming_soon_trailers (title);
CREATE INDEX ix_coming_soon_trailers_tmdb_id ON coming_soon_trailers (tmdb_id);
CREATE INDEX ix_coming_soon_tv_trailers_id ON coming_soon_tv_trailers (id);
CREATE INDEX ix_coming_soon_tv_trailers_sonarr_series_id ON coming_soon_tv_trailers (sonarr_series_id);
CREATE INDEX ix_coming_soon_tv_trailers_title ON coming_soon_tv_trailers (title);
CREATE INDEX ix_coming_soon_tv_trailers_tvdb_id ON coming_soon_tv_trailers (tvdb_id);
CREATE INDEX ix_community_templates_id ON community_templates (id);
CREATE INDEX ix_community_templates_name ON community_templates (name);
CREATE UNIQUE INDEX ix_genre_maps_genre ON genre_maps (genre);
CREATE UNIQUE INDEX ix_genre_maps_genre_norm ON genre_maps (genre_norm);
CREATE INDEX ix_genre_maps_id ON genre_maps (id);
CREATE INDEX ix_holiday_presets_id ON holiday_presets (id);
CREATE UNIQUE INDEX ix_holiday_presets_name ON holiday_presets (name);
CREATE INDEX ix_ignored_paths_id ON ignored_paths (id);
CREATE UNIQUE INDEX ix_ignored_paths_path_key ON ignored_paths (path_key);
CREATE INDEX ix_library_trailers_id ON library_trailers (id);
CREATE INDEX ix_library_trailers_radarr_movie_id ON library_trailers (radarr_movie_id);
CREATE INDEX ix_library_trailers_title ON library_trailers (title);
CREATE INDEX ix_library_trailers_tmdb_id ON library_trailers (tmdb_id);
CREATE INDEX ix_log_entries_category ON log_entries (category);
CREATE INDEX ix_log_entries_id ON log_entries (id);
CREATE INDEX ix_log_entries_level ON log_entries (level);
CREATE INDEX ix_log_entries_request_id ON log_entries (request_id);
CREATE INDEX ix_log_entries_timestamp ON log_entries (timestamp);
CREATE INDEX ix_prerolls_community_preroll_id ON prerolls (community_preroll_id);
CREATE INDEX ix_prerolls_file_hash ON prerolls (file_hash);
CREATE INDEX ix_prerolls_filename ON prerolls (filename);
CREATE INDEX ix_prerolls_id ON prerolls (id);
CREATE INDEX ix_saved_sequences_id ON saved_sequences (id);
CREATE INDEX ix_saved_sequences_name ON saved_sequences (name);
CREATE INDEX ix_schedules_id ON schedules (id);
CREATE INDEX ix_schedules_name ON schedules (name);
CREATE INDEX ix_sessions_id ON sessions (id);
CREATE UNIQUE INDEX ix_sessions_session_token ON sessions (session_token);
CREATE INDEX ix_settings_id ON settings (id);
CREATE INDEX ix_users_id ON users (id);
CREATE UNIQUE INDEX ix_users_username ON users (username);
