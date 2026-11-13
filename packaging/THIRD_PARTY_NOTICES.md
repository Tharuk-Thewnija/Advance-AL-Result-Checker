# Third-party components

This application uses Python, Qt for Python (PySide6 Essentials and Shiboken),
Selenium, pandas, NumPy, openpyxl, xlrd and their dependencies. Vendor licence and
copyright notices are included under `_internal/third_party_licenses/`.

Qt for Python and the Qt Essentials libraries are dynamically linked. Qt offers
open-source LGPL/GPL licensing options; see the included LGPLv3/GPLv3 texts and
the component notices. The shared libraries remain separate files in this bundle.
This application does not modify Qt or Shiboken.

Upstream projects and source:

- Qt for Python: https://code.qt.io/cgit/pyside/pyside-setup.git/ (6.12.0)
- Qt modules: https://code.qt.io/cgit/qt/ (6.12.0)
- Qt licensing and third-party acknowledgements: https://doc.qt.io/qt-6/licensing.html
- Qt for Python acknowledgements: https://doc.qt.io/qtforpython-6/licenses.html
- Python: https://www.python.org/downloads/source/
- Selenium: https://github.com/SeleniumHQ/selenium
- pandas: https://github.com/pandas-dev/pandas
- NumPy: https://github.com/numpy/numpy
- openpyxl: https://foss.heptapod.net/openpyxl/openpyxl
- xlrd: https://github.com/python-excel/xlrd

Python's licence is included by the bundler. Project-specific licences are collected
from the installed distributions. These notices do not choose a licence for the
application's own source code; that remains the maintainer's decision.
