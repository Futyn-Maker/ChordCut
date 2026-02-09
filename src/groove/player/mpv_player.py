"""MPV audio player wrapper for Groove."""

from typing import Callable

import mpv


class Player:
    """MPV-based audio player with playback controls."""

    def __init__(self):
        """Initialize the MPV player."""
        self._mpv = mpv.MPV(
            video=False,  # Audio only
            ytdl=False,   # Don't use youtube-dl
        )

        # Callbacks
        self._on_position_change: Callable[[float], None] | None = None
        self._on_duration_change: Callable[[float], None] | None = None
        self._on_end_file: Callable[[], None] | None = None
        self._on_error: Callable[[str], None] | None = None

        # State
        self._volume = 100
        self._duration = 0.0
        self._position = 0.0

        # Set up property observers
        @self._mpv.property_observer("time-pos")
        def time_observer(_name: str, value: float | None) -> None:
            if value is not None:
                self._position = value
                if self._on_position_change:
                    self._on_position_change(value)

        @self._mpv.property_observer("duration")
        def duration_observer(_name: str, value: float | None) -> None:
            if value is not None:
                self._duration = value
                if self._on_duration_change:
                    self._on_duration_change(value)

        @self._mpv.event_callback("end-file")
        def end_file_handler(event: mpv.MpvEvent) -> None:
            if self._on_end_file:
                self._on_end_file()

    @property
    def volume(self) -> int:
        """Get the current volume (0-100)."""
        return self._volume

    @volume.setter
    def volume(self, value: int) -> None:
        """Set the volume (0-100)."""
        self._volume = max(0, min(100, value))
        self._mpv.volume = self._volume

    @property
    def position(self) -> float:
        """Get the current playback position in seconds."""
        return self._position

    @property
    def duration(self) -> float:
        """Get the duration of the current track in seconds."""
        return self._duration

    @property
    def is_playing(self) -> bool:
        """Check if audio is currently playing (not paused)."""
        try:
            return not self._mpv.pause
        except Exception:
            return False

    @property
    def is_loaded(self) -> bool:
        """Check if a track is loaded."""
        try:
            return self._mpv.path is not None
        except Exception:
            return False

    def play(self, url: str) -> None:
        """Start playing an audio URL.

        Args:
            url: URL of the audio stream to play.
        """
        try:
            self._mpv.play(url)
            self._mpv.pause = False
        except Exception as e:
            if self._on_error:
                self._on_error(str(e))

    def pause(self) -> None:
        """Pause playback."""
        try:
            self._mpv.pause = True
        except Exception:
            pass

    def resume(self) -> None:
        """Resume playback."""
        try:
            self._mpv.pause = False
        except Exception:
            pass

    def toggle_pause(self) -> None:
        """Toggle between pause and play."""
        try:
            self._mpv.pause = not self._mpv.pause
        except Exception:
            pass

    def stop(self) -> None:
        """Stop playback."""
        try:
            self._mpv.stop()
        except Exception:
            pass

    def seek(self, seconds: float, relative: bool = True) -> None:
        """Seek in the current track.

        Args:
            seconds: Number of seconds to seek. Positive = forward,
                     negative = backward.
            relative: If True, seek relative to current position.
                      If False, seek to absolute position.
        """
        try:
            if relative:
                self._mpv.seek(seconds, "relative")
            else:
                self._mpv.seek(seconds, "absolute")
        except Exception:
            pass

    def volume_up(self, amount: int = 5) -> int:
        """Increase volume.

        Args:
            amount: Amount to increase (default 5).

        Returns:
            New volume level.
        """
        self.volume = self._volume + amount
        return self._volume

    def volume_down(self, amount: int = 5) -> int:
        """Decrease volume.

        Args:
            amount: Amount to decrease (default 5).

        Returns:
            New volume level.
        """
        self.volume = self._volume - amount
        return self._volume

    def set_on_position_change(
        self, callback: Callable[[float], None] | None
    ) -> None:
        """Set callback for position changes.

        Args:
            callback: Function to call with new position in seconds.
        """
        self._on_position_change = callback

    def set_on_duration_change(
        self, callback: Callable[[float], None] | None
    ) -> None:
        """Set callback for duration changes.

        Args:
            callback: Function to call with duration in seconds.
        """
        self._on_duration_change = callback

    def set_on_end_file(self, callback: Callable[[], None] | None) -> None:
        """Set callback for when playback ends.

        Args:
            callback: Function to call when track ends.
        """
        self._on_end_file = callback

    def set_on_error(self, callback: Callable[[str], None] | None) -> None:
        """Set callback for playback errors.

        Args:
            callback: Function to call with error message.
        """
        self._on_error = callback

    def shutdown(self) -> None:
        """Shutdown the player and release resources."""
        try:
            self._mpv.terminate()
        except Exception:
            pass


def format_duration(seconds: float) -> str:
    """Format seconds as MM:SS or HH:MM:SS.

    Args:
        seconds: Duration in seconds.

    Returns:
        Formatted duration string.
    """
    if seconds < 0:
        return "0:00"

    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
