"""Windows shell identity for a portable (unpackaged) application.

Windows resolves an application's name and icon from its Application
User Model ID.  An installed application is resolvable because the
shell has a registered entry for it; a portable one has none, so shell
surfaces that must name or draw the app - the Quick Settings media card
among them - can fail to resolve it and keep showing whatever they
resolved last.

Two things help, and neither writes anything outside the process:

* a stable process-wide AppUserModelID, so the identity does not change
  from launch to launch (it is otherwise derived from the host
  executable, e.g. ``python.exe`` when running from source);
* the same id, plus a display name and icon, on the main window's shell
  property store, which is where the shell looks when it has no
  registered entry for a window's id.

Everything here is best effort: failures are swallowed, because none of
it is required for the application to work.
"""

import ctypes
import logging
import sys
from ctypes import wintypes

_log = logging.getLogger(__name__)

# Stable identity for the Windows shell.  Changing it makes the shell
# treat the application as a different one.
APP_USER_MODEL_ID = "ChordCut"


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", _GUID), ("pid", ctypes.c_ulong)]


class _PROPVARIANT(ctypes.Structure):
    # 24 bytes on x64: the tag, three reserved words, then the value.
    _fields_ = [
        ("vt", ctypes.c_ushort),
        ("wReserved1", ctypes.c_ushort),
        ("wReserved2", ctypes.c_ushort),
        ("wReserved3", ctypes.c_ushort),
        ("data", ctypes.c_ubyte * 16),
    ]


def _guid(d1: int, d2: int, d3: int, rest: tuple[int, ...]) -> _GUID:
    return _GUID(d1, d2, d3, (ctypes.c_ubyte * 8)(*rest))


# {9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3} - the AppUserModel property set.
_FMTID_APP_USER_MODEL = _guid(
    0x9F4C2855,
    0x9F79,
    0x4B39,
    (0xA8, 0xD0, 0xE1, 0xD4, 0x2D, 0xE1, 0xD5, 0xF3),
)
_PKEY_ID = _PROPERTYKEY(_FMTID_APP_USER_MODEL, 5)
_PKEY_RELAUNCH_COMMAND = _PROPERTYKEY(_FMTID_APP_USER_MODEL, 2)
_PKEY_RELAUNCH_ICON = _PROPERTYKEY(_FMTID_APP_USER_MODEL, 3)
_PKEY_RELAUNCH_DISPLAY_NAME = _PROPERTYKEY(_FMTID_APP_USER_MODEL, 4)

# IPropertyStore {886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}
_IID_IPROPERTYSTORE = _guid(
    0x886D8EEB,
    0x8CF2,
    0x4446,
    (0x8D, 0x02, 0xCD, 0xBA, 0x1D, 0xBD, 0xCF, 0x99),
)

# IPropertyStore vtable slots (IUnknown occupies 0-2).
_SLOT_RELEASE = 2
_SLOT_SETVALUE = 6
_SLOT_COMMIT = 7

# Raw c_long rather than ctypes.HRESULT: HRESULT makes ctypes raise on
# any failure code, which would hide the actual status from us.
_SetValueFn = ctypes.WINFUNCTYPE(
    ctypes.c_long,
    ctypes.c_void_p,
    ctypes.POINTER(_PROPERTYKEY),
    ctypes.POINTER(_PROPVARIANT),
)
_CommitFn = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)
_ReleaseFn = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)


def set_process_app_id(app_id: str = APP_USER_MODEL_ID) -> bool:
    """Give the process a stable AppUserModelID.

    Must run before the process creates any window.
    """
    if sys.platform != "win32":
        return False
    try:
        func = ctypes.WinDLL("shell32").SetCurrentProcessExplicitAppUserModelID
        func.argtypes = [ctypes.c_wchar_p]
        func.restype = ctypes.HRESULT
        func(app_id)
        return True
    except Exception:
        _log.debug("SetCurrentProcessExplicitAppUserModelID failed", exc_info=True)
        return False


_VT_LPWSTR = 31


def _make_string_propvariant(text: str, ole32) -> _PROPVARIANT | None:
    """Build a VT_LPWSTR PROPVARIANT owning a CoTaskMem copy of *text*.

    ``InitPropVariantFromString`` is an inline helper in the SDK header,
    not a DLL export, so the variant is assembled by hand.  The string
    is freed later by ``PropVariantClear``.
    """
    size = (len(text) + 1) * ctypes.sizeof(ctypes.c_wchar)
    mem = ole32.CoTaskMemAlloc(size)
    if not mem:
        return None
    ctypes.memmove(mem, ctypes.create_unicode_buffer(text), size)
    var = _PROPVARIANT()
    var.vt = _VT_LPWSTR
    # The value union starts right after the tag and three reserved words.
    ctypes.memmove(
        ctypes.byref(var, _PROPVARIANT.data.offset),
        ctypes.byref(ctypes.c_void_p(mem)),
        ctypes.sizeof(ctypes.c_void_p),
    )
    return var


def _vtable_call(store: ctypes.c_void_p, slot: int, functype, *args) -> int:
    vtable = ctypes.cast(
        store,
        ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)),
    ).contents
    return functype(vtable[slot])(store, *args)


def set_window_app_id(
    hwnd: int,
    app_id: str = APP_USER_MODEL_ID,
    display_name: str | None = None,
    icon_path: str | None = None,
    relaunch_command: str | None = None,
) -> bool:
    """Stamp shell identity onto a window's property store.

    Gives the shell a name and icon to draw for this window's app id
    without registering anything on the machine.
    """
    if sys.platform != "win32" or not hwnd:
        return False

    store = ctypes.c_void_p()
    try:
        shell32 = ctypes.WinDLL("shell32")
        shell32.SHGetPropertyStoreForWindow.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(_GUID),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        shell32.SHGetPropertyStoreForWindow.restype = ctypes.c_long
        hr = shell32.SHGetPropertyStoreForWindow(
            wintypes.HWND(hwnd),
            ctypes.byref(_IID_IPROPERTYSTORE),
            ctypes.byref(store),
        )
        if hr != 0:
            _log.debug("SHGetPropertyStoreForWindow returned %#x", hr & 0xFFFFFFFF)
            return False
    except Exception:
        _log.debug("SHGetPropertyStoreForWindow failed", exc_info=True)
        return False

    if not store:
        return False

    try:
        ole32 = ctypes.WinDLL("ole32")
        ole32.CoTaskMemAlloc.argtypes = [ctypes.c_size_t]
        ole32.CoTaskMemAlloc.restype = ctypes.c_void_p
        ole32.PropVariantClear.argtypes = [ctypes.POINTER(_PROPVARIANT)]
        ole32.PropVariantClear.restype = ctypes.c_long
    except Exception:
        _log.debug("ole32 unavailable", exc_info=True)
        _vtable_call(store, _SLOT_RELEASE, _ReleaseFn)
        return False

    values: list[tuple[_PROPERTYKEY, str]] = [(_PKEY_ID, app_id)]
    if display_name:
        values.append((_PKEY_RELAUNCH_DISPLAY_NAME, display_name))
    if icon_path:
        values.append((_PKEY_RELAUNCH_ICON, icon_path))
    if relaunch_command:
        values.append((_PKEY_RELAUNCH_COMMAND, relaunch_command))

    written = 0
    try:
        for key, text in values:
            var = _make_string_propvariant(text, ole32)
            if var is None:
                continue
            try:
                hr = _vtable_call(
                    store,
                    _SLOT_SETVALUE,
                    _SetValueFn,
                    ctypes.byref(key),
                    ctypes.byref(var),
                )
                if hr == 0:
                    written += 1
                else:
                    _log.debug(
                        "SetValue(pid=%d) returned %#x",
                        key.pid,
                        hr & 0xFFFFFFFF,
                    )
            finally:
                ole32.PropVariantClear(ctypes.byref(var))
        # A window property store applies writes immediately; Commit is
        # harmless but not always implemented, so it does not gate success.
        _vtable_call(store, _SLOT_COMMIT, _CommitFn)
    except Exception:
        _log.debug("window property store update failed", exc_info=True)
    finally:
        try:
            _vtable_call(store, _SLOT_RELEASE, _ReleaseFn)
        except Exception:
            pass
    return written > 0
