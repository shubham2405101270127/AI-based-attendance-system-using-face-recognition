"""
Recognition Service - Feature 2 update.
create_session now accepts dept_code, subject, faculty_id.
Keeps backward compat: course/teacher still stored for old sessions.
"""

import pickle
import uuid
import logging

import aiosqlite

from app.core.face_engine import face_engine
from app.models.database import DB_PATH

logger = logging.getLogger(__name__)


async def reload_embeddings():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT fe.student_id, s.name, fe.embedding
            FROM face_embeddings fe
            JOIN students s ON s.student_id = fe.student_id
            WHERE s.is_active = 1
        """) as cur:
            rows = await cur.fetchall()
    records = [dict(r) for r in rows]
    face_engine.load_embeddings(records)
    logger.info(f"[Service] Reloaded {len(records)} embeddings.")
    return len(records)


async def create_session(
    dept_code:  str,
    subject:    str,
    faculty_id: str,
) -> str:
    session_id = str(uuid.uuid4())[:8].upper()

    # Also resolve faculty name to store in legacy 'teacher' column
    # so old dashboard queries still work during transition
    faculty_name = ""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT name FROM faculty WHERE faculty_id=?", (faculty_id,)
        ) as cur:
            row = await cur.fetchone()
        if row:
            faculty_name = row["name"]

        # Also resolve dept name for legacy 'course' column
        async with db.execute(
            "SELECT name FROM departments WHERE code=?", (dept_code,)
        ) as cur:
            row = await cur.fetchone()
        dept_name = row["name"] if row else dept_code

        await db.execute(
            """INSERT INTO attendance_sessions
               (session_id, course, teacher, dept_code, subject, faculty_id)
               VALUES (?,?,?,?,?,?)""",
            (session_id, f"{dept_name} - {subject}", faculty_name,
             dept_code, subject, faculty_id)
        )
        await db.commit()

    await reload_embeddings()
    logger.info(f"[Service] Session {session_id} created: {dept_code}/{subject}/{faculty_id}")
    return session_id


async def end_session(session_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE attendance_sessions SET ended_at=datetime('now'), is_active=0 WHERE session_id=?",
            (session_id,)
        )
        await db.commit()
    face_engine.reset_session(session_id)


async def mark_present(session_id: str, student_id: str, confidence: float) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM attendance_sessions WHERE session_id=? AND is_active=1",
            (session_id,)
        ) as cur:
            if not await cur.fetchone():
                return False
        try:
            await db.execute(
                """INSERT OR IGNORE INTO attendance_logs (session_id, student_id, confidence)
                   VALUES (?,?,?)""",
                (session_id, student_id, confidence)
            )
            await db.commit()
            return True
        except Exception as e:
            logger.error(f"[Service] mark_present error: {e}")
            return False


async def get_session_attendance(session_id: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT al.student_id, s.name, al.confidence, al.marked_at, al.status
            FROM attendance_logs al
            JOIN students s ON s.student_id = al.student_id
            WHERE al.session_id = ?
            ORDER BY al.marked_at DESC
        """, (session_id,)) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def save_face_embedding(student_id: str, embedding) -> bool:
    blob = pickle.dumps(embedding)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO face_embeddings (student_id, embedding) VALUES (?,?)",
            (student_id, blob)
        )
        await db.execute(
            "UPDATE students SET photo_count = photo_count + 1 WHERE student_id=?",
            (student_id,)
        )
        await db.commit()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT name FROM students WHERE student_id=?", (student_id,)
        ) as cur:
            row = await cur.fetchone()
    if row:
        face_engine.add_embedding(student_id, row["name"], embedding)
    return True
