"""Windows System Media Transport Controls (SMTC) integration.

Publishes a media session so hardware media keys, Bluetooth headset
buttons, and the Windows media flyout control ChordCut.  The OS
arbitrates between applications (the most recently playing session
receives the keys), so no key is ever grabbed exclusively.

The winrt packages are optional at runtime: if they are missing or
initialization fails, :meth:`MediaControls.create` returns ``None``
and the application runs without SMTC.

Thread note: WinRT events arrive on background threads.  Callbacks
set on this class are invoked as-is; the caller must marshal them to
the GUI thread (e.g. with ``wx.CallAfter``).
"""

import datetime
import logging
import time
from collections.abc import Callable

_log = logging.getLogger(__name__)

# Seconds between periodic timeline pushes while playing.
_TIMELINE_INTERVAL = 5.0
# A position jump larger than this (vs. extrapolation) means a seek.
_TIMELINE_JUMP = 2.0


class MediaControls:
    """Wrapper around the SystemMediaTransportControls session."""

    def __init__(self, smtc, wm) -> None:
        self._smtc = smtc
        self._wm = wm  # winrt.windows.media module
        self._tokens: list[tuple[str, object]] = []

        # Optional callbacks, all invoked on WinRT threads.
        self.on_play: Callable[[], None] | None = None
        self.on_pause: Callable[[], None] | None = None
        self.on_stop: Callable[[], None] | None = None
        self.on_next: Callable[[], None] | None = None
        self.on_previous: Callable[[], None] | None = None
        self.on_fast_forward: Callable[[], None] | None = None
        self.on_rewind: Callable[[], None] | None = None
        self.on_shuffle_requested: Callable[[bool], None] | None = None
        self.on_repeat_requested: Callable[[bool], None] | None = None
        self.on_position_requested: Callable[[float], None] | None = None

        # Throttle state for timeline pushes.
        self._last_push_wall = 0.0
        self._last_push_pos = 0.0
        self._last_status: object = None

        smtc.is_play_enabled = True
        smtc.is_pause_enabled = True
        smtc.is_stop_enabled = True
        smtc.is_next_enabled = True
        smtc.is_previous_enabled = True
        smtc.is_fast_forward_enabled = True
        smtc.is_rewind_enabled = True
        # Publish a complete (empty) music card before enabling, so the
        # system never sees a half-initialized session: a stopped
        # player with nothing loaded, ready to accept Play.
        du = smtc.display_updater
        du.type = wm.MediaPlaybackType.MUSIC
        du.update()
        smtc.playback_status = wm.MediaPlaybackStatus.STOPPED
        self._last_status = wm.MediaPlaybackStatus.STOPPED
        smtc.is_enabled = True

        self._tokens.append(
            (
                "button_pressed",
                smtc.add_button_pressed(self._on_button),
            )
        )
        self._tokens.append(
            (
                "shuffle_enabled_change_requested",
                smtc.add_shuffle_enabled_change_requested(self._on_shuffle),
            )
        )
        self._tokens.append(
            (
                "auto_repeat_mode_change_requested",
                smtc.add_auto_repeat_mode_change_requested(self._on_repeat),
            )
        )
        self._tokens.append(
            (
                "playback_position_change_requested",
                smtc.add_playback_position_change_requested(self._on_position),
            )
        )

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @staticmethod
    def create(hwnd: int) -> "MediaControls | None":
        """Create SMTC for a top-level window, or None if unavailable."""
        try:
            import winrt.windows.media as wm
            import winrt.windows.media.interop as interop

            smtc = interop.get_for_window(hwnd)
            return MediaControls(smtc, wm)
        except Exception:
            _log.debug("SMTC unavailable", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # WinRT event handlers (background threads)
    # ------------------------------------------------------------------

    def _on_button(self, _sender, args) -> None:
        try:
            btn = self._wm.SystemMediaTransportControlsButton
            handlers = {
                btn.PLAY: self.on_play,
                btn.PAUSE: self.on_pause,
                btn.STOP: self.on_stop,
                btn.NEXT: self.on_next,
                btn.PREVIOUS: self.on_previous,
                btn.FAST_FORWARD: self.on_fast_forward,
                btn.REWIND: self.on_rewind,
            }
            handler = handlers.get(args.button)
            if handler:
                handler()
        except Exception:
            _log.debug("SMTC button handler failed", exc_info=True)

    def _on_shuffle(self, _sender, args) -> None:
        try:
            if self.on_shuffle_requested:
                self.on_shuffle_requested(bool(args.requested_shuffle_enabled))
        except Exception:
            _log.debug("SMTC shuffle handler failed", exc_info=True)

    def _on_repeat(self, _sender, args) -> None:
        try:
            if self.on_repeat_requested:
                mode = args.requested_auto_repeat_mode
                enabled = mode != self._wm.MediaPlaybackAutoRepeatMode.NONE
                self.on_repeat_requested(enabled)
        except Exception:
            _log.debug("SMTC repeat handler failed", exc_info=True)

    def _on_position(self, _sender, args) -> None:
        try:
            if self.on_position_requested:
                self.on_position_requested(
                    args.requested_playback_position.total_seconds()
                )
        except Exception:
            _log.debug("SMTC position handler failed", exc_info=True)

    # ------------------------------------------------------------------
    # State pushes (called from the GUI thread)
    # ------------------------------------------------------------------

    def update_playback(self, playing: bool, loaded: bool = True) -> None:
        """Push the playback status; no-op when unchanged."""
        st = self._wm.MediaPlaybackStatus
        if not loaded:
            status = st.STOPPED
        elif playing:
            status = st.PLAYING
        else:
            status = st.PAUSED
        if status == self._last_status:
            return
        self._last_status = status
        try:
            self._smtc.playback_status = status
        except Exception:
            _log.debug("SMTC status push failed", exc_info=True)

    def update_metadata(
        self,
        title: str,
        artist: str,
        album: str,
        thumbnail_url: str | None,
    ) -> None:
        """Push track metadata to the media flyout."""
        try:
            du = self._smtc.display_updater
            du.type = self._wm.MediaPlaybackType.MUSIC
            props = du.music_properties
            props.title = title
            props.artist = artist
            props.album_title = album
            if thumbnail_url:
                import winrt.windows.foundation as wf
                import winrt.windows.storage.streams as streams

                du.thumbnail = streams.RandomAccessStreamReference.create_from_uri(
                    wf.Uri(thumbnail_url)
                )
            else:
                du.thumbnail = None
            du.update()
        except Exception:
            _log.debug("SMTC metadata push failed", exc_info=True)

    def clear_metadata(self) -> None:
        """Clear the media flyout when playback stops."""
        try:
            du = self._smtc.display_updater
            du.clear_all()
            du.update()
        except Exception:
            _log.debug("SMTC metadata clear failed", exc_info=True)

    def update_shuffle(self, enabled: bool) -> None:
        try:
            self._smtc.shuffle_enabled = enabled
        except Exception:
            _log.debug("SMTC shuffle push failed", exc_info=True)

    def update_repeat(self, enabled: bool) -> None:
        mode = self._wm.MediaPlaybackAutoRepeatMode
        try:
            self._smtc.auto_repeat_mode = mode.TRACK if enabled else mode.NONE
        except Exception:
            _log.debug("SMTC repeat push failed", exc_info=True)

    def update_timeline(
        self,
        position: float,
        duration: float,
        force: bool = False,
    ) -> None:
        """Push timeline state, throttled to avoid per-tick COM calls.

        Pushes when forced (track change), on a seek (position far from
        extrapolated), or every few seconds while playing.
        """
        now = time.monotonic()
        elapsed = now - self._last_push_wall
        expected = self._last_push_pos + elapsed
        if (
            not force
            and elapsed < _TIMELINE_INTERVAL
            and abs(position - expected) < _TIMELINE_JUMP
        ):
            return
        self._last_push_wall = now
        self._last_push_pos = position
        try:
            props = self._wm.SystemMediaTransportControlsTimelineProperties()
            props.start_time = datetime.timedelta(0)
            props.min_seek_time = datetime.timedelta(0)
            props.position = datetime.timedelta(seconds=max(0.0, position))
            props.end_time = datetime.timedelta(seconds=max(0.0, duration))
            props.max_seek_time = datetime.timedelta(seconds=max(0.0, duration))
            self._smtc.update_timeline_properties(props)
        except Exception:
            _log.debug("SMTC timeline push failed", exc_info=True)

    def shutdown(self) -> None:
        """Detach event handlers and disable the session."""
        removers = {
            "button_pressed": self._smtc.remove_button_pressed,
            "shuffle_enabled_change_requested": (
                self._smtc.remove_shuffle_enabled_change_requested
            ),
            "auto_repeat_mode_change_requested": (
                self._smtc.remove_auto_repeat_mode_change_requested
            ),
            "playback_position_change_requested": (
                self._smtc.remove_playback_position_change_requested
            ),
        }
        for name, token in self._tokens:
            try:
                removers[name](token)
            except Exception:
                pass
        self._tokens.clear()
        # Tell the system the session is gone for good (not merely
        # stopped) and wipe the card, so nothing stale outlives the
        # process.
        try:
            self._smtc.playback_status = self._wm.MediaPlaybackStatus.CLOSED
            du = self._smtc.display_updater
            du.clear_all()
            du.update()
        except Exception:
            pass
        try:
            self._smtc.is_enabled = False
        except Exception:
            pass
