from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QColor, QDragEnterEvent, QDropEvent, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .ffmpeg import (
    EncodeOptions,
    OperationMode,
    SubtitleTrack,
    default_output_path,
)
from .worker import EncodeWorker

LANGUAGES = [
    ("Português", "por"),
    ("Inglês", "eng"),
    ("Espanhol", "spa"),
    ("Francês", "fre"),
    ("Alemão", "ger"),
    ("Italiano", "ita"),
    ("Japonês", "jpn"),
    ("Outro…", "other"),
]
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v"}


def _resource_path(relative_path: str) -> Path:
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return bundle_root / relative_path


class SubtitleTable(QTableWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(0, 3, parent)
        self.setHorizontalHeaderLabels(["Ficheiro de legenda", "Idioma", "Título"])
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.setMinimumHeight(150)

    def add_subtitle(self, path: str, language: str = "por") -> None:
        path = os.path.abspath(path)
        if any(self.path_at(row) == path for row in range(self.rowCount())):
            return
        row = self.rowCount()
        self.insertRow(row)

        file_item = QTableWidgetItem(Path(path).name)
        file_item.setData(Qt.ItemDataRole.UserRole, path)
        file_item.setToolTip(path)
        file_item.setFlags(file_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.setItem(row, 0, file_item)

        language_box = QComboBox()
        for label, code in LANGUAGES:
            display_label = f"{label} [{code}]" if code != "other" else label
            language_box.addItem(display_label, code)
        index = language_box.findData(language)
        default_index = language_box.findData("other")
        language_box.setCurrentIndex(index if index >= 0 else default_index)
        language_box.currentIndexChanged.connect(
            lambda _index, box=language_box: self._select_other_language(box)
        )
        if language != "por" and index < 0:
            language_box.insertItem(
                language_box.count() - 1, f"Outro [{language}]", language
            )
            language_box.setCurrentIndex(language_box.count() - 2)
        self.setCellWidget(row, 1, language_box)

        title_item = QTableWidgetItem(Path(path).stem)
        self.setItem(row, 2, title_item)

    def _select_other_language(self, box: QComboBox) -> None:
        if box.currentData() != "other":
            return
        code, accepted = QInputDialogText.get_language_code(self)
        if not accepted:
            fallback = box.findData("und")
            if fallback < 0:
                box.addItem("Não definido [und]", "und")
                fallback = box.findData("und")
            box.setCurrentIndex(fallback)
            return
        selected = box.currentIndex()
        box.insertItem(selected, f"Outro [{code}]", code)
        box.setCurrentIndex(selected)

    def path_at(self, row: int) -> str:
        item = self.item(row, 0)
        return str(item.data(Qt.ItemDataRole.UserRole)) if item else ""

    def tracks(self) -> tuple[SubtitleTrack, ...]:
        tracks: list[SubtitleTrack] = []
        for row in range(self.rowCount()):
            language_box = self.cellWidget(row, 1)
            title_item = self.item(row, 2)
            tracks.append(
                SubtitleTrack(
                    path=self.path_at(row),
                    language=str(language_box.currentData()),
                    title=(
                        title_item.text().strip()
                        if title_item and title_item.text().strip()
                        else Path(self.path_at(row)).stem
                    ),
                )
            )
        return tuple(tracks)

    def remove_selected(self) -> None:
        rows = sorted({index.row() for index in self.selectedIndexes()}, reverse=True)
        for row in rows:
            self.removeRow(row)


class QInputDialogText:
    @staticmethod
    def get_language_code(parent: QWidget) -> tuple[str, bool]:
        while True:
            value, accepted = QInputDialog.getText(
                parent,
                "Idioma da legenda",
                "Código ISO 639-2 de três letras (ex.: por, eng, spa):",
            )
            if not accepted:
                return "", False
            code = value.strip().lower()
            if re.fullmatch(r"[a-z]{3}", code):
                return code, True
            QMessageBox.warning(
                parent, "Código inválido", "Introduza exatamente três letras."
            )


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SubFuse — Embutir legendas")
        self.setMinimumSize(760, 620)
        self.setAcceptDrops(True)
        self.worker: EncodeWorker | None = None
        self.video_path = ""
        self.font_color = "#FFFFFF"
        self._build_ui()
        self._update_mode_controls()

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        heading = QLabel("Embutir legendas")
        heading.setObjectName("heading")
        subtitle = QLabel("Adicione um vídeo e uma ou mais faixas SRT.")
        subtitle.setObjectName("muted")
        layout.addWidget(heading)
        layout.addWidget(subtitle)

        video_row = QHBoxLayout()
        self.video_label = QLabel("Arraste um vídeo para aqui ou escolha um ficheiro.")
        self.video_label.setObjectName("dropArea")
        self.video_label.setWordWrap(True)
        self.video_label.setMinimumHeight(66)
        self.video_button = QPushButton("Escolher vídeo…")
        self.video_button.clicked.connect(self._choose_video)
        video_row.addWidget(self.video_label, 1)
        video_row.addWidget(self.video_button)
        layout.addLayout(video_row)

        subtitle_header = QHBoxLayout()
        subtitle_header.addWidget(QLabel("Faixas de legenda"))
        subtitle_header.addStretch()
        add_button = QPushButton("Adicionar SRT…")
        add_button.clicked.connect(self._choose_subtitles)
        remove_button = QPushButton("Remover selecionada")
        remove_button.clicked.connect(self.subtitle_table_remove)
        subtitle_header.addWidget(add_button)
        subtitle_header.addWidget(remove_button)
        layout.addLayout(subtitle_header)

        self.subtitle_table = SubtitleTable()
        layout.addWidget(self.subtitle_table)

        mode_group = QFrame()
        mode_group.setObjectName("panel")
        mode_layout = QVBoxLayout(mode_group)
        mode_layout.setContentsMargins(14, 12, 14, 14)
        mode_layout.addWidget(QLabel("Modo de operação"))
        mode_row = QHBoxLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Softsub — selecionável no leitor", "softsub")
        self.mode_combo.addItem("Hardsub — queimado na imagem", "hardsub")
        self.mode_combo.currentIndexChanged.connect(self._update_mode_controls)
        mode_row.addWidget(self.mode_combo, 1)
        self.container_combo = QComboBox()
        self.container_combo.addItem("MKV (recomendado)", "mkv")
        self.container_combo.addItem("MP4 (mov_text)", "mp4")
        mode_row.addWidget(self.container_combo)
        mode_layout.addLayout(mode_row)

        self.hard_controls = QWidget()
        hard_form = QFormLayout(self.hard_controls)
        hard_form.setContentsMargins(0, 8, 0, 0)
        self.hard_track_combo = QComboBox()
        self.font_size = QSpinBox()
        self.font_size.setRange(8, 96)
        self.font_size.setValue(24)
        self.outline = QSpinBox()
        self.outline.setRange(0, 10)
        self.outline.setValue(2)
        self.color_button = QPushButton("Branco")
        self.color_button.clicked.connect(self._choose_color)
        hard_form.addRow("Legenda a queimar:", self.hard_track_combo)
        hard_form.addRow("Tamanho da fonte:", self.font_size)
        hard_form.addRow("Contorno:", self.outline)
        hard_form.addRow("Cor do texto:", self.color_button)
        mode_layout.addWidget(self.hard_controls)
        layout.addWidget(mode_group)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status = QLabel("Pronto.")
        self.status.setObjectName("muted")
        layout.addWidget(self.progress)
        layout.addWidget(self.status)

        action_row = QHBoxLayout()
        action_row.addStretch()
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel)
        self.start_button = QPushButton("Iniciar")
        self.start_button.setObjectName("primary")
        self.start_button.clicked.connect(self._start)
        action_row.addWidget(self.cancel_button)
        action_row.addWidget(self.start_button)
        layout.addLayout(action_row)

        self.setCentralWidget(root)
        self.setStyleSheet(
            """
            QMainWindow { background: palette(window); }
            QLabel#heading { font-size: 23px; font-weight: 650; }
            QLabel#muted { color: palette(mid); }
            QLabel#dropArea {
                border: 1px dashed palette(mid);
                border-radius: 8px;
                padding: 12px;
            }
            QFrame#panel { border: 1px solid palette(midlight); border-radius: 8px; }
            QPushButton { padding: 7px 12px; }
            QPushButton#primary { font-weight: 600; }
            QProgressBar { min-height: 12px; text-align: center; }
            """
        )

    def _choose_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar vídeo",
            "",
            "Vídeos (*.mp4 *.mkv *.avi *.mov *.webm *.m4v);;Todos os ficheiros (*)",
        )
        if path:
            self._set_video(path)

    def _choose_subtitles(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Selecionar legendas SRT", "", "Legendas SRT (*.srt)"
        )
        for path in paths:
            self.subtitle_table.add_subtitle(path)
        self._refresh_hard_tracks()

    def subtitle_table_remove(self) -> None:
        self.subtitle_table.remove_selected()
        self._refresh_hard_tracks()

    def _set_video(self, path: str) -> None:
        self.video_path = os.path.abspath(path)
        self.video_label.setText(self.video_path)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            if not url.isLocalFile():
                continue
            path = url.toLocalFile()
            suffix = Path(path).suffix.lower()
            if suffix == ".srt":
                self.subtitle_table.add_subtitle(path)
            elif suffix in VIDEO_EXTENSIONS:
                self._set_video(path)
        self._refresh_hard_tracks()
        event.acceptProposedAction()

    def _refresh_hard_tracks(self) -> None:
        current = self.hard_track_combo.currentData()
        self.hard_track_combo.clear()
        for row in range(self.subtitle_table.rowCount()):
            item = self.subtitle_table.item(row, 0)
            if item:
                self.hard_track_combo.addItem(item.text(), row)
        index = self.hard_track_combo.findData(current)
        if index >= 0:
            self.hard_track_combo.setCurrentIndex(index)

    def _update_mode_controls(self, *_args: object) -> None:
        is_hardsub = self.mode_combo.currentData() == "hardsub"
        self.container_combo.setEnabled(not is_hardsub)
        self.hard_controls.setVisible(is_hardsub)

    def _choose_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.font_color), self, "Cor da legenda")
        if color.isValid():
            self.font_color = color.name()
            self.color_button.setText(self.font_color.upper())
            self.color_button.setStyleSheet(
                f"background-color: {self.font_color}; color: "
                f"{'#000000' if color.lightness() > 128 else '#FFFFFF'}"
            )

    def _start(self) -> None:
        if not self.video_path:
            QMessageBox.warning(self, "Falta o vídeo", "Escolha ou arraste um vídeo.")
            return
        tracks = self.subtitle_table.tracks()
        if not tracks:
            QMessageBox.warning(
                self, "Faltam legendas", "Adicione pelo menos uma faixa SRT."
            )
            return

        mode: OperationMode = (
            "hardsub" if self.mode_combo.currentData() == "hardsub" else "softsub"
        )
        container = "mp4" if self.container_combo.currentData() == "mp4" else "mkv"
        output_path = default_output_path(self.video_path, mode, container)
        output_filter = (
            "MP4 (*.mp4)" if mode == "hardsub" or container == "mp4" else "MKV (*.mkv)"
        )
        output_path, _ = QFileDialog.getSaveFileName(
            self, "Guardar vídeo processado", output_path, output_filter
        )
        if not output_path:
            return
        expected_suffix = ".mp4" if mode == "hardsub" or container == "mp4" else ".mkv"
        if Path(output_path).suffix.lower() != expected_suffix:
            output_path = str(Path(output_path).with_suffix(expected_suffix))
        if os.path.exists(output_path):
            answer = QMessageBox.question(
                self,
                "Substituir ficheiro?",
                f"O ficheiro já existe:\n{output_path}\n\nQueres substituí-lo?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        options = EncodeOptions(
            video_path=self.video_path,
            subtitles=tracks,
            output_path=output_path,
            mode=mode,
            container=container,
            hard_subtitle_index=max(0, self.hard_track_combo.currentIndex()),
            font_size=self.font_size.value(),
            font_color=self.font_color,
            outline=self.outline.value(),
        )
        self.worker = EncodeWorker(options)
        self.worker.progress_changed.connect(self.progress.setValue)
        self.worker.succeeded.connect(self._succeeded)
        self.worker.failed.connect(self._failed)
        self.worker.cancelled.connect(self._cancelled)
        self.worker.finished.connect(self._worker_finished)
        self.progress.setValue(0)
        self.status.setText("A analisar e processar…")
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.worker.start()

    def _cancel(self) -> None:
        if self.worker:
            self.status.setText("A cancelar…")
            self.cancel_button.setEnabled(False)
            self.worker.cancel()

    def _succeeded(self, output_path: str) -> None:
        self.progress.setValue(100)
        self.status.setText(f"Concluído: {output_path}")
        QMessageBox.information(self, "Concluído", f"Vídeo guardado em:\n{output_path}")

    def _failed(self, message: str) -> None:
        self.status.setText("O processamento falhou.")
        QMessageBox.critical(self, "Erro no FFmpeg", message)

    def _cancelled(self) -> None:
        self.status.setText("Operação cancelada.")

    def _worker_finished(self) -> None:
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.worker = None

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.status.setText("A cancelar antes de fechar…")
            event.ignore()
            return
        event.accept()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="subfuse")
    parser.add_argument("--version", action="version", version=f"SubFuse {__version__}")
    parser.parse_args(argv)
    app = QApplication([sys.argv[0]])
    app.setApplicationName("SubFuse")
    app.setApplicationDisplayName(f"SubFuse {__version__}")
    icon = QIcon(str(_resource_path("assets/subfuse-icone.png")))
    app.setWindowIcon(icon)
    window = MainWindow()
    window.setWindowIcon(icon)
    window.setWindowTitle(f"SubFuse {__version__} — Embutir legendas")
    window.show()
    return app.exec()
