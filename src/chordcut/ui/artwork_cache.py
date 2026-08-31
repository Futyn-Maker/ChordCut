"""Cover art loading with disk and memory caching.

Thumbnails are fetched from the Jellyfin server on a small worker pool
(separate from the API client's, so art never starves library loads),
cached on disk under ``data/artcache/`` and in a memory LRU, and
delivered to the GUI thread via ``wx.CallAfter``.

The image tag is part of the cache key, so replacing a cover on the
server naturally invalidates old entries.
"""

import logging
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import wx

from chordcut.utils.paths import get_data_dir

logger = logging.getLogger(__name__)

_MEMORY_CACHE_SIZE = 300
_DISK_CACHE_LIMIT_BYTES = 200 * 1024 * 1024


class ArtworkProvider:
    """Async cover art loader with disk + memory caches."""

    def __init__(self, client):
        self._client = client
        self._executor = ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="artwork",
        )
        self._cache_dir = get_data_dir() / "artcache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        # key -> wx.Bitmap, oldest first
        self._memory: OrderedDict[str, wx.Bitmap] = OrderedDict()
        # Items known to have no fetchable image; never re-request.
        self._negative: set[str] = set()
        self._in_flight: set[str] = set()

        self._executor.submit(self._prune_disk_cache)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def _key(item_id: str, tag: str, size: int) -> str:
        return f"{item_id}_{tag}_{size}"

    def get_cached(self, item_id: str, tag: str, size: int) -> "wx.Bitmap | None":
        """Return the bitmap from the memory cache, or None."""
        key = self._key(item_id, tag, size)
        bmp = self._memory.get(key)
        if bmp is not None:
            self._memory.move_to_end(key)
        return bmp

    def is_negative(self, item_id: str, tag: str, size: int) -> bool:
        return self._key(item_id, tag, size) in self._negative

    def request(
        self,
        item_id: str,
        tag: str,
        size: int,
        callback: Callable[[], None],
    ) -> None:
        """Load the image in the background; run callback when cached.

        The callback fires on the GUI thread only on success (the image
        is then available via :meth:`get_cached`). Failures are
        negative-cached silently. Must be called on the GUI thread.
        """
        key = self._key(item_id, tag, size)
        if key in self._memory or key in self._negative or key in self._in_flight:
            return
        self._in_flight.add(key)
        self._executor.submit(self._load, key, item_id, tag, size, callback)

    # -- worker thread -------------------------------------------------

    def _load(
        self,
        key: str,
        item_id: str,
        tag: str,
        size: int,
        callback: Callable[[], None],
    ) -> None:
        try:
            data = self._read_disk(key)
            if data is None:
                data = self._fetch(item_id, size)
                if data:
                    self._write_disk(key, data)
            image = None
            if data:
                image = wx.Image(BytesIO(data))
                if image.IsOk():
                    image = self._scale_to_fit(image, size)
                else:
                    image = None
            wx.CallAfter(self._deliver, key, image, callback)
        except Exception:
            logger.debug("artwork load failed: %s", key, exc_info=True)
            wx.CallAfter(self._deliver, key, None, callback)

    def _fetch(self, item_id: str, size: int) -> bytes | None:
        return self._client.fetch_image(item_id, max_size=size * 2)

    @staticmethod
    def _scale_to_fit(image: wx.Image, size: int) -> wx.Image:
        """Scale to fit within a size x size square, keeping aspect."""
        w, h = image.GetWidth(), image.GetHeight()
        if w <= 0 or h <= 0 or (w <= size and h <= size):
            return image
        ratio = min(size / w, size / h)
        return image.Scale(
            max(1, round(w * ratio)),
            max(1, round(h * ratio)),
            wx.IMAGE_QUALITY_BICUBIC,
        )

    def _read_disk(self, key: str) -> bytes | None:
        path = self._cache_dir / f"{key}.img"
        try:
            return path.read_bytes()
        except OSError:
            return None

    def _write_disk(self, key: str, data: bytes) -> None:
        try:
            (self._cache_dir / f"{key}.img").write_bytes(data)
        except OSError:
            pass

    def _prune_disk_cache(self) -> None:
        """Trim the disk cache to the size limit, oldest files first."""
        try:
            files = sorted(
                self._cache_dir.glob("*.img"),
                key=lambda p: p.stat().st_mtime,
            )
            total = sum(p.stat().st_size for p in files)
            for path in files:
                if total <= _DISK_CACHE_LIMIT_BYTES:
                    break
                total -= path.stat().st_size
                path.unlink(missing_ok=True)
        except OSError:
            pass

    # -- GUI thread ----------------------------------------------------

    def _deliver(
        self,
        key: str,
        image: "wx.Image | None",
        callback: Callable[[], None],
    ) -> None:
        self._in_flight.discard(key)
        if image is None:
            self._negative.add(key)
            return
        self._memory[key] = wx.Bitmap(image)
        self._memory.move_to_end(key)
        while len(self._memory) > _MEMORY_CACHE_SIZE:
            self._memory.popitem(last=False)
        callback()
