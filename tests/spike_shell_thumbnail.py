"""SPIKE - can we get Windows' own thumbnail for a video file?

Explorer does not extract frames itself: it asks the shell thumbnail provider
via IShellItemImageFactory::GetImage, backed by the system thumbnail cache
(thumbcache_*.db). If that works from Python here, the panel should use it
instead of hand-rolling VLC snapshots + its own cache.

Calls the COM interface directly through ctypes - no pywin32 dependency.
"""

import ctypes
import sys
import time
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._harness import ROOT, bootstrap, sample

bootstrap()

from PyQt5.QtGui import QPixmap

HRESULT = ctypes.c_long
S_OK = 0

SIIGBF_RESIZETOFIT = 0x00
SIIGBF_BIGGERSIZEOK = 0x01
SIIGBF_THUMBNAILONLY = 0x08


class GUID(Structure):
    _fields_ = [
        ("Data1", c_ulong),
        ("Data2", c_ushort),
        ("Data3", c_ushort),
        ("Data4", c_ubyte * 8),
    ]


def make_guid(text):
    u = uuid.UUID(text)
    return GUID(u.time_low, u.time_mid, u.time_hi_version, (c_ubyte * 8)(*u.bytes[8:]))


class SIZE(Structure):
    _fields_ = [("cx", c_long), ("cy", c_long)]


IID_IShellItemImageFactory = make_guid("{BCC18B79-BA16-442F-80C4-8A59C30C463B}")

shell32 = ctypes.windll.shell32
gdi32 = ctypes.windll.gdi32

shell32.SHCreateItemFromParsingName.restype = HRESULT
shell32.SHCreateItemFromParsingName.argtypes = [
    c_wchar_p,
    c_void_p,
    POINTER(GUID),
    POINTER(c_void_p),
]

GETIMAGE_PROTO = ctypes.WINFUNCTYPE(HRESULT, c_void_p, SIZE, c_int, POINTER(c_void_p))


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


def hbitmap_to_pixmap(hbmp):
    """Read the DIB bits straight out of the HBITMAP.

    Qt's QtWin.fromHBITMAP() uses GetDIBits, which fails on the 32bpp
    alpha DIB section the shell hands back ("GetDIBits() failed to query
    data"). Reading bmBits directly sidesteps that.
    """
    from PyQt5.QtGui import QImage

    bm = BITMAP()
    if not gdi32.GetObjectW(hbmp, ctypes.sizeof(BITMAP), byref(bm)):
        return None, "GetObject failed"

    if not bm.bmBits or bm.bmWidth <= 0 or bm.bmHeight <= 0:
        return None, f"empty bitmap {bm.bmWidth}x{bm.bmHeight}"

    size = bm.bmWidthBytes * bm.bmHeight
    raw = ctypes.string_at(bm.bmBits, size)

    img = QImage(
        raw, bm.bmWidth, bm.bmHeight, bm.bmWidthBytes, QImage.Format_ARGB32
    ).copy()

    # DIB sections are bottom-up unless the height was negative
    return QPixmap.fromImage(img.mirrored(False, True)), "ok"


def shell_thumbnail(path: str, size: int = 128):
    """Return (hbitmap, hresult) for a file, using the shell's own provider."""
    item = c_void_p()
    hr = shell32.SHCreateItemFromParsingName(
        str(path), None, byref(IID_IShellItemImageFactory), byref(item)
    )
    if hr != S_OK or not item:
        return None, f"SHCreateItemFromParsingName hr=0x{hr & 0xFFFFFFFF:08X}"

    vtable = ctypes.cast(item, POINTER(c_void_p))[0]
    # IUnknown has 3 slots, so GetImage is slot 3
    get_image = GETIMAGE_PROTO(ctypes.cast(vtable, POINTER(c_void_p))[3])

    hbmp = c_void_p()
    hr = get_image(item, SIZE(size, size), SIIGBF_THUMBNAILONLY, byref(hbmp))

    # release the shell item
    release = ctypes.WINFUNCTYPE(c_ulong, c_void_p)(
        ctypes.cast(vtable, POINTER(c_void_p))[2]
    )
    release(item)

    if hr != S_OK or not hbmp:
        return None, f"GetImage hr=0x{hr & 0xFFFFFFFF:08X}"

    return hbmp, "ok"


FILES = [
    sample("probe.mp4"),
    sample("probe.mov"),
    ROOT / "README.md",  # not a video
    ROOT / "evidence" / "p3-panel-preview.png",  # an image
]

out_dir = ROOT / "evidence"
ok_count = 0

for path in FILES:
    if not path.is_file():
        print(f"  {path.name:28s} MISSING")
        continue

    t0 = time.monotonic()
    hbmp, status = shell_thumbnail(str(path), 128)
    elapsed = (time.monotonic() - t0) * 1000

    if hbmp is None:
        print(f"  {path.name:28s} {status}   ({elapsed:.0f} ms)")
        continue

    try:
        pm, conv = hbitmap_to_pixmap(hbmp)
    finally:
        gdi32.DeleteObject(hbmp)

    if pm is None:
        print(f"  {path.name:28s} convert failed: {conv}   ({elapsed:.0f} ms)")
        continue

    dst = out_dir / f"spike-thumb-{path.stem}.png"
    pm.save(str(dst))
    print(
        f"  {path.name:28s} {pm.width()}x{pm.height()}  {elapsed:.0f} ms -> {dst.name}"
    )
    ok_count += 1

print()
print(f"SPIKE RESULT: {ok_count} thumbnail(s) obtained from the shell")
if ok_count >= 2:
    print("=> the shell thumbnail API is usable; no VLC snapshots needed")
else:
    print("=> shell thumbnails did NOT work; fall back to VLC snapshots or drop them")
