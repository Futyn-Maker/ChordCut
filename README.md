[Download latest version (ChordCut-Windows.zip)](https://github.com/Futyn-Maker/chordcut/releases/latest/download/ChordCut-Windows.zip)

# ChordCut

ChordCut is a portable, accessible music client for [Jellyfin](https://jellyfin.org/) media servers on Windows. It is designed primarily for blind and visually impaired users and works with NVDA, JAWS, and other screen readers out of the box. All functionality is fully operable from the keyboard.

## Features

- Stream music directly from your Jellyfin server with no transcoding — all audio formats are played natively through MPV.
- Browse your library by tracks, artists, album artists, albums, and playlists with hierarchical drill-down navigation.
- Real-time search that filters the current section as you type.
- Sort tracks alphabetically or by date added.
- Filter by music library if your server has more than one.
- Playback queue with next/previous track, repeat, and shuffle.
- Create, rename, delete playlists and reorder tracks in them. Add or remove tracks from playlists.
- View plain and synced (timed) lyrics. Jump to any line in synced lyrics to seek to that moment.
- Download individual tracks to a configurable folder.
- View detailed properties for tracks (including bitrate, format, and file size), albums, artists, and playlists.
- Copy a Jellyfin web link for any item or a direct stream link for tracks.
- Sleep timer with three actions: close the program, shut down, or put the computer to sleep.
- System tray icon with basic playback controls — minimize and keep listening in the background.
- Connect to multiple Jellyfin servers and switch between them.
- Configurable volume and seek steps, output device selection, and persistent settings across restarts.
- Built-in auto-update — check for new versions on startup or on demand, download and install without leaving the app.
- Fully portable — the entire program runs from a single folder with no installation required.

## Getting Started

### Connecting to a Server

On first launch, ChordCut shows a login dialog. Enter your Jellyfin server URL (e.g. `https://demo.jellyfin.org/unstable`), username, and password, then press Connect. On subsequent launches, the saved credentials are used automatically.

### Interface Overview

The main window has four controls you cycle through with Tab:

1. **Section selector** — choose between Tracks, Playlists, Artists, Album Artists, and Albums.
2. **Search field** — type to filter the current list in real time.
3. **Library list** — the items in the current section. A label above the list shows a contextual count (e.g. "1100 tracks", "5 albums by Artist Name").
4. **Output device selector** — choose the audio output device.

The status bar at the bottom shows the current track, playback time, sleep timer countdown (if active), and volume level.

## Usage Guide

### Browsing the Library

Switch sections with the section selector. Press Enter on an artist to see their albums, Enter on an album to see its tracks, and so on. Press Backspace to go back one level.

### Playing Music

Press Enter on a track to start playback. This also creates a queue from all currently visible tracks. Use Shift+Right and Shift+Left to skip to the next or previous track. Press Escape to pause or resume.

Toggle repeat with Ctrl+Alt+R (loops the current track; next/previous still works). Toggle shuffle with Ctrl+Alt+S (reorders the queue; disabling it restores the original order). Stop playback entirely with Ctrl+Alt+Q — this also destroys the queue.

### Volume and Seeking

Ctrl+Up / Ctrl+Down adjusts volume. Ctrl+Right / Ctrl+Left seeks forward or backward. The step size for both is configurable in Settings (F8); defaults are 5% for volume and 5 seconds for seeking.

### Searching and Sorting

Type in the search field to filter the current section. The search matches by name for artists and playlists, by name and artist for albums, and by name, artist, and album artist for tracks.

Change the sort order of the Tracks section via View > Sorting: alphabetical A–Z or Z–A, or by date added newest or oldest first. Other sections have fixed sort orders (albums by track number, playlists by position, artists alphabetically).

### Library Filtering

If your server has multiple music libraries (e.g. "Music" and "Soundtracks"), use View > Libraries to check or uncheck which ones are visible. The selection is saved across restarts. Playlists are always shown regardless of library selection.

### Playlist Management

- **Create**: Ctrl+N or File > New Playlist. Enter a name in the dialog.
- **Rename**: select a playlist, press F2, or use the context menu.
- **Delete**: select a playlist, press Delete, or use the context menu. Confirm in the dialog.
- **Add a track**: open the context menu on any track, choose Add to Playlist, and pick a playlist from the submenu. The track is added to the top.
- **Remove a track**: inside a playlist, select a track and press Delete, or use the context menu.
- **Reorder tracks**: inside a playlist, use Alt+Up and Alt+Down to move the selected track, or use the context menu.

### Lyrics

Open the context menu on a track and choose View Lyrics for plain text, or Synced Lyrics for timed lyrics. In the synced lyrics dialog, press Enter on any line to seek to that timestamp. Ctrl+Up/Down adjusts volume and Ctrl+Right/Left seeks within the dialog, as in the main window. Press Backspace to close the dialog, or Escape to pause/resume playback. Use Ctrl+C to copy the selected line, or the Copy All button to copy all lyrics.

### Downloading Tracks

Select a track, press Ctrl+Shift+Enter (or use the context menu). A progress dialog appears. The download folder is configurable in Settings (F8); by default it is the `music` subfolder next to the executable.

### Properties and Links

Press Alt+Enter on any item to view its properties. For tracks, this includes bitrate, audio format, and file size. Press Ctrl+C in the properties dialog to copy a value.

In the main list, press Ctrl+C to copy the Jellyfin web link for the selected item, or Ctrl+Shift+C to copy the direct audio stream link.

### Context Menu

Press the Applications key, Shift+F10, or right-click to open the context menu. The available actions depend on the item type: play, open, go to artist/album, add to playlist, lyrics, download, copy link, properties, and more. Inside a playlist, additional options for removing and reordering tracks appear.

### Sleep Timer

Open via File > Sleep Timer. Set hours, minutes, and seconds, choose an action (close the program, shut down, or sleep), and press Enable Timer. The countdown appears in the status bar. Click the menu item again to cancel the timer.

### System Tray

Press Shift+Escape to minimize ChordCut to the notification area, or enable "Close button minimizes to tray" in Settings so that the close button also minimize instead of exiting. Left-click the tray icon or choose Restore from its context menu to bring the window back. The tray context menu also provides basic playback controls: pause/resume, next/previous track, volume, seeking, repeat, shuffle, and close.

### Multiple Servers

Add servers via File > Change Server > Manage Servers. In the dialog, use Add to connect to a new server, Edit to update credentials, or Delete to remove a server (the last server cannot be deleted). Switch between servers from the File > Change Server submenu.

### Settings

Press F8 or go to File > Settings to configure:

- **Download folder** — where downloaded tracks are saved.
- **Volume step** — how much volume changes per keypress (1–20%, default 5).
- **Seek step** — how far to seek per keypress (1–60 seconds, default 5).
- **Remember volume level on exit** — restore the last volume on next launch.
- **Remember output device on exit** — restore the last output device on next launch.
- **Close button minimizes to tray** — when checked, the close button minimize to the notification area instead of exiting. Use File > Exit or the tray menu to quit.
- **Check for updates on startup** — when checked (default), ChordCut silently checks for a newer version when launched. If an update is found, a dialog offers to download and install it. You can also check manually at any time via Help > Check for Updates.

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Tab | Cycle between section selector, search, list, and device selector |
| Enter | Play track / drill into item |
| Backspace | Go back one level |
| Escape | Pause / Resume |
| Shift+Escape | Minimize to system tray |
| Ctrl+Alt+Q | Stop playback and destroy queue |
| Shift+Right | Next track |
| Shift+Left | Previous track |
| Ctrl+Alt+X | Restart current track |
| Ctrl+Alt+R | Toggle repeat |
| Ctrl+Alt+S | Toggle shuffle |
| Ctrl+Up | Volume up |
| Ctrl+Down | Volume down |
| Ctrl+Right | Seek forward |
| Ctrl+Left | Seek backward |
| Ctrl+N | Create new playlist |
| F2 | Rename playlist |
| Delete | Delete playlist / Remove track from playlist |
| Alt+Up | Move track up in playlist |
| Alt+Down | Move track down in playlist |
| Alt+Enter | Properties |
| Ctrl+C | Copy Jellyfin link |
| Ctrl+Shift+C | Copy stream link (tracks only) |
| Ctrl+Shift+Enter | Download track |
| F5 | Refresh library |
| F8 | Settings |
| F1 | Keyboard shortcuts reference |
| Alt+F4 | Exit |

## Building from Source

ChordCut must be built on Windows (PyInstaller cannot cross-compile).

### Prerequisites

- Python 3.13 or later. Make sure "Add Python to PATH" is checked during installation.
- Git (to clone the repository).

### Steps

1. Clone the repository:
   ```
   git clone https://github.com/Futyn-Maker/chordcut.git
   cd chordcut
   ```

2. Run the build script:
   ```
   build\build.bat
   ```

The script will install all dependencies, download libmpv if it is not already present (or you can place `mpv-2.dll` / `libmpv-2.dll` into `resources\libmpv\` manually beforehand), compile translations, and build the application.

The output is a portable folder at `dist\ChordCut\`. Run `dist\ChordCut\ChordCut.exe` to launch.

## Translation

ChordCut uses GNU gettext for internationalization. The application detects the system locale automatically and loads the matching translation if available.

### Translating into a new language

1. Download the `chordcut.pot` template from the [latest GitHub release](https://github.com/Futyn-Maker/chordcut/releases/latest), or generate it from source:
   ```
   xgettext --add-comments=Translators -o locale/chordcut.pot --from-code=UTF-8 src/chordcut/*.py src/chordcut/**/*.py
   ```

2. Create a new `.po` file for your language (replace `xx` with the language code, e.g. `de`, `fr`, `es`):
   ```
   msginit -i locale/chordcut.pot -o locale/xx/LC_MESSAGES/chordcut.po -l xx
   ```

3. Open the `.po` file in any text editor or a tool like [Poedit](https://poedit.net/) and translate the strings.

4. Compile the translation:
   ```
   msgfmt -o locale/xx/LC_MESSAGES/chordcut.mo locale/xx/LC_MESSAGES/chordcut.po
   ```

5. Place the compiled `chordcut.mo` file into `locale/xx/LC_MESSAGES/` next to the ChordCut executable.

To update an existing translation after the template changes:
```
msgmerge -U locale/xx/LC_MESSAGES/chordcut.po locale/chordcut.pot
```

Then re-translate any new or changed strings and recompile.

## Credits

* ChordCut was inspired by [VKBoss+](https://vkboss.ru), an accessible VK music client. Many interface decisions and the overall UX approach were borrowed from that project. Thank you guys for the best music client for VK, which I still use to this day! :)
