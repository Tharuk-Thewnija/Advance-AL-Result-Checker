"""Generate the Windows icon and version resource from the project's branding/version."""
from pathlib import Path
import struct
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from al_results import __version__
from PySide6.QtCore import QByteArray, QBuffer, QIODevice
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


def main():
    folder = Path(__file__).resolve().parent
    app = QGuiApplication.instance() or QGuiApplication([])
    renderer = QSvgRenderer(str(folder / 'app.svg'))
    if not renderer.isValid():
        raise ValueError('The app icon SVG could not be loaded.')
    sizes = (16, 24, 32, 48, 64, 128, 256)
    entries = []; images = []; offset = 6 + 16 * len(sizes)
    for size in sizes:
        image = QImage(size, size, QImage.Format.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter); painter.end()
        data = QByteArray(); buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly); image.save(buffer, 'PNG'); buffer.close()
        png = bytes(data)
        entries.append(struct.pack('<BBBBHHII', size % 256, size % 256, 0, 0, 1, 32, len(png), offset))
        images.append(png); offset += len(png)
    header = struct.pack('<HHH', 0, 1, len(sizes))
    (folder / 'app.ico').write_bytes(header + b''.join(entries) + b''.join(images))
    version = tuple(int(x) for x in __version__.split('.')) + (0,)
    resource = f'''VSVersionInfo(
  ffi=FixedFileInfo(filevers={version}, prodvers={version}, mask=0x3f,
                   flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('FileDescription', 'A/L Results Collector'),
    StringStruct('FileVersion', '{__version__}'),
    StringStruct('ProductName', 'A/L Results Collector'),
    StringStruct('ProductVersion', '{__version__}'),
    StringStruct('OriginalFilename', 'ALResultsCollector.exe')
  ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)
'''
    (folder / 'windows-version.txt').write_text(resource, encoding='utf-8')


if __name__ == '__main__':
    main()
