from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys
from unittest.mock import patch
import pandas as pd
from al_results.models import InputWorkbook, RunConfig, RowResult
from al_results.checkpoints import CheckpointStore, CheckpointMismatch


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patch = patch('al_results.checkpoints.checkpoint_path', return_value=self.root / 'current.sqlite3')
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.book = InputWorkbook(self.root / 'a.xlsx', 'hash1', 'Sheet1', pd.DataFrame({'NIC': ['900000000V'] * 3}))
        self.config = RunConfig(self.book.path, ('20',), (), '2025', 180, self.root)

    def test_save_close_reopen_and_pending(self):
        store = CheckpointStore.open(self.book, self.config)
        store.save(RowResult(0, 'Completed', {'subject:20': 'A'}))
        store.save(RowResult(1, 'Skipped', {}, 'Skipped by user'))
        store.close()
        store = CheckpointStore.open(self.book, self.config)
        self.assertEqual(store.results()[0].values, {'subject:20': 'A'})
        self.assertEqual(store.pending_positions(), [2])
        self.assertTrue(store.matches(self.book, self.config))
        store.discard()
        self.assertFalse((self.root / 'current.sqlite3').exists())

    def test_mismatch_does_not_destroy_existing_progress(self):
        store = CheckpointStore.open(self.book, self.config)
        store.save(RowResult(0, 'Completed', {'subject:20': 'B'})); store.close()
        for book, config in [(replace(self.book, content_hash='changed'), self.config),
                             (replace(self.book, sheet_name='Other'), self.config),
                             (self.book, replace(self.config, subject_ids=('10',)))]:
            with self.subTest(book=book.content_hash, subject=config.subject_ids):
                with self.assertRaises(CheckpointMismatch):
                    CheckpointStore.open(book, config)
        store = CheckpointStore.open(self.book, self.config)
        self.assertEqual(len(store.results()), 1)
        store.discard()
        fresh = CheckpointStore.open(self.book, self.config)
        self.assertEqual(fresh.pending_positions(), [0, 1, 2]); fresh.close()

    def test_transaction_rollback_and_row_validation(self):
        store = CheckpointStore.open(self.book, self.config)
        self.addCleanup(store.close)
        with self.assertRaises(ValueError):
            store.save(RowResult(99, 'Completed', {}))
        with self.assertRaises(TypeError):
            store.save(RowResult(0, 'Completed', {'bad': object()}))
        self.assertEqual(store.results(), [])
        store.save(RowResult(0, 'Error', {}, 'timeout'))
        self.assertEqual(store.pending_positions(), [1, 2])

    def test_committed_result_survives_process_exit_without_cleanup(self):
        script = '''
import os, sys
from pathlib import Path
import pandas as pd
import al_results.checkpoints as checkpoints
from al_results.models import InputWorkbook, RunConfig, RowResult
root=Path(sys.argv[1])
checkpoints.checkpoint_path=lambda: root / 'current.sqlite3'
book=InputWorkbook(root/'a.xlsx', 'hash1', 'Sheet1', pd.DataFrame({'NIC':['900000000V']*3}))
config=RunConfig(book.path, ('20',), (), '2025', 180, root)
store=checkpoints.CheckpointStore.open(book,config)
store.save(RowResult(0,'Completed',{'subject:20':'A'}))
os._exit(33)
'''
        result = subprocess.run([sys.executable, '-c', script, str(self.root)], capture_output=True)
        self.assertEqual(result.returncode, 33, result.stderr)
        store = CheckpointStore.open(self.book, self.config)
        self.assertEqual(store.results()[0].values, {'subject:20': 'A'})
        self.assertEqual(store.pending_positions(), [1, 2]); store.close()
