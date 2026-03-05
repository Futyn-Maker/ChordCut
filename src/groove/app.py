"""Main application class for Groove."""

import wx

from groove.api import JellyfinClient
from groove.db import Database
from groove.db.database import ServerCredentials
from groove.i18n import _
from groove.player import Player
from groove.settings import Settings
from groove.ui import LoginDialog, MainWindow


class GrooveApp(wx.App):
    """Main wxPython application class."""

    def __init__(self):
        """Initialize the application."""
        self._db: Database | None = None
        self._client: JellyfinClient | None = None
        self._player: Player | None = None
        self._settings: Settings | None = None
        self._main_window: MainWindow | None = None

        super().__init__(redirect=False)

    def OnInit(self) -> bool:
        """Initialize the application (called by wxPython).

        Returns:
            True if initialization succeeded.
        """
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


def run() -> None:
    """Run the Groove application."""
    app = GrooveApp()
    app.MainLoop()
