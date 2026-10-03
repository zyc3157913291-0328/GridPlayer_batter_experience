# MOD: new file - Windows shell thumbnails (playlist panel thumbnails).
"""MOD: get a file's thumbnail from Windows itself.

Explorer does not extract video frames by itself: it asks the shell thumbnail
provider through IShellItemImageFactory::GetImage, which is backed by the
system thumbnail cache (thumbcache_*.db). Going through the same API means the
panel shows exactly what Explorer shows, and gets caching for free - no VLC
snapshots and no cache of our own.

Called through ctypes, so no pywin32/comtypes dependency is added.
"""

import ctypes
import uuid
from ctypes import (
    POINTER,
    Structure,
    byref,
    c_int,
    c_long,
    c_ubyte,
    c_ulong,
    c_ushort,
    c_void_p,
    c_wchar_p,
)
from pathlib import Path

HRESULT = ctypes.c_long
S_OK = 0

# ask for a thumbnail rather than the file-type icon; bigger sizes are fine
SIIGBF_BIGGERSIZEOK = 0x01
SIIGBF_THUMBNAILONLY = 0x08

# The shell fits the image inside a SIZE x SIZE box, so the LONG edge is capped
# at this value. Ask for noticeably more than the panel displays, otherwise a
# widescreen clip would come back only ~66px tall when 118 is wanted.
DEFAULT_SIZE = 256


class GUID(Structure):
    _fields_ = [
        ("Data1", c_ulong),
        ("Data2", c_ushort),
        ("Data3", c_ushort),
        ("Data4", c_ubyte * 8),
    ]


class SIZE(Structure):
    _fields_ = [("cx", c_long), ("cy", c_long)]


class BITMAP(Structure):
    _fields_ = [
        ("bmType", c_long),
        ("bmWidth", c_long),
        ("bmHeight", c_long),
        ("bmWidthBytes", c_long),
        ("bmPlanes", c_ushort),
        ("bmBitsPixel", c_ushort),
        ("bmBits", c_void_p),
    ]


class BITMAPINFOHEADER(Structure):
    _fields_ = [
        ("biSize", c_ulong),
        ("biWidth", c_long),
        ("biHeight", c_long),
        ("biPlanes", c_ushort),
        ("biBitCount", c_ushort),
        ("biCompression", c_ulong),
        ("biSizeImage", c_ulong),
        ("biXPelsPerMeter", c_long),
        ("biYPelsPerMeter", c_long),
        ("biClrUsed", c_ulong),
        ("biClrImportant", c_ulong),
    ]


class DIBSECTION(Structure):
    _fields_ = [
        ("dsBm", BITMAP),
        ("dsBmih", BITMAPINFOHEADER),
        ("dsBitfields", c_ulong * 3),
        ("dshSection", c_void_p),
        ("dsOffset", c_ulong),
    ]


def _make_guid(text):
    u = uuid.UUID(text)

    return GUID(u.time_low, u.time_mid, u.time_hi_version, (c_ubyte * 8)(*u.bytes[8:]))


IID_IShellItemImageFactory = _make_guid("{BCC18B79-BA16-442F-80C4-8A59C30C463B}")

_shell32 = ctypes.windll.shell32
_gdi32 = ctypes.windll.gdi32

_shell32.SHCreateItemFromParsingName.restype = HRESULT
_shell32.SHCreateItemFromParsingName.argtypes = [
    c_wchar_p,
    c_void_p,
    POINTER(GUID),
    POINTER(c_void_p),
]

_GETIMAGE_PROTO = ctypes.WINFUNCTYPE(HRESULT, c_void_p, SIZE, c_int, POINTER(c_void_p))
_RELEASE_PROTO = ctypes.WINFUNCTYPE(c_ulong, c_void_p)


def _get_image(hwnd_owner, path, size):
    """Call IShellItemImageFactory::GetImage; returns an HBITMAP or None."""
    item = c_void_p()

    hr = _shell32.SHCreateItemFromParsingName(
        str(path), None, byref(IID_IShellItemImageFactory), byref(item)
    )
    if hr != S_OK or not item:
        return None

    vtable = ctypes.cast(item, POINTER(c_void_p))[0]
    slots = ctypes.cast(vtable, POINTER(c_void_p))

    hbmp = c_void_p()
    try:
        # IUnknown occupies slots 0-2, so GetImage is slot 3
        get_image = _GETIMAGE_PROTO(slots[3])
        hr = get_image(item, SIZE(size, size), SIIGBF_THUMBNAILONLY, byref(hbmp))
    finally:
        _RELEASE_PROTO(slots[2])(item)

    if hr != S_OK or not hbmp:
        return None

    return hbmp


def _hbitmap_to_image(hbmp):
    """Read the DIB bits straight out of the HBITMAP.

    Qt's QtWin.fromHBITMAP() goes through GetDIBits, which fails on the 32bpp
    alpha DIB section the shell hands back ("GetDIBits() failed to query
    data"). Reading bmBits directly sidesteps that.

    Orientation is NOT inferred from biHeight. Measured on this machine with an
    asymmetric test clip (top half red, bottom half blue): the shell returns
    biHeight = +48 yet the rows are already stored top-down, so mirroring them
    produced upside-down thumbnails. Both "always mirror" and "mirror when
    biHeight > 0" were wrong; the rows are used as-is.
    """
    from PyQt5.QtGui import QImage

    dib = DIBSECTION()
    if not _gdi32.GetObjectW(hbmp, ctypes.sizeof(DIBSECTION), byref(dib)):
        return None

    bm = dib.dsBm
    if not bm.bmBits or bm.bmWidth <= 0 or bm.bmHeight <= 0:
        return None

    raw = ctypes.string_at(bm.bmBits, bm.bmWidthBytes * bm.bmHeight)

    return QImage(
        raw, bm.bmWidth, bm.bmHeight, bm.bmWidthBytes, QImage.Format_ARGB32
    ).copy()


def thumbnail_image(path, size: int = DEFAULT_SIZE):
    """A QImage thumbnail for `path`, or None if the shell has none.

    Returns a QImage rather than a QPixmap so the result can cross a thread
    boundary safely; convert on the GUI thread.
    """
    hbmp = _get_image(None, Path(path), size)
    if hbmp is None:
        return None

    try:
        return _hbitmap_to_image(hbmp)
    finally:
        _gdi32.DeleteObject(hbmp)


def com_initialize():
    """COM must be initialized on any thread that calls into the shell."""
    try:
        ctypes.windll.ole32.CoInitialize(None)
    except OSError:
        pass


def com_uninitialize():
    try:
        ctypes.windll.ole32.CoUninitialize()
    except OSError:
        pass
