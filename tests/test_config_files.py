"""Bounded private configuration reads and safe atomic replacement."""
import os
from pathlib import Path
import tempfile
import unittest

from ops_pilot.config import load, save

CONFIG = {'name': 'Synthetic', 'docker_context': 'default', 'container': 'owned',
          'health_url': 'http://127.0.0.1:8080/health'}


class ConfigurationFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'config.json'

    def test_private_roundtrip_and_atomic_replacement(self):
        save(self.path, CONFIG)
        save(self.path, dict(CONFIG, name='Updated'))
        self.assertEqual('Updated', load(self.path)[0]['name'])
        self.assertEqual(0o600, self.path.stat().st_mode & 0o777)

    def test_symlink_leaf_and_parent_refused_without_overwriting(self):
        save(self.path, CONFIG)
        before = self.path.read_bytes()
        leaf = self.root / 'linked.json'
        leaf.symlink_to(self.path)
        parent = self.root / 'linked-parent'
        parent.symlink_to(self.root, target_is_directory=True)
        for path in (leaf, parent / 'config.json'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                load(path)
            with self.assertRaises(ValueError):
                save(path, dict(CONFIG, name='Unwanted'))
        self.assertEqual(before, self.path.read_bytes())

    def test_fifo_rejected_without_blocking_on_read_or_write(self):
        os.mkfifo(self.path)
        with self.assertRaises(ValueError):
            load(self.path)
        with self.assertRaises(ValueError):
            save(self.path, CONFIG)

    def test_hardlink_and_public_read_permissions_refused(self):
        save(self.path, CONFIG)
        link = self.root / 'hardlink.json'
        os.link(self.path, link)
        with self.assertRaises(ValueError):
            load(self.path)
        with self.assertRaises(ValueError):
            save(self.path, CONFIG)
        link.unlink()
        self.path.chmod(0o644)
        with self.assertRaises(ValueError):
            load(self.path)
        self.path.chmod(0o600)
        self.assertEqual('Synthetic', load(self.path)[0]['name'])

    def test_oversized_and_malformed_configuration_refused(self):
        save(self.path, CONFIG)
        for raw in (b' ' * 8193, b'{', b'\xff', b'[]'):
            self.path.write_bytes(raw)
            with self.subTest(raw_length=len(raw)), self.assertRaises(ValueError):
                load(self.path)


if __name__ == '__main__':
    unittest.main()
