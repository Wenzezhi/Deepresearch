"""Local SQLite persistence. API responses never include model credentials."""
import json
import os
import sqlite3
from pathlib import Path
from uuid import uuid4
from contextlib import contextmanager
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv("RESEARCH_DB_PATH") or Path(__file__).resolve().parents[1] / "data/research.sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE IF NOT EXISTS profiles (id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (run_id TEXT NOT NULL, seq INTEGER NOT NULL, data TEXT NOT NULL, PRIMARY KEY(run_id,seq));
                CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY,data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS document_chunks (id INTEGER PRIMARY KEY AUTOINCREMENT,document_id TEXT NOT NULL,chunk_index INTEGER NOT NULL,page_start INTEGER,page_end INTEGER,content TEXT NOT NULL,FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,UNIQUE(document_id, chunk_index));
                CREATE INDEX IF NOT EXISTS idx_document_chunks_document ON document_chunks(document_id);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def public(profile):
        return {**{k: v for k, v in profile.items() if k != "api_key"}, "has_api_key": bool(profile.get("api_key"))}

    def bootstrap(self, config):
        with self.connect() as db:
            if db.execute("SELECT 1 FROM meta WHERE key='profiles_imported'").fetchone():
                return
            if not db.execute("SELECT 1 FROM profiles LIMIT 1").fetchone():
                base = config.llm_base_url
                if config.llm_provider == "ollama": base = config.sanitized_ollama_url()
                elif config.llm_provider == "lmstudio": base = config.lmstudio_base_url
                if base:
                    p = dict(id=uuid4().hex, name="默认模型", base_url=base, model_id=config.resolved_model(), api_key=config.llm_api_key or "", max_tokens=config.llm_max_tokens, timeout=config.llm_timeout, created_at=now())
                    db.execute("INSERT INTO profiles VALUES (?,?)", (p['id'], json.dumps(p)))
            db.execute("INSERT INTO meta VALUES ('profiles_imported','1')")

    def profiles(self):
        with self.connect() as db:
            return [self.public(json.loads(row['data'])) for row in db.execute("SELECT data FROM profiles ORDER BY rowid")]

    def profile(self, identifier):
        with self.connect() as db:
            row = db.execute("SELECT data FROM profiles WHERE id=?", (identifier,)).fetchone()
        if row is None: raise KeyError("模型配置不存在，请重新选择")
        return json.loads(row['data'])

    def save_profile(self, values, identifier=None):
        p = self.profile(identifier) if identifier else dict(id=uuid4().hex, created_at=now(), api_key="")
        # A blank key when editing preserves the existing secret.
        if not values.get('api_key'): values = {k: v for k, v in values.items() if k != 'api_key'}
        p.update(values)
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO profiles VALUES (?,?)", (p['id'], json.dumps(p)))
        return self.public(p)

    def delete_profile(self, identifier):
        self.profile(identifier)
        with self.connect() as db: db.execute("DELETE FROM profiles WHERE id=?", (identifier,))

    # def create_run(self, topic, profile, search_api, identifier=None):
    #     record = dict(id=identifier or uuid4().hex, title=topic, topic=topic, profile=profile,
    #                   search_api=search_api, status='running', created_at=now(), updated_at=now(), error=None)
    #     with self.connect() as db:
    #         db.execute("INSERT INTO runs VALUES (?,?)", (record['id'], json.dumps(record)))
    #     return record

    def create_run(
            self,
            topic,
            profile,
            search_api,
            identifier=None,
            document_ids=None
    ):
        record = dict(
            id=identifier or uuid4().hex,
            title=topic,
            topic=topic,
            profile=profile,
            search_api=search_api,
            document_ids=list(document_ids or []),
            status="running",
            created_at=now(),
            updated_at=now(),
            error=None
        )

        with self.connect() as db:
            db.execute(
                "INSERT INTO runs VALUES (?,?)",
                (
                    record["id"],
                    json.dumps(record)
                )
            )

        return record

    def run(self, identifier):
        with self.connect() as db:
            row=db.execute("SELECT data FROM runs WHERE id=?", (identifier,)).fetchone()
        if row is None: raise KeyError('研究记录不存在')
        return json.loads(row['data'])

    def runs(self, query=''):
        with self.connect() as db:
            records=[json.loads(r['data']) for r in db.execute("SELECT data FROM runs ORDER BY rowid DESC")]
        return [r for r in records if query.casefold() in (r['title']+' '+r['topic']).casefold()]

    def update_run(self, identifier, **values):
        with self.connect() as db:
            row=db.execute("SELECT data FROM runs WHERE id=?",(identifier,)).fetchone()
            if row is None: raise KeyError('研究记录不存在')
            record=json.loads(row['data']);record.update(values)
            db.execute("UPDATE runs SET data=? WHERE id=?",(json.dumps(record),identifier))
        return record

    def append_events(self, identifier, events):
        if not events: return
        with self.connect() as db:
            seq=db.execute("SELECT COALESCE(MAX(seq),0) FROM events WHERE run_id=?",(identifier,)).fetchone()[0]
            db.executemany("INSERT INTO events VALUES (?,?,?)",[(identifier,seq+i+1,json.dumps(e,ensure_ascii=False)) for i,e in enumerate(events)])

    def events(self, identifier, after=0):
        with self.connect() as db:
            return [dict(seq=r['seq'],event=json.loads(r['data'])) for r in db.execute("SELECT seq,data FROM events WHERE run_id=? AND seq>? ORDER BY seq LIMIT 1000",(identifier,after))]

    def delete_run(self, identifier):
        with self.connect() as db:
            row=db.execute("SELECT data FROM runs WHERE id=?",(identifier,)).fetchone()
            if row is None: raise KeyError('研究记录不存在')
            if json.loads(row['data'])['status']=='running': raise ValueError('运行中的研究暂不能删除，请等待结束')
            db.execute("DELETE FROM events WHERE run_id=?",(identifier,))
            db.execute("DELETE FROM runs WHERE id=?",(identifier,))

    # ---------------- 本地文献数据库操作 ----------------

    def save_document(self, record, chunks):
        """保存文献信息和文本片段。"""

        with self.connect() as db:
            db.execute(
                "INSERT INTO documents VALUES (?,?)",
                (
                    record["id"],
                    json.dumps(record, ensure_ascii=False)
                )
            )

            db.executemany(
                """
                INSERT INTO document_chunks
                (
                    document_id,
                    chunk_index,
                    page_start,
                    page_end,
                    content
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        record["id"],
                        item["chunk_index"],
                        item.get("page_start"),
                        item.get("page_end"),
                        item["content"]
                    )
                    for item in chunks
                ],
            )

    def documents(self):
        """获取全部文献。"""

        with self.connect() as db:
            rows = db.execute(
                "SELECT data FROM documents ORDER BY rowid DESC"
            ).fetchall()

        return [
            json.loads(row["data"])
            for row in rows
        ]

    def document(self, identifier):
        """根据 ID 获取文献。"""

        with self.connect() as db:
            row = db.execute(
                "SELECT data FROM documents WHERE id=?",
                (identifier,)
            ).fetchone()

        if row is None:
            raise KeyError("本地文献不存在")

        return json.loads(row["data"])

    def find_document_by_hash(self, sha256):
        """根据文件哈希检查重复文献。"""

        with self.connect() as db:

            rows = db.execute(
                "SELECT data FROM documents"
            ).fetchall()

        for row in rows:

            item = json.loads(row["data"])

            if item.get("sha256") == sha256:
                return item

        return None

    def document_chunks(self, identifiers):
        """获取所选文献的全部文本片段。"""

        identifiers = list(
            dict.fromkeys(identifiers or [])
        )

        if not identifiers:
            return []

        placeholders = ",".join(
            "?" for _ in identifiers
        )

        with self.connect() as db:
            rows = db.execute(
                f"""
                SELECT
                    c.document_id,
                    c.chunk_index,
                    c.page_start,
                    c.page_end,
                    c.content,
                    d.data AS document_data

                FROM document_chunks c

                JOIN documents d
                    ON d.id = c.document_id

                WHERE c.document_id IN ({placeholders})

                ORDER BY
                    c.document_id,
                    c.chunk_index
                """,
                identifiers
            ).fetchall()

        return [
            {
                "document_id": row["document_id"],
                "chunk_index": row["chunk_index"],
                "page_start": row["page_start"],
                "page_end": row["page_end"],
                "content": row["content"],
                "document": json.loads(row["document_data"]),
            }
            for row in rows
        ]

    def delete_document(self, identifier):
        """删除文献和对应文本片段。"""

        with self.connect() as db:
            row = db.execute(
                "SELECT data FROM documents WHERE id=?",
                (identifier,)
            ).fetchone()

            if row is None:
                raise KeyError("本地文献不存在")

            record = json.loads(row["data"])

            db.execute(
                "DELETE FROM document_chunks WHERE document_id=?",
                (identifier,)
            )

            db.execute(
                "DELETE FROM documents WHERE id=?",
                (identifier,)
            )

        return record

    def recover_runs(self):
        for r in self.runs():
            if r['status']=='running':
                self.append_events(r['id'],[{'type':'error','detail':'后端服务已重启，本次研究中断；已保存此前内容。'}])
                self.update_run(r['id'],status='interrupted',error='后端服务已重启，本次研究中断',ended_at=r['updated_at'],timing_active={})
