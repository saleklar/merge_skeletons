# -*- mode: python ; coding: utf-8 -*-
# macOS-specific spec — onedir mode required for .app bundles

a = Analysis(
    ['merge_skeletons.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['PySide6.QtXml'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # onedir: binaries go into COLLECT
    name='SpineSkeletonMerger',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    argv_emulation=True,     # macOS: handle open-file events
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SpineSkeletonMerger',
)

app = BUNDLE(
    coll,
    name='SpineSkeletonMerger.app',
    icon=None,
    bundle_identifier='com.saleklar.spine-skeleton-merger',
    info_plist={
        'CFBundleShortVersionString': '2.0.0',
        'NSHighResolutionCapable': True,
        'NSRequiresAquaSystemAppearance': False,
    },
)
