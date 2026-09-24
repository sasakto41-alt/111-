"""Диалог редактирования фразы: заголовок, текст, категория, хоткей."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from ..models import CATEGORIES, hotkey_conflicts, normalize_hotkey
from .theme import DANGER


class TextEditorDialog(QDialog):
    saved = Signal(str)    # id
    deleted = Signal(str)  # id

    def __init__(self, store, entry, parent=None):
        super().__init__(parent)
        self.store = store
        self.entry = entry
        self.setWindowTitle("Редактирование фразы")
        self.setModal(True)
        self.resize(520, 420)

        v = QVBoxLayout(self)
        v.setSpacing(10)
        form = QFormLayout()
        form.setSpacing(8)

        self.ed_title = QLineEdit(entry.title)
        self.ed_title.setPlaceholderText("Например: Приветствие")
        form.addRow("Название:", self.ed_title)

        self.cb_cat = QComboBox()
        self.cb_cat.addItems(CATEGORIES)
        if entry.category in CATEGORIES:
            self.cb_cat.setCurrentText(entry.category)
        form.addRow("Категория:", self.cb_cat)

        self.ed_text = QPlainTextEdit()
        self.ed_text.setPlainText(entry.text)
        self.ed_text.setPlaceholderText(
            "Текст для вставки. Enter НЕ нажимается программой — вы подтверждаете чат сами."
        )
        form.addRow("Текст:", self.ed_text)

        self.ed_hotkey = QLineEdit(entry.hotkey)
        self.ed_hotkey.setPlaceholderText("напр. F7 или ctrl+1 (пусто — без хоткея)")
        form.addRow("Горячая клавиша:", self.ed_hotkey)
        v.addLayout(form)

        self.lbl_err = QLabel("")
        self.lbl_err.setWordWrap(True)
        self.lbl_err.setStyleSheet(f"color: {DANGER};")
        self.lbl_err.hide()
        v.addWidget(self.lbl_err)

        h = QHBoxLayout()
        btn_del = QPushButton("Удалить")
        btn_del.setObjectName("danger")
        btn_del.clicked.connect(self._delete)
        h.addWidget(btn_del)
        h.addStretch(1)
        btn_cancel = QPushButton("Отмена")
        btn_cancel.clicked.connect(self.reject)
        h.addWidget(btn_cancel)
        btn_save = QPushButton("Сохранить")
        btn_save.setObjectName("primary")
        btn_save.setDefault(True)
        btn_save.clicked.connect(self._save)
        h.addWidget(btn_save)
        v.addLayout(h)

    # ------------------------------------------------------------ validation --
    def validate(self) -> str:
        title = self.ed_title.text().strip()
        text = self.ed_text.toPlainText().strip()
        if not title:
            return "Укажите название фразы"
        if not text:
            return "Текст не может быть пустым"
        hk_raw = self.ed_hotkey.text().strip()
        if hk_raw:
            from ..models import is_valid_hotkey

            if not is_valid_hotkey(hk_raw):
                return ("Хоткей некорректен: используйте F1–F24 или комбинацию "
                        "ctrl/alt/shift+клавиша (например ctrl+1)")
            others = [e.hotkey for e in self.store.entries if e.id != self.entry.id]
            conflicts = hotkey_conflicts(hk_raw, self.store.settings.menu_hotkey, others)
            if conflicts:
                return "Клавиша " + "; ".join(conflicts)
        return ""

    # ----------------------------------------------------------------- slots --
    def _save(self) -> None:
        err = self.validate()
        if err:
            self.lbl_err.setText(err)
            self.lbl_err.show()
            return
        self.accept()

    def _delete(self) -> None:
        ret = QMessageBox.question(
            self, "Удаление", f"Удалить фразу «{self.entry.title}»?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if ret == QMessageBox.Yes:
            self.deleted.emit(self.entry.id)
            self.accept()

    def result_entry(self) -> dict:
        return {
            "title": self.ed_title.text().strip(),
            "text": self.ed_text.toPlainText().rstrip(),
            "category": self.cb_cat.currentText(),
            "hotkey": normalize_hotkey(self.ed_hotkey.text()) if self.ed_hotkey.text().strip() else "",
        }
