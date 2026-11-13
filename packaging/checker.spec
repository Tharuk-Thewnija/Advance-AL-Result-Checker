# Build on Windows: py -m PyInstaller --noconfirm packaging/checker.spec
from pathlib import Path
from importlib import metadata
import os
import sys
from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH).parent
# External desktop tools may prepend incompatible DLLs (notably ICU) to PATH.
# Build against Python, Qt's hook-supplied paths, and Windows system libraries.
windows = Path(os.environ['SystemRoot'])
os.environ['PATH'] = os.pathsep.join(map(str, [Path(sys.base_prefix), Path(sys.base_prefix) / 'DLLs', windows / 'System32', windows]))
data = collect_data_files('selenium')
data += [(str(root / 'al_results' / 'data' / 'subjects.json'), 'al_results/data')]
data += [(str(root / 'qt_app' / 'qml'), 'qt_app/qml'),
         (str(root / 'packaging' / 'app.ico'), 'packaging'),
         (str(root / 'packaging' / 'licenses'), 'third_party_licenses'),
         (str(root / 'packaging' / 'THIRD_PARTY_NOTICES.md'), '.')]
# Preserve vendor copyright/licence files in the installed one-folder bundle.
for name in ('PySide6-Essentials', 'shiboken6', 'selenium', 'pandas', 'numpy',
             'openpyxl', 'xlrd', 'trio', 'urllib3', 'certifi', 'attrs',
             'trio-websocket', 'websocket-client', 'cffi', 'python-dateutil', 'tzdata'):
    dist = metadata.distribution(name)
    for path in dist.files or []:
        if '/licenses/' in str(path).replace('\\', '/') or path.name.upper().startswith(('LICENSE', 'COPYING')):
            source = Path(dist.locate_file(path))
            if source.is_file():
                data.append((str(source), 'third_party_licenses/' + name + '/' + str(path.parent)))

a = Analysis([str(root / 'checker.py')], pathex=[str(root)], binaries=[], datas=data,
             hiddenimports=['openpyxl', 'xlrd'],
             excludes=['tkinter', '_tkinter', 'customtkinter', 'matplotlib', 'scipy', 'IPython',
                       'pytest', 'notebook', 'PyQt5', 'PyQt6', 'PySide2', 'qt_app.tests',
                       'tests', 'xlwt'],
             noarchive=False)
# This Qt Windows build uses the OS-provided, unversioned ICU API. A third-party
# icuuc.dll with suffixed symbols must never shadow Windows' copy in the bundle.
a.binaries = [item for item in a.binaries if Path(item[0]).name.lower() != 'icuuc.dll']
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='ALResultsCollector',
          debug=False, strip=False, upx=False, console=False,
          icon=str(root / 'packaging' / 'app.ico'),
          version=str(root / 'packaging' / 'windows-version.txt'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='ALResultsCollector')
