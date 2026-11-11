"""Import the bundled history without overwriting local records. Standard library only."""
from contextlib import closing
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = '''
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS profiles (id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (run_id TEXT NOT NULL, seq INTEGER NOT NULL, data TEXT NOT NULL, PRIMARY KEY(run_id,seq));
CREATE TABLE IF NOT EXISTS reading_objects (id TEXT PRIMARY KEY, kind TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS shared_imports (digest TEXT PRIMARY KEY, imported_at TEXT DEFAULT CURRENT_TIMESTAMP);
'''

def resolve_paths(value, root):
    if isinstance(value, str): return value.replace('${PROJECT_ROOT}', root.as_posix())
    if isinstance(value, list): return [resolve_paths(v, root) for v in value]
    if isinstance(value, dict): return {k: resolve_paths(v, root) for k, v in value.items()}
    return value

def safe_child(base, relative):
    base = base.resolve()
    path = (base / relative).resolve()
    if not path.is_relative_to(base) or path == base:
        raise ValueError('Invalid note path in snapshot')
    return path

def import_history(snapshot, database, root=ROOT):
    snapshot, database, root = Path(snapshot), Path(database), Path(root).resolve()
    content = snapshot.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    payload = json.loads(content)
    if payload.get('format_version') != 1: raise ValueError('Unsupported history format')
    tables = payload['tables']
    for name in ('profiles','runs','events','reading_objects'):
        if not isinstance(tables.get(name), list): raise ValueError('Missing table: '+name)
    # Validate and read all note paths before touching the database.
    note_files = []
    for rel in payload.get('notes', []):
        source = safe_child(snapshot.parent / 'notes', rel)
        target = safe_child(root / 'backend/notes', rel)
        text = source.read_text(encoding='utf-8')
        if source.suffix == '.json':
            text = json.dumps(resolve_paths(json.loads(text), root), ensure_ascii=False, indent=2)
        else: text = resolve_paths(text, root)
        note_files.append((target,text))
    database.parent.mkdir(parents=True,exist_ok=True)
    created_files = []
    with closing(sqlite3.connect(database, timeout=30)) as db, db:
        db.executescript(SCHEMA)
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM shared_imports WHERE digest=?',(digest,)).fetchone():
            return {'already_imported': True}
        def encoded(value): return json.dumps(resolve_paths(value,root),ensure_ascii=False)
        counts = dict(profiles=0,runs=0,events=0,reading_objects=0,notes=0)
        try:
            for row in tables['profiles']:
                profile=dict(row['data']);profile['api_key']=''
                counts['profiles'] += db.execute('INSERT OR IGNORE INTO profiles VALUES (?,?)',(row['id'],encoded(profile))).rowcount
            new_runs=set()
            for row in tables['runs']:
                if db.execute('INSERT OR IGNORE INTO runs VALUES (?,?)',(row['id'],encoded(row['data']))).rowcount:
                    new_runs.add(row['id']);counts['runs']+=1
            # Never append old snapshot events to a run that has already been edited locally.
            for row in tables['events']:
                if row['run_id'] in new_runs:
                    counts['events'] += db.execute('INSERT INTO events VALUES (?,?,?)',(row['run_id'],row['seq'],encoded(row['data']))).rowcount
            for row in tables['reading_objects']:
                counts['reading_objects'] += db.execute('INSERT OR IGNORE INTO reading_objects VALUES (?,?,?)',(row['id'],row['kind'],encoded(row['data']))).rowcount
            if tables['profiles']:
                db.execute("INSERT OR IGNORE INTO meta VALUES ('profiles_imported','1')")
            for target,text in note_files:
                target.parent.mkdir(parents=True,exist_ok=True)
                try:
                    with target.open('x',encoding='utf-8') as f: f.write(text)
                except FileExistsError: continue
                created_files.append(target);counts['notes']+=1
            db.execute('INSERT INTO shared_imports(digest) VALUES (?)',(digest,))
            db.commit()
        except Exception:
            db.rollback()
            for file in created_files: file.unlink(missing_ok=True)
            raise
    return counts

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',type=Path,default=ROOT/'shared-data/history.json')
    parser.add_argument('--db',type=Path,default=ROOT/'backend/data/research.sqlite3')
    args=parser.parse_args()
    print(json.dumps(import_history(args.snapshot,args.db),ensure_ascii=False))
