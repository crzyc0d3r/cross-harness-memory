"""Local, explicitly stated text memory; scope checks live below the harness."""
from __future__ import annotations

from datetime import datetime, timezone
from contextlib import contextmanager
import json
import re
import sqlite3
import uuid


def words(text):
    return set(re.findall(r"\w+", text.casefold()))


class LocalMemory:
    """One SQLite file, independent private roots, no model or automatic extraction."""

    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL UNIQUE);
            CREATE TABLE IF NOT EXISTS records (
                ordinal INTEGER PRIMARY KEY AUTOINCREMENT,
                id TEXT NOT NULL UNIQUE, memory_id TEXT NOT NULL,
                body TEXT NOT NULL, dedup TEXT,
                FOREIGN KEY(memory_id) REFERENCES memories(id),
                UNIQUE(memory_id, dedup));
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path)
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def for_user(self, user):
        """Trusted host binds identity here; a prompt cannot select its owner."""
        if not isinstance(user, str) or not user.strip():
            raise ValueError("A nonempty trusted user identity is required")
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO memories VALUES (?,?)",
                       ("hmem_" + uuid.uuid4().hex, user))
            mid = db.execute("SELECT id FROM memories WHERE owner=?", (user,)).fetchone()[0]
        return BoundMemory(self, user, mid)


class BoundMemory:
    """A host-created scope is reused across any number of harness sessions."""

    def __init__(self, store, owner, memory_id):
        self.store, self.owner, self.memory_id = store, owner, memory_id

    def _check(self, db):
        if not db.execute("SELECT 1 FROM memories WHERE id=? AND owner=?",
                          (self.memory_id, self.owner)).fetchone():
            raise PermissionError("memory_not_found")

    def remember(self, text, *, writer, standing=False, record_type="fact", dedup=None,
                 attributes=None, parts=None, writer_type="agent"):
        if not isinstance(text, str) or not text.strip() or len(text) > 16000:
            raise ValueError("Text must contain 1–16000 characters")
        if record_type not in {"fact", "episode"}:
            raise ValueError("This local example keeps facts and episodes only")
        if not isinstance(writer, str) or not writer.strip():
            raise ValueError("A writer is required")
        if writer_type not in {"human", "agent"}:
            raise ValueError("Writer type must be human or agent")
        if standing and writer_type != "human":
            raise PermissionError("Only a person may set a standing preference")
        if standing and record_type != "fact":
            raise ValueError("Only an explicit fact is standing in this example")
        record = {"id": "hrec_" + uuid.uuid4().hex, "object": "memory.record",
                  "memory_id": self.memory_id, "type": record_type,
                  "title": text[:120], "content": parts or [{"type": "text", "text": text}],
                  "attributes": {**(attributes or {}), "standing": bool(standing)},
                  "version": 1, "status": "active", "supersedes": None,
                  "time": {"written_at": datetime.now(timezone.utc).isoformat(),
                           "valid_from": None, "valid_to": None, "invalidated_at": None},
                  "written_by": {"kind": "member", "id": writer, "type": writer_type},
                  "references": [], "trust": "untrusted"}
        with self.store.connect() as db:
            self._check(db)
            if dedup is not None:
                old = db.execute("SELECT body FROM records WHERE memory_id=? AND dedup=?",
                                 (self.memory_id, dedup)).fetchone()
                if old:
                    return json.loads(old[0])
            db.execute("INSERT INTO records(id,memory_id,body,dedup) VALUES (?,?,?,?)",
                       (record["id"], self.memory_id, json.dumps(record), dedup))
        return record

    def all(self):
        with self.store.connect() as db:
            self._check(db)
            rows = db.execute("SELECT body FROM records WHERE memory_id=? ORDER BY ordinal DESC",
                              (self.memory_id,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def prime(self, budget=4000):
        if type(budget) is not int or budget < 1:
            raise ValueError("budget must be a positive integer")
        out, used = [], 0
        standing = [r for r in self.all() if r["attributes"]["standing"]]
        for record in standing:
            cost = max(1, (len(json.dumps(record)) + 3) // 4)
            if out and used + cost > budget:
                break
            out.append(record)
            used += cost
        return {"object": "memory.prime", "records": out, "tokens": used,
                "truncated": len(out) < len(standing)}

    def recall(self, query, limit=8):
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be nonempty text")
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("limit must be an integer from 1 to 50")
        wanted, matches = words(query), []
        for record in self.all():
            tokens = words(" ".join(p["text"] for p in record["content"]))
            overlap = len(wanted & tokens)
            if overlap:
                matches.append({"record": record,
                                "memory": {"id": self.memory_id, "name": "Private memory"},
                                "score": overlap / len(wanted), "why": ["text"]})
        matches.sort(key=lambda m: m["score"], reverse=True)
        return {"results": matches[:limit], "children": [], "degraded": ["query:lexical_only"],
                "abstain": not matches}

    def observe(self, user_text, answer, *, session_id, turn_id, writer):
        parts = [{"type": "text", "role": "user", "text": user_text},
                 {"type": "text", "role": "assistant", "text": answer}]
        return self.remember(user_text + "\n" + answer, writer=writer, record_type="episode",
                             dedup=f"turn:{session_id}:{turn_id}", parts=parts,
                             attributes={"session": session_id, "turn": turn_id})
