"""
Attendance API - Feature 2 update.
Session start now takes dept_code, subject, faculty_id.
All Feature 1 delete endpoints kept intact.
"""

import io
import csv
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import aiosqlite

from app.services.recognition_service import (
    create_session, end_session, get_session_attendance
)
from app.models.database import DB_PATH

logger = logging.getLogger(__name__)
router = APIRouter()


class SessionIn(BaseModel):
    dept_code:  str = ""
    subject:    str = ""
    faculty_id: str = ""


@router.post("/session/start")
async def start_session(body: SessionIn):
    if not body.dept_code:
        raise HTTPException(400, "dept_code is required.")
    if not body.subject:
        raise HTTPException(400, "subject is required.")
    if not body.faculty_id:
        raise HTTPException(400, "faculty_id is required.")

    session_id = await create_session(body.dept_code, body.subject, body.faculty_id)
    return {"session_id": session_id, "subject": body.subject}


@router.post("/session/{session_id}/end")
async def stop_session(session_id: str):
    await end_session(session_id)
    return {"ok": True}


@router.get("/session/{session_id}/live")
async def live_attendance(session_id: str):
    records = await get_session_attendance(session_id)
    return {"session_id": session_id, "count": len(records), "records": records}


# ── Paginated session list (Feature 1, kept intact) ───────────────────────────

@router.get("/sessions")
async def list_sessions(offset: int = 0, limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute(
            "SELECT COUNT(*) FROM attendance_sessions WHERE is_deleted = 0"
        ) as cur:
            total = (await cur.fetchone())[0]

        async with db.execute("""
            SELECT
                s.session_id,
                s.course,
                s.teacher,
                s.dept_code,
                s.subject,
                s.faculty_id,
                d.name   AS dept_name,
                f.name   AS faculty_name,
                s.started_at,
                s.ended_at,
                s.is_active,
                COUNT(al.id) AS attendance_count
            FROM attendance_sessions s
            LEFT JOIN departments d      ON d.code       = s.dept_code
            LEFT JOIN faculty f          ON f.faculty_id = s.faculty_id
            LEFT JOIN attendance_logs al ON al.session_id = s.session_id
            WHERE s.is_deleted = 0
            GROUP BY s.session_id
            ORDER BY s.started_at DESC
            LIMIT ? OFFSET ?
        """, (limit, offset)) as cur:
            rows = await cur.fetchall()

    return {"total": total, "sessions": [dict(r) for r in rows]}


# ── Delete endpoints (Feature 1, kept intact) ─────────────────────────────────

@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE attendance_sessions SET is_deleted = 1 WHERE session_id = ?",
            (session_id,)
        )
        await db.commit()
    return {"ok": True}


@router.delete("/sessions/bulk")
async def delete_sessions_bulk(payload: dict):
    ids = payload.get("session_ids", [])
    if not ids:
        raise HTTPException(400, "No session IDs provided.")
    placeholders = ",".join("?" * len(ids))
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE attendance_sessions SET is_deleted = 1 WHERE session_id IN ({placeholders})",
            ids
        )
        await db.commit()
    return {"ok": True, "deleted": len(ids)}


@router.delete("/sessions/clear-all")
async def clear_all_sessions():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE attendance_sessions SET is_deleted = 1")
        await db.commit()
    return {"ok": True}


# ── Reports ───────────────────────────────────────────────────────────────────

@router.get("/report/today")
async def today_report():
    from datetime import date
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT s.student_id, s.name, s.course,
                   COUNT(DISTINCT al.session_id) AS sessions_attended,
                   MAX(al.marked_at) AS last_seen
            FROM students s
            LEFT JOIN attendance_logs al
                ON al.student_id = s.student_id
               AND date(al.marked_at) = ?
            WHERE s.is_active = 1
            GROUP BY s.student_id
            ORDER BY s.name
        """, (today,)) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.get("/report/export/{session_id}")
async def export_csv(session_id: str):
    records = await get_session_attendance(session_id)
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["student_id", "name", "status", "confidence", "marked_at"]
    )
    writer.writeheader()
    writer.writerows(records)
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=attendance_{session_id}.csv"
        }
    )
