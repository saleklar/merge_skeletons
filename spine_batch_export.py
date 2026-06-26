"""
Spine Batch PNG-Sequence Exporter  —  per-project settings
Each row in the table has its own: Animation, FPS, Scale, Output dir.
Use "Set all rows" to push the global defaults to every row at once.

Spine CLI: Spine.exe -i <file> -o <outdir> -e <settings.json>
"""
import sys
import os
import json
import subprocess
import tempfile

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog,
    QGroupBox, QTextEdit, QFrame,
    QSpinBox, QDoubleSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView
)
from PySide6.QtCore import Qt, QThread, Signal

STYLE = """
QWidget { background:#1e1e2e; color:#cdd6f4; font-family:Segoe UI; font-size:13px; }
QGroupBox { border:1px solid #45475a; border-radius:6px; margin-top:10px; padding:8px; color:#89b4fa; font-weight:bold; }
QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 4px; }
QLineEdit,QSpinBox,QDoubleSpinBox { background:#313244; border:1px solid #45475a; border-radius:4px; padding:3px 6px; color:#cdd6f4; }
QLineEdit:focus,QSpinBox:focus,QDoubleSpinBox:focus { border:1px solid #89b4fa; }
QSpinBox::up-button,QSpinBox::down-button,QDoubleSpinBox::up-button,QDoubleSpinBox::down-button { width:14px; }
QPushButton { background:#313244; border:1px solid #45475a; border-radius:4px; padding:4px 12px; color:#cdd6f4; }
QPushButton:hover { background:#45475a; }
QPushButton#run_btn { background:#89b4fa; color:#1e1e2e; font-weight:bold; padding:7px 24px; font-size:14px; border-radius:6px; }
QPushButton#run_btn:hover { background:#b4befe; }
QPushButton#run_btn:disabled { background:#45475a; color:#6c7086; }
QTableWidget { background:#181825; border:1px solid #45475a; border-radius:4px; gridline-color:#313244; }
QTableWidget::item { padding:3px 6px; }
QTableWidget::item:selected { background:#313244; color:#cdd6f4; }
QHeaderView::section { background:#1e1e2e; color:#89b4fa; border:none; border-bottom:1px solid #45475a; padding:4px 6px; }
QTextEdit { background:#181825; border:1px solid #45475a; border-radius:4px; color:#a6e3a1; font-family:Consolas; font-size:12px; padding:6px; }
QFrame[frameShape="4"] { color:#45475a; }
"""

COL_FILE=0; COL_ANIM=1; COL_FPS=2; COL_SCALE=3; COL_OUTDIR=4
COLUMNS=["Spine file","Animation (empty=all)","FPS","Scale","Output dir (empty=next to file)"]


class ExportWorker(QThread):
    progress = Signal(int, str, str)
    finished = Signal()

    def __init__(self, spine_exe, jobs):
        super().__init__()
        self.spine_exe = spine_exe
        self.jobs = jobs

    def run(self):
        total = len(self.jobs)
        for job in self.jobs:
            row = job['row']
            name = os.path.basename(job['spine_file'])
            self.progress.emit(row, f"[{row+1}/{total}] Exporting {name} ...", "#89b4fa")
            os.makedirs(job['out_dir'], exist_ok=True)
            settings = {"class":"pngexport","name":job['anim'],"fps":job['fps'],"scale":job['scale'],"premultipliedAlpha":False}
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as tf:
                json.dump(settings, tf)
                sp = tf.name
            try:
                r = subprocess.run([self.spine_exe,'-i',job['spine_file'],'-o',job['out_dir'],'-e',sp], capture_output=True, text=True, timeout=300)
                if r.returncode == 0:
                    self.progress.emit(row, f"  OK -> {job['out_dir']}", "#a6e3a1")
                else:
                    self.progress.emit(row, f"  FAIL: {(r.stderr or r.stdout or 'error').strip()}", "#f38ba8")
            except subprocess.TimeoutExpired:
                self.progress.emit(row, "  TIMEOUT", "#f38ba8")
            except FileNotFoundError:
                self.progress.emit(row, f"  Spine not found: {self.spine_exe}", "#f38ba8"); break
            except Exception as e:
                self.progress.emit(row, f"  ERROR: {e}", "#f38ba8")
            finally:
                try: os.unlink(sp)
                except: pass
        self.progress.emit(-1, "--- All done ---", "#6c7086")
        self.finished.emit()


class BatchExportUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Spine Batch PNG Exporter  |  per-project settings")
        self.setMinimumWidth(940)
        self._build()
        self.setStyleSheet(STYLE)
        self._worker = None

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(10); root.setContentsMargins(16,16,16,16)

        # Spine exe
        exe_box = QGroupBox("Spine Executable")
        exe_row = QHBoxLayout(exe_box)
        exe_row.addWidget(QLabel("Path:"))
        self.exe_edit = QLineEdit(r"C:\Program Files\Spine\Spine.exe")
        btn_exe = QPushButton("Browse"); btn_exe.setFixedWidth(70); btn_exe.clicked.connect(self._browse_exe)
        exe_row.addWidget(self.exe_edit); exe_row.addWidget(btn_exe)
        root.addWidget(exe_box)

        # Global defaults
        def_box = QGroupBox('Global Defaults  —  edit here then click  "Set all rows"  to apply to every project')
        def_row = QHBoxLayout(def_box)
        def_row.addWidget(QLabel("Animation:"))
        self.def_anim = QLineEdit(); self.def_anim.setPlaceholderText("empty = all"); self.def_anim.setMaximumWidth(140)
        def_row.addWidget(self.def_anim); def_row.addSpacing(10)
        def_row.addWidget(QLabel("FPS:"))
        self.def_fps = QSpinBox(); self.def_fps.setRange(1,120); self.def_fps.setValue(25); self.def_fps.setFixedWidth(58)
        def_row.addWidget(self.def_fps); def_row.addSpacing(10)
        def_row.addWidget(QLabel("Scale:"))
        self.def_scale = QDoubleSpinBox(); self.def_scale.setRange(0.1,4.0); self.def_scale.setSingleStep(0.25); self.def_scale.setValue(1.0); self.def_scale.setFixedWidth(66)
        def_row.addWidget(self.def_scale); def_row.addSpacing(10)
        def_row.addWidget(QLabel("Output dir:"))
        self.def_outdir = QLineEdit(); self.def_outdir.setPlaceholderText("empty = subfolder next to each .spine file")
        btn_bo = QPushButton("..."); btn_bo.setFixedWidth(26); btn_bo.clicked.connect(self._browse_def_out)
        def_row.addWidget(self.def_outdir); def_row.addWidget(btn_bo); def_row.addSpacing(10)
        btn_setall = QPushButton("Set all rows ->"); btn_setall.clicked.connect(self._set_all_rows)
        def_row.addWidget(btn_setall)
        root.addWidget(def_box)

        # Table
        tbl_box = QGroupBox("Projects  (double-click any cell to edit per-project  |  drag .spine files onto the table)")
        tbl_layout = QVBoxLayout(tbl_box)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(COL_FILE,  QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(COL_ANIM,  QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(COL_FPS,   QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(COL_SCALE, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(COL_OUTDIR,QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(220)
        tbl_layout.addWidget(self.table)
        btn_row = QHBoxLayout()
        for label, slot in [("Add files...",self._add_files),("Add folder...",self._add_folder),("Remove selected",self._remove_selected),("Clear all",self.table.clearContents)]:
            b = QPushButton(label); b.clicked.connect(slot); btn_row.addWidget(b)
        btn_row.addStretch()
        tbl_layout.addLayout(btn_row)
        root.addWidget(tbl_box)

        # Run
        run_row = QHBoxLayout(); run_row.addStretch()
        self.run_btn = QPushButton("Export All"); self.run_btn.setObjectName("run_btn")
        self.run_btn.setFixedWidth(130); self.run_btn.clicked.connect(self._run)
        run_row.addWidget(self.run_btn); root.addLayout(run_row)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine); root.addWidget(sep)
        self.log = QTextEdit(); self.log.setReadOnly(True); self.log.setMinimumHeight(130)
        root.addWidget(self.log)

    def _browse_exe(self):
        p,_ = QFileDialog.getOpenFileName(self,"Locate Spine","","Executables (*.exe);;All (*)")
        if p: self.exe_edit.setText(os.path.normpath(p))

    def _browse_def_out(self):
        p = QFileDialog.getExistingDirectory(self,"Default output root",self.def_outdir.text() or "")
        if p: self.def_outdir.setText(os.path.normpath(p))

    def _add_row(self, path):
        r = self.table.rowCount(); self.table.insertRow(r)
        out = ""
        if self.def_outdir.text().strip():
            proj = os.path.splitext(os.path.basename(path))[0]
            out = os.path.join(self.def_outdir.text().strip(), proj, "export")
        self.table.setItem(r,COL_FILE,  QTableWidgetItem(path))
        self.table.setItem(r,COL_ANIM,  QTableWidgetItem(self.def_anim.text()))
        self.table.setItem(r,COL_FPS,   QTableWidgetItem(str(self.def_fps.value())))
        self.table.setItem(r,COL_SCALE, QTableWidgetItem(str(self.def_scale.value())))
        self.table.setItem(r,COL_OUTDIR,QTableWidgetItem(out))
        self.table.item(r,COL_FILE).setFlags(Qt.ItemIsEnabled|Qt.ItemIsSelectable)

    def _add_paths(self, paths):
        existing = {self.table.item(i,COL_FILE).text() for i in range(self.table.rowCount())}
        for p in paths:
            p = os.path.normpath(p)
            if p not in existing: self._add_row(p); existing.add(p)

    def _add_files(self):
        ps,_ = QFileDialog.getOpenFileNames(self,"Add .spine files","","Spine (*.spine)")
        self._add_paths(ps)

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self,"Scan folder for .spine files")
        if not folder: return
        found=[]
        for rd,_,files in os.walk(folder):
            for f in files:
                if f.endswith('.spine'): found.append(os.path.join(rd,f))
        self._add_paths(found)

    def _remove_selected(self):
        for r in sorted({i.row() for i in self.table.selectedItems()},reverse=True):
            self.table.removeRow(r)

    def _set_all_rows(self):
        for r in range(self.table.rowCount()):
            self.table.item(r,COL_ANIM).setText(self.def_anim.text())
            self.table.item(r,COL_FPS).setText(str(self.def_fps.value()))
            self.table.item(r,COL_SCALE).setText(str(self.def_scale.value()))
            if self.def_outdir.text().strip():
                spine_file = self.table.item(r,COL_FILE).text()
                proj = os.path.splitext(os.path.basename(spine_file))[0]
                self.table.item(r,COL_OUTDIR).setText(os.path.join(self.def_outdir.text().strip(),proj,"export"))

    def _cell(self,r,c):
        item=self.table.item(r,c); return item.text().strip() if item else ""

    def _log(self,msg,color="#a6e3a1"):
        self.log.append(f'<span style="color:{color};">{msg}</span>')

    def _run(self):
        exe = self.exe_edit.text().strip()
        if not os.path.isfile(exe): self._log(f"ERROR: Spine not found: {exe}","#f38ba8"); return
        if self.table.rowCount()==0: self._log("ERROR: Add .spine files.","#f38ba8"); return
        jobs=[]
        for r in range(self.table.rowCount()):
            sf = self._cell(r,COL_FILE)
            if not os.path.isfile(sf): self._log(f"SKIP row {r+1}: {sf}","#fab387"); continue
            out = self._cell(r,COL_OUTDIR) or os.path.join(os.path.dirname(sf),"export")
            try: fps=int(self._cell(r,COL_FPS) or "25")
            except: fps=25
            try: scale=float(self._cell(r,COL_SCALE) or "1.0")
            except: scale=1.0
            jobs.append({'row':r,'spine_file':sf,'anim':self._cell(r,COL_ANIM),'fps':fps,'scale':scale,'out_dir':out})
        if not jobs: return
        self.log.clear()
        self._log(f"Starting — {len(jobs)} project(s)","#fab387")
        self.run_btn.setEnabled(False)
        self._worker = ExportWorker(exe, jobs)
        self._worker.progress.connect(lambda row,msg,col: self._log(f"[{row+1}] {msg}" if row>=0 else msg, col))
        self._worker.finished.connect(lambda: self.run_btn.setEnabled(True))
        self._worker.start()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = BatchExportUI()
    win.show()
    sys.exit(app.exec())
