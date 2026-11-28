import sys
import io
import tempfile
from pathlib import Path

from PIL import Image, ImageOps
from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import (
    QFont, QDragEnterEvent, QDropEvent, QPainter, QColor, QLinearGradient,
    QPixmap, QBrush, QPen, QPainterPath,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QFileDialog, QProgressBar,
    QSpinBox, QMessageBox, QAbstractItemView, QFrame, QGraphicsDropShadowEffect,
    QScrollArea, QSizePolicy,
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


# ---------------------------------------------------------------------------
# Visual helpers
# ---------------------------------------------------------------------------

def add_shadow(widget, blur=34, y=10, alpha=150, color="#050810"):
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y)
    c = QColor(color)
    c.setAlpha(alpha)
    effect.setColor(c)
    widget.setGraphicsEffect(effect)
    return effect


class Backdrop(QWidget):
    """Paints a soft aurora gradient that the glass panels sit on top of."""

    def __init__(self):
        super().__init__()
        self.setObjectName("root")
        self._cache = None

    def resizeEvent(self, event):
        self._cache = None
        super().resizeEvent(event)

    def _render(self):
        w = max(self.width(), 1)
        h = max(self.height(), 1)
        pm = QPixmap(w, h)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)

        # Flat, pure black backdrop with only a barely-there top sheen.
        base = QLinearGradient(0, 0, 0, h)
        base.setColorAt(0.0, QColor("#080808"))
        base.setColorAt(0.45, QColor("#020202"))
        base.setColorAt(1.0, QColor("#000000"))
        p.fillRect(0, 0, w, h, QBrush(base))

        p.end()
        return pm

    def paintEvent(self, event):
        if self._cache is None or self._cache.size() != self.size():
            self._cache = self._render()
        p = QPainter(self)
        p.drawPixmap(0, 0, self._cache)


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


class FileRow(QWidget):
    """A glass pill row used inside the file list."""

    def __init__(self, name, meta, tooltip=""):
        super().__init__()
        self.setObjectName("fileRow")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 11, 14, 11)
        lay.setSpacing(12)

        self.name_label = QLabel(name)
        self.name_label.setObjectName("rowName")
        self.name_label.setToolTip(tooltip or name)

        self.meta_label = QLabel(meta)
        self.meta_label.setObjectName("rowMeta")

        self.status_label = QLabel("Waiting")
        self.status_label.setObjectName("rowStatus")
        self.status_label.setProperty("kind", "neutral")

        lay.addWidget(self.name_label, 1)
        lay.addWidget(self.meta_label)
        lay.addWidget(self.status_label)

    def set_status(self, text, kind="neutral"):
        self.status_label.setText(text)
        self.status_label.setProperty("kind", kind)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)


def _arrow_pixmap(color, up=True, size=10):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor(color))
    pen.setWidthF(1.8)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    path = QPainterPath()
    if up:
        path.moveTo(1.5, size - 3.0)
        path.lineTo(size / 2, 3.0)
        path.lineTo(size - 1.5, size - 3.0)
    else:
        path.moveTo(1.5, 3.0)
        path.lineTo(size / 2, size - 3.0)
        path.lineTo(size - 1.5, 3.0)
    p.drawPath(path)
    p.end()
    return pm


def _write_arrow_assets(folder):
    folder.mkdir(parents=True, exist_ok=True)
    up = folder / "arrow_up.png"
    down = folder / "arrow_down.png"
    _arrow_pixmap("#cfcfcf", True).save(str(up))
    _arrow_pixmap("#cfcfcf", False).save(str(down))
    return up, down


def _status_kind(note):
    low = note.lower()
    if "failed" in low or "cannot" in low or "unsupported" in low:
        return "error"
    if "target met" in low:
        return "ok"
    if "within" in low:
        return "info"
    if "could not" in low:
        return "warn"
    return "neutral"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Compressor")
        self.setMinimumSize(820, 560)
        self.files = []
        self.rows = []
        self.worker = None
        self._build_ui()
        self.setAcceptDrops(True)

    def _build_ui(self):
        backdrop = Backdrop()
        outer = QVBoxLayout(backdrop)
        outer.setContentsMargins(30, 26, 30, 26)
        outer.setSpacing(16)

        # Header stays fixed at the top.
        header = QHBoxLayout()
        header.setSpacing(14)

        mark = QLabel("IMG")
        mark.setObjectName("logoMark")
        mark.setFixedSize(52, 52)
        mark.setAlignment(Qt.AlignCenter)
        header.addWidget(mark)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Image Compressor")
        title.setObjectName("title")
        subtitle = QLabel("Batch compress JPG & PNG — fast, quiet, fully offline")
        subtitle.setObjectName("subtitle")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch()

        badge = QLabel("●  OFFLINE")
        badge.setObjectName("badge")
        header.addWidget(badge, alignment=Qt.AlignTop)
        outer.addLayout(header)

        # The middle section scrolls when the window is short.
        scroll = QScrollArea()
        scroll.setObjectName("scroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        root = QWidget()
        root.setObjectName("content")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.setSpacing(13)

        # --- Drop zone ---------------------------------------------------
        drop = QFrame()
        drop.setObjectName("dropArea")
        drop_layout = QVBoxLayout(drop)
        drop_layout.setContentsMargins(18, 20, 18, 20)
        drop_layout.setSpacing(4)

        drop_icon = QLabel("＋")
        drop_icon.setObjectName("dropIcon")
        drop_icon.setFixedSize(56, 56)
        drop_icon.setAlignment(Qt.AlignCenter)

        drop_text = QLabel("Drop your images here")
        drop_text.setObjectName("dropText")
        drop_text.setAlignment(Qt.AlignCenter)
        drop_hint = QLabel("or browse from your computer   ·   JPG, JPEG, PNG")
        drop_hint.setObjectName("subtitle")
        drop_hint.setAlignment(Qt.AlignCenter)

        self.add_btn = QPushButton("Browse Images")
        self.add_btn.setObjectName("secondaryButton")
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.clicked.connect(self.choose_files)

        icon_wrap = QHBoxLayout()
        icon_wrap.addStretch()
        icon_wrap.addWidget(drop_icon)
        icon_wrap.addStretch()

        btn_wrap = QHBoxLayout()
        btn_wrap.addStretch()
        btn_wrap.addWidget(self.add_btn)
        btn_wrap.addStretch()

        drop_layout.addLayout(icon_wrap)
        drop_layout.addWidget(drop_text)
        drop_layout.addWidget(drop_hint)
        drop_layout.addSpacing(6)
        drop_layout.addLayout(btn_wrap)
        # Let the box size itself to its contents so nothing is ever squeezed.
        drop.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        add_shadow(drop, blur=40, y=14, alpha=150)
        layout.addWidget(drop)

        # --- List header -------------------------------------------------
        list_header = QHBoxLayout()
        list_label = QLabel("Selected images")
        list_label.setObjectName("sectionTitle")
        self.count_label = QLabel("0 files")
        self.count_label.setObjectName("pill")
        list_header.addWidget(list_label)
        list_header.addStretch()
        list_header.addWidget(self.count_label)
        layout.addLayout(list_header)

        self.list_widget = DropList()
        self.list_widget.setObjectName("fileList")
        self.list_widget.setMinimumHeight(128)
        self.list_widget.setSelectionMode(QAbstractItemView.NoSelection)
        self.list_widget.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list_widget.files_dropped.connect(self.add_files)
        layout.addWidget(self.list_widget, 1)

        # --- Settings card ----------------------------------------------
        controls = QFrame()
        controls.setObjectName("card")
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(20, 16, 20, 18)
        controls_layout.setSpacing(12)

        settings_title = QLabel("Compression settings")
        settings_title.setObjectName("cardTitle")
        controls_layout.addWidget(settings_title)

        row = QHBoxLayout()
        row.setSpacing(14)

        target_col = QVBoxLayout()
        target_col.setSpacing(5)
        target_label = QLabel("Target size")
        target_label.setObjectName("fieldLabel")
        self.target_spin = QSpinBox()
        self.target_spin.setRange(30, 5000)
        self.target_spin.setValue(TARGET_KB)
        self.target_spin.setSuffix(" KB")
        target_col.addWidget(target_label)
        target_col.addWidget(self.target_spin)

        max_col = QVBoxLayout()
        max_col.setSpacing(5)
        max_label = QLabel("Maximum allowed")
        max_label.setObjectName("fieldLabel")
        self.max_spin = QSpinBox()
        self.max_spin.setRange(50, 10000)
        self.max_spin.setValue(MAX_KB)
        self.max_spin.setSuffix(" KB")
        max_col.addWidget(max_label)
        max_col.addWidget(self.max_spin)

        row.addLayout(target_col)
        row.addLayout(max_col)
        row.addStretch()

        self.clear_btn = QPushButton("Clear list")
        self.clear_btn.setObjectName("textButton")
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.clicked.connect(self.clear_files)
        row.addWidget(self.clear_btn, alignment=Qt.AlignBottom)

        controls_layout.addLayout(row)
        add_shadow(controls, blur=30, y=10, alpha=120)
        layout.addWidget(controls)

        # --- Progress ----------------------------------------------------
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFixedHeight(12)

        # --- Footer ------------------------------------------------------
        footer = QHBoxLayout()
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("subtitle")
        footer.addWidget(self.status_label)
        footer.addStretch()

        self.compress_btn = QPushButton("Compress Images")
        self.compress_btn.setObjectName("primaryButton")
        self.compress_btn.setMinimumWidth(200)
        self.compress_btn.setMinimumHeight(46)
        self.compress_btn.setCursor(Qt.PointingHandCursor)
        self.compress_btn.clicked.connect(self.start_compression)
        add_shadow(self.compress_btn, blur=26, y=8, alpha=170, color="#000000")
        footer.addWidget(self.compress_btn)

        layout.addStretch()
        scroll.setWidget(root)

        outer.addWidget(scroll, 1)
        outer.addWidget(self.progress)
        outer.addLayout(footer)

        self.setCentralWidget(backdrop)
        up, down = _write_arrow_assets(Path(tempfile.gettempdir()) / "image_compressor_assets")
        css = STYLESHEET.replace("__ARROW_UP__", up.as_posix()).replace("__ARROW_DOWN__", down.as_posix())
        self.setStyleSheet(css)

    # --- actions ---------------------------------------------------------
    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Choose images", "", "Images (*.jpg *.jpeg *.png)"
        )
        self.add_files(paths)

    def add_files(self, paths):
        added = 0
        for p in paths:
            path = Path(p)
            if path.is_file() and path.suffix.lower() in (".jpg", ".jpeg", ".png"):
                if str(path) not in self.files:
                    self.files.append(str(path))
                    try:
                        size = format_size(path.stat().st_size)
                    except OSError:
                        size = "Unknown size"
                    self._add_row(path.name, size, str(path))
                    added += 1
        if added:
            self.count_label.setText(f"{len(self.files)} files")
            self.status_label.setText(f"{len(self.files)} image(s) ready")

    def _add_row(self, name, meta, tooltip):
        row = FileRow(name, meta, tooltip)
        item = QListWidgetItem()
        item.setSizeHint(QSize(0, row.sizeHint().height() + 6))
        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, row)
        self.rows.append(row)

    def clear_files(self):
        if self.worker and self.worker.isRunning():
            return
        self.files.clear()
        self.rows.clear()
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
        self.status_label.setText("Compressing…")
        self.worker = Worker(self.files, output_dir, target, maximum)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.item_done.connect(self.update_item)
        self.worker.finished_all.connect(self.compression_finished)
        self.worker.start()

    def update_item(self, index, size, note):
        if 0 <= index < len(self.rows):
            self.rows[index].meta_label.setText(size)
            self.rows[index].set_status(note, _status_kind(note))

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


STYLESHEET = """
QWidget#root {
    color: #ededed;
    font-family: "Segoe UI Variable Display", "Segoe UI", sans-serif;
    font-size: 10pt;
}
QWidget#content { background: transparent; }
QScrollArea#scroll { background: transparent; border: 0; }
QScrollArea#scroll > QWidget > QWidget { background: transparent; }
QScrollBar:vertical {
    background: transparent; width: 10px; margin: 4px 2px 4px 0;
}
QScrollBar::handle:vertical {
    background: rgba(255, 255, 255, 0.16); border-radius: 5px; min-height: 40px;
}
QScrollBar::handle:vertical:hover { background: rgba(255, 255, 255, 0.30); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

QLabel#logoMark {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #fafafa, stop:1 #c9c9c9);
    color: #0a0a0a;
    border-radius: 15px;
    font-size: 11pt;
    font-weight: 800;
    letter-spacing: 1px;
}

QLabel#title { font-size: 24pt; font-weight: 700; color: #ffffff; }
QLabel#subtitle { color: #8a8a8a; font-size: 9.5pt; }

QLabel#badge {
    color: #d8d8d8;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.18);
    border-radius: 12px;
    padding: 6px 13px;
    font-size: 8pt;
    font-weight: 700;
    letter-spacing: 1px;
}

QLabel#sectionTitle { font-size: 12.5pt; font-weight: 600; color: #f5f5f5; }

QLabel#pill {
    color: #c4c4c4;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 11px;
    padding: 4px 12px;
    font-size: 8.5pt;
    font-weight: 600;
}

/* Glass card */
QFrame#card {
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 18px;
}
QLabel#cardTitle { font-size: 11pt; font-weight: 600; color: #ededed; }
QLabel#fieldLabel { color: #8a8a8a; font-size: 8.5pt; font-weight: 600; }

/* Drop area */
QFrame#dropArea {
    background: rgba(255, 255, 255, 0.03);
    border: 2px dashed rgba(255, 255, 255, 0.30);
    border-radius: 22px;
}
QLabel#dropIcon {
    color: #f0f0f0;
    background: rgba(255, 255, 255, 0.07);
    border: 1px solid rgba(255, 255, 255, 0.22);
    border-radius: 28px;
    font-size: 26pt;
}
QLabel#dropText { color: #f7f7f7; font-size: 15pt; font-weight: 600; }

/* File list */
QListWidget#fileList {
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid rgba(255, 255, 255, 0.09);
    border-radius: 18px;
    padding: 8px;
    outline: 0;
}
QListWidget#fileList::item {
    background: transparent;
    border: 0;
    border-radius: 12px;
    margin: 3px 2px;
}
QListWidget#fileList::item:hover {
    background: rgba(255, 255, 255, 0.06);
}

QLabel#rowName { color: #f2f2f2; font-size: 10pt; font-weight: 600; }
QLabel#rowMeta { color: #8a8a8a; font-size: 9pt; }
QLabel#rowStatus {
    border-radius: 11px;
    padding: 5px 12px;
    font-size: 8.5pt;
    font-weight: 600;
    background: rgba(255, 255, 255, 0.06);
    color: #c4c4c4;
}
QLabel#rowStatus[kind="ok"]    { background: rgba(255, 255, 255, 0.16); color: #ffffff; }
QLabel#rowStatus[kind="info"]  { background: rgba(255, 255, 255, 0.10); color: #dcdcdc; }
QLabel#rowStatus[kind="warn"]  { background: rgba(255, 255, 255, 0.06); color: #b0b0b0; }
QLabel#rowStatus[kind="error"] { background: rgba(255, 255, 255, 0.04); color: #8f8f8f; }

/* Inputs */
QSpinBox {
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 11px;
    padding: 8px 10px;
    min-width: 92px;
    color: #f5f5f5;
    selection-background-color: #444444;
}
QSpinBox:hover { border: 1px solid rgba(255, 255, 255, 0.32); }
QSpinBox:focus { border: 1px solid rgba(255, 255, 255, 0.55); }
QSpinBox::up-button, QSpinBox::down-button {
    subcontrol-origin: border;
    width: 22px;
    background: transparent;
    border: 0;
}
QSpinBox::up-button { subcontrol-position: top right; margin: 4px 4px 0 0; }
QSpinBox::down-button { subcontrol-position: bottom right; margin: 0 4px 4px 0; }
QSpinBox::up-button:hover, QSpinBox::down-button:hover {
    background: rgba(255, 255, 255, 0.14);
    border-radius: 5px;
}
QSpinBox::up-arrow {
    image: url("__ARROW_UP__");
    width: 10px;
    height: 10px;
}
QSpinBox::down-arrow {
    image: url("__ARROW_DOWN__");
    width: 10px;
    height: 10px;
}

/* Buttons */
QPushButton { border: 0; border-radius: 12px; padding: 10px 18px; font-weight: 600; }

QPushButton#primaryButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ffffff, stop:1 #d0d0d0);
    color: #0a0a0a;
    font-size: 10.5pt;
    font-weight: 700;
}
QPushButton#primaryButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ffffff, stop:1 #e2e2e2);
}
QPushButton#primaryButton:pressed {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #d8d8d8, stop:1 #b4b4b4);
}
QPushButton#primaryButton:disabled {
    background: rgba(255, 255, 255, 0.08);
    color: #6f6f6f;
}

QPushButton#secondaryButton {
    background: rgba(255, 255, 255, 0.08);
    color: #f0f0f0;
    border: 1px solid rgba(255, 255, 255, 0.18);
}
QPushButton#secondaryButton:hover {
    background: rgba(255, 255, 255, 0.16);
    border: 1px solid rgba(255, 255, 255, 0.38);
}
QPushButton#secondaryButton:disabled { color: #6f6f6f; }

QPushButton#textButton {
    background: transparent;
    color: #9a9a9a;
}
QPushButton#textButton:hover {
    color: #ffffff;
    background: rgba(255, 255, 255, 0.08);
}
QPushButton#textButton:disabled { color: #565656; }

/* Progress */
QProgressBar {
    background: rgba(255, 255, 255, 0.06);
    border: 0;
    border-radius: 6px;
    text-align: center;
    color: #dcdcdc;
    font-size: 8pt;
    font-weight: 600;
}
QProgressBar::chunk {
    border-radius: 6px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #e8e8e8, stop:1 #9a9a9a);
}
"""


def _apply_dark_titlebar(window):
    """Ask Windows to render the native title bar in dark mode."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = int(window.winId())
        dwm = ctypes.windll.dwmapi
        value = ctypes.c_int(1)
        # 20 = DWMWA_USE_IMMERSIVE_DARK_MODE (Win10 2004+); 19 on older builds.
        for attr in (20, 19):
            res = dwm.DwmSetWindowAttribute(
                hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)
            )
            if res == 0:
                break
    except Exception:
        pass


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    pal = app.palette()
    pal.setColor(pal.ColorRole.Window, QColor("#0a0a0a"))
    pal.setColor(pal.ColorRole.WindowText, QColor("#ededed"))
    pal.setColor(pal.ColorRole.Base, QColor("#0f0f0f"))
    pal.setColor(pal.ColorRole.AlternateBase, QColor("#151515"))
    pal.setColor(pal.ColorRole.Text, QColor("#ededed"))
    pal.setColor(pal.ColorRole.Button, QColor("#1a1a1a"))
    pal.setColor(pal.ColorRole.ButtonText, QColor("#ededed"))
    pal.setColor(pal.ColorRole.ToolTipBase, QColor("#1a1a1a"))
    pal.setColor(pal.ColorRole.ToolTipText, QColor("#ededed"))
    pal.setColor(pal.ColorRole.Highlight, QColor("#3a3a3a"))
    pal.setColor(pal.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(pal)
    font = QFont("Segoe UI Variable Display", 10)
    if not font.exactMatch():
        font = QFont("Segoe UI", 10)
    app.setFont(font)
    window = MainWindow()
    window.show()
    _apply_dark_titlebar(window)
    sys.exit(app.exec())
