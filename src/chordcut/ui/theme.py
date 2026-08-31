"""System-derived colors and metrics for custom-drawn controls.

Every color used by custom drawing must come from here so that Windows
High Contrast themes and system color changes apply automatically.
Nothing in this module may touch locale (LC_NUMERIC must stay "C").
"""

import ctypes
import ctypes.wintypes

import wx


def is_high_contrast() -> bool:
    """Return True when a Windows High Contrast theme is active."""

    class _HIGHCONTRASTW(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.wintypes.UINT),
            ("dwFlags", ctypes.wintypes.DWORD),
            ("lpszDefaultScheme", ctypes.wintypes.LPWSTR),
        ]

    SPI_GETHIGHCONTRAST = 0x0042
    HCF_HIGHCONTRASTON = 0x00000001
    hc = _HIGHCONTRASTW()
    hc.cbSize = ctypes.sizeof(_HIGHCONTRASTW)
    ok = ctypes.windll.user32.SystemParametersInfoW(
        SPI_GETHIGHCONTRAST, hc.cbSize, ctypes.byref(hc), 0
    )
    return bool(ok) and bool(hc.dwFlags & HCF_HIGHCONTRASTON)


def _sys(colour_id: int) -> wx.Colour:
    return wx.SystemSettings.GetColour(colour_id)


def _blend(fg: wx.Colour, bg: wx.Colour, alpha: float) -> wx.Colour:
    """Blend fg into bg; alpha is the fg fraction (0..1)."""
    return wx.Colour(
        round(fg.Red() * alpha + bg.Red() * (1 - alpha)),
        round(fg.Green() * alpha + bg.Green() * (1 - alpha)),
        round(fg.Blue() * alpha + bg.Blue() * (1 - alpha)),
    )


class Theme:
    """Snapshot of system colors, fonts and metrics.

    Recompute (create a new instance) on wx.EVT_SYS_COLOUR_CHANGED and
    wx.EVT_DPI_CHANGED.
    """

    def __init__(self, window: wx.Window):
        self.high_contrast = is_high_contrast()

        self.window_bg = _sys(wx.SYS_COLOUR_WINDOW)
        self.text = _sys(wx.SYS_COLOUR_WINDOWTEXT)
        self.secondary_text = _sys(wx.SYS_COLOUR_GRAYTEXT)
        self.selection_bg = _sys(wx.SYS_COLOUR_HIGHLIGHT)
        self.selection_text = _sys(wx.SYS_COLOUR_HIGHLIGHTTEXT)
        self.header_bg = _sys(wx.SYS_COLOUR_BTNFACE)
        self.header_text = _sys(wx.SYS_COLOUR_BTNTEXT)
        self.grid_line = _sys(wx.SYS_COLOUR_BTNSHADOW)
        self.accent = _sys(wx.SYS_COLOUR_HOTLIGHT)

        if self.high_contrast:
            # No alpha blends in high contrast: use pure system colors.
            self.hover_bg = self.selection_bg
            self.hover_text = self.selection_text
            self.unfocused_selection_bg = self.selection_bg
            self.unfocused_selection_text = self.selection_text
        else:
            self.hover_bg = _blend(self.selection_bg, self.window_bg, 0.15)
            self.hover_text = self.text
            self.unfocused_selection_bg = _blend(
                self.selection_bg, self.window_bg, 0.30
            )
            self.unfocused_selection_text = self.text

        self.font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
        header_font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
        self.header_font = header_font.Bold()

        dc = wx.ClientDC(window)
        dc.SetFont(self.font)
        text_height = dc.GetCharHeight()
        self.row_height = max(window.FromDIP(24), text_height + window.FromDIP(8))
        self.header_height = max(window.FromDIP(22), text_height + window.FromDIP(6))
        self.cell_padding = window.FromDIP(8)
