"""Обнаружение уведомления «объявление одобрено» (v3.10.0).

Как это работает:
  • приложение каждые 3 секунды снимает ПЕРВИЧНЫЙ экран (QScreen.grabWindow,
    выполняется в GUI-потоке) и передаёт PNG рабочему потоку;
  • рабочий поток запускает ВСТРОЕННЫЙ распознаватель Windows 10/11
    (Windows.Media.Ocr) через PowerShell — НИКАКИХ новых pip-зависимостей
    и НИКАКОГО Tesseract ставить не нужно;
  • распознанный текст ищется на слова-маркеры («одобрен», «одобрили»);
  • уведомления, которые были на экране ДО начала ожидания, не важны:
    проверка запускается только после старта ожидания и срабатывает один раз.

Требования на машине: Windows 10/11 и русский язык в списке языков Windows
(на русских Windows есть по умолчанию). Если OCR недоступен — честная
ошибка и отмена ожидания (см. «Отмена» в сценарии F9).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from .config import get_assets_dir
from .journal import log

# слова-маркеры одобрения (регистр не важен; «одобрен» покрывает
# «одобрено/одобрена/одобрено и опубликовано» и т.п.)
APPROVAL_KEYWORDS = ("одобрен", "одобрили")

_OCR_NA_MARKER = "__OCR_NA__"


def match_approval(text: str) -> bool:
    """True, если в распознанном тексте есть маркер одобрения."""
    t = (text or "").lower()
    if not t:
        return False
    return any(k in t for k in APPROVAL_KEYWORDS)


def ocr_available() -> bool:
    """OCR физически возможен на этой машине (Windows + PowerShell)?"""
    if sys.platform != "win32":
        return False
    return shutil.which("powershell") is not None


class OcrUnavailable(RuntimeError):
    """Встроенный OCR Windows недоступен (не Windows/нет языкового пакета)."""


def _ocr_script_path() -> Path:
    return get_assets_dir() / "ocr.ps1"


def ocr_region_to_text(image_path: str, x: int = 0, y: int = 0,
                       w: int = 0, h: int = 0, timeout_s: float = 40.0) -> str:
    """Распознать текст на PNG (можно обрезать область X/Y/W/H). Блокирует поток.

    Возвращает распознанный текст (может быть пустым). Бросает OcrUnavailable,
    если распознаватель недоступен на этой машине.
    """
    if not ocr_available():
        raise OcrUnavailable("OCR Windows недоступен (нужны Windows 10/11 и PowerShell)")
    ps1 = _ocr_script_path()
    if not ps1.exists():
        raise OcrUnavailable(f"не найден скрипт распознавания: {ps1}")
    cmd = [
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", str(ps1), image_path,
        "-X", str(int(x)), "-Y", str(int(y)), "-W", str(int(w)), "-H", str(int(h)),
    ]
    try:
        cp = subprocess.run(
            cmd, capture_output=True, timeout=timeout_s,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as e:
        raise OcrUnavailable(f"OCR не ответил за {timeout_s:.0f} с") from e
    out = (cp.stdout or b"").decode("utf-8", errors="replace").strip()
    if _OCR_NA_MARKER in out:
        raise OcrUnavailable(
            "OCR Windows недоступен: добавьте русский язык в "
            "«Параметры → Время и язык → Язык» и перезапустите программу"
        )
    if cp.returncode != 0:
        err = (cp.stderr or b"").decode("utf-8", errors="replace").strip()[:200]
        log(f"OCR: ошибка PowerShell (код {cp.returncode}): {err}")
        return ""
    return out


class ApprovalWatcher(QObject):
    """Рабочий поток распознавания: получает PNG-кадры, ищет одобрение.

    GUI-поток снимает экран и вызывает submit(path, x, y, w, h). Поток по
    очереди прогоняет кадры через OCR и излучает recognized при первом
    совпадении (дальше кадры игнорируются до reset). Однократно излучает
    ocr_error, если распознаватель недоступен.
    """

    recognized = Signal(str)    # текст уведомления об одобрении (первое совпадение)
    ocr_error = Signal(str)     # OCR недоступен/упал — ожидание бессмысленно
    probe_done = Signal(bool)   # кадр обработан (True = найдено совпадение)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pending: tuple | None = None
        self._lock = threading.Lock()
        self._evt = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._found = False
        self._error_sent = False

    # ------------------------------------------------------------------ api --
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._found = False
        self._error_sent = False
        self._thread = threading.Thread(
            target=self._loop, name="MTH-ocr-watch", daemon=True
        )
        self._thread.start()
        log("одобрение: поток распознавания запущен (OCR Windows, раз в ~3 с)")

    def stop(self) -> None:
        self._stop.set()
        self._evt.set()
        t = self._thread
        self._thread = None
        if t is not None and t.is_alive():
            t.join(timeout=1.5)

    def reset(self) -> None:
        """Новое ожидание: забыть прошлые результаты."""
        with self._lock:
            self._pending = None
        self._found = False
        self._error_sent = False

    def submit(self, path: str, x: int = 0, y: int = 0, w: int = 0, h: int = 0) -> None:
        """Передать кадр на распознавание (перезаписывает невзятый предыдущий)."""
        if self._found:
            return
        with self._lock:
            self._pending = (path, int(x), int(y), int(w), int(h))
        self._evt.set()

    # ---------------------------------------------------------------- loop --
    def _loop(self) -> None:
        while not self._stop.is_set():
            if not self._evt.wait(0.2):
                continue
            self._evt.clear()
            if self._stop.is_set():
                break
            with self._lock:
                item = self._pending
                self._pending = None
            if item is None or self._found:
                continue
            path, x, y, w, h = item
            try:
                text = ocr_region_to_text(path, x, y, w, h)
            except OcrUnavailable as e:
                if not self._error_sent:
                    self._error_sent = True
                    log(f"одобрение: {e}")
                    self.ocr_error.emit(str(e))
                continue
            except Exception as e:
                log(f"одобрение: сбой распознавания: {e}")
                continue
            finally:
                # кадр больше не нужен — не копим мусор во временной папке
                try:
                    if path and os.path.exists(path):
                        os.unlink(path)
                except Exception:
                    pass
            if match_approval(text):
                self._found = True
                log(f"одобрение: УВЕДЕНО в уведомлении: {text[:120]!r}")
                self.recognized.emit(text)
                self.probe_done.emit(True)
            else:
                self.probe_done.emit(False)


def make_probe_file(suffix: str = ".png") -> str:
    """Путь временного файла для кадра OCR (в системной temp-папке)."""
    fd, path = tempfile.mkstemp(prefix="mth_ocr_", suffix=suffix)
    os.close(fd)
    return path
