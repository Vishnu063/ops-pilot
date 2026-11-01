"""Real private SQLite backup/restore regressions; no infrastructure access."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ops_pilot.backup import backup, restore, verify
from ops_pilot.freelance import Workspace


class BackupSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = Workspace(self.root / 'state')
        self.job = self.workspace.import_job({'title': 'Synthetic backup', 'description': 'Docker'})

    def snapshot(self, name='snapshot'):
        dest = self.root / name
        backup(self.workspace, dest)
        return dest

    def test_uri_punctuation_roundtrip_preserves_data(self):
        snapshot = self.snapshot('snapshot ?# with spaces')
        restored = self.root / 'restore ?# with spaces'
        verify(snapshot)
        restore(snapshot, restored)
        self.assertEqual(self.job['id'], Workspace(restored).get(self.job['id'])['id'])
        self.assertEqual(0o600, (restored / 'freelance/workspace.sqlite3').stat().st_mode & 0o777)

    def test_manifest_symlink_is_refused(self):
        snapshot = self.snapshot()
        manifest = snapshot / 'manifest.json'
        outside = self.root / 'outside.json'
        manifest.rename(outside)
        manifest.symlink_to(outside)
        with self.assertRaises(ValueError):
            verify(snapshot)

    def test_source_symlink_component_is_refused(self):
        snapshot = self.snapshot()
        link = self.root / 'linked-parent'
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            verify(link / snapshot.name)

    def test_backup_and_restore_refuse_symlinked_destination_parents(self):
        snapshot = self.snapshot()
        real = self.root / 'real'
        real.mkdir()
        link = self.root / 'linked'
        link.symlink_to(real, target_is_directory=True)
        for action in (lambda: backup(self.workspace, link / 'backup'),
                       lambda: restore(snapshot, link / 'restore')):
            with self.assertRaises(ValueError):
                action()
        self.assertEqual([], list(real.iterdir()))

    def test_fifo_manifest_is_refused_without_reading(self):
        snapshot = self.snapshot()
        manifest = snapshot / 'manifest.json'
        manifest.unlink()
        os.mkfifo(manifest)
        with self.assertRaises(ValueError):
            verify(snapshot)

    def test_hardlinked_database_is_refused(self):
        snapshot = self.snapshot()
        os.link(snapshot / 'workspace.sqlite3', self.root / 'linked.sqlite3')
        with self.assertRaises(ValueError):
            verify(snapshot)

    def test_manifest_shape_and_size_are_bounded(self):
        for value in ([], {'version': 1}, {'version': 1, 'sha256': 'invalid'},
                      {'version': 1, 'sha256': 'a' * 64, 'padding': 'x' * 8192}):
            with self.subTest(value_type=type(value).__name__):
                snapshot = self.snapshot('case-' + str(len(list(self.root.iterdir()))))
                (snapshot / 'manifest.json').write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    verify(snapshot)

    def test_backup_hashing_does_not_read_entire_database_into_memory(self):
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('Unbounded file read')):
            snapshot = self.snapshot()
            restore(snapshot, self.root / 'restored')
        self.assertEqual('Synthetic backup', Workspace(self.root / 'restored').get(self.job['id'])['title'])


if __name__ == '__main__':
    unittest.main()
