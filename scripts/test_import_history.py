from contextlib import closing
import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('importer', ROOT/'scripts/import-history.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class HistoryImportTest(unittest.TestCase):
    def test_actual_snapshot_and_repeat_preserves_local_changes(self):
        snapshot=ROOT/'shared-data/history.json'
        payload=json.loads(snapshot.read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);database=root/'backend/data/research.sqlite3'
            counts=module.import_history(snapshot,database,root)
            for table in ('profiles','runs','events','reading_objects'):
                self.assertEqual(counts[table],len(payload['tables'][table]))
            with closing(sqlite3.connect(database)) as db, db:
                for (data,) in db.execute('SELECT data FROM profiles'):
                    self.assertEqual(json.loads(data)['api_key'],'')
                first=payload['tables']['runs'][0]['id']
                db.execute('UPDATE runs SET data=? WHERE id=?',('{"local":"edited"}',first))
                db.execute("INSERT INTO reading_objects VALUES ('new-chat','conversation','{}')")
            self.assertTrue(module.import_history(snapshot,database,root)['already_imported'])
            with closing(sqlite3.connect(database)) as db, db:
                self.assertEqual(db.execute('SELECT data FROM runs WHERE id=?',(first,)).fetchone()[0],'{"local":"edited"}')
                self.assertIsNotNone(db.execute("SELECT 1 FROM reading_objects WHERE id='new-chat'").fetchone())
            self.assertEqual(len(list((root/'backend/notes').rglob('*.*'))),len(payload['notes']))

    def test_collision_does_not_append_old_events(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);dbpath=root/'data.sqlite3'
            payload=json.loads((ROOT/'shared-data/history.json').read_text(encoding='utf-8'))
            first=payload['tables']['runs'][0]['id']
            with closing(sqlite3.connect(dbpath)) as db, db:
                db.executescript(module.SCHEMA)
                db.execute('INSERT INTO runs VALUES (?,?)',(first,'{"local":true}'))
                db.execute('INSERT INTO events VALUES (?,?,?)',(first,1,'{"type":"local"}'))
            module.import_history(ROOT/'shared-data/history.json',dbpath,root)
            with closing(sqlite3.connect(dbpath)) as db, db:
                self.assertEqual(db.execute('SELECT data FROM events WHERE run_id=?',(first,)).fetchall(),[('{"type":"local"}',)])

    def test_reject_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with self.assertRaises(ValueError):module.safe_child(root,'../escape')
            self.assertEqual(module.resolve_paths('${PROJECT_ROOT}/backend/notes/a.md',root),root.as_posix()+'/backend/notes/a.md')

if __name__=='__main__':unittest.main()
