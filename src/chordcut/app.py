"""Main application class for ChordCut."""

import ctypes
import threading
import wx

from chordcut.api import JellyfinClient
from chordcut.db import Database
from chordcut.db.database import ServerCredentials
from chordcut.i18n import _
from chordcut.player import Player
from chordcut.settings import Settings
from chordcut.ui import LoginDialog, MainWindow

# Named Windows Event used to signal the first instance to activate.
_ACTIVATE_EVENT_NAME = "Global\\ChordCut_ActivateWindow"


class ChordCutApp(wx.App):
    """Main wxPython application class."""

    def __init__(self):
        """Initialize the application."""
        self._db: Database | None = None
        self._client: JellyfinClient | None = None
        self._player: Player | None = None
        self._settings: Settings | None = None
        self._main_window: MainWindow | None = None
        self._instance_checker: wx.SingleInstanceChecker | None = None
        # Win32 HANDLE to the named activation event (first instance only).
        self._activate_event: int = 0

        super().__init__(redirect=False)

    def OnInit(self) -> bool:
        """Initialize the application (called by wxPython).

        Returns:
            True if initialization succeeded.
        """
        # Single-instance guard: if another copy is running, signal it
        # to restore/focus its window, then exit this second instance.
        checker = wx.SingleInstanceChecker("ChordCut")
        self._instance_checker = checker
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        if checker.IsAnotherRunning():
            handle = kernel32.OpenEventW(
                0x0002,  # EVENT_MODIFY_STATE
                False,
                _ACTIVATE_EVENT_NAME,
            )
            if handle:
                kernel32.SetEvent(handle)
                kernel32.CloseHandle(handle)
            return False

        # Create the named event that a future second instance can signal.
        self._activate_event = kernel32.CreateEventW(
            None, False, False, _ACTIVATE_EVENT_NAME,
        )

        # Initialize core components
        self._settings = Settings()
        self._db = Database()
        self._client = JellyfinClient()
        self._player = Player()

        # Look up the last active server from settings
        server_id = self._settings.active_server_id
        server = (
            self._db.get_server(server_id)
            if server_id is not None
            else None
        )

        # If no active server in settings, check if there are servers in DB
        # (handles migration from older versions where DB exists but no settings)
        if server is None:
            all_servers = self._db.get_all_servers()
            if all_servers:
                server = all_servers[0]
                # Persist this as the active server
                self._settings.active_server_id = server.id
                self._settings.save()

        if server:
            # Try to reconnect with saved token
            if self._try_reconnect(server):
                self._show_main_window()
                return True

        # No saved credentials or reconnect failed - show login
        if self._show_login(prefill=server):
            self._show_main_window()
            return True

        # User cancelled login
        return False

    def _try_reconnect(self, server: ServerCredentials) -> bool:
        """Try to reconnect using saved credentials.

        Args:
            server: Saved server credentials.

        Returns:
            True if reconnection succeeded.
        """
        return self._client.login_with_token(
            server.url,
            server.user_id,
            server.access_token,
            server.device_id,
        )

    def _show_login(
        self,
        prefill: ServerCredentials | None = None,
    ) -> bool:
        """Show the login dialog and authenticate.

        Args:
            prefill: Optional server whose URL/username to pre-fill.

        Returns:
            True if login succeeded, False if cancelled.
        """
        # Track last entered values so we can re-fill after failure.
        last_url: str = ""
        last_username: str = ""

        while True:
            dialog = LoginDialog()

            if last_url:
                # Re-fill with what the user previously typed.
                dialog.set_server_url(last_url)
                dialog.set_username(last_username)
            elif prefill:
                dialog.set_server_url(prefill.url)
                dialog.set_username(prefill.username)

            result = dialog.ShowModal()

            if result != wx.ID_OK:
                dialog.Destroy()
                return False

            # Try to authenticate
            server_url = dialog.server_url
            username = dialog.username
            password = dialog.password
            dialog.Destroy()

            # Remember these for the next iteration on failure.
            last_url = server_url
            last_username = username

            # Show progress
            # Translators: Busy dialog message shown while connecting to the Jellyfin server.
            progress = wx.BusyInfo(_("Connecting to server..."))

            auth_result = self._client.login(server_url, username, password)

            del progress

            if auth_result:
                # Save credentials
                creds = ServerCredentials(
                    id=None,
                    url=server_url,
                    user_id=self._client.user_id or "",
                    username=username,
                    access_token=self._client.access_token or "",
                    device_id=self._client.device_id,
                )
                server_id = self._db.save_server(creds)
                self._settings.active_server_id = server_id
                self._settings.save()
                return True
            else:
                wx.MessageBox(
                    # Translators: Error message shown when the server connection fails.
                    _("Failed to connect to the server.\n\n"
                      "Please check the server URL and your credentials."),
                    # Translators: Title of the connection error dialog.
                    _("Connection Failed"),
                    wx.OK | wx.ICON_ERROR,
                )

    def _show_main_window(self) -> None:
        """Show the main application window."""
        self._main_window = MainWindow(
            self._db,
            self._client,
            self._player,
            self._settings,
        )

        self._main_window.Show()

        # Load library
        self._main_window.load_library()

        # Listen for activation signals from future second instances.
        self._start_instance_listener()

    def _start_instance_listener(self) -> None:
        """Start a daemon thread that waits for a second-instance signal."""
        handle = self._activate_event
        if not handle:
            return

        def listen() -> None:
            while True:
                # Wait up to 500 ms so the thread can exit when the
                # process ends (daemon threads are killed on exit).
                result = ctypes.WinDLL("kernel32").WaitForSingleObject(  # type: ignore[attr-defined]
                    handle, 500,
                )
                if result == 0 and self._main_window:  # WAIT_OBJECT_0
                    wx.CallAfter(
                        self._main_window._restore_from_tray,
                    )

        threading.Thread(target=listen, daemon=True).start()

    def OnExit(self) -> int:
        """Clean up Windows handles on exit."""
        if self._activate_event:
            ctypes.WinDLL("kernel32").CloseHandle(  # type: ignore[attr-defined]
                self._activate_event,
            )
            self._activate_event = 0
        return 0


def run() -> None:
    """Run the ChordCut application."""
    app = ChordCutApp()
    app.MainLoop()
