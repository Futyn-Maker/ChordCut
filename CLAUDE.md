# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ChordCut is a portable, accessible Jellyfin music client for Windows, built for blind and visually impaired users with full NVDA/JAWS screen reader support. It uses MPV for native audio playback without server-side transcoding.

**Stack:** Python 3.13+, wxPython (GUI), python-mpv (audio), jellyfin-apiclient-python (API), SQLite (cache), PyInstaller (packaging).

## Development Commands

```bash
# Run the app (from repo root)
python -m chordcut

# Install dependencies
pip install -r requirements.txt

# Build Windows executable (Windows only, runs from build/build.bat)
# Requires: Python 3.13+, PyInstaller, gettext tools, libmpv DLL in resources/libmpv/
build\build.bat

# Compile translations (.po → .mo)
msgfmt -o locale/<lang>/LC_MESSAGES/chordcut.mo locale/<lang>/LC_MESSAGES/chordcut.po

# Generate translation template
xgettext --add-comments=Translators -o locale/chordcut.pot --from-code=UTF-8 \
    src/chordcut/*.py src/chordcut/**/*.py
```

There are no automated tests. The app is tested manually on Windows with a real Jellyfin server. Development/editing can happen in WSL but building and running requires Windows.

## Architecture

### Entry Point & App Lifecycle
`src/chordcut/__main__.py` → `app.py:ChordCutApp` (wx.App). Enforces single instance via `wx.SingleInstanceChecker` + Windows named event for focus signaling. On init: loads Settings → Database → JellyfinClient → Player → authenticates → creates MainWindow → loads library.

### Core Components (all passed into MainWindow)
- **JellyfinClient** (`api/client.py`) — Wrapper around jellyfin-apiclient-python. All calls run in `ThreadPoolExecutor(max_workers=2)`. Bulk operations (per-library pagination, playlist items) use inner pools with up to 4 workers.
- **Player** (`player/mpv_player.py`) — Thin MPV wrapper. Audio-only (`video=False`). Property observers for position/duration, event callback for track end.
- **Database** (`db/database.py`) — SQLite with normalized schema: servers, libraries, tracks, artists, album_artists, albums, playlists, playlist_tracks, plus junction tables. All query methods accept optional `library_ids: set[str]` for library filtering.
- **Settings** (`settings.py`) — JSON file persistence for user preferences (volume, seek step, sort order, active server, etc.).

### MainWindow (`ui/main_window.py` — largest file)
Central controller orchestrating all UI and logic. Key state: `_queue` (playback queue snapshot), `_nav_stack` (drill-in/out navigation), `_all_items`/`_filtered_items` (current view), per-type library caches (`_lib_tracks`, `_lib_albums`, etc.).

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
GNU gettext. All user-facing strings use `_()`. Translations live in `locale/<lang>/LC_MESSAGES/`.

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

The workflow automatically: calculates a `v{YYYY.MM.DD}[.N]` tag, bumps `__version__` in `src/chordcut/__init__.py`, builds the Windows executable, packages it as `ChordCut-Windows.zip`, commits the version bump, tags, pushes, and creates a GitHub Release with the ZIP and `.pot` template attached.

**After the release**, pull the version bump commit locally:
```bash
git pull origin main
```

## Adding or Updating Translations

All user-facing strings must be wrapped with `_()` (or `ngettext()` for plurals) imported from `chordcut.i18n`, and preceded by a `# Translators:` comment explaining context.

### Adding a new translation language

1. **Generate/update the `.pot` template** from current source:
   ```bash
   find src/chordcut -name "*.py" | sort | xargs xgettext \
     --add-comments=Translators --from-code=UTF-8 \
     --package-name=ChordCut -o locale/chordcut.pot
   ```
2. **Create the language directory and initial `.po` file** (e.g., for French `fr`):
   ```bash
   mkdir -p locale/fr/LC_MESSAGES
   msginit -i locale/chordcut.pot -o locale/fr/LC_MESSAGES/chordcut.po -l fr --no-translator
   ```
3. **Translate** the `msgstr` entries in `locale/fr/LC_MESSAGES/chordcut.po`. Each entry has a `msgid` (English source) and `msgstr` (translation to fill in). Context is provided by `# Translators:` comments extracted from source.
4. **Compile** the `.po` to binary `.mo`:
   ```bash
   msgfmt -o locale/fr/LC_MESSAGES/chordcut.mo locale/fr/LC_MESSAGES/chordcut.po
   ```
5. **Register the LCID mapping** (optional, for auto-detection on Windows): add the language's Windows LCID hex code to the `lcid_map` dict in `src/chordcut/i18n.py:_get_system_language()`. This enables automatic language selection for Windows users. If the LCID is not in the hardcoded map, it falls back to `locale.windows_locale` lookup, which covers most languages.

### Updating an existing translation after source strings change

1. **Regenerate the `.pot` template** (same command as step 1 above).
2. **Merge new strings** into the existing `.po` file:
   ```bash
   msgmerge -U locale/<lang>/LC_MESSAGES/chordcut.po locale/chordcut.pot
   ```
   This preserves existing translations and marks new/changed strings as untranslated (fuzzy).
3. **Translate** any new or fuzzy entries in the `.po` file.
4. **Recompile** to `.mo` (same as step 4 above).

The release workflow automatically regenerates the `.pot`, compiles all `.po` → `.mo`, and includes them in the build. The `.pot` file is also attached to each GitHub Release for external translators.
