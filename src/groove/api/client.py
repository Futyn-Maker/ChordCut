"""Threaded Jellyfin API client wrapper."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from jellyfin_apiclient_python import JellyfinClient as BaseJellyfinClient

from groove import __app_name__, __version__


class JellyfinClient:
    """Wrapper around jellyfin-apiclient-python with threading support."""

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
        """Authenticate with the Jellyfin server.

        Args:
            server_url: URL of the Jellyfin server.
            username: Username to authenticate with.
            password: Password for the user.

        Returns:
            Authentication result dict with user info and access token,
            or None if authentication failed.
        """
        # Ensure URL doesn't have trailing slash
        server_url = server_url.rstrip("/")
        self._server_url = server_url

        try:
            # Connect to server
            self._client.auth.connect_to_address(server_url)

            # Attempt login
            result = self._client.auth.login(server_url, username, password)

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
        """Authenticate using a stored access token.

        Args:
            server_url: URL of the Jellyfin server.
            user_id: User ID from previous login.
            access_token: Access token from previous login.
            device_id: Device ID used for previous login.

        Returns:
            True if authentication succeeded, False otherwise.
        """
        server_url = server_url.rstrip("/")
        self._server_url = server_url
        self._user_id = user_id
        self._access_token = access_token
        self._device_id = device_id

        # Update client config with stored device ID
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

            # Verify token is still valid by making a simple request
            user_info = self._client.jellyfin.get_user()
            return user_info is not None
        except Exception:
            return False

    def get_all_tracks(self) -> list[dict]:
        """Get all audio tracks from the library.

        Returns:
            List of track dictionaries from Jellyfin.
        """
        if not self._user_id:
            return []

        try:
            result = self._client.jellyfin.user_items(
                params={
                    "IncludeItemTypes": "Audio",
                    "Recursive": True,
                    "Fields": "AudioInfo,ParentId",
                    "SortBy": "AlbumArtist,Album,SortName",
                    "SortOrder": "Ascending",
                }
            )
            return result.get("Items", [])
        except Exception:
            return []

    def get_all_tracks_async(
        self,
        callback: Callable[[list[dict]], None],
        error_callback: Callable[[Exception], None] | None = None,
    ) -> None:
        """Get all audio tracks asynchronously.

        Args:
            callback: Function to call with the results.
            error_callback: Function to call if an error occurs.
        """
        def task():
            try:
                result = self.get_all_tracks()
                callback(result)
            except Exception as e:
                if error_callback:
                    error_callback(e)

        self._executor.submit(task)

    def get_stream_url(self, item_id: str) -> str:
        """Get the streaming URL for an audio track.

        Uses direct streaming (static=true) so Jellyfin sends the
        original file as-is.  MPV handles every audio format natively,
        so there is no need for server-side transcoding, and this
        avoids format-allowlist issues (e.g. WAV not playing).

        Args:
            item_id: Jellyfin item ID of the track.

        Returns:
            URL for direct streaming without transcoding.
        """
        if not self._server_url or not self._access_token:
            return ""

        return (
            f"{self._server_url}/Audio/{item_id}/stream"
            f"?api_key={self._access_token}&static=true"
        )

    def get_direct_stream_url(self, item_id: str) -> str:
        """Get a direct (non-transcoded) streaming URL.

        Args:
            item_id: Jellyfin item ID of the track.

        Returns:
            URL for direct streaming without transcoding.
        """
        if not self._server_url or not self._access_token:
            return ""

        return (
            f"{self._server_url}/Audio/{item_id}/stream"
            f"?api_key={self._access_token}&static=true"
        )

    def search_tracks(self, query: str) -> list[dict]:
        """Search for audio tracks by name.

        Args:
            query: Search query string.

        Returns:
            List of matching track dictionaries.
        """
        if not self._user_id:
            return []

        try:
            result = self._client.jellyfin.user_items(
                params={
                    "IncludeItemTypes": "Audio",
                    "Recursive": True,
                    "SearchTerm": query,
                    "Fields": "AudioInfo,ParentId",
                    "Limit": 100,
                }
            )
            return result.get("Items", [])
        except Exception:
            return []

    def shutdown(self) -> None:
        """Shutdown the client and thread pool."""
        self._executor.shutdown(wait=False)
