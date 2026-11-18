"""View commands. Python 3.3 syntax only.

Screenshot strategy:
1. Modern NX (2512+): NXOpen Gateway.ImageExportBuilder (silent, headless-safe).
2. NX10: no ImageExportBuilder -> fall back to Win32 PrintWindow/BitBlt on the
   NX main window (must be visible, not minimized), encoded as PNG with zlib.
"""

import os
import struct
import zlib

import NXOpen
import NXOpen.Gateway


def _write_png(path, width, height, raw_bgra):
    stride = width * 4

    def chunk(tag, data):
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    rows = []
    for y in range(height):
        base = y * stride
        rgb = bytearray()
        for x in range(width):
            i = base + x * 4
            rgb.append(raw_bgra[i + 2])
            rgb.append(raw_bgra[i + 1])
            rgb.append(raw_bgra[i])
        rows.append(b"\x00" + bytes(rgb))
    payload = zlib.compress(b"".join(rows), 6)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", payload)
    png += chunk(b"IEND", b"")
    fh = open(path, "wb")
    try:
        fh.write(png)
    finally:
        fh.close()


def _capture_nx_window(path):
    import ctypes
    from ctypes import wintypes as w

    pid = os.getpid()
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

    enum_proc = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    windows = []

    def callback(hwnd, lparam):
        owner = w.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value != pid or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        rect = w.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        if width > 200 and height > 150:
            windows.append((int(hwnd), width, height))
        return True

    user32.EnumWindows(enum_proc(callback), 0)
    if not windows:
        raise RuntimeError(
            "NX 窗口已最小化或不可见，无法截图；请恢复 NX 窗口后重试（或改用 2512 的 ImageExport）"
        )
    hwnd, width, height = max(windows, key=lambda item: item[1] * item[2])

    class BitmapInfoHeader(ctypes.Structure):
        _fields_ = [
            ("biSize", w.DWORD),
            ("biWidth", w.LONG),
            ("biHeight", w.LONG),
            ("biPlanes", w.WORD),
            ("biBitCount", w.WORD),
            ("biCompression", w.DWORD),
            ("biSizeImage", w.DWORD),
            ("biXPelsPerMeter", w.LONG),
            ("biYPelsPerMeter", w.LONG),
            ("biClrUsed", w.DWORD),
            ("biClrImportant", w.DWORD),
        ]

    gdi32.CreateDIBSection.argtypes = [
        w.HDC,
        ctypes.POINTER(BitmapInfoHeader),
        w.UINT,
        ctypes.POINTER(ctypes.c_void_p),
        w.HANDLE,
        w.DWORD,
    ]
    gdi32.CreateDIBSection.restype = w.HANDLE

    window_dc = user32.GetWindowDC(hwnd)
    memory_dc = gdi32.CreateCompatibleDC(window_dc)
    header = BitmapInfoHeader()
    header.biSize = ctypes.sizeof(BitmapInfoHeader)
    header.biWidth = width
    header.biHeight = -height
    header.biPlanes = 1
    header.biBitCount = 32
    bits = ctypes.c_void_p()
    dib = gdi32.CreateDIBSection(
        memory_dc, ctypes.byref(header), 0, ctypes.byref(bits), None, 0
    )
    old = gdi32.SelectObject(memory_dc, dib)
    try:
        rendered = user32.PrintWindow(hwnd, memory_dc, 2)
        if not rendered:
            gdi32.BitBlt(memory_dc, 0, 0, width, height, window_dc, 0, 0, 0x00CC0020)
        raw = ctypes.string_at(bits, width * height * 4)
    finally:
        gdi32.SelectObject(memory_dc, old)
        gdi32.DeleteObject(dib)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(hwnd, window_dc)
    _write_png(path, width, height, raw)
    return {"file": path, "exists": os.path.exists(path), "width": width, "height": height}


def screenshot(st, args):
    path = args.get("path")
    if not path:
        raise RuntimeError("screenshot 需要 path（PNG 输出路径）")
    wp = st.session.Parts.Work
    view = args.get("view")
    if view == "fit" and wp is not None:
        try:
            wp.ModelingViews.WorkView.Orient(
                NXOpen.View.Canned.Trimetric, NXOpen.View.ScaleAdjustment.Fit
            )
        except Exception:
            pass
    try:
        builder = NXOpen.UI.GetUI().CreateImageExportBuilder()
    except Exception:
        return {"data": _capture_nx_window(path), "facts": {}}
    try:
        builder.RegionMode = False
        builder.FileFormat = NXOpen.Gateway.ImageExportBuilder.FileFormats.Png
        builder.FileName = path
        builder.BackgroundOption = NXOpen.Gateway.ImageExportBuilder.BackgroundOptions.Original
        builder.EnhanceEdges = False
        builder.Commit()
    finally:
        builder.Destroy()
    return {"data": {"file": path, "exists": os.path.exists(path)}, "facts": {}}
