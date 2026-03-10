# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ChordCut is a portable, accessible Jellyfin music client for Windows, designed for blind users with full NVDA/JAWS screen reader support. Python 3.13+, wxPython GUI, MPV audio, SQLite storage.

## Development & Build

Development happens in WSL. Building and testing must be done on Windows (PyInstaller cannot cross-compile).

```bash
# Syntax check (WSL — no wxPython/mpv available)
python3 -m py_compile src/chordcut/db/database.py src/chordcut/utils/paths.py

# Build on Windows (run from project root)
build\build.bat

# Manual build on Windows
pip install pyinstaller wxPython python-mpv jellyfin-apiclient-python
pyinstaller --clean --noconfirm build/chordcut.spec
```

There are no unit tests. Verification is manual on Windows with a real Jellyfin server.

## Architecture

**Startup flow** (`app.py`): `OnInit` first checks `wx.SingleInstanceChecker` — if another instance is running it opens the named Windows Event `Global\ChordCut_ActivateWindow`, signals it (causing the first instance to restore its window), and returns False. Otherwise it creates that event, starts a daemon listener thread, then creates Settings, Database, JellyfinClient, Player → reads `settings.active_server_id` → looks up server via `db.get_server(id)` → tries token reconnect → if none or failed, shows LoginDialog (saves new server_id to settings) → creates MainWindow → calls `load_library()`. MainWindow applies saved volume and audio device in `_apply_startup_settings()`.

**Data flow — two loading modes** (`main_window.py` → `database.py` → `client.py`):

`load_library()` checks `count_tracks(server_id)` (unfiltered) to choose the mode:

*Cold load* (< 100 cached tracks — first launch, empty/partial DB):
1. `fetch_library_paginated()` runs in a background thread: fetches music views, then sends `Limit=0` requests in parallel for each library (gets `TotalRecordCount` and warms the server's query cache), then paginates tracks in pages of 200 (`StartIndex`/`Limit`) sequentially per library.
2. Each page callback is marshaled to the GUI thread via `wx.CallAfter()`. The handler writes the batch to SQLite via `cache_library_batch()`, reloads all in-memory lists from DB, and refreshes the current view.
3. The label shows "X of Y tracks" where X and Y are scoped to **enabled libraries only** (per-library counts stored in `_lib_track_counts` / `_lib_loaded_counts`). Toggling a library mid-load instantly recalculates the visible counts.
4. Search field is hidden (removed from tab order) until visible libraries are fully loaded. Tracks can be played individually but no playback queue is built during cold load.
5. When all enabled libraries finish loading, `_finish_cold_load()` fires: search appears, label normalizes. Hidden libraries continue loading in the background silently.
6. After all libraries finish, playlists are fetched (items in parallel) and cached. `_loading_in_progress` is cleared.

*Warm load* (≥ 100 cached tracks — normal restart):
1. Cached library data from SQLite is shown **instantly** (tracks, artists, albums, playlists).
2. A background thread fetches fresh data via `get_library_async()` (music views + all tracks per library in parallel + playlists + playlist items in parallel).
3. When the fetch completes, `wx.CallAfter()` marshals the callback to the GUI thread.
4. SQLite cache is fully replaced via `cache_library()` (DELETE + INSERT in one transaction) and `cache_playlists()`; the current view refreshes in-place preserving focus.

A `_loading_in_progress` flag prevents concurrent loads (F5 during an active load is ignored).

**Threading model**: All Jellyfin API calls run in a `ThreadPoolExecutor(max_workers=2)`. Per-library track fetches (warm load) and per-playlist item fetches use short-lived inner `ThreadPoolExecutor` pools (max 4 workers) for parallelism. MPV runs its own event thread. Everything that touches wxPython UI goes through `wx.CallAfter()`. Database access is on the main thread only.

**Library navigation** (`main_window.py`): A `wx.Choice` selector switches between five sections: Tracks, Playlists, Artists, Album Artists, Albums. Each section loads its top-level items from in-memory lists (populated from DB cache). Hierarchical drill-down uses a `_nav_stack` of `_NavState` dataclass snapshots. Enter drills into sub-items (e.g. Artist → Albums → Tracks), Backspace pops back restoring focus. The section selector stays unchanged during drill-down; only the list label updates contextually (e.g. "5 albums by My Chemical Romance").

**LibraryListBox** (`ui/library_list.py`, extends `wx.ListBox`): Generic replacement for the old `TrackListBox`. Uses a native Win32 LISTBOX control. A pluggable formatter function (`set_formatter()`) controls how each dict is rendered as a display string. The `FORMATTERS` dict maps level types to their formatting functions. Focus preservation across refreshes is done by tracking the focused item's Jellyfin `Id`.

**List labels**: The visible `wx.StaticText` label shows a contextual count (e.g. "1100 tracks", "5 albums by X", "12 tracks in The Black Parade"). The same string is set as the ListBox accessible `Name` so screen readers announce it on Tab-focus. Updated by `_update_list_label()` on every filter/refresh/navigation.

**Music library selection** (`main_window.py`): A server can have multiple music libraries (e.g. "Music", "Soundtracks"). The View → Libraries submenu shows checkable items for each library. All are checked by default. Unchecking a library hides its tracks, albums, artists, and album artists from all views. Playlists are unaffected (cross-library). The enabled/disabled state is persisted in the `libraries.enabled` DB column via `set_library_enabled()`, so the selection survives restarts. Library views are fetched via `/Users/{userId}/Views` filtered by `CollectionType=music`, and tracks are fetched per-library using `ParentId={libraryId}` to tag each track with its `LibraryId`.

**Streaming**: Uses `/Audio/{id}/stream?static=true` (direct passthrough, no transcoding). MPV handles all formats natively, so the server never needs to transcode. This is intentional — avoids format-allowlist issues.

**Audio device selection** (`main_window.py`): A `wx.Choice` selector after the library list (last in tab order). Populated from MPV's `audio-device-list` property. First item is "Default (device name)" (`auto`), followed by all output devices, and "No device" (`null`) last. Changing the selection sets MPV's `audio-device` property, which switches output seamlessly without interrupting playback.

**Playback queue** (`main_window.py`): Built when a track is played via Enter. The queue is a snapshot of `_filtered_items` at time of play. A `_QueueOrigin` dataclass records where the queue was created (section, nav depth, context). Auto-focus on the next track works only when the user is in the same section/level. Queue is pruned on library refresh/library toggle (tracks removed from library are dropped). Stop (`Ctrl+Alt+Q`) destroys the queue. Repeat loops the current track without blocking next/prev navigation. Shuffle reorders the queue (not the list display); disabling shuffle restores the original order.

**Context menu** (`ui/context_menu.py`): Dynamic menu built per item type. Tracks get: Play, Go to Artist/Album, Add to Playlist (submenu), View Lyrics, Synced Lyrics, Download, Copy Link, Properties. When viewing playlist tracks, also: Remove from Playlist, Move Up, Move Down. Albums get: Open, Go to Artist, Copy Link, Properties. Artists get: Open, Copy Link, Properties. Playlists get: Open, Rename, Delete, Copy Link, Properties. Sub-levels add a "Go Back" item.

**Playlist CRUD** (`main_window.py`): Create (Ctrl+N or File → New Playlist, text entry dialog, async `POST /Playlists`), Rename (F2 or context menu, text entry dialog with old name pre-filled, async `POST /Items/{id}` with full item body), Delete (Delete key or context menu, confirmation dialog, async `DELETE /Items/{id}`). All three update DB and in-memory `_lib_playlists` immediately, then fire async API calls.

**Playlist management** (`main_window.py`): Three operations on playlist tracks via context menu and keyboard. "Add to Playlist" submenu appears on all tracks — lists all playlists, disables those already containing the track; adds to the top (API add + move to index 0). "Remove from Playlist" (Delete key) appears only inside playlist tracks — shows confirmation, updates UI instantly, then fires async API request. "Move Up/Down" (Alt+Up/Down) reorders tracks within a playlist — swaps in `_all_items` immediately, updates DB positions, fires async `Move/{newIndex}` API call. All three use `PlaylistItemId` (stored in `playlist_tracks.playlist_item_id` DB column) for API calls. The `_current_playlist_id()` helper detects when we're inside a playlist by checking `_nav_stack[-1].level_type == "playlists"`.

**Multi-server support** (`main_window.py`, `ui/dialogs/servers_dialog.py`): File → Change Server is a submenu listing all saved servers as radio items (active server checked); clicking an inactive server triggers token reconnect then `_reset_for_server_switch()` + `load_library()`. "Manage Servers..." opens `ServersDialog`: Add (full login → cold load of new server), Edit (pre-filled login dialog; on success warm-reloads if active server; on failure restores old client state), Delete (confirmation, cascade DELETE in DB, switches to first remaining server; last server cannot be deleted). `_current_server: ServerCredentials | None` on MainWindow holds the server in use by the current load. `_load_server_id: int | None` guards stale background callbacks: when a server switch clears it to `None`, any in-flight `wx.CallAfter` closures from the old load see the mismatch and exit without touching the DB or UI.

**Sleep timer** (`main_window.py`, `ui/dialogs/timer_dialog.py`): File → Sleep Timer opens `TimerDialog` with three `wx.SpinCtrl` fields (hours 0–23, minutes 0–59, seconds 0–59) and a `wx.Choice` action selector (Close the program / Shut down the computer / Put the computer to sleep). Clicking "Enable Timer" starts a `wx.Timer` that fires every second; the remaining time is shown in status bar pane 3 as `Timer: HH:MM:SS`. The File menu item is a check item — it shows a checkmark while the timer is running, and clicking it again cancels and resets the timer. On expiry: close calls `self.Close()`, shutdown calls `shutdown /s /t 0`, sleep calls `rundll32.exe powrprof.dll,SetSuspendState 0,1,0`. The countdown timer is stopped in `_on_close`. The timer is not persisted — it resets on restart.

**System tray icon** (`main_window.py`, `ui/tray_icon.py`): A `TrayIcon` (`wx.adv.TaskBarIcon` subclass) is created unconditionally on startup and stays visible in the notification area at all times. If no `.ico` file is present, the icon is generated programmatically (a purple 16×16 bitmap with a "G" glyph). Shift+Escape hides the main window; left-clicking the tray icon or choosing "Restore" from its context menu calls `_restore_from_tray()` (Show + Restore + Raise). The tray context menu provides minimal playback controls: Restore, Pause/Resume, Previous Track, Next Track, Volume Up, Volume Down, Seek Forward, Seek Backward, Repeat (checkable), Shuffle (checkable), Close. "Close" calls `_force_close()` which destroys the tray icon then calls `self.Close()`. The main window's `_on_close` always destroys the tray icon before shutting down. `_tray_toggle_repeat()` and `_tray_toggle_shuffle()` are dedicated helpers that toggle state and also sync the main menu's check items, so both entry points stay consistent.

**Dialogs** (`ui/dialogs/`): Properties (ListBox with key-value lines, Ctrl+C to copy), plain lyrics (read-only TextCtrl), synced lyrics (ListBox with `[MM:SS] text`, Enter seeks), download (Gauge progress bar, background thread), settings (download folder via `wx.DirPickerCtrl`, volume/seek steps, remember-on-exit checkboxes), servers (ListBox + Add/Edit/Delete buttons, Delete key accelerator), timer (hours/minutes/seconds spin controls, action dropdown, validates non-zero duration).

**Settings** (`settings.py`): User preferences are stored in `settings.json` next to the executable (not in `data/` alongside the DB). `Settings` loads on startup and is passed to `MainWindow`. On exit, `_on_close` saves current volume and device if the corresponding "remember" checkboxes are enabled. Volume/seek steps are read on every use so changes take effect immediately. Download dir is read on each download. Persisted keys: `active_server_id` (replaces the old DB `is_active` flag), `download_dir`, `volume_step`, `seek_step`, `remember_volume`, `remember_device`, `volume`, `device`, `track_sort`. Defaults: volume 80, steps 5, track_sort `date_desc`, active_server_id None.

**Track sorting** (`main_window.py`): The View → Sorting submenu controls how the top-level Tracks section is ordered. Four radio options: Alphabetical A–Z (`alpha_asc`), Alphabetical Z–A (`alpha_desc`), By date added newest first (`date_desc`, default), By date added oldest first (`date_asc`). The setting is persisted in `settings.json` via `track_sort` and passed to `Database.get_all_tracks(sort=...)` which uses different `ORDER BY` clauses. Only the top-level Tracks section is affected — album tracks always sort by track number, playlist tracks by playlist position, and artists/albums stay alphabetical. The `DateCreated` timestamp from Jellyfin is stored in the `tracks.date_created` DB column.

**Lyrics API**: `GET /Audio/{itemId}/Lyrics` returns `{Lyrics: [{Start: ticks, Text: str}]}`. Available from Jellyfin 10.9+. Fetched async; no caching.

## Database Schema

**Normalized library cache** — all entities are extracted from track API responses (plus a separate playlists fetch):

| Table | Purpose |
|-------|---------|
| `servers` | Server credentials and connection info (no `is_active` — active server ID lives in `settings.json`) |
| `libraries` | Music library views from the server (with `enabled` flag) |
| `tracks` | Cached audio tracks (with `artist_display`, `library_id`, `date_created`) |
| `artists` | Unique artists (from `ArtistItems`) |
| `album_artists` | Unique album artists (from `AlbumArtists`) |
| `albums` | Unique albums (with `artist_display`, `library_id`) |
| `track_artists` | Many-to-many: track ↔ artist |
| `album_album_artists` | Many-to-many: album ↔ album artist |
| `playlists` | Cached playlists |
| `playlist_tracks` | Playlist membership with position and `playlist_item_id` |
| `playback_positions` | Future: audiobook position memory |

**Library filtering**: Tracks and albums store `library_id` linking them to a music library. Query methods accept an optional `library_ids: set[str]` parameter — when provided, results are filtered to only include items from the selected libraries. Artists and album artists are filtered transitively through their tracks/albums. Playlists are cross-library and never filtered.

**Cache write methods**: `cache_library(server_id, tracks)` does DELETE + INSERT in a single transaction (warm load). `clear_library_cache(server_id)` + `cache_library_batch(server_id, tracks)` split the operation for progressive loading (cold load) — clear once, then insert batches incrementally. Both share `_insert_library_data()` which extracts artists, album_artists, albums, and mapping tables from the tracks list. `count_tracks(server_id)` returns the unfiltered track count (used to choose cold vs warm load).

**Schema migration**: `_init_schema()` uses `CREATE TABLE IF NOT EXISTS` for all tables. No backward-compatible migrations are maintained — the DB is deleted on schema changes during development.

## Internationalization (i18n)

All user-facing strings are wrapped with `_()` (or `ngettext()` for plurals) from `chordcut.i18n`. The application automatically detects the system locale and loads the appropriate translation from `locale/{lang}/LC_MESSAGES/chordcut.mo`. If no translation exists, English strings are used (fallback mode).

**Locale folder structure:**

```
locale/
├── chordcut.pot              # Translation template (generated)
├── ru/
│   └── LC_MESSAGES/
│       ├── chordcut.po       # Russian translation source
│       └── chordcut.mo       # Compiled translation (build artifact, not in git)
└── ... (other languages)
```

**Rules for new strings:**

1. Import `from chordcut.i18n import _` (and `ngettext` if needed) in every UI module.
2. Wrap every user-facing string literal with `_()`.
3. Add a `# Translators:` comment on the line(s) immediately before each `_()` call explaining the context — these comments are extracted into `.pot` files by `xgettext --add-comments=Translators`.
4. Use `ngettext("{n} track", "{n} tracks", n).format(n=n)` for count-dependent strings.
5. Never use f-strings inside `_()` — use `_("...{var}...").format(var=val)` so `xgettext` can extract the template.
6. Keep the gettext domain name `"chordcut"`.

**Updating translations:**

1. Regenerate the .pot template after adding/modifying strings:
   ```bash
   xgettext --add-comments=Translators -o locale/chordcut.pot --from-code=UTF-8 \
       src/chordcut/*.py src/chordcut/**/*.py
   ```

2. Update existing .po files with new strings:
   ```bash
   msgmerge -U locale/ru/LC_MESSAGES/chordcut.po locale/chordcut.pot
   ```

3. Compile .po to .mo (happens automatically during build, or manually):
   ```bash
   msgfmt -o locale/ru/LC_MESSAGES/chordcut.mo locale/ru/LC_MESSAGES/chordcut.po
   ```

**Creating a new translation:**

```bash
msginit -i locale/chordcut.pot -o locale/{lang}/LC_MESSAGES/chordcut.po -l {lang}
# Edit the .po file, then compile:
msgfmt -o locale/{lang}/LC_MESSAGES/chordcut.mo locale/{lang}/LC_MESSAGES/chordcut.po
```

## Key Conventions

- **Data format consistency**: The DB layer returns dicts with Jellyfin PascalCase keys (`Id`, `Name`, `AlbumArtist`, `ArtistDisplay`, `RunTimeTicks`) via converter methods (`_track_to_dict`, `_artist_to_dict`, `_album_to_dict`, `_playlist_to_dict`). The UI always expects this format regardless of data source (cache vs API).
- **Multi-artist display**: Tracks store `ArtistDisplay` (all artists comma-joined) in addition to `AlbumArtist` (primary). Albums store `ArtistDisplay` for their album artist(s). Formatters use `ArtistDisplay` for rendering.
- **Portable paths**: `utils/paths.py` detects frozen (PyInstaller) vs source execution. Database and cache live in `data/` next to the executable. `settings.json` lives directly next to the executable (via `get_settings_path()`). Nothing is stored in user profile folders.
- **Search debounce**: 50ms `wx.Timer` prevents filtering on every keystroke. Search is contextual: filters by Name for artists/playlists, by Name+ArtistDisplay for albums, by Name+ArtistDisplay+AlbumArtist for tracks.
- **MPV end-file race condition**: When starting a new track while one is playing, MPV fires `end-file` for the old track. The callback checks `player.is_loaded` to avoid resetting the UI for the new track.
- **Window title**: Managed by `_update_title()` — shows "Track - ChordCut - Version" when playing/paused, "ChordCut - Version" when idle. `_current_track` stays set during pause.
- **libmpv DLL**: Must be placed in `resources/libmpv/` before building. Accepts `mpv-2.dll`, `libmpv-2.dll`, or `mpv-1.dll`.

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Tab | Move between section selector, search, and list |
| Up/Down | Navigate items |
| Enter | Play track / drill into item |
| Backspace | Go back one navigation level |
| Escape | Pause/Resume playback |
| Shift+Escape | Minimize to system tray |
| Ctrl+Alt+Q | Stop playback (destroys queue) |
| Shift+Right | Next track in queue |
| Shift+Left | Previous track in queue |
| Ctrl+Alt+X | Restart current track |
| Ctrl+Alt+R | Toggle repeat mode |
| Ctrl+Alt+S | Toggle shuffle mode |
| Ctrl+Up/Down | Volume ± (configurable step, default 5%) |
| Ctrl+Right/Left | Seek ± (configurable step, default 5 seconds) |
| Alt+Enter | Properties dialog |
| Ctrl+C | Copy Jellyfin link |
| Ctrl+Shift+C | Copy stream link (tracks only) |
| Ctrl+Shift+Enter | Download track |
| Ctrl+N | Create new playlist |
| F2 | Rename playlist (in playlists section) |
| Delete | Remove track from playlist / delete playlist |
| Alt+Up | Move track up in playlist (in playlist tracks only) |
| Alt+Down | Move track down in playlist (in playlist tracks only) |
| F5 | Refresh library from server |
| F8 | Settings dialog |
| F1 | Show keyboard shortcuts dialog |
| Alt+F4 | Exit |

Accelerators are defined in `MainWindow._setup_accelerators()`. Menu bar mnemonics provide the same actions via Alt key. Context menu activated with Applications key, Shift+F10, or right-click.

## Adding a New Feature

Follow these steps in order:

1. **Research the Jellyfin API** — If the feature requires API endpoints not yet used in `client.py`, search for documentation or examples first. If docs are insufficient, check whether a `.env` file exists in the project root — it may contain credentials for a real Jellyfin server. Write throwaway debug scripts to hit the API, inspect responses, and understand the data shape. **Delete all debug scripts when done.**

2. **Plan the data flow** — Decide where data lives: does it need a new SQLite table? A new method in `database.py`? A new async wrapper in `client.py`? Follow the existing pattern: API → cache in DB → load from cache on startup, refresh in background.

3. **Implement bottom-up** — Database schema/methods → API client methods → UI components. This way each layer can be syntax-checked independently.

4. **Maintain accessibility** — Use `wx.ListBox` (not `wx.ListCtrl`) for any new lists. Add a visible `wx.StaticText` count label and set the ListBox `Name` to match. Ensure full keyboard operability and screen reader compatibility.

5. **Syntax-check in WSL** — Run `python3 -m py_compile` on changed files. wxPython/mpv imports will fail in WSL, but pure-Python modules (db, utils) can be verified.

6. **Refactor and review** — After the feature works, step back and assess:
   - Are any files becoming too large? Split if a module exceeds ~400 lines or handles unrelated concerns.
   - Can anything be simplified or deduplicated?
   - Did the change touch a pattern used elsewhere that also needs updating (e.g. a new dict key that `_track_to_dict()` should include)?
   - Are there stale methods, unused imports, or dead code left behind?
   - Update `CLAUDE.md` if the change affects architecture, conventions, or shortcuts.

## Development Roadmap

### Stage 1: MVP Foundation — COMPLETED

**Goal**: Connect to Jellyfin, display all tracks, search, and play with basic controls.

- Project setup (pyproject.toml, src layout, requirements.txt)
- SQLite database layer with credential storage and track caching
- Threaded Jellyfin API client (login, token reconnect, track fetching)
- MPV player wrapper (play, pause, stop, seek, volume, event callbacks)
- Login dialog with validation
- Main window with native ListBox, search debounce, status bar, menu bar
- Keyboard shortcuts for all playback controls
- Screen reader accessibility via native LISTBOX control (no custom IAccessible needed)
- Two-mode loading: cold load (progressive pagination with per-page UI updates) and warm load (instant from cache, bulk background refresh)
- PyInstaller build script and spec file

### Stage 2: Library Navigation — COMPLETED

**Goal**: Full media library browsing with artists, albums, playlists.

- Section selector (`wx.Choice`): Tracks, Playlists, Artists, Album Artists, Albums
- Tab order: Section selector → Search box → Library list → Output device selector
- Hierarchical navigation: Artists → Albums → Tracks, Album Artists → Albums → Tracks, Albums → Tracks, Playlists → Tracks
- `Enter` to drill down, `Backspace` to go up with focus restoration
- Normalized SQLite schema: artists, album_artists, albums, playlists, track_artists, album_album_artists, playlist_tracks tables
- Library data extracted from single `get_all_tracks()` response; playlists fetched separately
- Multi-artist support: `ArtistDisplay` field with comma-joined artist names
- Contextual search: filters by appropriate fields per section/level
- Contextual list labels: "N tracks in Album", "N albums by Artist", etc.
- `LibraryListBox` with pluggable formatters replaces `TrackListBox`
- In-memory library cache for instant section switching
- Background refresh updates DB + in-memory data without disrupting sub-level browsing
- Progressive cold load: paginated track fetching (200/page) with per-page UI updates, "X of Y tracks" progress label scoped to enabled libraries, search hidden until loaded, queue deferred until complete
- Multi-library support: per-library track fetching, Libraries submenu with checkable filters, library_id on tracks/albums
- Playlists shown regardless of library selection (cross-library entity)

### Stage 3: Enhanced Player & Context Menu — COMPLETED

**Goal**: Full playback features and track actions.

- Playback queue: created on Enter, auto-advances, auto-focuses if in same section
- Queue updates on library refresh/toggle; destroyed on Stop
- Repeat mode (Ctrl+Alt+R): loops current track, next/prev still works
- Shuffle mode (Ctrl+Alt+S): shuffles queue, not list display; unshuffle restores order
- Next/Previous track (Shift+Right/Left)
- Restart track (Ctrl+Alt+X)
- OS toast notifications for repeat/shuffle toggle (screen-reader accessible)
- Context menu on all library items (Applications key / right-click / Shift+F10)
- Properties dialog: track (with bitrate/format/size from API), artist (album/track counts), album (track count/duration), playlist (track count/duration)
- Copy Jellyfin web link (Ctrl+C) for all item types
- Download track (Ctrl+Shift+Enter) to `music/` folder with progress bar
- Plain lyrics dialog (read-only text with Copy)
- Synced lyrics dialog (ListBox with timestamps, Enter to seek)
- Go to Artist / Go to Album navigation from context menu
- Audio device selector (`wx.Choice`): lists all output devices, "Default (device name)" first, "No device" last. Switches MPV `audio-device` seamlessly without interrupting playback. Last in tab order, visible in all sections.
- New files: `ui/context_menu.py`, `ui/dialogs/properties_dialog.py`, `ui/dialogs/lyrics_dialog.py`, `ui/dialogs/download_dialog.py`

### Stage 4: Settings & Persistence — COMPLETED

**Goal**: User-configurable settings with persistent state across restarts.

- Settings dialog (F8 / File → Settings): download folder (`wx.DirPickerCtrl`), volume step, seek step, remember-volume and remember-device checkboxes
- Settings stored in `settings.json` next to the executable (separate from DB)
- `Settings` class (`settings.py`) with typed properties; loaded at startup, saved on demand
- Volume restored to saved level on launch (default 75); device restored if saved
- Volume and device saved on exit when the corresponding checkbox is checked
- Library enabled/disabled state persisted in `libraries.enabled` DB column; survives restarts and server refreshes
- Download folder is configurable; `DownloadDialog` accepts a `download_dir` parameter
- Volume and seek steps applied dynamically (no restart needed)

### Stage 5: Sleep Timer — COMPLETED

**Goal**: Allow the user to schedule an automatic action (close, shutdown, sleep) after a configurable delay.

- File → Sleep Timer opens a setup dialog with hour/minute/second fields and an action dropdown
- Countdown shown in status bar pane 3 (`Timer: HH:MM:SS`); File menu item checked while active
- Clicking the active menu item cancels and resets the timer
- On expiry: closes the app, shuts down Windows, or suspends via `powrprof.dll`
- New file: `ui/dialogs/timer_dialog.py`

### Stage 6: System Tray — COMPLETED

**Goal**: Allow the user to minimize ChordCut to the notification area for background playback.

- System tray icon always visible (`TrayIcon` in `ui/tray_icon.py`); icon generated programmatically if no `.ico` is bundled
- Shift+Escape hides the main window to tray; left-click or "Restore" menu item restores it
- Tray right-click menu: Restore, Pause/Resume, Previous/Next Track, Volume Up/Down, Seek Forward/Backward, Repeat (checkable), Shuffle (checkable), Close
- "Close" from tray menu performs a full shutdown; tray icon is also destroyed in `_on_close`
- New file: `ui/tray_icon.py`

### Stage 7: Audiobooks

**Goal**: Separate audiobook section with position memory.

- Detect audiobook libraries from Jellyfin
- Chapter navigation within books
- Persist playback position per book in SQLite
- Resume from last position on book selection
