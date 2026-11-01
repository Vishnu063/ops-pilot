"""Filesystem/SQLite integration tests, independent of external services/sockets."""
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from ops_pilot.storage import private_database, PrivateConnection
from ops_pilot.runtime import Runtime
from types import SimpleNamespace
from unittest.mock import Mock

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

    def hub(self, directory=None):
        from ops_pilot.ecosystem import EventHub
        pilot=SimpleNamespace(config={'name':'synthetic','container':'owned'},health={'url':'http://127.0.0.1:8080'},action=Mock())
        return EventHub(pilot,directory or self.root,'synthetic')

    def test_ecosystem_symlinked_directory_is_refused_before_chmod(self):
        victim=self.root/'victim';victim.mkdir();victim.chmod(0o755)
        (self.root/'ecosystem').symlink_to(victim,target_is_directory=True)
        with self.assertRaises(ValueError):self.hub()
        self.assertEqual(0o755,victim.stat().st_mode&0o777)
        self.assertFalse((victim/'events.sqlite3').exists())

    def test_ecosystem_database_and_journal_links_are_refused(self):
        for kind in ('symlink','hardlink','journal'):
            with self.subTest(kind=kind):
                directory=self.root/kind;state=directory/'ecosystem';state.mkdir(parents=True)
                victim=directory/'victim';victim.write_text('unchanged');victim.chmod(0o644)
                path=state/'events.sqlite3'
                if kind=='hardlink':os.link(victim,path)
                else:Path(str(path)+('-journal' if kind=='journal' else '')).symlink_to(victim)
                with self.assertRaises(ValueError):self.hub(directory)
                self.assertEqual('unchanged',victim.read_text())
                self.assertEqual(0o644,victim.stat().st_mode&0o777)

    def test_ecosystem_connection_rechecks_replacement_and_closes(self):
        hub=self.hub();db=hub.connect()
        with db:self.assertEqual((1,),db.execute('SELECT 1').fetchone())
        with self.assertRaises(sqlite3.ProgrammingError):db.execute('SELECT 1')
        hub.path.unlink();victim=self.root/'victim';victim.write_text('unchanged')
        hub.path.symlink_to(victim)
        with self.assertRaises(ValueError):hub.state()
        self.assertEqual('unchanged',victim.read_text())

    def test_ecosystem_reopen_repairs_modes_and_preserves_audit(self):
        hub=self.hub()
        with hub.connect() as db:hub._audit(db,None,'test','synthetic',{'observed':True})
        hub.path.chmod(0o666);hub.root.chmod(0o755)
        reopened=self.hub()
        self.assertEqual(0o600,reopened.path.stat().st_mode&0o777)
        self.assertEqual(0o700,reopened.root.stat().st_mode&0o777)
        self.assertEqual('synthetic',reopened.state()['audit'][0]['action'])

    def test_ecosystem_operation_lock_cannot_follow_symlink(self):
        hub=self.hub();victim=self.root/'victim';victim.write_text('unchanged')
        (hub.root/'operation.lock').symlink_to(victim)
        payload=dict(incident_id='a'*24,revision=1,action='investigate',plan_id=None)
        with self.assertRaises(ValueError):hub.action(payload)
        self.assertFalse(hub.pilot.action.called)
        self.assertEqual('unchanged',victim.read_text())
