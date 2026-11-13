"""Check that the actual QML view loads and settings bind to the controller."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import QCoreApplication, QEvent, QMetaObject
from PySide6.QtWidgets import QApplication
from PySide6.QtQuick import QQuickItem
from qt_app.backend import Bridge
from qt_app.main import load_ui


class ViewTests(unittest.TestCase):
    def test_real_view_settings_and_search_bindings(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'LOCALAPPDATA': directory}):
            bridge = Bridge()
            engine, window = load_ui(bridge)
            warnings = []
            engine.warnings.connect(lambda errors: warnings.extend(str(e) for e in errors))
            try:
                app.processEvents()
                self.assertEqual(window.title(), 'A/L Results Collector — Qt preview')
                from PySide6.QtCore import QObject
                year = window.findChild(QObject, 'examYearInput')
                self.assertIsNotNone(year)
                year.setProperty('text', '2024')
                QMetaObject.invokeMethod(year, 'textEdited')
                self.assertEqual(bridge.examYear, '2024')
                search = window.findChild(QObject, 'subjectSearch')
                search.setProperty('text', '20'); app.processEvents()
                self.assertEqual(bridge.filtered.rowCount(), 1)
                bridge.selectField('Candidate Name', True); app.processEvents()
                def visual_item(item, name):
                    if item.objectName() == name:
                        return item
                    for child in item.childItems():
                        found = visual_item(child, name)
                        if found is not None:
                            return found
                checkbox = visual_item(window.contentItem(), 'field-Candidate Name')
                self.assertIsNotNone(checkbox)
                self.assertTrue(checkbox.property('checked'))
                for i in range(100):
                    bridge.log(f'Activity line {i}')
                import time
                deadline = time.monotonic() + 2
                scroll = window.findChild(QObject, 'activityScroll')
                self.assertIsNotNone(scroll)
                flickable = scroll.property('contentItem')
                while flickable.property('contentY') <= 0 and time.monotonic() < deadline:
                    app.processEvents(); time.sleep(.01)
                self.assertGreater(flickable.property('contentY'), 0)
                self.assertFalse(warnings, warnings)
            finally:
                bridge.requestClose(); bridge.timer.stop()
                window.close(); engine.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
