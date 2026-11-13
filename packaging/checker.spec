# Build on Windows: py -m PyInstaller --noconfirm packaging/checker.spec
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH).parent
data = collect_data_files('customtkinter') + collect_data_files('selenium')
data += [(str(root / 'al_results' / 'data' / 'subjects.json'), 'al_results/data')]

a = Analysis([str(root / 'checker.py')], pathex=[str(root)], binaries=[], datas=data,
             hiddenimports=['openpyxl', 'xlrd'],
             excludes=['matplotlib', 'scipy', 'IPython', 'pytest', 'notebook', 'PyQt5', 'PySide6'],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='ALResultsCollector',
          debug=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='ALResultsCollector')
