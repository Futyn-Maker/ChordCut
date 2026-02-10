# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Groove is a portable, accessible Jellyfin music client for Windows, designed for blind users with full NVDA/JAWS screen reader support. Python 3.13+, wxPython GUI, MPV audio, SQLite storage.

## Development & Build

Development happens in WSL. Building and testing must be done on Windows (PyInstaller cannot cross-compile).

```bash
# Syntax check (WSL — no wxPython/mpv available)
python3 -m py_compile src/groove/db/database.py src/groove/utils/paths.py

# Build on Windows (run from project root)
build\build.bat

# Manual build on Windows
pip install pyinstaller wxPython python-mpv jellyfin-apiclient-python
pyinstaller --clean --noconfirm build/groove.spec
```

There are no unit tests. Verification is manual on Windows with a real Jellyfin server.

## Architecture

**Startup flow** (`app.py`): GrooveApp creates Database, JellyfinClient, Player → checks for stored token → if none, shows LoginDialog → creates MainWindow → calls `load_library()`.

**Data flow** (`main_window.py` → `database.py` → `client.py`):
1. On startup, cached library data from SQLite is shown **instantly** (tracks, artists, albums, playlists)
2. A background thread fetches fresh data from Jellyfin via `get_library_async()` (music views + tracks per library + playlists + playlist items in one operation)
3. When the fetch completes, `wx.CallAfter()` marshals the callback to the GUI thread
4. SQLite cache is updated via `cache_libraries()`, `cache_library()` and `cache_playlists()`; the current view refreshes in-place preserving focus

**Threading model**: All Jellyfin API calls run in a `ThreadPoolExecutor(max_workers=2)`. MPV runs its own event thread. Everything that touches wxPython UI goes through `wx.CallAfter()`. Database access is on the main thread only.

**Library navigation** (`main_window.py`): A `wx.Choice` selector switches between five sections: Tracks, Playlists, Artists, Album Artists, Albums. Each section loads its top-level items from in-memory lists (populated from DB cache). Hierarchical drill-down uses a `_nav_stack` of `_NavState` dataclass snapshots. Enter drills into sub-items (e.g. Artist → Albums → Tracks), Backspace pops back restoring focus. The section selector stays unchanged during drill-down; only the list label updates contextually (e.g. "5 albums by My Chemical Romance").

**LibraryListBox** (`ui/library_list.py`, extends `wx.ListBox`): Generic replacement for the old `TrackListBox`. Uses a native Win32 LISTBOX control. A pluggable formatter function (`set_formatter()`) controls how each dict is rendered as a display string. The `FORMATTERS` dict maps level types to their formatting functions. Focus preservation across refreshes is done by tracking the focused item's Jellyfin `Id`.

**List labels**: The visible `wx.StaticText` label shows a contextual count (e.g. "1100 tracks", "5 albums by X", "12 tracks in The Black Parade"). The same string is set as the ListBox accessible `Name` so screen readers announce it on Tab-focus. Updated by `_update_list_label()` on every filter/refresh/navigation.

**Music library selection** (`main_window.py`): A server can have multiple music libraries (e.g. "Music", "Soundtracks"). The View → Libraries submenu shows checkable items for each library. All are checked by default. Unchecking a library hides its tracks, albums, artists, and album artists from all views. Playlists are unaffected (cross-library). Library views are fetched via `/Users/{userId}/Views` filtered by `CollectionType=music`, and tracks are fetched per-library using `ParentId={libraryId}` to tag each track with its `LibraryId`.

**Streaming**: Uses `/Audio/{id}/stream?static=true` (direct passthrough, no transcoding). MPV handles all formats natively, so the server never needs to transcode. This is intentional — avoids format-allowlist issues.

## Database Schema

**Normalized library cache** — all entities are extracted from a single `get_all_tracks()` API response (plus a separate playlists fetch):

| Table | Purpose |
|-------|---------|
| `servers` | Server credentials and connection info |
| `libraries` | Music library views from the server |
| `tracks` | Cached audio tracks (with `artist_display`, `library_id`) |
| `artists` | Unique artists (from `ArtistItems`) |
| `album_artists` | Unique album artists (from `AlbumArtists`) |
| `albums` | Unique albums (with `artist_display`, `library_id`) |
| `track_artists` | Many-to-many: track ↔ artist |
| `album_album_artists` | Many-to-many: album ↔ album artist |
| `playlists` | Cached playlists |
| `playlist_tracks` | Playlist membership with position |
| `playback_positions` | Future: audiobook position memory |

**Library filtering**: Tracks and albums store `library_id` linking them to a music library. Query methods accept an optional `library_ids: set[str]` parameter — when provided, results are filtered to only include items from the selected libraries. Artists and album artists are filtered transitively through their tracks/albums. Playlists are cross-library and never filtered.

**Schema migration**: `_init_schema()` uses `CREATE TABLE IF NOT EXISTS` for all tables. No backward-compatible migrations are maintained — the DB is deleted on schema changes during development.

## Internationalization (i18n)

All user-facing strings are wrapped with `_()` (or `ngettext()` for plurals) from `groove.i18n`, which uses Python's `gettext` module with `fallback=True` (returns the original English string when no translation is installed).

**Rules for new strings:**

1. Import `from groove.i18n import _` (and `ngettext` if needed) in every UI module.
2. Wrap every user-facing string literal with `_()`.
3. Add a `# Translators:` comment on the line(s) immediately before each `_()` call explaining the context — these comments are extracted into `.pot` files by `xgettext -c Translators`.
4. Use `ngettext("{n} track", "{n} tracks", n).format(n=n)` for count-dependent strings.
5. Never use f-strings inside `_()` — use `_("...{var}...").format(var=val)` so `xgettext` can extract the template.
6. Keep the gettext domain name `"groove"`.

**Generating a .pot template:**

```bash
xgettext -c Translators -o locale/groove.pot --from-code=UTF-8 \
    src/groove/*.py src/groove/**/*.py
```

## Key Conventions

- **Data format consistency**: The DB layer returns dicts with Jellyfin PascalCase keys (`Id`, `Name`, `AlbumArtist`, `ArtistDisplay`, `RunTimeTicks`) via converter methods (`_track_to_dict`, `_artist_to_dict`, `_album_to_dict`, `_playlist_to_dict`). The UI always expects this format regardless of data source (cache vs API).
- **Multi-artist display**: Tracks store `ArtistDisplay` (all artists comma-joined) in addition to `AlbumArtist` (primary). Albums store `ArtistDisplay` for their album artist(s). Formatters use `ArtistDisplay` for rendering.
- **Portable paths**: `utils/paths.py` detects frozen (PyInstaller) vs source execution. All persistent data lives in `data/` next to the executable. Nothing is stored in user profile folders.
- **Search debounce**: 50ms `wx.Timer` prevents filtering on every keystroke. Search is contextual: filters by Name for artists/playlists, by Name+ArtistDisplay for albums, by Name+ArtistDisplay+AlbumArtist for tracks.
- **MPV end-file race condition**: When starting a new track while one is playing, MPV fires `end-file` for the old track. The callback checks `player.is_loaded` to avoid resetting the UI for the new track.
- **Window title**: Managed by `_update_title()` — shows "Track - Groove - Version" when playing/paused, "Groove - Version" when idle. `_current_track` stays set during pause.
- **libmpv DLL**: Must be placed in `resources/libmpv/` before building. Accepts `mpv-2.dll`, `libmpv-2.dll`, or `mpv-1.dll`.

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Tab | Move between section selector, search, and list |
| Up/Down | Navigate items |
| Enter | Play track / drill into item |
| Backspace | Go back one navigation level |
| Escape | Pause/Resume playback |
| Ctrl+S | Stop playback |
| Ctrl+Up/Down | Volume ±5% |
| Ctrl+Right/Left | Seek ±10 seconds |
| F5 | Refresh library from server |
| F1 | Show keyboard shortcuts dialog |
| Ctrl+Shift+S | Change server |
| Alt+F4 | Exit |

Accelerators are defined in `MainWindow._setup_accelerators()`. Menu bar mnemonics provide the same actions via Alt key.

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
- Cache-first loading (instant startup, background refresh)
- PyInstaller build script and spec file

### Stage 2: Library Navigation — COMPLETED

**Goal**: Full media library browsing with artists, albums, playlists.

- Section selector (`wx.Choice`): Tracks, Playlists, Artists, Album Artists, Albums
- Tab order: Section selector → Search box → Library list
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
- Multi-library support: per-library track fetching, Libraries submenu with checkable filters, library_id on tracks/albums
- Playlists shown regardless of library selection (cross-library entity)

### Stage 3: Enhanced Player & Context Menu

**Goal**: Full playback features and track actions.

- Play queue with next/previous track
- Play album from selected track
- Shuffle/repeat modes
- Context menu: track properties, lyrics (from Jellyfin metadata), download to PC, copy stream URL
- Extended menu bar: Next, Previous in Playback menu

### Stage 4: Global Search

**Goal**: Search across all content types simultaneously.

- Search box that queries artists, albums, and tracks
- Results grouped by type in the list view
- Keyboard shortcut to focus global search (Ctrl+F)

### Stage 5: Audiobooks

**Goal**: Separate audiobook section with position memory.

- Detect audiobook libraries from Jellyfin
- Chapter navigation within books
- Persist playback position per book in SQLite
- Resume from last position on book selection
