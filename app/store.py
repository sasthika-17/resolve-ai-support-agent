"""Durable local state; all state transitions that matter are conditional SQL writes."""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from app.schemas import AppError


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return uuid.uuid4().hex


class Store:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / 'resolve.sqlite3'
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS customers(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tickets(id TEXT PRIMARY KEY, subject TEXT NOT NULL,
                    body TEXT NOT NULL, customer_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
                    created_at TEXT NOT NULL, resolution TEXT);
                CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, title TEXT NOT NULL,
                    text TEXT NOT NULL, created_at TEXT NOT NULL, indexed_model TEXT);
                CREATE TABLE IF NOT EXISTS chunks(id TEXT PRIMARY KEY, document_id TEXT NOT NULL,
                    title TEXT NOT NULL, text TEXT NOT NULL, embedding TEXT NOT NULL, model TEXT NOT NULL);
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(id UNINDEXED, title, text);
                CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, ticket_id TEXT NOT NULL,
                    status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    mode TEXT NOT NULL, feedback TEXT NOT NULL, snapshot TEXT, draft TEXT,
                    sources TEXT NOT NULL DEFAULT '[]', usage TEXT NOT NULL DEFAULT '{}',
                    error TEXT, error_code TEXT, review_note TEXT, elapsed_ms INTEGER NOT NULL DEFAULT 0,
                    version TEXT NOT NULL);
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_run ON runs(ticket_id)
                    WHERE status IN ('running','waiting_review','resuming');
                CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL, at TEXT NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL);
            ''')
            if 'error_code' not in {row['name'] for row in db.execute('PRAGMA table_info(runs)')}:
                db.execute('ALTER TABLE runs ADD COLUMN error_code TEXT')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def seed(self, content: dict):
        with self.connect() as db:
            for customer in content['customers']:
                db.execute('INSERT OR IGNORE INTO customers VALUES (?,?)',
                           (customer['id'], json.dumps(customer)))
            for ticket in content['tickets']:
                db.execute('INSERT OR IGNORE INTO tickets(id,subject,body,customer_id,created_at) VALUES (?,?,?,?,?)',
                           (ticket['id'], ticket['subject'], ticket['body'], ticket['customer_id'], now()))
            for doc in content['documents']:
                db.execute('INSERT OR IGNORE INTO documents VALUES (?,?,?,?,NULL)',
                           (doc['id'], doc['title'], doc['text'], now()))

    def customers(self):
        with self.connect() as db:
            return [json.loads(r['data']) for r in db.execute('SELECT data FROM customers')]

    def customer(self, customer_id):
        with self.connect() as db:
            row = db.execute('SELECT data FROM customers WHERE id=?', (customer_id,)).fetchone()
        if not row:
            raise AppError('Customer not found.', 404, 'customer_missing')
        return json.loads(row['data'])

    def tickets(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT id,subject,body,customer_id,status,created_at FROM tickets ORDER BY created_at DESC, id')]

    def ticket(self, ticket_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM tickets WHERE id=?', (ticket_id,)).fetchone()
        if not row:
            raise AppError('Ticket not found.', 404, 'ticket_missing')
        ticket = dict(row)
        ticket['resolution'] = json.loads(ticket['resolution']) if ticket['resolution'] else None
        ticket['customer'] = self.customer(ticket['customer_id'])
        with self.connect() as db:
            ticket['runs'] = [r['id'] for r in db.execute('SELECT id FROM runs WHERE ticket_id=? ORDER BY created_at DESC', (ticket_id,))]
        return ticket

    def add_ticket(self, ticket):
        self.customer(ticket.customer_id)
        identifier = uid()
        with self.connect() as db:
            db.execute('INSERT INTO tickets(id,subject,body,customer_id,created_at) VALUES (?,?,?,?,?)',
                       (identifier, ticket.subject, ticket.body, ticket.customer_id, now()))
        return self.ticket(identifier)

    def documents(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT d.*, (SELECT count(*) FROM chunks c WHERE c.document_id=d.id) AS chunks FROM documents d ORDER BY created_at, id')]

    def add_document(self, document):
        identifier = uid()
        with self.connect() as db:
            if db.execute('SELECT count(*) FROM documents').fetchone()[0] >= 50:
                raise AppError('This local workspace supports up to 50 documents.', 413, 'document_limit')
            db.execute('INSERT INTO documents VALUES (?,?,?,?,NULL)',
                       (identifier, document.title, document.text, now()))
        return identifier

    def create_run(self, ticket_id, mode, feedback, version):
        identifier = uid()
        try:
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                ticket = db.execute('SELECT status FROM tickets WHERE id=?', (ticket_id,)).fetchone()
                if ticket is None:
                    raise AppError('Ticket not found.', 404, 'ticket_missing')
                if ticket['status'] != 'open':
                    raise AppError('This ticket already has an approved resolution. Create a new ticket for a follow-up.', 409, 'ticket_closed')
                db.execute('INSERT INTO runs(id,ticket_id,status,created_at,updated_at,mode,feedback,version) VALUES (?,?,?,?,?,?,?,?)',
                           (identifier, ticket_id, 'running', now(), now(), mode, feedback, version))
        except sqlite3.IntegrityError:
            raise AppError('Finish or reject the current run before starting another.', 409, 'run_active') from None
        self.event(identifier, 'started', 'Agent run started. No resolution has been recorded.')
        return identifier

    def run(self, run_id, private=False):
        with self.connect() as db:
            row = db.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
            events = [dict(e) for e in db.execute('SELECT at,kind,detail FROM events WHERE run_id=? ORDER BY id', (run_id,))]
        if not row:
            raise AppError('Run not found.', 404, 'run_missing')
        result = dict(row)
        for name in ['draft', 'sources', 'usage']:
            result[name] = json.loads(result[name]) if result[name] else None
        if not private:
            result.pop('snapshot')
        result['events'] = events
        return result

    def event(self, run_id, kind, detail):
        with self.connect() as db:
            db.execute('INSERT INTO events(run_id,at,kind,detail) VALUES (?,?,?,?)', (run_id, now(), kind, detail[:3000]))

    def save_sources(self, run_id, passages):
        with self.connect() as db:
            row = db.execute('SELECT sources FROM runs WHERE id=?', (run_id,)).fetchone()
            existing = {s['source_id']: s for s in json.loads(row['sources'])}
            existing.update({s['source_id']: s for s in passages})
            db.execute('UPDATE runs SET sources=?,updated_at=? WHERE id=?', (json.dumps(list(existing.values())), now(), run_id))

    def waiting(self, run_id, snapshot, draft, usage, elapsed):
        with self.connect() as db:
            cursor = db.execute("UPDATE runs SET status='waiting_review',snapshot=?,draft=?,usage=?,elapsed_ms=?,updated_at=? WHERE id=? AND status='running'",
                                (snapshot, json.dumps(draft), json.dumps(usage), elapsed, now(), run_id))
            if cursor.rowcount != 1:
                raise AppError('The run no longer accepts a draft.', 409, 'run_changed')
        self.event(run_id, 'review_required', 'Draft validated. The write tool is paused for human approval.')

    def claim_review(self, run_id, note):
        with self.connect() as db:
            cursor = db.execute("UPDATE runs SET status='resuming',review_note=?,updated_at=? WHERE id=? AND status='waiting_review'", (note, now(), run_id))
            if cursor.rowcount != 1:
                raise AppError('This review was already handled or is not ready.', 409, 'review_conflict')

    def commit_resolution(self, run_id, resolution):
        # Idempotency and byte-equivalent draft checks protect against replay and changed arguments.
        with self.connect() as db:
            row = db.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
            if row['status'] == 'approved':
                return
            if row['status'] != 'resuming' or json.loads(row['draft']) != resolution:
                raise AppError('Only the exact human-approved draft may be recorded.', 409, 'approval_mismatch')
            cursor = db.execute("UPDATE tickets SET status=?,resolution=? WHERE id=? AND status='open'",
                                (resolution['disposition'], json.dumps(resolution), row['ticket_id']))
            if cursor.rowcount != 1:
                raise AppError('Ticket was already resolved.', 409, 'ticket_closed')
            db.execute("UPDATE runs SET status='approved',snapshot=NULL,updated_at=? WHERE id=?", (now(), run_id))
        self.event(run_id, 'approved', 'Human-approved resolution recorded locally. No customer message was sent.')

    def reject(self, run_id, snapshot):
        with self.connect() as db:
            db.execute("UPDATE runs SET status='rejected',snapshot=?,updated_at=? WHERE id=? AND status='resuming'", (snapshot, now(), run_id))
        self.event(run_id, 'rejected', 'Draft rejected. No resolution was recorded; the ticket remains open.')

    def fail(self, run_id, message, code='agent_failed'):
        with self.connect() as db:
            db.execute("UPDATE runs SET status='failed',error=?,error_code=?,snapshot=NULL,updated_at=? WHERE id=? AND status IN ('running','resuming')", (message, code, now(), run_id))
        self.event(run_id, 'error', message)

    def recover_interrupted(self):
        with self.connect() as db:
            db.execute("UPDATE runs SET status='failed',error='Local server stopped during execution. Start a new run.',error_code='server_interrupted',snapshot=NULL,updated_at=? WHERE status IN ('running','resuming')", (now(),))
