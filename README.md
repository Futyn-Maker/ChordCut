# ChordCut

An accessible Jellyfin music client for Windows, designed for blind and visually impaired users with full screen reader support.

## Features (MVP)

- Connect to Jellyfin server with username/password authentication
- Browse all audio tracks in your library
- Search/filter tracks by title, artist, or album
- Stream audio playback (supports lossy and lossless)
- Full keyboard accessibility
- Screen reader friendly (NVDA, JAWS)

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Tab | Move between search and track list |
| Up/Down | Navigate tracks |
| Enter | Play selected track |
| Escape | Pause/Resume playback |
| Ctrl+Up | Volume up |
| Ctrl+Down | Volume down |
| Ctrl+Right | Seek forward 10 seconds |
| Ctrl+Left | Seek backward 10 seconds |
| F5 | Refresh library |
| F1 | Show keyboard shortcuts |
| Alt+F4 | Exit |

## Building on Windows

### Prerequisites

1. **Python 3.13+** - Download from [python.org](https://python.org)
   - During installation, check "Add Python to PATH"

2. **libmpv** - Download from [SourceForge](https://sourceforge.net/projects/mpv-player-windows/files/libmpv/)
   - Extract `mpv-2.dll` (or `libmpv-2.dll`) to the `resources/libmpv/` folder

### Build Steps

1. Copy the entire project folder to Windows

2. Open Command Prompt in the project folder

3. Run the build script:
   ```batch
   build\build.bat
   ```

4. The built application will be in `dist\ChordCut\`

5. Run `dist\ChordCut\ChordCut.exe`

### Manual Build (Alternative)

```batch
pip install pyinstaller wxPython python-mpv jellyfin-apiclient-python
pyinstaller --clean --noconfirm build/chordcut.spec
mkdir dist\ChordCut\data
copy resources\libmpv\mpv-2.dll dist\ChordCut\
```

## Project Structure

```
chordcut/
├── src/chordcut/          # Source code
│   ├── api/             # Jellyfin API client
│   ├── db/              # SQLite database
│   ├── player/          # MPV audio player
│   ├── ui/              # wxPython user interface
│   └── utils/           # Utilities
├── resources/libmpv/    # Place libmpv DLL here
├── data/                # Database storage (created at runtime)
└── build/               # Build scripts and config
```

## Data Storage

All data is stored in the `data/` subfolder next to the executable:
- `chordcut.db` - Server credentials and cached library data

The application is fully portable - copy the entire `ChordCut/` folder to move it.

## Requirements

- Windows 10/11
- Jellyfin server (tested with 10.11.5+)
- libmpv (bundled in release builds)

## Development

Development is done in WSL. To verify syntax:

```bash
python3 -m py_compile src/chordcut/**/*.py
```

Building must be done on Windows (or via Wine) as PyInstaller cannot cross-compile.

## License

MIT License
