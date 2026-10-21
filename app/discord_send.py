"""Отправка скриншота объявления в Discord (v3.10.0).

Основной способ (выбран пользователем): программа САМА переключается в
открытый Discord, вставляет текст «Госволна N/13» и СКРИНШОТ (как вложение)
в ТЕКУЩИЙ канал и нажимает Enter — отправка идёт от вашего аккаунта, как
будто вы сделали это вручную. Никаких вебхуков и ботов настраивать не нужно.

Запасной способ: если окно Discord не найдено (свёрнут в трей и т.п.) и в
Настройках вписан вебхук — скриншот уйдёт через вебхук в заданный канал.

Важно про Enter: в Discord программа нажимает Enter сама — это часть
автоматизации, которую пользователь явно запросил (как авто-Enter в макросе).

Буфер обмена заполняется через WinAPI напрямую (ctypes) из рабочего потока —
Qt-буфер доступен только из GUI-потока, а клавиши жмутся там же, где и для
макросов (SendInput, сканкоды, MTH_DRYRUN уважается).
"""
from __future__ import annotations

import ctypes
import json
import sys
import time
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QImage

from . import injector, window_utils
from .journal import log

DRY_RUN = injector.DRY_RUN

DISCORD_TITLE_MARKERS = ("discord",)

CF_UNICODETEXT = 13
CF_DIB = 8
GMEM_MOVEABLE = 0x0002

_is_windows = sys.platform == "win32"
if _is_windows:
    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32


# --------------------------------------------------------------- окно Discord --
def find_discord_window() -> int:
    """hwnd окна Discord (первое видимое окно с «discord» в заголовке) или 0."""
    try:
        for marker in DISCORD_TITLE_MARKERS:
            hwnd = window_utils.find_target_window(marker, "")
            if hwnd:
                return hwnd
    except Exception:
        pass
    return 0


# ----------------------------------------------------------- буфер (WinAPI) --
def _clipboard_set(data: bytes, fmt: int) -> bool:
    """Положить сырые данные в буфер (WinAPI, любой поток)."""
    if not _is_windows:
        return False
    try:
        for _ in range(10):                      # буфер может быть занят
            if _user32.OpenClipboard(0):
                break
            time.sleep(0.05)
        else:
            return False
        try:
            _user32.EmptyClipboard()
            if not data:
                return True
            h = _kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
            if not h:
                return False
            ptr = _kernel32.GlobalLock(h)
            if not ptr:
                _kernel32.GlobalFree(h)
                return False
            ctypes.memmove(ptr, data, len(data))
            _kernel32.GlobalUnlock(h)
            if not _user32.SetClipboardData(fmt, h):
                _kernel32.GlobalFree(h)
                return False
            return True
        finally:
            _user32.CloseClipboard()
    except Exception as e:
        log(f"буфер: ошибка WinAPI: {e}")
        return False


def set_clipboard_text(text: str) -> bool:
    """Текст в буфер (CF_UNICODETEXT)."""
    if DRY_RUN:
        log(f"буфер: текст {text!r} (DRY)")
        return True
    payload = text.encode("utf-16-le") + b"\x00\x00"
    ok = _clipboard_set(payload, CF_UNICODETEXT)
    log(f"буфер: текст {'положен' if ok else 'НЕ удался'} ({len(text)} симв.)")
    return ok


def qimage_to_dib(img: QImage) -> bytes:
    """QImage → CF_DIB (BITMAPINFOHEADER + 32bpp BGRA снизу вверх).

    Discord принимает вставку через CF_DIB — так вставляются скриншоты из
    «Ножниц» и других программ. Формат ARGB32 в памяти — это и есть BGRA.
    """
    im = img.convertToFormat(QImage.Format_ARGB32)
    w, h = im.width(), im.height()
    bpl = im.bytesPerLine()
    raw = bytes(im.constBits())          # топ-даун, BGRA (у ARGB32 в LE)
    stride = w * 4
    rows = [raw[y * bpl: y * bpl + stride] for y in range(h)]
    body = b"".join(reversed(rows))      # DIB хранится снизу вверх

    class BMIH(ctypes.Structure):
        _fields_ = [
            ("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
            ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
            ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
            ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
            ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
            ("biClrImportant", ctypes.c_uint32),
        ]

    hdr = BMIH(40, w, h, 1, 32, 0, stride * h, 0, 0, 0, 0)
    return bytes(hdr) + body


def set_clipboard_image(img: QImage) -> bool:
    """Картинка в буфер (CF_DIB)."""
    if DRY_RUN:
        log(f"буфер: картинка {img.width()}x{img.height()} (DRY)")
        return True
    ok = _clipboard_set(qimage_to_dib(img), CF_DIB)
    log(f"буфер: картинка {'положена' if ok else 'НЕ удалась'} ({img.width()}x{img.height()})")
    return ok


# ---------------------------------------------------------------- вебхук (фолбэк) --
def build_multipart(text: str, png_bytes: bytes, filename: str = "screenshot.png") -> tuple:
    """Собрать multipart/form-data для вебхука Discord. Чистая функция (тесты)."""
    boundary = "----MTH" + uuid.uuid4().hex
    payload = json.dumps({"content": text or ""}).encode("utf-8")
    parts = [
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="payload_json"\r\n\r\n',
        payload, b"\r\n",
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="files[0]"; filename="{filename}"\r\n'
        .encode(),
        b"Content-Type: image/png\r\n\r\n",
        png_bytes, b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    body = b"".join(parts)
    return f"multipart/form-data; boundary={boundary}", body


def send_via_webhook(url: str, text: str, png_path: str, timeout_s: float = 20.0) -> bool:
    """Отправка через вебхук Discord (запасной путь, блокирует поток)."""
    url = (url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        log("вебхук: адрес не задан/некорректен — отправка невозможна")
        return False
    try:
        import urllib.error
        import urllib.request

        png = Path(png_path).read_bytes()
        ctype, body = build_multipart(text, png)
        req = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Content-Type": ctype})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            ok = 200 <= resp.status < 300
        log(f"вебхук: отправка {'успешна' if ok else 'отклонена'}")
        return ok
    except urllib.error.HTTPError as e:
        log(f"вебхук: HTTP {e.code}: {e.read()[:200]!r}")
        return False
    except Exception as e:
        log(f"вебхук: ошибка: {e}")
        return False


# -------------------------------------------------------- рабочий поток отправки --
class DiscordSendWorker(QObject):
    """Отправка «текст + скриншот» в Discord в рабочем потоке (UI не блокируется).

    deliver(image, png_path, text, webhook): фокус Discord → текст (Ctrl+V) →
    картинка (Ctrl+V) → Enter. Если окно Discord не найдено и задан вебхук —
    отправка через вебхук. Результат — сигнал finished(ok, detail).
    """

    deliver = Signal(object, str, str, str)
    finished = Signal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.deliver.connect(self._deliver)

    @Slot(object, str, str, str)
    def _deliver(self, img: QImage, png_path: str, text: str, webhook: str) -> None:
        t0 = time.monotonic()
        try:
            ok, detail = self._send(img, png_path, text, webhook)
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
            log(f"discord: сбой отправки: {detail}")
        log(f"discord: отправка завершена за {time.monotonic() - t0:.2f} с "
            f"(итог: {'OK' if ok else 'НЕ УДАЛОСЬ'})")
        self.finished.emit(ok, detail)

    @staticmethod
    def _send(img: QImage, png_path: str, text: str, webhook: str) -> tuple:
        hwnd = find_discord_window()
        if not hwnd and (webhook or "").strip():
            log("discord: окно Discord не найдено — отправляю через вебхук")
            return send_via_webhook(webhook, text, png_path), "webhook"
        if not hwnd:
            log("discord: окно Discord НЕ найдено; вебхук не задан — "
                "скриншот остался в data/screenshots")
            return False, "discord-not-found"

        if not window_utils.focus_window(hwnd):
            log("discord: не удалось переключиться в окно Discord")
        time.sleep(0.45)

        # 1) текст сообщения («Госволна 4/13»)
        if not set_clipboard_text(text):
            return False, "clipboard-text"
        injector.press_ctrl_v()
        time.sleep(0.35)

        # 2) скриншот как вложение
        if not set_clipboard_image(img):
            return False, "clipboard-image"
        injector.press_ctrl_v()
        time.sleep(1.3)          # Discord должен успеть собрать вложение

        # 3) отправка (Enter — часть запрошенной автоматизации)
        injector.press_enter()
        time.sleep(0.4)
        log(f"discord: вставлено в Discord: {text!r} + скриншот")
        return True, "ok"
