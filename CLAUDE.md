# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ChordCut is a portable, accessible Jellyfin music client for Windows, built for blind and visually impaired users with full NVDA/JAWS screen reader support. It uses MPV for native audio playback without server-side transcoding.

**Stack:** Python 3.12+, wxPython (GUI), python-mpv (audio), jellyfin-apiclient-python (API), SQLite (cache), PyInstaller (packaging).

## Development Commands

```bash
# Run the app (from repo root)
python run.py

# Install dependencies
pip install -r requirements.txt

# Build Windows executable (Windows only, runs from build/build.bat)
# Requires: Python 3.12+, PyInstaller, Babel, libmpv DLL in resources/libmpv/
build\build.bat

# Compile translations (.po → .mo)
pybabel compile -d locale -D chordcut

# Generate translation template
pybabel extract --add-comments=Translators --charset=UTF-8 \
  --project=ChordCut -o locale/chordcut.pot src/chordcut/
```

There are no automated tests. The app is tested manually on Windows with a real Jellyfin server. Building and running requires Windows.

## Architecture

### Entry Point & App Lifecycle

`src/chordcut/__main__.py` → `app.py:ChordCutApp` (wx.App). The entry point sets up the dev environment when running from source (adds `resources/libmpv/` to PATH so `import mpv` can find the DLL). Enforces single instance via `wx.SingleInstanceChecker` + Windows named event for focus signaling. On init: sets up `wx.Locale` for standard widget translations → loads Settings → Database → JellyfinClient → Player → authenticates → creates MainWindow → loads library.

### Core Components (all passed into MainWindow)

- **JellyfinClient** (`api/client.py`) — Wrapper around jellyfin-apiclient-python. All calls run in `ThreadPoolExecutor(max_workers=2)`. Bulk operations (per-library pagination, playlist items) use inner pools with up to 4 workers. Batch playlist mutations: `add_tracks_to_playlist_top` (batch add + fetch + move to top, N+2 requests) and `remove_tracks_from_playlist` (comma-separated entry IDs).
- **Player** (`player/mpv_player.py`) — Thin MPV wrapper. Audio-only (`video=False`). Property observers for position/duration, event callback for track end.
- **Database** (`db/database.py`) — SQLite with normalized schema: servers, libraries, tracks, artists, album_artists, albums, playlists, playlist_tracks, plus junction tables. All query methods accept optional `library_ids: set[str]` for library filtering. Schema versioned via `PRAGMA user_version`; migrations live in `db/migrations.py`.
- **Settings** (`settings.py`) — JSON file persistence for user preferences (volume, seek step, sort order, check for updates, active server, etc.). Unknown keys in `settings.json` are silently ignored on load; missing keys fall back to `_DEFAULTS`.

### MainWindow (`ui/main_window.py` — largest file)

Central controller orchestrating all UI and logic. Key state: `_queue` (playback queue snapshot), `_nav_stack` (drill-in/out navigation), `_all_items`/`_filtered_items` (current view), per-type library caches (`_lib_tracks`, `_lib_albums`, etc.), `_selected_tracks`/`_selected_track_ids` (multi-track selection, persists across navigation).

Multi-track selection adds a secondary `LibraryListBox` and a "Clear selection" button, shown only when tracks are selected. Action methods (`_copy_link`, `_copy_stream_link`, `_download_tracks`, `_add_to_playlist`, `_remove_from_playlist`) are unified to accept `list[dict]` — single-item callers pass `[item]`. Adding to a playlist always places tracks at the top via `add_tracks_to_playlist_top` (batch add + fetch + N moves = N+2 requests). Bulk removal uses `remove_tracks_from_playlist` (single `DELETE` with comma-separated entry IDs). The selection context menu is built by `build_selection_context_menu()` in `ui/context_menu.py`.

**Library loading has two modes:**

- **Cold load** (<100 cached tracks): sequential paginated fetch, batches of 200, progressive UI updates
- **Warm load** (≥100 cached): instant display from SQLite cache, background refresh replaces cache on completion

### Threading Model

- All Jellyfin API calls in ThreadPoolExecutor (never on GUI thread)
- GUI updates marshaled via `wx.CallAfter()` from worker threads
- Database operations on main thread only
- MPV runs its own event thread

### Accessibility Patterns

- Native Win32 LISTBOX (`LibraryListBox` in `ui/library_list.py`) — required for NVDA/JAWS compatibility
- List labels set as accessible names so screen readers announce item counts
- Full keyboard navigation: Tab cycles controls, Enter drills in, Backspace backs out
- All menus have keyboard mnemonics

### Portable Paths (`utils/paths.py`)

Detects frozen (PyInstaller) vs source execution. Data stored next to executable: `data/chordcut.db`, `settings.json`, `data/music/` (downloads).

### i18n (`i18n.py`)

Gettext via Babel. All user-facing strings use `_()`. Translations live in `locale/<lang>/LC_MESSAGES/`. The module exposes `current_language` (a two-letter code like `'ru'` or `'en'`) used by the Help → Documentation menu item to open the matching localized HTML documentation (`readme_<lang>.html`) in the default browser, falling back to `readme_en.html`.

Standard wx widget labels (OK, Cancel, Yes, No, Close, etc.) are translated separately by `wx.Locale`, initialized in `app.py`. This requires `wxstd.mo` catalog files — PyInstaller does not bundle these automatically, so the build script copies them from the wxPython package into `_internal/locale/`. Buttons that use standard IDs (`wx.ID_OK`, `wx.ID_CANCEL`, etc.) should **not** have custom labels that duplicate the standard text; omit the label and let `wx.Locale` handle it. Custom labels are only appropriate when the text is intentionally different (e.g. `_("&Connect")` for `wx.ID_OK`).

**Important:** `LC_NUMERIC` must remain `"C"` at all times — MPV crashes otherwise. Both `i18n.py` and `app.py` restore it after any locale-changing calls.

### Auto-Updates (`updater.py`)

Checks for new releases via the GitHub API (`GET /repos/{owner}/{repo}/releases/latest`). The target repository is defined by `__repo__` in `src/chordcut/__init__.py` — change it there for forks.

**Startup check:** if `Settings.check_updates` is enabled (default), `app.py` calls `MainWindow.check_updates_on_startup()` after the window is shown. The check runs in a daemon thread; errors and "already latest" are silently ignored.

**Manual check:** Help → Check for Updates. Shows errors (with HTTP code), "up to date", or the update dialog.

**Update flow:** download ZIP to temp dir → extract → write a batch script (`chordcut_update.bat`) → launch it detached → close the app. The batch script waits for the process to exit, removes `_internal/` (which includes locale files and must be fully replaced), copies new files via `xcopy` (preserving `data/`, `settings.json`, `music/`), starts the new executable, and self-deletes.

## Versioning

Semantic date-based: `v{YYYY.MM.DD}[.N]`. Version string lives in `src/chordcut/__init__.py`. CI workflow (`.github/workflows/release.yml`) auto-bumps it on release.

## Making a Release

The release is built by a GitHub Actions workflow (`.github/workflows/release.yml`). To trigger it:

1. **Ensure `main` is up to date** — all changes intended for the release must be pushed to `main`.
2. **Trigger the workflow** via GitHub CLI:

   ```bash
   # Without changelog:
   gh workflow run release.yml

   # With changelog/release notes:
   gh workflow run release.yml -f changelog="- Added feature X
   - Fixed bug Y"
   ```

3. **Monitor the run** until it completes:
   ```bash
   gh run list --workflow=release.yml --limit=1
   gh run watch          # watches the most recent run
   ```
4. **Verify the release** was created:
   ```bash
   gh release list --limit=1
   ```

The workflow: calculates a `v{YYYY.MM.DD}[.N]` tag, bumps `__version__` in `src/chordcut/__init__.py`, downloads libmpv, regenerates the `.pot` translation template, then delegates the actual build to `build\build.bat` (which installs dependencies, compiles translations, runs PyInstaller, copies wx translations, and generates HTML documentation from `README*.md` via pandoc). After the build, the workflow packages the output as `ChordCut-Windows.zip`, commits the version bump, tags, pushes, and creates a GitHub Release with the ZIP and `.pot` template attached.

**After the release**, pull the version bump commit locally:

```bash
git pull origin main
```

## Adding or Updating Translations

All user-facing strings must be wrapped with `_()` (or `ngettext()` for plurals) imported from `chordcut.i18n`, and preceded by a `# Translators:` comment explaining context. See [Writing translator comments](#writing-translator-comments) below for placement rules.

### Adding a new translation language

1. **Generate/update the `.pot` template** from current source (requires `pip install babel`):
   ```bash
   pybabel extract --add-comments=Translators --charset=UTF-8 \
     --project=ChordCut -o locale/chordcut.pot src/chordcut/
   ```
2. **Create the language directory and initial `.po` file** (e.g., for French `fr`):
   ```bash
   pybabel init -i locale/chordcut.pot -d locale -D chordcut -l fr
   ```
3. **Translate** the `msgstr` entries in `locale/fr/LC_MESSAGES/chordcut.po`. Each entry has a `msgid` (English source) and `msgstr` (translation to fill in). Context is provided by `# Translators:` comments extracted from source.
4. **Compile** the `.po` to binary `.mo`:
   ```bash
   pybabel compile -d locale -D chordcut
   ```
5. **Register the LCID mapping** (optional, for auto-detection on Windows): add the language's Windows LCID hex code to the `lcid_map` dict in `src/chordcut/i18n.py:_get_system_language()`. This enables automatic language selection for Windows users. If the LCID is not in the hardcoded map, it falls back to `locale.windows_locale` lookup, which covers most languages.

### Updating an existing translation after source strings change

1. **Regenerate the `.pot` template** (same command as step 1 above).
2. **Merge new strings** into the existing `.po` file:
   ```bash
   pybabel update -i locale/chordcut.pot -d locale -D chordcut
   ```
   This preserves existing translations and marks new/changed strings as untranslated (fuzzy).
3. **Translate** any new or fuzzy entries in the `.po` file.
4. **Recompile** to `.mo` (same as step 4 above).

The release workflow automatically regenerates the `.pot`, compiles all `.po` → `.mo`, and includes them in the build. The `.pot` file is also attached to each GitHub Release for external translators.

### Writing translator comments

This project uses Babel (`pybabel extract`) for string extraction. Babel uses Python's tokenizer and correctly handles multi-line `_()` and `ngettext()` calls — Ruff's formatter may freely wrap these calls without breaking comment extraction.

**Rule 1 — comment goes directly before `_()`**, not before an outer function call:

```python
# WRONG — comment is on the line before wx.Button(), not _()
# Translators: Save button.
wx.Button(panel, wx.ID_OK, _("Save"))

# CORRECT — comment inside the outer call, directly above _()
wx.Button(
    panel, wx.ID_OK,
    # Translators: Save button.
    _("Save"),
)
```

**Rule 2 — no blank lines** between the comment and the `_()` / `ngettext()` call. Other comments (like `# fmt: off`) between `# Translators:` and the call are fine.

Multiple consecutive comment lines directly before `_()` are all captured and appear together in the `.pot`.

**Do not use f-strings inside `_()`** — they evaluate before gettext can translate the string. Always use `_("...{placeholder}...").format(placeholder=value)`.

## Database Migrations

Schema is versioned with SQLite's `PRAGMA user_version`. The current version number, the migration list, and all migration functions live in `src/chordcut/db/migrations.py`. The base table definitions (`CREATE TABLE IF NOT EXISTS`) live in `src/chordcut/db/models.py:SCHEMA`.

On startup `Database._init_schema()` runs `SCHEMA` (idempotent), then applies any migrations whose version exceeds the database's `user_version`, then sets `user_version` to `SCHEMA_VERSION`.

### How to add a migration (step by step)

When you need to change the database schema (add/remove a table, add/remove/rename a column, add an index, etc.):

1. **Edit `SCHEMA` in `src/chordcut/db/models.py`** to reflect the final desired state. This is what fresh installs will get. For example, add a new column to a `CREATE TABLE` block, or add a new `CREATE TABLE IF NOT EXISTS` statement.

2. **Open `src/chordcut/db/migrations.py`** and:
   - Write a migration function `_migrate_to_N(conn: sqlite3.Connection) -> None` that performs the change on an existing database. The function **must be defensive** — it should check whether the change is already present before applying it, because it also runs on fresh databases where `SCHEMA` already includes the change.
   - Append `(N, _migrate_to_N)` to the `MIGRATIONS` list.
   - Set `SCHEMA_VERSION = N`.

3. **Never delete old migrations.** A user could be updating from any previous version, so all migrations must remain in order.

### Example migration

Adding a `genre` column to `tracks` and a new `favorites` table:

```python
# In migrations.py:

def _migrate_to_2(conn: sqlite3.Connection) -> None:
    # Add column — check first because fresh DBs already have it.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(tracks)")}
    if "genre" not in cols:
        conn.execute("ALTER TABLE tracks ADD COLUMN genre TEXT")
    # New tables are handled by CREATE TABLE IF NOT EXISTS in SCHEMA,
    # so no action needed here for the favorites table.

SCHEMA_VERSION = 2
MIGRATIONS.append((2, _migrate_to_2))
```

And in `models.py`, update the `tracks` table in `SCHEMA` to include the `genre TEXT` column, and add the `CREATE TABLE IF NOT EXISTS favorites (...)` block.
