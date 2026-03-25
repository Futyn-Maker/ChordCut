"""Threaded Jellyfin API client wrapper."""

import uuid
from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)
from typing import Callable

from jellyfin_apiclient_python import JellyfinClient as BaseJellyfinClient

from chordcut import __app_name__, __version__


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
            "ChordCut Device",
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
            "ChordCut Device",
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

    def get_music_views(self) -> list[dict]:
        """Get music library views from the server.

        Returns a list of dicts with Id and Name for each
        music library (CollectionType == "music").
        """
        if not self._user_id:
            return []

        try:
            url = f"Users/{self._user_id}/Views"
            result = self._client.jellyfin._get(url)
            views = result.get("Items", [])
            return [
                {"Id": v["Id"], "Name": v.get("Name", "")}
                for v in views
                if v.get("CollectionType") == "music"
            ]
        except Exception:
            return []

    _TRACK_FIELDS = (
        "ArtistItems,Artists,"
        "AlbumArtists,DateCreated"
    )

    def get_tracks_by_library(
        self, library_id: str,
    ) -> list[dict]:
        """Get all audio tracks in a specific library."""
        if not self._user_id:
            return []

        try:
            result = self._client.jellyfin.user_items(
                params={
                    "ParentId": library_id,
                    "IncludeItemTypes": "Audio",
                    "Recursive": True,
                    "Fields": self._TRACK_FIELDS,
                    "SortBy": "AlbumArtist,Album,SortName",
                    "SortOrder": "Ascending",
                }
            )
            return result.get("Items", [])
        except Exception:
            return []

    def get_tracks_page(
        self,
        library_id: str,
        start_index: int,
        limit: int,
    ) -> tuple[list[dict], int]:
        """Fetch a page of tracks from a library.

        Returns ``(items, total_count)``.
        """
        if not self._user_id:
            return [], 0

        try:
            result = self._client.jellyfin.user_items(
                params={
                    "ParentId": library_id,
                    "IncludeItemTypes": "Audio",
                    "Recursive": True,
                    "Fields": self._TRACK_FIELDS,
                    "SortBy": "AlbumArtist,Album,SortName",
                    "SortOrder": "Ascending",
                    "StartIndex": start_index,
                    "Limit": limit,
                }
            )
            return (
                result.get("Items", []),
                result.get("TotalRecordCount", 0),
            )
        except Exception:
            return [], 0

    def get_track_count(
        self, library_id: str,
    ) -> int:
        """Get total track count (warms server cache)."""
        if not self._user_id:
            return 0

        try:
            result = self._client.jellyfin.user_items(
                params={
                    "ParentId": library_id,
                    "IncludeItemTypes": "Audio",
                    "Recursive": True,
                    "Limit": 0,
                }
            )
            return result.get("TotalRecordCount", 0)
        except Exception:
            return 0

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
                        "ArtistItems,Artists,"
                        "AlbumArtists,DateCreated"
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
        """Get audio items in a playlist.

        Uses the dedicated Playlists endpoint so that
        ``PlaylistItemId`` is included in each item.
        """
        if not self._user_id:
            return []

        try:
            url = "Playlists/{pid}/Items".format(
                pid=playlist_id,
            )
            result = self._client.jellyfin._get(
                url,
                params={
                    "userId": self._user_id,
                    "Fields": (
                        "AudioInfo,ParentId,"
                        "ArtistItems,Artists,"
                        "AlbumArtists,DateCreated"
                    ),
                },
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
            [
                list[dict], list[dict],
                list[dict], dict[str, list[dict]],
            ],
            None,
        ],
        error_callback: (
            Callable[[Exception], None] | None
        ) = None,
    ) -> None:
        """Fetch entire library asynchronously.

        Fetches music views, tracks per library, playlists,
        and playlist items in one background operation.
        The callback receives
        (libraries, tracks, playlists, playlist_items_by_id).
        Each track dict is tagged with "LibraryId".

        Per-library track fetches and per-playlist item
        fetches are parallelized for speed.
        """
        def task():
            try:
                libraries = self.get_music_views()

                # Fetch tracks per library in parallel
                all_tracks: list[dict] = []
                if libraries:
                    all_tracks = (
                        self._fetch_tracks_parallel(
                            libraries,
                        )
                    )
                else:
                    # Fallback: no views found, fetch all
                    all_tracks = self.get_all_tracks()

                # Fetch playlists, then items in parallel
                playlists = self.get_playlists()
                playlist_items = (
                    self._fetch_playlist_items_parallel(
                        playlists,
                    )
                )

                callback(
                    libraries, all_tracks,
                    playlists, playlist_items,
                )
            except Exception as e:
                if error_callback:
                    error_callback(e)

        self._executor.submit(task)

    def _fetch_tracks_parallel(
        self, libraries: list[dict],
    ) -> list[dict]:
        """Fetch tracks from all libraries in parallel."""
        all_tracks: list[dict] = []
        with ThreadPoolExecutor(
            max_workers=min(len(libraries), 4),
        ) as pool:
            futures = {
                pool.submit(
                    self.get_tracks_by_library,
                    lib["Id"],
                ): lib["Id"]
                for lib in libraries
            }
            for future in as_completed(futures):
                lib_id = futures[future]
                lib_tracks = future.result()
                for t in lib_tracks:
                    t["LibraryId"] = lib_id
                all_tracks.extend(lib_tracks)
        return all_tracks

    def _fetch_playlist_items_parallel(
        self, playlists: list[dict],
    ) -> dict[str, list[dict]]:
        """Fetch items for all playlists in parallel."""
        playlist_items: dict[str, list[dict]] = {}
        pids: list[str] = [
            pl["Id"] for pl in playlists
            if pl.get("Id")
        ]
        if not pids:
            return playlist_items

        with ThreadPoolExecutor(
            max_workers=min(len(pids), 4),
        ) as pool:
            futures = {
                pool.submit(
                    self.get_playlist_items, pid,
                ): pid
                for pid in pids
            }
            for future in as_completed(futures):
                pid = futures[future]
                playlist_items[pid] = future.result()
        return playlist_items

    # --- Paginated library fetch ---

    _PAGE_SIZE = 200

    def fetch_library_paginated(
        self,
        libraries_callback: Callable[
            [list[dict], dict[str, int]], None,
        ],
        page_callback: Callable[
            [list[dict], str, int], None,
        ],
        done_callback: Callable[
            [list[dict], dict[str, list[dict]]], None,
        ],
        error_callback: (
            Callable[[Exception], None] | None
        ) = None,
    ) -> None:
        """Fetch library data with per-page callbacks.

        Used for progressive loading on cold start.

        *libraries_callback(libraries, lib_counts)* is
        called once after music views and per-library track
        counts are fetched.  *lib_counts* maps library Id
        to total track count.

        *page_callback(batch, library_id, page_count)* is
        called for each page of tracks.

        *done_callback(playlists, playlist_items)* is
        called when everything (including playlists) is
        done.
        """
        def task():
            try:
                # 1. Get music views
                libraries = self.get_music_views()
                if not libraries:
                    libraries_callback([], {})
                    done_callback([], {})
                    return

                # 2. Warm server cache + get counts
                lib_counts: dict[str, int] = {}
                with ThreadPoolExecutor(
                    max_workers=min(
                        len(libraries), 4,
                    ),
                ) as pool:
                    futures = {
                        pool.submit(
                            self.get_track_count,
                            lib["Id"],
                        ): lib["Id"]
                        for lib in libraries
                    }
                    for future in as_completed(
                        futures,
                    ):
                        lid = futures[future]
                        lib_counts[lid] = (
                            future.result()
                        )

                libraries_callback(libraries, lib_counts)

                # 3. Paginate per library (sequential)
                for lib in libraries:
                    lib_id = lib["Id"]
                    lib_total = lib_counts.get(
                        lib_id, 0,
                    )
                    start = 0
                    while start < lib_total:
                        items, _ = self.get_tracks_page(
                            lib_id,
                            start,
                            self._PAGE_SIZE,
                        )
                        if not items:
                            break
                        for t in items:
                            t["LibraryId"] = lib_id
                        page_callback(
                            items, lib_id, len(items),
                        )
                        start += self._PAGE_SIZE

                # 4. Playlists (parallel items)
                playlists = self.get_playlists()
                pl_items = (
                    self._fetch_playlist_items_parallel(
                        playlists,
                    )
                )
                done_callback(playlists, pl_items)

            except Exception as e:
                if error_callback:
                    error_callback(e)

        self._executor.submit(task)

    # --- Playlist CRUD ---

    def create_playlist(self, name: str) -> str | None:
        """Create a new empty playlist.

        Returns the new playlist ID, or *None* on failure.
        """
        if not self._user_id:
            return None
        try:
            result = self._client.jellyfin._post(
                "Playlists",
                json={
                    "Name": name,
                    "UserId": self._user_id,
                    "MediaType": "Audio",
                },
            )
            return result.get("Id") if result else None
        except Exception:
            return None

    def create_playlist_async(
        self,
        name: str,
        callback: Callable[[str | None], None],
        error_callback: (
            Callable[[Exception], None] | None
        ) = None,
    ) -> None:
        """Create a playlist asynchronously."""
        def task() -> None:
            try:
                result = self.create_playlist(name)
                callback(result)
            except Exception as e:
                if error_callback:
                    error_callback(e)

        self._executor.submit(task)

    def rename_playlist(
        self, playlist_id: str, new_name: str,
    ) -> bool:
        """Rename a playlist.

        Fetches the full item, changes the name, and
        POSTs it back (Jellyfin requires the full body).
        """
        if not self._user_id:
            return False
        try:
            item = self._client.jellyfin.user_items(
                handler="/{id}".format(id=playlist_id),
            )
            if not item:
                return False
            item["Name"] = new_name
            self._client.jellyfin._post(
                "Items/{id}".format(id=playlist_id),
                json=item,
            )
            return True
        except Exception:
            return False

    def rename_playlist_async(
        self,
        playlist_id: str,
        new_name: str,
        callback: Callable[[bool], None],
        error_callback: (
            Callable[[Exception], None] | None
        ) = None,
    ) -> None:
        """Rename a playlist asynchronously."""
        def task() -> None:
            try:
                result = self.rename_playlist(
                    playlist_id, new_name,
                )
                callback(result)
            except Exception as e:
                if error_callback:
                    error_callback(e)

        self._executor.submit(task)

    def delete_playlist(
        self, playlist_id: str,
    ) -> bool:
        """Delete a playlist."""
        try:
            self._client.jellyfin._delete(
                "Items/{id}".format(id=playlist_id),
            )
            return True
        except Exception:
            return False

    def delete_playlist_async(
        self,
        playlist_id: str,
        callback: Callable[[bool], None] | None = None,
        error_callback: (
            Callable[[Exception], None] | None
        ) = None,
    ) -> None:
        """Delete a playlist asynchronously."""
        def task() -> None:
            try:
                result = self.delete_playlist(
                    playlist_id,
                )
                if callback:
                    callback(result)
            except Exception as e:
                if error_callback:
                    error_callback(e)

        self._executor.submit(task)

    # --- Playlist item mutations ---

    def add_to_playlist(
        self, playlist_id: str, track_id: str,
    ) -> bool:
        """Add a track to the top of a playlist.

        Appends the track (server puts it at the end),
        then moves it to index 0.
        """
        if not self._user_id:
            return False
        try:
            url = "Playlists/{pid}/Items".format(
                pid=playlist_id,
            )
            self._client.jellyfin._post(
                url,
                params={
                    "ids": track_id,
                    "userId": self._user_id,
                },
            )
            # Move to top: find PlaylistItemId first
            items = self.get_playlist_items(playlist_id)
            pid = None
            for it in items:
                if it.get("Id") == track_id:
                    pid = it.get("PlaylistItemId")
                    break
            if pid:
                move_url = (
                    "Playlists/{plid}/Items/{pid}"
                    "/Move/{idx}"
                ).format(
                    plid=playlist_id, pid=pid, idx=0,
                )
                self._client.jellyfin._post(move_url)
            return True
        except Exception:
            return False

    def add_to_playlist_async(
        self,
        playlist_id: str,
        track_id: str,
        callback: Callable[[bool], None],
        error_callback: (
            Callable[[Exception], None] | None
        ) = None,
    ) -> None:
        """Add a track to a playlist asynchronously."""
        def task() -> None:
            try:
                result = self.add_to_playlist(
                    playlist_id, track_id,
                )
                callback(result)
            except Exception as e:
                if error_callback:
                    error_callback(e)

        self._executor.submit(task)

    def remove_from_playlist(
        self,
        playlist_id: str,
        playlist_item_id: str,
    ) -> bool:
        """Remove a track from a playlist."""
        try:
            url = "Playlists/{pid}/Items".format(
                pid=playlist_id,
            )
            self._client.jellyfin._delete(
                url,
                params={"entryIds": playlist_item_id},
            )
            return True
        except Exception:
            return False

    def remove_from_playlist_async(
        self,
        playlist_id: str,
        playlist_item_id: str,
        callback: Callable[[bool], None] | None = None,
        error_callback: (
            Callable[[Exception], None] | None
        ) = None,
    ) -> None:
        """Remove a track from a playlist async."""
        def task() -> None:
            try:
                result = self.remove_from_playlist(
                    playlist_id, playlist_item_id,
                )
                if callback:
                    callback(result)
            except Exception as e:
                if error_callback:
                    error_callback(e)

        self._executor.submit(task)

    def move_playlist_item(
        self,
        playlist_id: str,
        playlist_item_id: str,
        new_index: int,
    ) -> bool:
        """Move a playlist item to a new position."""
        try:
            url = (
                "Playlists/{plid}/Items/{pid}"
                "/Move/{idx}"
            ).format(
                plid=playlist_id,
                pid=playlist_item_id,
                idx=new_index,
            )
            self._client.jellyfin._post(url)
            return True
        except Exception:
            return False

    def move_playlist_item_async(
        self,
        playlist_id: str,
        playlist_item_id: str,
        new_index: int,
        callback: Callable[[bool], None] | None = None,
        error_callback: (
            Callable[[Exception], None] | None
        ) = None,
    ) -> None:
        """Move a playlist item asynchronously."""
        def task() -> None:
            try:
                result = self.move_playlist_item(
                    playlist_id,
                    playlist_item_id,
                    new_index,
                )
                if callback:
                    callback(result)
            except Exception as e:
                if error_callback:
                    error_callback(e)

        self._executor.submit(task)

    def add_tracks_to_playlist_top(
        self,
        playlist_id: str,
        track_ids: list[str],
    ) -> bool:
        """Add tracks to the top of a playlist.

        1. Batch-add all tracks in one request (server
           appends them at the end).
        2. Fetch playlist items to obtain PlaylistItemIds.
        3. Move each added track to positions 0, 1, 2, …
           so the order matches *track_ids*.

        Cost: 1 add + 1 fetch + N moves = N+2 requests.
        """
        if not self._user_id or not track_ids:
            return False
        try:
            # 1. Batch add
            url = "Playlists/{pid}/Items".format(
                pid=playlist_id,
            )
            self._client.jellyfin._post(
                url,
                params={
                    "ids": ",".join(track_ids),
                    "userId": self._user_id,
                },
            )

            # 2. Fetch items to get PlaylistItemIds
            items = self.get_playlist_items(playlist_id)
            id_to_pid: dict[str, str] = {}
            for it in items:
                tid = it.get("Id", "")
                pid = it.get("PlaylistItemId", "")
                if tid in id_to_pid:
                    # Duplicate track — keep the last
                    # occurrence (the newly added one).
                    pass
                id_to_pid[tid] = pid

            # 3. Move each to position 0 in reverse order.
            # Moving an item to 0 pushes everything down,
            # so processing [A, B, C] reversed gives:
            #   move C→0  => [C, …]
            #   move B→0  => [B, C, …]
            #   move A→0  => [A, B, C, …]
            for tid in reversed(track_ids):
                pid = id_to_pid.get(tid)
                if pid:
                    move_url = (
                        "Playlists/{plid}/Items/{pid}"
                        "/Move/{idx}"
                    ).format(
                        plid=playlist_id,
                        pid=pid,
                        idx=0,
                    )
                    self._client.jellyfin._post(move_url)

            return True
        except Exception:
            return False

    def add_tracks_to_playlist_top_async(
        self,
        playlist_id: str,
        track_ids: list[str],
        callback: Callable[[bool], None],
        error_callback: (
            Callable[[Exception], None] | None
        ) = None,
    ) -> None:
        """Add tracks to playlist top asynchronously."""
        def task() -> None:
            try:
                result = (
                    self.add_tracks_to_playlist_top(
                        playlist_id, track_ids,
                    )
                )
                callback(result)
            except Exception as e:
                if error_callback:
                    error_callback(e)

        self._executor.submit(task)

    def remove_tracks_from_playlist(
        self,
        playlist_id: str,
        playlist_item_ids: list[str],
    ) -> bool:
        """Remove multiple tracks from a playlist.

        Uses a single API call with comma-separated entry IDs.
        """
        if not playlist_item_ids:
            return False
        try:
            url = "Playlists/{pid}/Items".format(
                pid=playlist_id,
            )
            self._client.jellyfin._delete(
                url,
                params={
                    "entryIds": ",".join(
                        playlist_item_ids,
                    ),
                },
            )
            return True
        except Exception:
            return False

    def remove_tracks_from_playlist_async(
        self,
        playlist_id: str,
        playlist_item_ids: list[str],
        callback: Callable[[bool], None] | None = None,
        error_callback: (
            Callable[[Exception], None] | None
        ) = None,
    ) -> None:
        """Remove multiple tracks from a playlist async."""
        def task() -> None:
            try:
                result = self.remove_tracks_from_playlist(
                    playlist_id, playlist_item_ids,
                )
                if callback:
                    callback(result)
            except Exception as e:
                if error_callback:
                    error_callback(e)

        self._executor.submit(task)

    # --- Images ---

    def get_image_url(
        self, item_id: str, max_size: int = 200,
        quality: int = 80,
    ) -> str:
        """Build URL for an item's primary image."""
        if not self._server_url:
            return ""
        return (
            "{base}/Items/{id}/Images/Primary"
            "?maxWidth={sz}&maxHeight={sz}&quality={q}"
        ).format(
            base=self._server_url, id=item_id,
            sz=max_size, q=quality,
        )

    def fetch_image(
        self, item_id: str, max_size: int = 200,
    ) -> bytes | None:
        """Download an item's primary image as raw bytes.

        Returns *None* when the item has no image or on error.
        """
        url = self.get_image_url(item_id, max_size)
        if not url:
            return None
        try:
            import urllib.request
            req = urllib.request.Request(url)
            if self._access_token:
                req.add_header(
                    "Authorization",
                    'MediaBrowser Token="{tok}"'.format(
                        tok=self._access_token,
                    ),
                )
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.read()
        except Exception:
            return None

    def fetch_image_async(
        self,
        item_id: str,
        callback: Callable[[bytes | None], None],
        max_size: int = 200,
    ) -> None:
        """Fetch an item's primary image asynchronously."""
        def task() -> None:
            result = self.fetch_image(item_id, max_size)
            callback(result)
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
                        "ArtistItems,Artists,"
                        "AlbumArtists,DateCreated"
                    ),
                    "Limit": 100,
                }
            )
            return result.get("Items", [])
        except Exception:
            return []

    # --- Lyrics ---

    def get_lyrics(self, item_id: str) -> dict | None:
        """Get lyrics for an audio track.

        Returns dict with ``Lyrics`` key containing a list
        of ``{Start, Text}`` cues, or *None*.
        """
        if not self._user_id:
            return None
        try:
            url = "Audio/{id}/Lyrics".format(id=item_id)
            result = self._client.jellyfin._get(url)
            return result
        except Exception:
            return None

    def get_lyrics_async(
        self,
        item_id: str,
        callback: Callable[[dict | None], None],
    ) -> None:
        """Fetch lyrics asynchronously."""
        def task() -> None:
            result = self.get_lyrics(item_id)
            callback(result)
        self._executor.submit(task)

    # --- Item details ---

    def get_item_details(
        self, item_id: str,
    ) -> dict | None:
        """Get full item details including MediaSources."""
        if not self._user_id:
            return None
        try:
            result = self._client.jellyfin.user_items(
                handler="/{id}".format(id=item_id),
                params={
                    "Fields": (
                        "MediaSources,DateCreated,Path"
                    ),
                },
            )
            return result
        except Exception:
            return None

    def get_item_details_async(
        self,
        item_id: str,
        callback: Callable[[dict | None], None],
    ) -> None:
        """Fetch item details asynchronously."""
        def task() -> None:
            result = self.get_item_details(item_id)
            callback(result)
        self._executor.submit(task)

    def shutdown(self) -> None:
        """Shutdown the client and thread pool."""
        self._executor.shutdown(wait=False)
