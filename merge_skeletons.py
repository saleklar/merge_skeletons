import json
import copy
import sys
import os

# ─────────────────────────────────────────────
# Core logic
# ─────────────────────────────────────────────

# All top-level array keys in a Spine 4.x JSON that need merging
ARRAY_KEYS = ['bones', 'slots', 'ik', 'transform', 'path', 'physics']


def prefix_skeleton(data, prefix):
    """
    Rename every named entity in the skeleton JSON with a prefix.
    Covers: bones, slots, skins (all attachment types including meshes),
    ik/transform/path/physics constraints, and all animation timelines.
    """
    d = copy.deepcopy(data)

    def p(name):
        return f"{prefix}{name}" if name else name

    # Bones
    for bone in d.get('bones', []):
        bone['name'] = p(bone['name'])
        if bone.get('parent'):
            bone['parent'] = p(bone['parent'])

    # Slots
    for slot in d.get('slots', []):
        slot['name'] = p(slot['name'])
        slot['bone'] = p(slot['bone'])

    # Skins — deep copy all attachment data as-is (preserves meshes, regions, etc.)
    # For clipping attachments, remap the 'end' slot reference too.
    new_skins = []
    for skin in d.get('skins', []):
        new_att = {}
        for slot_name, atts in skin.get('attachments', {}).items():
            new_atts_for_slot = {}
            for att_name, att_data in atts.items():
                att_copy = copy.deepcopy(att_data)
                # Clipping attachments reference an end slot by name
                if isinstance(att_copy, dict) and att_copy.get('type') == 'clipping':
                    if att_copy.get('end'):
                        att_copy['end'] = p(att_copy['end'])
                new_atts_for_slot[att_name] = att_copy
            new_att[p(slot_name)] = new_atts_for_slot
        new_skin = copy.deepcopy(skin)
        new_skin['attachments'] = new_att
        new_skins.append(new_skin)
    d['skins'] = new_skins

    # IK constraints
    for c in d.get('ik', []):
        c['name'] = p(c['name'])
        c['bones'] = [p(b) for b in c.get('bones', [])]
        if c.get('target'): c['target'] = p(c['target'])

    # Transform constraints
    for c in d.get('transform', []):
        c['name'] = p(c['name'])
        c['bones'] = [p(b) for b in c.get('bones', [])]
        if c.get('target'): c['target'] = p(c['target'])

    # Path constraints
    for c in d.get('path', []):
        c['name'] = p(c['name'])
        c['bones'] = [p(b) for b in c.get('bones', [])]
        if c.get('target'): c['target'] = p(c['target'])
        if c.get('slot'):   c['slot']   = p(c['slot'])

    # Physics constraints (Spine 4.2+)
    for c in d.get('physics', []):
        c['name'] = p(c['name'])
        if c.get('bone'): c['bone'] = p(c['bone'])

    # Animations
    new_anims = {}
    for anim_name, anim_data in d.get('animations', {}).items():
        anim_data = copy.deepcopy(anim_data)

        # Bone timelines  ← was missing before
        anim_data['bones'] = {p(k): v for k, v in anim_data.get('bones', {}).items()}

        # Slot timelines
        anim_data['slots'] = {p(k): v for k, v in anim_data.get('slots', {}).items()}

        # Deform timelines (skin → slot → attachment)
        new_deform = {}
        for skin_name, skin_slots in anim_data.get('deform', {}).items():
            new_deform[skin_name] = {p(k): v for k, v in skin_slots.items()}
        if new_deform: anim_data['deform'] = new_deform

        # Attachments timelines (skin → slot → attachment) — Spine 4.x
        new_attachments = {}
        for skin_name, skin_slots in anim_data.get('attachments', {}).items():
            new_attachments[skin_name] = {p(k): v for k, v in skin_slots.items()}
        if new_attachments: anim_data['attachments'] = new_attachments

        # DrawOrder timelines — each entry has an 'offsets' list with 'slot' keys
        new_draw = []
        for entry in anim_data.get('drawOrder', []):
            entry = copy.deepcopy(entry)
            if 'offsets' in entry:
                for offset in entry['offsets']:
                    if 'slot' in offset:
                        offset['slot'] = p(offset['slot'])
            new_draw.append(entry)
        if new_draw: anim_data['drawOrder'] = new_draw

        # Constraint timelines
        for tl_key in ('ik', 'transform', 'path', 'physics'):
            if tl_key in anim_data:
                anim_data[tl_key] = {p(k): v for k, v in anim_data[tl_key].items()}

        new_anims[anim_name] = anim_data
    d['animations'] = new_anims

    return d


def remap_weighted_mesh_indices(skin_data, bone_offset):
    """
    Weighted mesh vertices store bone indices as integers into the skeleton's bones array.
    After merging, imported bones are appended after base bones, so all indices need
    to be shifted by bone_offset (= number of bones in the base skeleton).
    """
    for slot_name, atts in skin_data.get('attachments', {}).items():
        for att_name, att in atts.items():
            if not isinstance(att, dict): continue
            if att.get('type') != 'mesh': continue
            uvs    = att.get('uvs', [])
            verts  = att.get('vertices', [])
            # Weighted mesh: vertex count != len(uvs)/2
            if len(verts) <= len(uvs):
                continue  # not weighted
            new_verts = []
            i = 0
            while i < len(verts):
                count = int(verts[i])
                new_verts.append(count)
                i += 1
                for _ in range(count):
                    new_verts.append(int(verts[i]) + bone_offset)  # shift bone index
                    new_verts.append(verts[i+1])  # weight
                    new_verts.append(verts[i+2])  # local x
                    new_verts.append(verts[i+3])  # local y
                    i += 4
            att['vertices'] = new_verts


def merge(base_data, import_data, prefix, slot_insert_index=None):
    """
    Merge import_data (prefixed) into base_data.
    slot_insert_index: where in the slots array to insert imported slots.
      None / -1 = append at end (top of draw order).
      0          = insert at start (bottom of draw order).
    Returns the merged dict.
    """
    result = copy.deepcopy(base_data)
    imp    = prefix_skeleton(import_data, prefix)

    # Record base bone count BEFORE appending — used to remap weighted mesh indices
    base_bone_count = len(result.get('bones', []))

    # Bones — re-parent imported root bone(s) to base 'root' to avoid multiple roots
    base_bone_names = {b['name'] for b in result.get('bones', [])}
    result.setdefault('bones', [])
    for bone in imp.get('bones', []):
        if not bone.get('parent') and bone['name'] != 'root':
            bone['parent'] = 'root'
        result['bones'].append(bone)

    # Slots — insert at chosen position
    result.setdefault('slots', [])
    imp_slots = imp.get('slots', [])
    if slot_insert_index is None or slot_insert_index < 0:
        result['slots'] += imp_slots
    else:
        idx = min(slot_insert_index, len(result['slots']))
        result['slots'] = result['slots'][:idx] + imp_slots + result['slots'][idx:]

    # Constraint arrays
    for key in ('ik', 'transform', 'path', 'physics'):
        result.setdefault(key, [])
        result[key] += imp.get(key, [])

    # Skins — merge into matching skin by name, or append new
    # First remap weighted mesh bone indices in imported skins
    for imp_skin in imp.get('skins', []):
        remap_weighted_mesh_indices(imp_skin, base_bone_count)

    result.setdefault('skins', [])
    for imp_skin in imp.get('skins', []):
        skin_name = imp_skin.get('name', 'default')
        existing = next((s for s in result['skins'] if s.get('name') == skin_name), None)
        if existing is None:
            result['skins'].append(copy.deepcopy(imp_skin))
        else:
            # Merge attachments into existing skin
            for slot_name, atts in imp_skin.get('attachments', {}).items():
                existing.setdefault('attachments', {})[slot_name] = copy.deepcopy(atts)

    # Animations — prefix name on collision
    result.setdefault('animations', {})
    for anim_name, anim_data in imp.get('animations', {}).items():
        key = anim_name if anim_name not in result['animations'] else f"{prefix}{anim_name}"
        result['animations'][key] = anim_data

    return result


def cleanup_stale_refs(data):
    """
    After merging, remove any references to bones/slots that no longer exist.
    - Clipping attachments whose 'end' slot is missing → remove 'end' key
    - Animation bone timelines referencing missing bones → drop those timelines
    - Animation slot timelines referencing missing slots → drop those timelines
    Returns (cleaned_data, list_of_warnings)
    """
    import copy
    d = copy.deepcopy(data)
    warnings = []

    valid_bones = {b['name'] for b in d.get('bones', [])}
    valid_slots = {s['name'] for s in d.get('slots', [])}

    # Fix clipping attachments with missing end slot
    for skin in d.get('skins', []):
        for slot_name, atts in skin.get('attachments', {}).items():
            for att_name, att_data in atts.items():
                if isinstance(att_data, dict) and att_data.get('type') == 'clipping':
                    end = att_data.get('end')
                    if end and end not in valid_slots:
                        warnings.append(f"Removed stale clipping end '{end}' from attachment '{att_name}' (slot not found)")
                        del att_data['end']

    # Fix animation timelines
    for anim_name, anim_data in d.get('animations', {}).items():
        # Bone timelines
        bad_bones = [b for b in anim_data.get('bones', {}) if b not in valid_bones]
        for b in bad_bones:
            warnings.append(f"Removed stale bone timeline '{b}' from animation '{anim_name}'")
            del anim_data['bones'][b]

        # Slot timelines
        bad_slots = [s for s in anim_data.get('slots', {}) if s not in valid_slots]
        for s in bad_slots:
            warnings.append(f"Removed stale slot timeline '{s}' from animation '{anim_name}'")
            del anim_data['slots'][s]

        # Deform timelines
        for skin_name, skin_slots in anim_data.get('deform', {}).items():
            bad_deform = [s for s in skin_slots if s not in valid_slots]
            for s in bad_deform:
                warnings.append(f"Removed stale deform slot '{s}' from animation '{anim_name}'")
                del skin_slots[s]

        # Attachments timelines (Spine 4.x)
        for skin_name, skin_slots in anim_data.get('attachments', {}).items():
            bad_atts = [s for s in skin_slots if s not in valid_slots]
            for s in bad_atts:
                warnings.append(f"Removed stale attachment slot '{s}' from animation '{anim_name}'")
                del skin_slots[s]

        # DrawOrder slot references
        for entry in anim_data.get('drawOrder', []):
            if 'offsets' in entry:
                entry['offsets'] = [o for o in entry['offsets'] if o.get('slot') in valid_slots]

    return d, warnings


def run_merge(base_path, import_path, output_path, prefix, slot_insert_index=None):
    base_data   = json.load(open(base_path,   encoding='utf-8'))
    import_data = json.load(open(import_path, encoding='utf-8'))
    result      = merge(base_data, import_data, prefix, slot_insert_index)
    result, cleanup_warnings = cleanup_stale_refs(result)

    stats = {
        'bones':    len(result.get('bones', [])),
        'slots':    len(result.get('slots', [])),
        'anims':    len(result.get('animations', {})),
        'skins':    len(result.get('skins', [])),
        'warnings': cleanup_warnings,
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, separators=(',', ':'))

    return stats


def run_prefix_only(source_path, output_path, prefix):
    data    = json.load(open(source_path, encoding='utf-8'))
    result  = prefix_skeleton(data, prefix)
    stats = {
        'bones':    len(result.get('bones', [])),
        'slots':    len(result.get('slots', [])),
        'anims':    len(result.get('animations', {})),
        'skins':    len(result.get('skins', [])),
        'warnings': [],
    }
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, separators=(',', ':'))
    return stats


# ─────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog,
    QGroupBox, QTextEdit,
    QFrame, QSpinBox, QCheckBox, QSizePolicy
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

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
QLineEdit, QSpinBox {
    background: #313244;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px 8px;
    color: #cdd6f4;
}
QLineEdit:focus, QSpinBox:focus { border: 1px solid #89b4fa; }
QSpinBox::up-button, QSpinBox::down-button { width: 16px; }
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


class PathRow(QWidget):
    def __init__(self, label, placeholder="", save=False, directory=False, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        lbl = QLabel(label)
        lbl.setFixedWidth(110)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        btn = QPushButton("Browse")
        btn.setFixedWidth(70)
        layout.addWidget(lbl)
        layout.addWidget(self.edit)
        layout.addWidget(btn)
        self._save = save
        self._directory = directory
        btn.clicked.connect(self._browse)

    def _browse(self):
        if self._directory:
            path = QFileDialog.getExistingDirectory(self, "Select folder", self.edit.text() or "")
        elif self._save:
            path, _ = QFileDialog.getSaveFileName(self, "Save as", self.edit.text() or "", "Spine Files (*.spine *.json)")
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Open", self.edit.text() or "", "Spine JSON (*.json)")
        if path:
            self.edit.setText(os.path.normpath(path))

    def path(self): return self.edit.text().strip()
    def set_path(self, p): self.edit.setText(p)


class MergeUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Spine Skeleton Merger  |  v2")
        self.setMinimumWidth(700)
        self._build()
        self.setStyleSheet(STYLE)

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(16, 16, 16, 16)

        # ── Files ─────────────────────────────────────────────────
        files_box = QGroupBox("Files")
        files_layout = QVBoxLayout(files_box)
        files_layout.setSpacing(6)
        self.row_base   = PathRow("Base JSON:",   "Target/base skeleton")
        self.row_source = PathRow("Source JSON:", "Skeleton to prefix / import")
        self.row_output = PathRow("Output JSON:", "Where to save result", save=True)
        files_layout.addWidget(self.row_base)
        files_layout.addWidget(self.row_source)
        files_layout.addWidget(self.row_output)
        root.addWidget(files_box)

        # ── Prefix ────────────────────────────────────────────────
        prefix_box = QGroupBox("Prefix")
        prefix_layout = QHBoxLayout(prefix_box)
        lbl_p = QLabel("Prefix string:")
        lbl_p.setFixedWidth(110)
        lbl_p.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.prefix_edit = QLineEdit()
        self.prefix_edit.setPlaceholderText("e.g.  h1_   or   ab_")
        self.prefix_edit.setMaximumWidth(160)
        hint = QLabel(
            "Spine requires every bone, slot and constraint name to be unique. "
            "When merging two skeletons, a prefix prevents name collisions — "
            "e.g. prefix \"h1_\" turns bone \"arm\" into \"h1_arm\" so it never "
            "clashes with the same-named bone in the base skeleton."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #6c7086; font-size: 11px;")
        prefix_layout.addWidget(lbl_p)
        prefix_layout.addWidget(self.prefix_edit)
        prefix_layout.addSpacing(12)
        prefix_layout.addWidget(hint)
        prefix_layout.addStretch()
        root.addWidget(prefix_box)

        # ── Layer order ───────────────────────────────────────────
        order_box = QGroupBox("Slot / Layer Insert Position")
        order_layout = QHBoxLayout(order_box)
        self.chk_custom_insert = QCheckBox("Insert at slot index:")
        self.chk_custom_insert.setChecked(False)
        self.spin_insert = QSpinBox()
        self.spin_insert.setRange(0, 9999)
        self.spin_insert.setValue(0)
        self.spin_insert.setFixedWidth(80)
        self.spin_insert.setEnabled(False)
        hint2 = QLabel("Leave unchecked to append at end (top of draw stack).  0 = very bottom.")
        hint2.setStyleSheet("color: #6c7086; font-size: 11px;")
        order_layout.addWidget(self.chk_custom_insert)
        order_layout.addWidget(self.spin_insert)
        order_layout.addSpacing(12)
        order_layout.addWidget(hint2)
        order_layout.addStretch()
        self.chk_custom_insert.toggled.connect(self.spin_insert.setEnabled)
        root.addWidget(order_box)

        # ── Run ───────────────────────────────────────────────────
        run_row = QHBoxLayout()
        run_row.addStretch()
        self.run_btn = QPushButton("Run")
        self.run_btn.setObjectName("run_btn")
        self.run_btn.setFixedWidth(120)
        self.run_btn.clicked.connect(self._run)
        run_row.addWidget(self.run_btn)
        root.addLayout(run_row)

        # ── Log ───────────────────────────────────────────────────
        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        root.addWidget(sep)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(130)
        root.addWidget(self.log)

        # Wire
        self.row_source.edit.textChanged.connect(self._auto_output)

    def _auto_output(self, text):
        if not text:
            return
        base, ext = os.path.splitext(text)
        if not self.row_output.path():
            self.row_output.set_path(base + '_merged' + ext)

    def _log(self, msg, color="#a6e3a1"):
        self.log.append(f'<span style="color:{color};">{msg.replace(chr(10), "<br>")}</span>')

    def _run(self):
        self.log.clear()
        prefix = self.prefix_edit.text().strip()
        source = self.row_source.path()
        output = self.row_output.path()

        if not prefix:
            self._log("ERROR: Enter a prefix string.", "#f38ba8"); return
        if not source or not os.path.isfile(source):
            self._log("ERROR: Source JSON not found.", "#f38ba8"); return
        if not output:
            self._log("ERROR: Output path is empty.", "#f38ba8"); return

        try:
            base = self.row_base.path()
            if not base or not os.path.isfile(base):
                self._log("ERROR: Base JSON not found.", "#f38ba8"); return
            insert_idx = self.spin_insert.value() if self.chk_custom_insert.isChecked() else None
            stats = run_merge(base, source, output, prefix, insert_idx)
            self._log("Full merge — done.")
            for w in stats.get('warnings', []):
                self._log(f"  CLEANED: {w}", "#fab387")

            self._log(
                f"  Bones: {stats['bones']}   Slots: {stats['slots']}   "
                f"Skins: {stats['skins']}   Animations: {stats['anims']}"
            )
            self._log(f"  → {output}")
        except Exception as e:
            import traceback
            self._log(f"ERROR: {e}", "#f38ba8")
            self._log(traceback.format_exc(), "#f38ba8")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = MergeUI()
    win.show()
    sys.exit(app.exec())
