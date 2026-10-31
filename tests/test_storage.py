"""Filesystem/SQLite integration tests, independent of external services/sockets."""
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from ops_pilot.storage import private_database, PrivateConnection
from ops_pilot.runtime import Runtime

CONFIG={'docker_context':'default','container':'owned','health_url':'http://127.0.0.1:9000'}

class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_existing_monitor_permissions_are_corrected_without_losing_state(self):
        state=Runtime(self.root/'state',CONFIG);state.save(True,123,True)
        state.path.chmod(0o666);state.path.parent.chmod(0o755)
        reopened=Runtime(state.path.parent,CONFIG)
        self.assertEqual(reopened.path.stat().st_mode&0o777,0o600)
        self.assertEqual(reopened.path.parent.stat().st_mode&0o777,0o700)
        self.assertEqual(reopened.load(),{'enabled':True,'maintenance_until':123,'failed':True})

    def test_monitor_symlink_does_not_modify_victim(self):
        target=self.root/'victim';target.write_text('unchanged');target.chmod(0o644)
        (self.root/'monitor.sqlite3').symlink_to(target)
        with self.assertRaises(ValueError):Runtime(self.root,CONFIG)
        self.assertEqual(target.read_text(),'unchanged');self.assertEqual(target.stat().st_mode&0o777,0o644)

    def test_hardlink_rejected_without_permission_change(self):
        target=self.root/'victim';target.write_text('unchanged');target.chmod(0o644)
        os.link(target,self.root/'monitor.sqlite3')
        with self.assertRaises(ValueError):Runtime(self.root,CONFIG)
        self.assertEqual(target.stat().st_mode&0o777,0o644)

    def test_fifo_and_directory_rejected_without_blocking(self):
        for kind in ('fifo','directory'):
            path=self.root/kind
            if kind=='fifo':os.mkfifo(path)
            else:path.mkdir()
            with self.assertRaises(ValueError):private_database(path)

    def test_linked_journal_is_rejected_before_database_creation(self):
        target=self.root/'victim';target.write_text('unchanged')
        path=self.root/'state.sqlite3';Path(str(path)+'-journal').symlink_to(target)
        with self.assertRaises(ValueError):private_database(path)
        self.assertFalse(path.exists());self.assertEqual(target.read_text(),'unchanged')

    def test_symlinked_parent_refused_without_creating_nested_directories(self):
        real=self.root/'real';real.mkdir();link=self.root/'link';link.symlink_to(real,target_is_directory=True)
        with self.assertRaises(ValueError):Runtime(link/'nested',CONFIG)
        self.assertFalse((real/'nested').exists())

    def test_context_closes_after_commit_and_rolls_back_on_error(self):
        path=private_database(self.root/'state.sqlite3')
        db=sqlite3.connect(path,factory=PrivateConnection)
        with db:db.execute('CREATE TABLE evidence(value TEXT)');db.execute("INSERT INTO evidence VALUES ('kept')")
        with self.assertRaises(sqlite3.ProgrammingError):db.execute('SELECT 1')
        db=sqlite3.connect(path,factory=PrivateConnection)
        with self.assertRaises(RuntimeError):
            with db:
                db.execute("INSERT INTO evidence VALUES ('discarded')")
                raise RuntimeError('simulated failure')
        with self.assertRaises(sqlite3.ProgrammingError):db.execute('SELECT 1')
        with sqlite3.connect(path,factory=PrivateConnection) as check:
            self.assertEqual(check.execute('SELECT value FROM evidence').fetchall(),[('kept',)])

    def test_connection_rechecks_replacement_symlink(self):
        state=Runtime(self.root/'state',CONFIG)
        state.path.unlink();target=self.root/'victim';target.write_text('unchanged')
        state.path.symlink_to(target)
        with self.assertRaises(ValueError):state.load()
        self.assertEqual(target.read_text(),'unchanged')

    def test_freelance_and_diagnostics_reject_linked_databases(self):
        from ops_pilot.freelance import Workspace
        from ops_pilot.diagnostics import Diagnostics
        target=self.root/'victim';target.write_text('unchanged')
        directory=self.root/'freelance';directory.mkdir();(directory/'workspace.sqlite3').symlink_to(target)
        with self.assertRaises(ValueError):Workspace(self.root)
        config=self.root/'config.json';config.write_text(json.dumps({'environment':'lab','tools':{'jenkins':{'base_url':'http://127.0.0.1:8080','resource':'owned'}}}));config.chmod(0o600)
        directory=self.root/'diagnostics'/'lab';directory.mkdir(parents=True);(directory/'reports.sqlite3').symlink_to(target)
        with self.assertRaises(ValueError):Diagnostics(config,self.root)
        self.assertEqual(target.read_text(),'unchanged')
