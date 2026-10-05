# PyInstaller recipe for a single-file Windows executable.
# Usage, from the repository root:  pyinstaller --clean survey_tabulator.spec

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []

# pyreadstat and ttkbootstrap ship binaries and data files that PyInstaller
# does not always find on its own, so they are collected explicitly.
for package in ('pyreadstat', 'ttkbootstrap'):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ['src/app.py'],
    pathex=['src'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Heavy libraries that may be installed but are never imported by the app
    excludes=['torch', 'torchvision', 'scipy', 'matplotlib', 'numpy.testing', 'notebook', 'nbconvert'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SurveyTabulator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,            # only used if UPX is found (see --upx-dir)
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,       # no console window behind the application
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
