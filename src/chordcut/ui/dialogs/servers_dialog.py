"""Server management dialog for ChordCut."""

import wx

from chordcut.api import JellyfinClient
from chordcut.db import Database, ServerCredentials
from chordcut.i18n import _
from chordcut.settings import Settings
from chordcut.ui.dialogs.login_dialog import LoginDialog


class ServersDialog(wx.Dialog):
    """Dialog for managing saved Jellyfin servers.

    After ShowModal(), check :attr:`server_switch_needed` to know
    whether the active server changed and a reload is required.
    """

    def __init__(
        self,
        parent: wx.Window,
        db: Database,
        client: JellyfinClient,
        settings: Settings,
    ):
        super().__init__(
            parent,
            # Translators: Title of the server management dialog.
            title=_("Manage Servers"),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )

        self._db = db
        self._client = client
        self._settings = settings
        self._server_switch_needed = False
        self._servers: list[ServerCredentials] = []

        self._create_controls()
        self._do_layout()
        self._bind_events()
        self._load_servers()

        self.SetMinSize((450, 300))
        self.SetSize((500, 350))
        self.CenterOnScreen()

    def _create_controls(self) -> None:
        """Create the dialog controls."""
        self._list_label = wx.StaticText(
            self,
            # Translators: Label for the server list.
            label=_("&Servers:"),
        )
        self._server_list = wx.ListBox(
            self,
            style=wx.LB_SINGLE,
            # Translators: Accessible name for the server list.
            name=_("Servers"),
        )

        self._add_btn = wx.Button(
            self,
            wx.ID_ANY,
            # Translators: Button to add a new server.
            _("&Add..."),
        )
        self._edit_btn = wx.Button(
            self,
            wx.ID_ANY,
            # Translators: Button to edit the selected server.
            _("&Edit..."),
        )
        self._delete_btn = wx.Button(
            self,
            wx.ID_ANY,
            # Translators: Button to delete the selected server.
            _("&Delete"),
        )
        self._close_btn = wx.Button(self, wx.ID_CLOSE)
        self._close_btn.SetDefault()

    def _do_layout(self) -> None:
        """Layout the dialog controls."""
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        main_sizer.Add(
            self._list_label,
            flag=wx.LEFT | wx.TOP,
            border=10,
        )
        main_sizer.Add(
            self._server_list,
            proportion=1,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP,
            border=10,
        )

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.Add(self._add_btn, flag=wx.RIGHT, border=5)
        btn_sizer.Add(self._edit_btn, flag=wx.RIGHT, border=5)
        btn_sizer.Add(self._delete_btn)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(self._close_btn)

        main_sizer.Add(
            btn_sizer,
            flag=wx.EXPAND | wx.ALL,
            border=10,
        )

        self.SetSizer(main_sizer)

    def _bind_events(self) -> None:
        """Bind event handlers."""
        self._add_btn.Bind(wx.EVT_BUTTON, self._on_add)
        self._edit_btn.Bind(wx.EVT_BUTTON, self._on_edit)
        self._delete_btn.Bind(wx.EVT_BUTTON, self._on_delete)
        self._close_btn.Bind(
            wx.EVT_BUTTON,
            lambda e: self.EndModal(wx.ID_CLOSE),
        )
        self._server_list.Bind(
            wx.EVT_KEY_DOWN, self._on_list_key,
        )

    def _on_list_key(self, event: wx.KeyEvent) -> None:
        """Handle Delete key in the list."""
        if event.GetKeyCode() == wx.WXK_DELETE:
            self._on_delete(event)
        else:
            event.Skip()

    def _load_servers(self) -> None:
        """Refresh the server list from the database."""
        self._servers = self._db.get_all_servers()
        active_id = self._settings.active_server_id
        strings = [
            "{user} @ {url}".format(
                user=s.username, url=s.url,
            )
            for s in self._servers
        ]
        self._server_list.Set(strings)

        # Select active server
        for i, s in enumerate(self._servers):
            if s.id == active_id:
                self._server_list.SetSelection(i)
                break

        self._update_button_state()

    def _update_button_state(self) -> None:
        """Enable/disable buttons based on selection."""
        has_sel = self._server_list.GetSelection() != wx.NOT_FOUND
        self._edit_btn.Enable(has_sel)
        self._delete_btn.Enable(
            has_sel and len(self._servers) > 1,
        )

    def _on_add(self, event: wx.CommandEvent) -> None:
        """Add a new server via login dialog.

        On failure the login dialog is re-shown with the previously
        entered URL and username preserved.  On success the dialog
        closes automatically and the main window reloads.
        """
        url = ""
        username = ""

        while True:
            dialog = LoginDialog(self)
            if url:
                dialog.set_server_url(url)
                dialog.set_username(username)

            if dialog.ShowModal() != wx.ID_OK:
                dialog.Destroy()
                return

            url = dialog.server_url
            username = dialog.username
            password = dialog.password
            dialog.Destroy()

            # Translators: Busy dialog shown while connecting.
            progress = wx.BusyInfo(
                _("Connecting to server...")
            )
            ok = self._client.login(url, username, password)
            del progress

            if ok:
                creds = ServerCredentials(
                    id=None,
                    url=url,
                    user_id=self._client.user_id or "",
                    username=username,
                    access_token=(
                        self._client.access_token or ""
                    ),
                    device_id=self._client.device_id,
                )
                server_id = self._db.save_server(creds)
                self._settings.active_server_id = server_id
                self._settings.save()
                self._server_switch_needed = True
                # Close dialog; main window will reload.
                self.EndModal(wx.ID_OK)
                return

            wx.MessageBox(
                # Translators: Error when adding server fails.
                _("Failed to connect to the server.\n\n"
                  "Please check the URL and credentials."),
                # Translators: Title of connection error dialog.
                _("Connection Failed"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            # Loop back: dialog will reopen with pre-filled data.

    def _on_edit(self, event: wx.CommandEvent) -> None:
        """Edit the selected server's credentials."""
        sel = self._server_list.GetSelection()
        if sel == wx.NOT_FOUND:
            return
        server = self._servers[sel]

        dialog = LoginDialog(self)
        dialog.set_server_url(server.url)
        dialog.set_username(server.username)
        if dialog.ShowModal() != wx.ID_OK:
            dialog.Destroy()
            return

        url = dialog.server_url
        username = dialog.username
        password = dialog.password
        dialog.Destroy()

        url_changed = url != server.url
        username_changed = username != server.username
        has_password = bool(password)

        # Skip if nothing changed
        if not url_changed and not username_changed and not has_password:
            return

        # Translators: Busy dialog shown while connecting.
        progress = wx.BusyInfo(_("Connecting to server..."))
        ok = self._client.login(url, username, password)
        del progress

        if not ok:
            wx.MessageBox(
                # Translators: Error when editing server fails.
                _("Failed to connect to the server.\n\n"
                  "The previous connection data will be kept."),
                # Translators: Title of connection error dialog.
                _("Connection Failed"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            # Reconnect to the original server so the client
            # is back in a valid state.
            self._client.login_with_token(
                server.url,
                server.user_id,
                server.access_token,
                server.device_id,
            )
            return

        creds = ServerCredentials(
            id=server.id,
            url=url,
            user_id=self._client.user_id or "",
            username=username,
            access_token=self._client.access_token or "",
            device_id=self._client.device_id,
        )
        self._db.save_server(creds)

        # If this was the active server, signal a reload
        if server.id == self._settings.active_server_id:
            self._server_switch_needed = True

        self._load_servers()

    def _on_delete(self, event: wx.CommandEvent) -> None:
        """Delete the selected server after confirmation."""
        sel = self._server_list.GetSelection()
        if sel == wx.NOT_FOUND:
            return

        if len(self._servers) <= 1:
            wx.MessageBox(
                # Translators: Error shown when deleting the last server.
                _("Cannot delete the last server."),
                # Translators: Error dialog title.
                _("Cannot Delete"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        server = self._servers[sel]
        label = "{user} @ {url}".format(
            user=server.username, url=server.url,
        )
        result = wx.MessageBox(
            # Translators: Confirmation message for server deletion.
            # {server} is the server label.
            _("Delete server \"{server}\"?\n\n"
              "All cached data for this server will be"
              " removed.").format(server=label),
            # Translators: Title of the delete confirmation dialog.
            _("Confirm Delete"),
            wx.YES_NO | wx.ICON_WARNING,
            self,
        )
        if result != wx.YES:
            return

        was_active = (
            server.id == self._settings.active_server_id
        )
        self._db.delete_server(server.id)

        if was_active:
            # Switch to first remaining server and close dialog.
            remaining = self._db.get_all_servers()
            if remaining:
                new_server = remaining[0]
                # Translators: Busy dialog while reconnecting.
                progress = wx.BusyInfo(
                    _("Connecting to server...")
                )
                ok = self._client.login_with_token(
                    new_server.url,
                    new_server.user_id,
                    new_server.access_token,
                    new_server.device_id,
                )
                del progress
                if not ok:
                    # Token may be stale; load_library will
                    # handle the reconnect on next call.
                    pass
                self._settings.active_server_id = new_server.id
                self._settings.save()
                self._server_switch_needed = True
                self.EndModal(wx.ID_OK)
                return

        # Non-active server deleted: just refresh the list.
        self._load_servers()

    @property
    def server_switch_needed(self) -> bool:
        """True if the active server changed and a reload is needed."""
        return self._server_switch_needed
