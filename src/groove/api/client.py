"""Threaded Jellyfin API client wrapper."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from jellyfin_apiclient_python import JellyfinClient as BaseJellyfinClient

from groove import __app_name__, __version__


class JellyfinClient:
    """Wrapper around jellyfin-apiclient-python with threading."""

    def __init__(self):
        """Initialize the Jellyfin client."""
        self._client = BaseJellyfinClient()
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._server_url: str | None = None
        self._user_id: str | None = None
        self._access_token: str | None = None
        self._device_id: str | None = None

        # Configure client application info
        self._device_id = str(uuid.uuid4())
        self._client.config.app(
            __app_name__,
            __version__,
            "Groove Device",
            self._device_id,
        )
        self._client.config.data["auth.ssl"] = True

    @property
    def device_id(self) -> str:
        """Get the device ID used for this client."""
        return self._device_id or ""

    @property
    def user_id(self) -> str | None:
        """Get the authenticated user ID."""
        return self._user_id

    @property
    def access_token(self) -> str | None:
        """Get the access token."""
        return self._access_token

    @property
    def server_url(self) -> str | None:
        """Get the server URL."""
        return self._server_url

    def login(
        self, server_url: str, username: str, password: str
    ) -> dict | None:
        """Authenticate with the Jellyfin server."""
        server_url = server_url.rstrip("/")
        self._server_url = server_url

        try:
            self._client.auth.connect_to_address(server_url)
            result = self._client.auth.login(
                server_url, username, password,
            )

            if result and "AccessToken" in result:
                self._access_token = result["AccessToken"]
                self._user_id = result["User"]["Id"]
                return result
            return None
        except Exception:
            return None

    def login_with_token(
        self,
        server_url: str,
        user_id: str,
        access_token: str,
        device_id: str,
    ) -> bool:
        """Authenticate using a stored access token."""
        server_url = server_url.rstrip("/")
        self._server_url = server_url
        self._user_id = user_id
        self._access_token = access_token
        self._device_id = device_id

        self._client.config.app(
            __app_name__,
            __version__,
            "Groove Device",
            device_id,
        )

        try:
            self._client.authenticate(
                {
                    "Servers": [
                        {
                            "AccessToken": access_token,
                            "address": server_url,
                            "UserId": user_id,
                        }
                    ]
                },
                discover=False,
            )

            user_info = self._client.jellyfin.get_user()
            return user_info is not None
        except Exception:
            return False

    # --- Library fetching ---

    def get_all_tracks(self) -> list[dict]:
        """Get all audio tracks from the library."""
        if not self._user_id:
            return []

        try:
            result = self._client.jellyfin.user_items(
                params={
                    "IncludeItemTypes": "Audio",
                    "Recursive": True,
                    "Fields": (
                        "AudioInfo,ParentId,"
                        "ArtistItems,Artists,AlbumArtists"
                    ),
                    "SortBy": "AlbumArtist,Album,SortName",
                    "SortOrder": "Ascending",
                }
            )
            return result.get("Items", [])
        except Exception:
            return []

    def get_playlists(self) -> list[dict]:
        """Get all playlists from the library."""
        if not self._user_id:
            return []

        try:
            result = self._client.jellyfin.user_items(
                params={
                    "IncludeItemTypes": "Playlist",
                    "Recursive": True,
                    "SortBy": "SortName",
                    "SortOrder": "Ascending",
                }
            )
            return result.get("Items", [])
        except Exception:
            return []

    def get_playlist_items(
        self, playlist_id: str,
    ) -> list[dict]:
        """Get audio items in a playlist."""
        if not self._user_id:
            return []

        try:
            result = self._client.jellyfin.user_items(
                params={
                    "ParentId": playlist_id,
                    "Fields": (
                        "AudioInfo,ParentId,"
                        "ArtistItems,Artists,AlbumArtists"
                    ),
                }
            )
            return result.get("Items", [])
        except Exception:
            return []

    def get_all_tracks_async(
        self,
        callback: Callable[[list[dict]], None],
        error_callback: (
            Callable[[Exception], None] | None
        ) = None,
    ) -> None:
        """Get all audio tracks asynchronously."""
        def task():
            try:
                result = self.get_all_tracks()
                callback(result)
            except Exception as e:
                if error_callback:
                    error_callback(e)

        self._executor.submit(task)

    def get_library_async(
        self,
        callback: Callable[
            [list[dict], list[dict], dict[str, list[dict]]],
            None,
        ],
        error_callback: (
            Callable[[Exception], None] | None
        ) = None,
    ) -> None:
        """Fetch entire library asynchronously.

        Fetches tracks, playlists, and playlist items in one
        background operation.  The callback receives
        (tracks, playlists, playlist_items_by_id).
        """
        def task():
            try:
                tracks = self.get_all_tracks()
                playlists = self.get_playlists()
                playlist_items: dict[str, list[dict]] = {}
                for pl in playlists:
                    pid = pl.get("Id")
                    if pid:
                        playlist_items[pid] = (
                            self.get_playlist_items(pid)
                        )
                callback(tracks, playlists, playlist_items)
            except Exception as e:
                if error_callback:
                    error_callback(e)

        self._executor.submit(task)

    # --- Streaming ---

    def get_stream_url(self, item_id: str) -> str:
        """Get the direct streaming URL for an audio track."""
        if not self._server_url or not self._access_token:
            return ""

        return (
            f"{self._server_url}/Audio/{item_id}/stream"
            f"?api_key={self._access_token}&static=true"
        )

    def search_tracks(self, query: str) -> list[dict]:
        """Search for audio tracks by name."""
        if not self._user_id:
            return []

        try:
            result = self._client.jellyfin.user_items(
                params={
                    "IncludeItemTypes": "Audio",
                    "Recursive": True,
                    "SearchTerm": query,
                    "Fields": (
                        "AudioInfo,ParentId,"
                        "ArtistItems,Artists,AlbumArtists"
                    ),
                    "Limit": 100,
                }
            )
            return result.get("Items", [])
        except Exception:
            return []

    def shutdown(self) -> None:
        """Shutdown the client and thread pool."""
        self._executor.shutdown(wait=False)
