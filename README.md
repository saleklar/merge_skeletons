# Spine Skeleton Merger

A GUI tool to merge two Spine 4.x skeleton JSON files into one, or prefix all named entities in a skeleton for use with Spine Editor import.

## Features

- **Prefix only** — Rename all bones, slots, skins, constraints and animation refs with a prefix (useful for Spine Editor manual import)
- **Full merge** — Combine two Spine JSONs into a single file, with automatic weighted-mesh bone-index remapping and stale-reference cleanup
- Configurable slot insert position (draw order control)
- Dark themed PySide6 GUI

## Usage

### From source

```bash
pip install -r requirements.txt
python merge_skeletons.py
```

### Pre-built binaries

Download from the [Releases](../../releases) page or the [Actions](../../actions) tab:

- `SpineSkeletonMerger.exe` — Windows
- `SpineSkeletonMerger-Mac.zip` — macOS `.app` bundle

## Build locally

```bash
pip install pyinstaller
pyinstaller merge_skeletons.spec
```

Output is in the `dist/` folder.
