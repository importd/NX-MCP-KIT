"""View commands. Python 3.3 syntax only.

Screenshot strategy:
1. Modern NX (2512+): NXOpen Gateway.ImageExportBuilder (silent, headless-safe).
2. NX10: no ImageExportBuilder -> fall back to Win32 PrintWindow/BitBlt on the
   NX main window (must be visible, not minimized), encoded as PNG with zlib.

Screenshots are expensive for an agent (image tokens), so this module keeps the
output small by default:
  * crop=True   -> NX10 capture is trimmed to the graphics viewport (the
    MDIClient child window) instead of the whole window with menu bar, toolbars
    and the part navigator.
  * width=900   -> nearest-neighbour downsample so the pixel count stays bounded
    (1634x1174 whole window -> roughly 900x680 viewport).
  * fit=True    -> fit the work view before capture so the model fills the shot.
Callers may override (crop=False, width=0), but that is a deliberate choice.

Only take screenshots for user-facing deliverables or when the geometry is
genuinely ambiguous. Prefer nx_measure / nx_inspect / nx_assert numbers.
"""

import os
import struct
import zlib

import NXOpen
import NXOpen.Gateway

DEFAULT_WIDTH = 900

# Per-process counter so a runaway loop of screenshots is at least visible.
_SHOT_COUNT = [0]


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


def _crop_bgra(raw, width, height, rect, stride):
    x, y, w, h = rect
    if x < 0 or y < 0 or x + w > width or y + h > height or w <= 0 or h <= 0:
        return raw, width, height, None
    out = bytearray()
    for row in range(y, y + h):
        start = row * stride + x * 4
        out += raw[start:start + w * 4]
    return bytes(out), w, h, (x, y, w, h)


def _scale_bgra(raw, width, height, dst_width):
    """Nearest-neighbour downsample; no-op when dst_width <= 0 or >= width."""
    if not dst_width or dst_width <= 0 or dst_width >= width:
        return raw, width, height
    ratio = float(width) / float(dst_width)
    dst_height = int(round(float(height) / ratio))
    if dst_height < 1:
        dst_height = 1
    stride = width * 4
    dst_stride = dst_width * 4
    cols = []
    for dx in range(dst_width):
        sx = int(dx * ratio)
        if sx >= width:
            sx = width - 1
        cols.append(sx * 4)
    out = bytearray(dst_stride * dst_height)
    for dy in range(dst_height):
        sy = int(dy * ratio)
        if sy >= height:
            sy = height - 1
        src_row = sy * stride
        dst_row = dy * dst_stride
        for dx in range(dst_width):
            si = src_row + cols[dx]
            di = dst_row + dx * 4
            out[di] = raw[si]
            out[di + 1] = raw[si + 1]
            out[di + 2] = raw[si + 2]
            out[di + 3] = raw[si + 3]
    return bytes(out), dst_width, dst_height


def _find_viewport(hwnd, win_left, win_top, win_width, win_height):
    """Rect of the graphics viewport inside the main window, in window pixels."""
    import ctypes
    from ctypes import wintypes as w

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetWindowRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
    user32.GetClassNameW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [w.HWND]
    user32.EnumChildWindows.argtypes = [
        w.HWND,
        ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM),
        w.LPARAM,
    ]

    proc = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    children = []

    def callback(child, lparam):
        if not user32.IsWindowVisible(child):
            return True
        name = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(child, name, 256)
        rect = w.RECT()
        user32.GetWindowRect(child, ctypes.byref(rect))
        children.append((name.value, rect.left, rect.top, rect.right, rect.bottom))
        return True

    user32.EnumChildWindows(hwnd, proc(callback), 0)

    chosen = None
    for entry in children:
        if "MDIClient" in entry[0]:
            chosen = entry
            break
    if chosen is None:
        best = -1
        for entry in children:
            area = (entry[3] - entry[1]) * (entry[4] - entry[2])
            if area > best:
                best = area
                chosen = entry
    if chosen is None:
        return None

    x = chosen[1] - win_left
    y = chosen[2] - win_top
    wd = chosen[3] - chosen[1]
    ht = chosen[4] - chosen[2]
    if x < 0:
        wd += x
        x = 0
    if y < 0:
        ht += y
        y = 0
    if x + wd > win_width:
        wd = win_width - x
    if y + ht > win_height:
        ht = win_height - y
    if wd < 50 or ht < 50:
        return None
    return (x, y, wd, ht)


def _capture_nx_window(path, crop=False, target_width=0):
    import ctypes
    from ctypes import wintypes as w

    pid = os.getpid()
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    # 64-bit handles must be declared explicitly; ctypes defaults to a 32-bit int.
    user32.GetWindowDC.argtypes = [w.HWND]
    user32.GetWindowDC.restype = w.HDC
    user32.ReleaseDC.argtypes = [w.HWND, w.HDC]
    user32.ReleaseDC.restype = ctypes.c_int
    user32.PrintWindow.argtypes = [w.HWND, w.HDC, w.UINT]
    user32.PrintWindow.restype = w.BOOL
    gdi32.CreateCompatibleDC.argtypes = [w.HDC]
    gdi32.CreateCompatibleDC.restype = w.HDC
    gdi32.SelectObject.argtypes = [w.HDC, w.HANDLE]
    gdi32.SelectObject.restype = w.HANDLE
    gdi32.DeleteObject.argtypes = [w.HANDLE]
    gdi32.DeleteObject.restype = w.BOOL
    gdi32.DeleteDC.argtypes = [w.HDC]
    gdi32.DeleteDC.restype = w.BOOL
    gdi32.BitBlt.argtypes = [
        w.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        w.HDC, ctypes.c_int, ctypes.c_int, w.DWORD,
    ]
    gdi32.BitBlt.restype = w.BOOL

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
            windows.append((int(hwnd), rect.left, rect.top, width, height))
        return True

    user32.EnumWindows(enum_proc(callback), 0)
    if not windows:
        raise RuntimeError(
            "NX 窗口已最小化或不可见，无法截图；请恢复 NX 窗口后重试（或改用 2512 的 ImageExport）"
        )
    hwnd, win_left, win_top, width, height = max(
        windows, key=lambda item: item[3] * item[4]
    )

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

    full_width, full_height = width, height
    crop_rect = None
    if crop:
        try:
            crop_rect = _find_viewport(hwnd, win_left, win_top, width, height)
        except Exception:
            crop_rect = None
        if crop_rect is not None:
            raw, width, height, crop_rect = _crop_bgra(
                raw, width, height, crop_rect, width * 4
            )
    raw, width, height = _scale_bgra(raw, width, height, target_width)

    _write_png(path, width, height, raw)
    return {
        "file": path,
        "exists": os.path.exists(path),
        "width": width,
        "height": height,
        "full_width": full_width,
        "full_height": full_height,
        "cropped": crop_rect,
    }


def _fit_work_view(parts_work):
    if parts_work is None:
        return False
    try:
        work_view = parts_work.ModelingViews.WorkView
    except Exception:
        return False
    try:
        work_view.Fit()
        return True
    except Exception:
        pass
    try:
        work_view.Orient(
            NXOpen.View.Canned.Trimetric, NXOpen.View.ScaleAdjustment.Fit
        )
        return True
    except Exception:
        return False


def screenshot(st, args):
    path = args.get("path")
    if not path:
        raise RuntimeError("screenshot 需要 path（PNG 输出路径）")
    parts_work = st.session.Parts.Work
    view = args.get("view") or ""
    crop = args.get("crop")
    if crop is None:
        crop = True
    target_width = args.get("width")
    if target_width is None:
        target_width = DEFAULT_WIDTH
    try:
        target_width = int(target_width)
    except Exception:
        target_width = DEFAULT_WIDTH
    if target_width < 0:
        target_width = 0

    # Fit first so the model fills the viewport; keep the current orientation.
    if view in ("", "fit") or args.get("fit"):
        _fit_work_view(parts_work)
    if view == "trimetric" and parts_work is not None:
        try:
            parts_work.ModelingViews.WorkView.Orient(
                NXOpen.View.Canned.Trimetric, NXOpen.View.ScaleAdjustment.Fit
            )
        except Exception:
            pass

    try:
        builder = NXOpen.UI.GetUI().CreateImageExportBuilder()
    except Exception:
        _SHOT_COUNT[0] += 1
        data = _capture_nx_window(path, crop=crop, target_width=target_width)
        data["shots"] = _SHOT_COUNT[0]
        return {"data": data, "facts": {}}
    try:
        builder.RegionMode = False
        builder.FileFormat = NXOpen.Gateway.ImageExportBuilder.FileFormats.Png
        builder.FileName = path
        builder.BackgroundOption = NXOpen.Gateway.ImageExportBuilder.BackgroundOptions.Original
        builder.EnhanceEdges = False
        builder.Commit()
    finally:
        builder.Destroy()
    _SHOT_COUNT[0] += 1
    return {
        "data": {
            "file": path,
            "exists": os.path.exists(path),
            "shots": _SHOT_COUNT[0],
            "note": "ImageExport 只导视口；crop/width 仅作用于 NX10 PrintWindow 路径",
        },
        "facts": {},
    }
