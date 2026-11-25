import sys
import io
from pathlib import Path

from PIL import Image, ImageOps
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QFileDialog, QProgressBar,
    QSpinBox, QGroupBox, QMessageBox, QAbstractItemView, QFrame
)

TARGET_KB = 100
SOFT_KB = 120
MAX_KB = 150


def format_size(n):
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.2f} MB"


def encode_jpeg(img, quality, optimize=True):
    buf = io.BytesIO()
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.save(buf, "JPEG", quality=quality, optimize=optimize, progressive=True)
    return buf.getvalue()


def compress_image(src: Path, dst: Path, target_bytes: int, max_bytes: int):
    soft_bytes = min(120 * 1024, max_bytes)

    with Image.open(src) as opened:
        img = ImageOps.exif_transpose(opened)
        original_format = (opened.format or src.suffix.lstrip(".")).upper()
        if original_format == "JPG":
            original_format = "JPEG"

        if original_format == "JPEG":
            # Try the requested target first, then the preferred 120 KB band,
            # and finally the hard maximum. At each stage keep the best quality.
            candidates = []
            lo, hi = 35, 95
            while lo <= hi:
                q = (lo + hi) // 2
                data = encode_jpeg(img.copy(), q)
                if len(data) <= max_bytes:
                    candidates.append((q, data))
                    lo = q + 1
                else:
                    hi = q - 1

            fitting = [(q, data) for q, data in candidates if len(data) <= target_bytes]
            if fitting:
                quality, best = max(fitting, key=lambda item: item[0])
                note = f"Target met • quality {quality}"
            else:
                fitting = [(q, data) for q, data in candidates if len(data) <= soft_bytes]
                if fitting:
                    quality, best = max(fitting, key=lambda item: item[0])
                    note = f"Within 120 KB band • quality {quality}"
                elif candidates:
                    quality, best = max(candidates, key=lambda item: item[0])
                    note = f"Within maximum • quality {quality}"
                else:
                    best = encode_jpeg(img.copy(), 35)
                    note = "Could not reach maximum without resizing"

            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(best)
            return len(best), note

        if original_format == "PNG":
            # Lossless optimization only. Never quantize or discard colors.
            buf = io.BytesIO()
            img.save(buf, "PNG", optimize=True, compress_level=9)
            data = buf.getvalue()
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(data)
            if len(data) <= target_bytes:
                note = "Target met • lossless"
            elif len(data) <= soft_bytes:
                note = "Within 120 KB band • lossless"
            elif len(data) <= max_bytes:
                note = "Within maximum • lossless"
            else:
                note = "PNG cannot reach limit losslessly"
            return len(data), note

        raise ValueError("Unsupported image format")


class Worker(QThread):
    progress = Signal(int)
    item_done = Signal(int, str, str)
    finished_all = Signal()

    def __init__(self, files, output_dir, target_kb, max_kb):
        super().__init__()
        self.files = files
        self.output_dir = Path(output_dir)
        self.target_bytes = target_kb * 1024
        self.max_bytes = max_kb * 1024

    def run(self):
        total = len(self.files)
        for i, src in enumerate(self.files):
            try:
                src = Path(src)
                out = self.output_dir / src.name
                # Avoid overwriting an earlier output with the same name.
                if out.exists():
                    out = self.output_dir / f"{src.stem}_compressed{src.suffix}"
                size, note = compress_image(src, out, self.target_bytes, self.max_bytes)
                self.item_done.emit(i, format_size(size), note)
            except Exception as e:
                self.item_done.emit(i, "Failed", str(e))
            self.progress.emit(int((i + 1) * 100 / total))
        self.finished_all.emit()


class DropList(QListWidget):
    files_dropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        paths = [u.toLocalFile() for u in event.mimeData().urls()]
        self.files_dropped.emit(paths)
        event.acceptProposedAction()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Compressor")
        self.setMinimumSize(760, 620)
        self.files = []
        self.worker = None
        self._build_ui()
        self.setAcceptDrops(True)

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title = QLabel("Image Compressor")
        title.setObjectName("title")
        subtitle = QLabel("Compress JPG and PNG images in batches")
        subtitle.setObjectName("subtitle")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch()
        badge = QLabel("OFFLINE")
        badge.setObjectName("badge")
        header.addWidget(badge, alignment=Qt.AlignTop)
        layout.addLayout(header)

        drop = QFrame()
        drop.setObjectName("dropArea")
        drop_layout = QVBoxLayout(drop)
        drop_layout.setContentsMargins(18, 20, 18, 20)
        drop_layout.setSpacing(8)
        drop_icon = QLabel("＋")
        drop_icon.setObjectName("dropIcon")
        drop_icon.setAlignment(Qt.AlignCenter)
        drop_text = QLabel("Drop images here")
        drop_text.setObjectName("dropText")
        drop_text.setAlignment(Qt.AlignCenter)
        drop_hint = QLabel("or choose files from your computer  •  JPG, JPEG, PNG")
        drop_hint.setObjectName("subtitle")
        drop_hint.setAlignment(Qt.AlignCenter)
        self.add_btn = QPushButton("Browse Images")
        self.add_btn.setObjectName("secondaryButton")
        self.add_btn.clicked.connect(self.choose_files)
        drop_layout.addWidget(drop_icon)
        drop_layout.addWidget(drop_text)
        drop_layout.addWidget(drop_hint)
        drop_layout.addWidget(self.add_btn, alignment=Qt.AlignCenter)
        layout.addWidget(drop)

        list_header = QHBoxLayout()
        list_label = QLabel("Selected images")
        list_label.setObjectName("sectionTitle")
        self.count_label = QLabel("0 files")
        self.count_label.setObjectName("subtitle")
        list_header.addWidget(list_label)
        list_header.addStretch()
        list_header.addWidget(self.count_label)
        layout.addLayout(list_header)

        self.list_widget = DropList()
        self.list_widget.setObjectName("fileList")
        self.list_widget.setMinimumHeight(190)
        self.list_widget.files_dropped.connect(self.add_files)
        layout.addWidget(self.list_widget, 1)

        controls = QGroupBox("Compression settings")
        controls.setObjectName("settings")
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(16, 18, 16, 14)
        controls_layout.addWidget(QLabel("Target size"))
        self.target_spin = QSpinBox()
        self.target_spin.setRange(30, 5000)
        self.target_spin.setValue(TARGET_KB)
        self.target_spin.setSuffix(" KB")
        controls_layout.addWidget(self.target_spin)
        controls_layout.addSpacing(18)
        controls_layout.addWidget(QLabel("Maximum allowed"))
        self.max_spin = QSpinBox()
        self.max_spin.setRange(50, 10000)
        self.max_spin.setValue(MAX_KB)
        self.max_spin.setSuffix(" KB")
        controls_layout.addWidget(self.max_spin)
        controls_layout.addStretch()
        self.clear_btn = QPushButton("Clear list")
        self.clear_btn.setObjectName("textButton")
        self.clear_btn.clicked.connect(self.clear_files)
        controls_layout.addWidget(self.clear_btn)
        layout.addWidget(controls)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        layout.addWidget(self.progress)

        footer = QHBoxLayout()
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("subtitle")
        footer.addWidget(self.status_label)
        footer.addStretch()
        self.compress_btn = QPushButton("Compress Images")
        self.compress_btn.setObjectName("primaryButton")
        self.compress_btn.setMinimumWidth(190)
        self.compress_btn.clicked.connect(self.start_compression)
        footer.addWidget(self.compress_btn)
        layout.addLayout(footer)

        self.setCentralWidget(root)
        self.setStyleSheet("""
            QWidget#root { background: #10141d; color: #e8edf5; font-family: "Segoe UI"; font-size: 10pt; }
            QLabel#title { font-size: 23pt; font-weight: 700; color: #f4f7fb; }
            QLabel#subtitle { color: #98a4b5; font-size: 9pt; }
            QLabel#badge { color: #6ee7b7; background: #12352e; border: 1px solid #1d5948; border-radius: 9px; padding: 5px 10px; font-size: 8pt; font-weight: 700; }
            QFrame#dropArea { background: #171e2a; border: 2px dashed #3b4a60; border-radius: 14px; }
            QLabel#dropIcon { color: #7c9cff; font-size: 28pt; }
            QLabel#dropText { color: #f4f7fb; font-size: 14pt; font-weight: 600; }
            QLabel#sectionTitle { font-size: 12pt; font-weight: 600; }
            QListWidget#fileList { background: #171e2a; border: 1px solid #2b3545; border-radius: 12px; padding: 7px; outline: 0; }
            QListWidget#fileList::item { padding: 10px; border-bottom: 1px solid #273142; }
            QGroupBox#settings { border: 1px solid #2b3545; border-radius: 12px; margin-top: 8px; padding-top: 10px; color: #cbd5e1; font-weight: 600; }
            QGroupBox#settings::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
            QSpinBox { background: #202a39; border: 1px solid #3a475a; border-radius: 7px; padding: 7px; min-width: 85px; color: white; }
            QPushButton { border: 0; border-radius: 8px; padding: 10px 16px; font-weight: 600; }
            QPushButton#primaryButton { background: #5578f6; color: white; }
            QPushButton#primaryButton:hover { background: #6b89ff; }
            QPushButton#primaryButton:disabled { background: #38445e; color: #8793a8; }
            QPushButton#secondaryButton { background: #263449; color: #dce6f7; border: 1px solid #40516b; }
            QPushButton#secondaryButton:hover { background: #30425c; }
            QPushButton#textButton { background: transparent; color: #aab7ca; }
            QPushButton#textButton:hover { color: white; background: #263449; }
            QProgressBar { background: #202a39; border: 0; border-radius: 6px; height: 10px; text-align: center; color: #dce6f7; }
            QProgressBar::chunk { background: #5578f6; border-radius: 6px; }
        """)

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Choose images", "", "Images (*.jpg *.jpeg *.png)"
        )
        self.add_files(paths)

    def add_files(self, paths):
        valid = []
        for p in paths:
            path = Path(p)
            if path.is_file() and path.suffix.lower() in (".jpg", ".jpeg", ".png"):
                if str(path) not in self.files:
                    self.files.append(str(path))
                    valid.append(path)
        for path in valid:
            try:
                size = format_size(path.stat().st_size)
            except OSError:
                size = "Unknown size"
            item = QListWidgetItem(f"  {path.name}     •     {size}     →     Waiting")
            item.setToolTip(str(path))
            self.list_widget.addItem(item)
        self.count_label.setText(f"{len(self.files)} files")
        self.status_label.setText(f"{len(self.files)} image(s) ready")

    def clear_files(self):
        if self.worker and self.worker.isRunning():
            return
        self.files.clear()
        self.list_widget.clear()
        self.count_label.setText("0 files")
        self.progress.setValue(0)
        self.status_label.setText("Ready")

    def start_compression(self):
        if not self.files:
            QMessageBox.information(self, "No images", "Add at least one JPG or PNG image first.")
            return
        target = self.target_spin.value()
        maximum = self.max_spin.value()
        if maximum < target:
            QMessageBox.warning(self, "Invalid settings", "Maximum allowed size must be equal to or greater than target size.")
            return

        output_dir = QFileDialog.getExistingDirectory(self, "Choose output folder")
        if not output_dir:
            return

        self.compress_btn.setEnabled(False)
        self.add_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self.progress.setValue(0)
        self.status_label.setText("Compressing...")
        self.worker = Worker(self.files, output_dir, target, maximum)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.item_done.connect(self.update_item)
        self.worker.finished_all.connect(self.compression_finished)
        self.worker.start()

    def update_item(self, index, size, note):
        item = self.list_widget.item(index)
        if item:
            name = Path(self.files[index]).name
            item.setText(f"  {name}     •     {size}     •     {note}")

    def compression_finished(self):
        self.compress_btn.setEnabled(True)
        self.add_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)
        self.status_label.setText("Finished — check the output folder")
        QMessageBox.information(self, "Done", "Image processing is complete.\nCheck the output folder for the results.")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.add_files([u.toLocalFile() for u in event.mimeData().urls()])
        event.acceptProposedAction()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
