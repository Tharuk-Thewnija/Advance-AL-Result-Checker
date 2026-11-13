"""Create a safe demonstration workbook; replace sample NICs before collection."""
from pathlib import Path
import pandas as pd

if __name__ == '__main__':
    path = Path('sample_students.xlsx')
    if path.exists():
        raise SystemExit('sample_students.xlsx already exists; choose another directory.')
    pd.DataFrame({'Student': ['Example student 1', 'Example student 2'],
                  'NIC': ['REPLACE_WITH_NIC_1', 'REPLACE_WITH_NIC_2']}).to_excel(path, index=False)
    print(f'Created {path.resolve()}. Sample IDs are intentionally invalid; replace them with your student NICs.')
