# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPECPATH)

a = Analysis(
    ['main.py'],
    pathex=[str(root)],
    binaries=[],
    datas=[
        ('VERSION.json', '.'),
        ('lang', 'lang'),
        ('data', 'data'),
        ('docs', 'docs'),
        # PATCH_048: read at run time via root_dir / Path(__file__); were not bundled,
        # so the EXE's AI request ZIP silently left out the protocol/schema files.
        ('resources', 'resources'),
        ('module1/*.json', 'module1'),
        ('module1/*.md', 'module1'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AZRAS_Planning',
    version=str(root / 'version_info_AZRAS_Planning.txt'),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AZRAS_Planning',
)
