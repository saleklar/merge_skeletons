"""
Spine Batch PNG-Sequence Exporter
Calls the Spine CLI (spine.exe / Spine.app) for each project file.

Spine CLI reference:
  Spine -i <input.spine> -o <output_dir> -e <export_settings.json>
  Spine -i <input.spine> -o <output_dir> -e png --exportFps 25 --exportScale 1

Usage: python spine_batch_export.py
"""
import sys
import os
import json
import subprocess
import tempfile

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog,
    QGroupBox, QTextEdit, QFrame, QSpinBox,
    QDoubleSpinBox, QCheckBox, QListWidget, QListWidgetItem,
    QAbstractItemView, QSizePolicy
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QColor

# ─────────────────────────────────────────────
STYLE = """
QWidget {
    background: #1e1e2e;
    color: #cdd6f4;
    font-family: Segoe UI;
    font-size: 13px;
}
QGroupBox {
    border: 1px solid #45475a;
    border-radius: 6px;
    margin-top: 10px;
    padding: 8px;
    color: #89b4fa;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QLineEdit, QSpinBox, QDoubleSpinBox {
    background: #313244;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px 8px;
    color: #cdd6f4;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus { border: 1px solid #89b4fa; }
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width: 16px; }
QPushButton {
    background: #313244;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px 12px;
    color: #cdd6f4;
}
QPushButton:hover { background: #45475a; }
QPushButton#run_btn {
    background: #89b4fa;
    color: #1e1e2e;
    font-weight: bold;
    padding: 7px 24px;
    font-size: 14px;
    border-radius: 6px;
}
QPushButton#run_btn:hover { background: #b4befe; }
QPushButton#run_btn:disabled { background: #45475a; color: #6c7086; }
QListWidget {
    background: #181825;
    border: 1px solid #45475a;
    border-radius: 4px;
    color: #cdd6f4;
}
QListWidget::item:selected { background: #313244; }
QTextEdit {
    background: #181825;
    border: 1px solid #45475a;
    border-radius: 4px;
    color: #a6e3a1;
    font-family: Consolas;
    font-size: 12px;
    padding: 6px;
}
QCheckBox { spacing: 6px; }
QFrame[frameShape="4"] { color: #45475a; }
"""


# ─────────────────────────────────────────────
# Worker thread — runs Spine CLI jobs one by one
# ─────────────────────────────────────────────
class ExportWorker(QThread):
    progress = Signal(str, str)   # (message, color)
    finished = Signal()

    def __init__(self, spine_exe, jobs, fps, scale, anim_filter, output_subdir):
        super().__init__()
        self.spine_exe    = spine_exe
        self.jobs         = jobs          # list of (spine_file, output_dir)
        self.fps          = fps
        self.scale        = scale
        self.anim_filter  = anim_filter.strip()
        self.output_subdir = output_subdir

    def run(self):
        total = len(self.jobs)
        for idx, (spine_file, out_dir) in enumerate(self.jobs, 1):
            name = os.path.basename(spine_file)
            self.progress.emit(f"[{idx}/{total}] Exporting {name} …", "#89b4fa")

            os.makedirs(out_dir, exist_ok=True)

            # Build export settings JSON for png sequence
            settings = {
                "class": "pngexport",
                "name":  "",          # all animations
                "fps":   self.fps,
                "scale": self.scale,
                "premultipliedAlpha": False,
            }
            if self.anim_filter:
                settings["name"] = self.anim_filter

            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.json', delete=False, encoding='utf-8'
            ) as tf:
                json.dump(settings, tf)
                settings_path = tf.name

            try:
                cmd = [
                    self.spine_exe,
                    '-i', spine_file,
                    '-o', out_dir,
                    '-e', settings_path,
                ]
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                if result.returncode == 0:
                    self.progress.emit(f"  ✓ Done → {out_dir}", "#a6e3a1")
                else:
                    err = (result.stderr or result.stdout or "unknown error").strip()
                    self.progress.emit(f"  ✗ FAILED: {err}", "#f38ba8")
            except subprocess.TimeoutExpired:
                self.progress.emit(f"  ✗ TIMEOUT after 5 min", "#f38ba8")
            except FileNotFoundError:
                self.progress.emit(
                    f"  ✗ Spine executable not found: {self.spine_exe}", "#f38ba8"
                )
                break
            except Exception as e:
                self.progress.emit(f"  ✗ ERROR: {e}", "#f38ba8")
            finally:
                try:
                    os.unlink(settings_path)
                except Exception:
                    pass

        self.progress.emit("─── All done ───", "#6c7086")
        self.finished.emit()


# ─────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────
class BatchExportUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Spine Batch PNG Exporter")
        self.setMinimumWidth(720)
        self._build()
        self.setStyleSheet(STYLE)
        self._worker = None

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(16, 16, 16, 16)

        # ── Spine executable ──────────────────────────────────────
        exe_box = QGroupBox("Spine Executable")
        exe_layout = QHBoxLayout(exe_box)
        lbl_exe = QLabel("Spine path:")
        lbl_exe.setFixedWidth(90)
        lbl_exe.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.exe_edit = QLineEdit()
        self.exe_edit.setPlaceholderText(
            r"e.g.  C:\Program Files\Spine\Spine.exe   or   /Applications/Spine.app/Contents/MacOS/Spine"
        )
        btn_exe = QPushButton("Browse")
        btn_exe.setFixedWidth(70)
        btn_exe.clicked.connect(self._browse_exe)
        exe_layout.addWidget(lbl_exe)
        exe_layout.addWidget(self.exe_edit)
        exe_layout.addWidget(btn_exe)
        root.addWidget(exe_box)

        # ── Project files ─────────────────────────────────────────
        proj_box = QGroupBox("Spine Projects  (.spine files)")
        proj_layout = QVBoxLayout(proj_box)
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.file_list.setMinimumHeight(120)
        self.file_list.setAcceptDrops(True)
        self.file_list.setDragDropMode(QAbstractItemView.DragDrop)
        proj_layout.addWidget(self.file_list)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("Add files…")
        btn_add.clicked.connect(self._add_files)
        btn_add_dir = QPushButton("Add folder…")
        btn_add_dir.clicked.connect(self._add_folder)
        btn_rem = QPushButton("Remove selected")
        btn_rem.clicked.connect(self._remove_selected)
        btn_clr = QPushButton("Clear all")
        btn_clr.clicked.connect(self.file_list.clear)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_add_dir)
        btn_row.addWidget(btn_rem)
        btn_row.addWidget(btn_clr)
        btn_row.addStretch()
        proj_layout.addLayout(btn_row)
        root.addWidget(proj_box)

        # ── Output ────────────────────────────────────────────────
        out_box = QGroupBox("Output")
        out_layout = QVBoxLayout(out_box)

        self.chk_same_dir = QCheckBox(
            "Export next to each project file  (creates a sub-folder per project)"
        )
        self.chk_same_dir.setChecked(True)
        self.chk_same_dir.toggled.connect(self._on_same_dir_toggled)
        out_layout.addWidget(self.chk_same_dir)

        custom_row = QHBoxLayout()
        self.lbl_custom = QLabel("Output folder:")
        self.lbl_custom.setFixedWidth(110)
        self.lbl_custom.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("Common root output folder")
        btn_out = QPushButton("Browse")
        btn_out.setFixedWidth(70)
        btn_out.clicked.connect(self._browse_out)
        custom_row.addWidget(self.lbl_custom)
        custom_row.addWidget(self.out_edit)
        custom_row.addWidget(btn_out)
        out_layout.addLayout(custom_row)

        subdir_row = QHBoxLayout()
        lbl_sub = QLabel("Sub-folder name:")
        lbl_sub.setFixedWidth(110)
        lbl_sub.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.subdir_edit = QLineEdit("export")
        self.subdir_edit.setMaximumWidth(160)
        lbl_sub_hint = QLabel("appended to the output path for each project")
        lbl_sub_hint.setStyleSheet("color: #6c7086; font-size: 11px;")
        subdir_row.addWidget(lbl_sub)
        subdir_row.addWidget(self.subdir_edit)
        subdir_row.addSpacing(8)
        subdir_row.addWidget(lbl_sub_hint)
        subdir_row.addStretch()
        out_layout.addLayout(subdir_row)
        root.addWidget(out_box)
        self._on_same_dir_toggled(True)

        # ── Export settings ───────────────────────────────────────
        cfg_box = QGroupBox("Export Settings")
        cfg_layout = QHBoxLayout(cfg_box)

        lbl_fps = QLabel("FPS:")
        lbl_fps.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(1, 120)
        self.fps_spin.setValue(25)
        self.fps_spin.setFixedWidth(64)

        lbl_scale = QLabel("Scale:")
        lbl_scale.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(0.1, 4.0)
        self.scale_spin.setSingleStep(0.25)
        self.scale_spin.setValue(1.0)
        self.scale_spin.setFixedWidth(70)

        lbl_anim = QLabel("Animation filter:")
        lbl_anim.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.anim_edit = QLineEdit()
        self.anim_edit.setPlaceholderText("leave empty = all animations")
        self.anim_edit.setMaximumWidth(200)

        cfg_layout.addWidget(lbl_fps)
        cfg_layout.addWidget(self.fps_spin)
        cfg_layout.addSpacing(16)
        cfg_layout.addWidget(lbl_scale)
        cfg_layout.addWidget(self.scale_spin)
        cfg_layout.addSpacing(16)
        cfg_layout.addWidget(lbl_anim)
        cfg_layout.addWidget(self.anim_edit)
        cfg_layout.addStretch()
        root.addWidget(cfg_box)

        # ── Run ───────────────────────────────────────────────────
        run_row = QHBoxLayout()
        run_row.addStretch()
        self.run_btn = QPushButton("Export All")
        self.run_btn.setObjectName("run_btn")
        self.run_btn.setFixedWidth(130)
        self.run_btn.clicked.connect(self._run)
        run_row.addWidget(self.run_btn)
        root.addLayout(run_row)

        # ── Log ───────────────────────────────────────────────────
        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        root.addWidget(sep)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(140)
        root.addWidget(self.log)

    # ── helpers ──────────────────────────────────────────────────
    def _on_same_dir_toggled(self, checked):
        self.lbl_custom.setEnabled(not checked)
        self.out_edit.setEnabled(not checked)

    def _browse_exe(self):
        path, _ = QFileDialog.getOpenFileName(self, "Locate Spine executable", "", "Executables (*.exe);;All Files (*)")
        if path:
            self.exe_edit.setText(os.path.normpath(path))

    def _browse_out(self):
        path = QFileDialog.getExistingDirectory(self, "Select output folder", self.out_edit.text() or "")
        if path:
            self.out_edit.setText(os.path.normpath(path))

    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add Spine projects", "", "Spine Files (*.spine)"
        )
        self._add_paths(paths)

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Add folder (scans for *.spine)")
        if not folder:
            return
        found = []
        for root_dir, _, files in os.walk(folder):
            for f in files:
                if f.endswith('.spine'):
                    found.append(os.path.join(root_dir, f))
        self._add_paths(found)

    def _add_paths(self, paths):
        existing = {self.file_list.item(i).text() for i in range(self.file_list.count())}
        for p in paths:
            p = os.path.normpath(p)
            if p not in existing:
                self.file_list.addItem(p)
                existing.add(p)

    def _remove_selected(self):
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))

    def _log(self, msg, color="#a6e3a1"):
        self.log.append(f'<span style="color:{color};">{msg}</span>')

    # ── run ──────────────────────────────────────────────────────
    def _run(self):
        spine_exe = self.exe_edit.text().strip()
        if not spine_exe:
            self._log("ERROR: Set the Spine executable path.", "#f38ba8"); return
        if not os.path.isfile(spine_exe):
            self._log(f"ERROR: Spine executable not found: {spine_exe}", "#f38ba8"); return

        count = self.file_list.count()
        if count == 0:
            self._log("ERROR: Add at least one .spine file.", "#f38ba8"); return

        subdir = self.subdir_edit.text().strip() or "export"
        jobs = []
        for i in range(count):
            spine_file = self.file_list.item(i).text()
            if self.chk_same_dir.isChecked():
                out_dir = os.path.join(os.path.dirname(spine_file), subdir)
            else:
                custom = self.out_edit.text().strip()
                if not custom:
                    self._log("ERROR: Set a custom output folder or enable 'export next to project'.", "#f38ba8")
                    return
                proj_name = os.path.splitext(os.path.basename(spine_file))[0]
                out_dir = os.path.join(custom, proj_name, subdir)
            jobs.append((spine_file, out_dir))

        self.log.clear()
        self._log(f"Starting batch export — {count} project(s)", "#fab387")
        self.run_btn.setEnabled(False)

        self._worker = ExportWorker(
            spine_exe=spine_exe,
            jobs=jobs,
            fps=self.fps_spin.value(),
            scale=self.scale_spin.value(),
            anim_filter=self.anim_edit.text(),
            output_subdir=subdir,
        )
        self._worker.progress.connect(self._log)
        self._worker.finished.connect(lambda: self.run_btn.setEnabled(True))
        self._worker.start()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = BatchExportUI()
    win.show()
    sys.exit(app.exec())
