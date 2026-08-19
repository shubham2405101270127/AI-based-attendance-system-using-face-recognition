"""Dashboard analytics API."""

from fastapi import APIRouter
from app.models.database import DB_PATH
import aiosqlite

router = APIRouter()


@router.get("/stats")
async def dashboard_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute("SELECT COUNT(*) AS c FROM students WHERE is_active=1") as cur:
            total_students = (await cur.fetchone())["c"]

        async with db.execute(
            "SELECT COUNT(*) AS c FROM attendance_sessions WHERE date(started_at)=date('now')"
        ) as cur:
            sessions_today = (await cur.fetchone())["c"]

        async with db.execute("""
            SELECT COUNT(DISTINCT al.student_id) AS c
            FROM attendance_logs al
            WHERE date(al.marked_at) = date('now')
        """) as cur:
            present_today = (await cur.fetchone())["c"]

        async with db.execute("""
            SELECT s.name, COUNT(al.id) AS absences
            FROM students s
            LEFT JOIN attendance_logs al ON al.student_id = s.student_id
            WHERE s.is_active = 1
            GROUP BY s.student_id
            ORDER BY absences ASC
            LIMIT 5
        """) as cur:
            top_absentees = [dict(r) for r in await cur.fetchall()]

        async with db.execute("""
            SELECT date(al.marked_at) AS day, COUNT(DISTINCT al.student_id) AS count
            FROM attendance_logs al
            GROUP BY day
            ORDER BY day DESC
            LIMIT 14
        """) as cur:
            daily_trend = [dict(r) for r in await cur.fetchall()]

    attendance_rate = round(present_today / total_students * 100, 1) if total_students else 0

    return {
        "total_students": total_students,
        "sessions_today": sessions_today,
        "present_today": present_today,
        "absent_today": total_students - present_today,
        "attendance_rate": attendance_rate,
        "top_absentees": top_absentees,
        "daily_trend": list(reversed(daily_trend)),
    }
