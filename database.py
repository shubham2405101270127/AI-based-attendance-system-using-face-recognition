"""
Database - Feature 3 fixed.
Uses individual execute() calls throughout — no executescript for indexes.
This avoids SQLite's executescript running indexes before migrations complete.
"""

import aiosqlite
import os

DB_PATH = "data/attendance.db"


async def init_db():
    os.makedirs("data", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:

        await db.execute("PRAGMA journal_mode=WAL")

        # ── Step 1: Core tables ───────────────────────────────────────────────

        await db.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id    TEXT    UNIQUE NOT NULL,
                name          TEXT    NOT NULL,
                email         TEXT    DEFAULT '',
                course        TEXT    DEFAULT '',
                photo_count   INTEGER DEFAULT 0,
                enrolled_at   TEXT    DEFAULT (datetime('now')),
                is_active     INTEGER DEFAULT 1
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS face_embeddings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id  TEXT    NOT NULL REFERENCES students(student_id),
                embedding   BLOB    NOT NULL,
                captured_at TEXT    DEFAULT (datetime('now'))
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS departments (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                code       TEXT    UNIQUE NOT NULL,
                name       TEXT    UNIQUE NOT NULL,
                created_at TEXT    DEFAULT (datetime('now'))
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS subjects (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT    NOT NULL,
                dept_code  TEXT    NOT NULL REFERENCES departments(code),
                created_at TEXT    DEFAULT (datetime('now')),
                UNIQUE(name, dept_code)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS faculty (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                faculty_id TEXT    UNIQUE NOT NULL,
                name       TEXT    NOT NULL,
                dept_code  TEXT    NOT NULL REFERENCES departments(code),
                email      TEXT    DEFAULT '',
                created_at TEXT    DEFAULT (datetime('now')),
                is_active  INTEGER DEFAULT 1
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS attendance_sessions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT    UNIQUE NOT NULL,
                course      TEXT,
                teacher     TEXT,
                started_at  TEXT    DEFAULT (datetime('now')),
                ended_at    TEXT,
                is_active   INTEGER DEFAULT 1
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS attendance_logs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT    NOT NULL REFERENCES attendance_sessions(session_id),
                student_id  TEXT    NOT NULL REFERENCES students(student_id),
                status      TEXT    DEFAULT 'present',
                confidence  REAL,
                marked_at   TEXT    DEFAULT (datetime('now')),
                UNIQUE(session_id, student_id)
            )
        """)

        await db.commit()

        # ── Step 2: Migrations — each wrapped individually ────────────────────
        # Safe to re-run: exception means column already exists, we skip it.

        migrations = [
            # Feature 1
            "ALTER TABLE attendance_sessions ADD COLUMN is_deleted  INTEGER DEFAULT 0",
            # Feature 2
            "ALTER TABLE attendance_sessions ADD COLUMN dept_code   TEXT",
            "ALTER TABLE attendance_sessions ADD COLUMN subject     TEXT",
            "ALTER TABLE attendance_sessions ADD COLUMN faculty_id  TEXT",
            # Feature 3
            "ALTER TABLE students ADD COLUMN city          TEXT DEFAULT ''",
            "ALTER TABLE students ADD COLUMN dept_code     TEXT",
            "ALTER TABLE students ADD COLUMN phone         TEXT DEFAULT ''",
            "ALTER TABLE students ADD COLUMN guardian_type TEXT DEFAULT 'Father'",
            "ALTER TABLE students ADD COLUMN guardian_rel  TEXT DEFAULT ''",
        ]

        for sql in migrations:
            try:
                await db.execute(sql)
                await db.commit()
            except Exception:
                pass  # column already exists — ignore

        # ── Step 3: Indexes — individual execute() after all migrations done ──
        # Using individual calls so a failure on one doesn't block the others.

        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_logs_session  ON attendance_logs(session_id)",
            "CREATE INDEX IF NOT EXISTS idx_logs_student  ON attendance_logs(student_id)",
            "CREATE INDEX IF NOT EXISTS idx_embed_student ON face_embeddings(student_id)",
            "CREATE INDEX IF NOT EXISTS idx_subjects_dept ON subjects(dept_code)",
            "CREATE INDEX IF NOT EXISTS idx_faculty_dept  ON faculty(dept_code)",
            "CREATE INDEX IF NOT EXISTS idx_students_dept ON students(dept_code)",
        ]

        for sql in indexes:
            try:
                await db.execute(sql)
                await db.commit()
            except Exception:
                pass  # index already exists — ignore

        await db.commit()

    print(f"[DB] Initialized at {DB_PATH}")


async def get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db
