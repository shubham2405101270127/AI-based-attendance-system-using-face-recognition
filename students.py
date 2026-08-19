"""
Students API - Feature 3 update.
- New register endpoint: name, city, dept_code, phone, guardian fields
- Roll number auto-generated: 26 + dept_code + sequential 2-digit
- Updated list and profile endpoints return all new fields
- All Feature 2 meta endpoints kept intact
"""

import cv2
import numpy as np
import base64
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import aiosqlite

from app.services.recognition_service import (
    save_face_embedding, reload_embeddings
)
from app.models.database import DB_PATH

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Pydantic models ───────────────────────────────────────────────────────────

class StudentIn(BaseModel):
    name:          str
    city:          str  = ""
    dept_code:     str  = ""
    phone:         str  = ""
    guardian_type: str  = "Father"   # Mother | Father | Guardian
    guardian_rel:  str  = ""         # filled only when guardian_type == Guardian


class FaceCaptureIn(BaseModel):
    student_id: str
    image_b64:  str


class NewDeptIn(BaseModel):
    code: str
    name: str


class NewSubjectIn(BaseModel):
    name:      str
    dept_code: str


class NewFacultyIn(BaseModel):
    name:      str
    dept_code: str
    email:     str = ""


# ── Roll number generator ─────────────────────────────────────────────────────

async def _next_roll(dept_code: str) -> str:
    """
    Format: 26 + dept_code (2 digits) + sequence (2 digits, zero-padded).
    Example: BCA (01) first student → 260101
             BCA second student     → 260102
             BTech (03) first       → 260301
    Sequential within each department, no gaps.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM students WHERE dept_code = ? AND is_active = 1",
            (dept_code,)
        ) as cur:
            row   = await cur.fetchone()
            count = (row[0] if row else 0) + 1
    return f"26{dept_code}{count:02d}"


# ── Student endpoints ─────────────────────────────────────────────────────────

@router.post("/register")
async def register(body: StudentIn):
    # Validate required fields
    if not body.name.strip():
        raise HTTPException(400, "Name is required.")
    if not body.dept_code:
        raise HTTPException(400, "Department is required.")
    if not body.phone.strip():
        raise HTTPException(400, "Phone number is required.")
    if body.guardian_type == "Guardian" and not body.guardian_rel.strip():
        raise HTTPException(400, "Guardian relation is required when guardian type is Guardian.")

    # Verify dept exists
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT name FROM departments WHERE code = ?", (body.dept_code,)
        ) as cur:
            dept = await cur.fetchone()
    if not dept:
        raise HTTPException(400, f"Department code '{body.dept_code}' not found.")

    # Generate roll number
    student_id = await _next_roll(body.dept_code)

    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                """INSERT INTO students
                   (student_id, name, city, dept_code, phone,
                    guardian_type, guardian_rel,
                    course, email)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    student_id,
                    body.name.strip(),
                    body.city.strip(),
                    body.dept_code,
                    body.phone.strip(),
                    body.guardian_type,
                    body.guardian_rel.strip(),
                    dept["name"],   # store dept name in legacy course column
                    "",
                )
            )
            await db.commit()
        except aiosqlite.IntegrityError:
            # Very rare race condition — retry with incremented count
            raise HTTPException(409, "Roll number conflict. Please try again.")

    return {
        "ok":        True,
        "student_id": student_id,
        "message":   f"Enrolled as {student_id}",
    }


@router.post("/capture-face")
async def capture_face(body: FaceCaptureIn):
    from app.core.face_engine import face_engine
    try:
        img_bytes = base64.b64decode(body.image_b64)
        nparr     = np.frombuffer(img_bytes, np.uint8)
        frame     = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    except Exception:
        raise HTTPException(400, "Invalid image data.")

    embedding = face_engine.extract_embedding(frame)
    if embedding is None:
        raise HTTPException(
            422,
            "No face detected. Ensure good lighting and face the camera directly."
        )

    await save_face_embedding(body.student_id, embedding)
    return {"ok": True, "message": "Face captured and saved."}


@router.get("/")
async def list_students():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT
                   s.student_id, s.name, s.city,
                   s.dept_code,  d.name AS dept_name,
                   s.phone, s.guardian_type, s.guardian_rel,
                   s.photo_count, s.enrolled_at
               FROM students s
               LEFT JOIN departments d ON d.code = s.dept_code
               WHERE s.is_active = 1
               ORDER BY s.enrolled_at DESC"""
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.get("/{student_id}/attendance")
async def student_attendance(student_id: str):
    """Full attendance history — used in student profile modal."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT
                   al.session_id,
                   al.confidence,
                   al.marked_at,
                   al.status,
                   sess.subject,
                   sess.dept_code,
                   d.name  AS dept_name,
                   f.name  AS faculty_name
               FROM attendance_logs al
               JOIN attendance_sessions sess ON sess.session_id = al.session_id
               LEFT JOIN departments d ON d.code       = sess.dept_code
               LEFT JOIN faculty f     ON f.faculty_id = sess.faculty_id
               WHERE al.student_id = ?
                 AND sess.is_deleted = 0
               ORDER BY al.marked_at DESC
               LIMIT 200""",
            (student_id,)
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.delete("/{student_id}")
async def delete_student(student_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE students SET is_active = 0 WHERE student_id = ?",
            (student_id,)
        )
        await db.commit()
    await reload_embeddings()
    return {"ok": True}


# ── Meta: departments ─────────────────────────────────────────────────────────

@router.get("/meta/departments")
async def get_departments():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT code, name FROM departments ORDER BY name"
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.post("/meta/departments")
async def add_department(body: NewDeptIn):
    code = body.code.strip().upper()
    name = body.name.strip()
    if not code or not name:
        raise HTTPException(400, "Code and name are required.")
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO departments (code, name) VALUES (?,?)", (code, name)
            )
            await db.commit()
        except aiosqlite.IntegrityError:
            raise HTTPException(409, "Department code or name already exists.")
    return {"ok": True, "code": code, "name": name}


# ── Meta: subjects ────────────────────────────────────────────────────────────

@router.get("/meta/subjects/{dept_code}")
async def get_subjects(dept_code: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, name FROM subjects WHERE dept_code = ? ORDER BY name",
            (dept_code,)
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.post("/meta/subjects")
async def add_subject(body: NewSubjectIn):
    name = body.name.strip()
    if not name or not body.dept_code:
        raise HTTPException(400, "Name and dept_code are required.")
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO subjects (name, dept_code) VALUES (?,?)",
                (name, body.dept_code)
            )
            await db.commit()
        except aiosqlite.IntegrityError:
            raise HTTPException(409, "Subject already exists in this department.")
    return {"ok": True, "name": name}


# ── Meta: faculty ─────────────────────────────────────────────────────────────

@router.get("/meta/faculty/{dept_code}")
async def get_faculty_by_dept(dept_code: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT faculty_id, name FROM faculty
               WHERE dept_code = ? AND is_active = 1 ORDER BY name""",
            (dept_code,)
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.post("/meta/faculty")
async def add_faculty(body: NewFacultyIn):
    name = body.name.strip()
    if not name or not body.dept_code:
        raise HTTPException(400, "Name and dept_code are required.")
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM faculty") as cur:
            count = (await cur.fetchone())[0] + 1
        fac_id = f"FAC{count:03d}"
        try:
            await db.execute(
                "INSERT INTO faculty (faculty_id, name, dept_code, email) VALUES (?,?,?,?)",
                (fac_id, name, body.dept_code, body.email.strip())
            )
            await db.commit()
        except aiosqlite.IntegrityError:
            raise HTTPException(409, "Faculty ID conflict — try again.")
    return {"ok": True, "faculty_id": fac_id, "name": name}


@router.get("/meta/faculty-all")
async def get_all_faculty():
    """All faculty with dept info and session count — used by faculty dashboard."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT f.faculty_id, f.name, f.dept_code, f.email,
                      d.name AS dept_name,
                      COUNT(DISTINCT s.session_id) AS total_sessions
               FROM faculty f
               LEFT JOIN departments d ON d.code = f.dept_code
               LEFT JOIN attendance_sessions s
                   ON s.faculty_id = f.faculty_id AND s.is_deleted = 0
               WHERE f.is_active = 1
               GROUP BY f.faculty_id
               ORDER BY f.name"""
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.get("/meta/faculty/{faculty_id}/sessions")
async def get_faculty_sessions(faculty_id: str):
    """All sessions taken by one faculty member — used in faculty profile modal."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT s.session_id, s.subject, s.dept_code,
                      d.name AS dept_name,
                      s.started_at, s.ended_at, s.is_active,
                      COUNT(al.id) AS attendance_count
               FROM attendance_sessions s
               LEFT JOIN departments d ON d.code = s.dept_code
               LEFT JOIN attendance_logs al ON al.session_id = s.session_id
               WHERE s.faculty_id = ? AND s.is_deleted = 0
               GROUP BY s.session_id
               ORDER BY s.started_at DESC""",
            (faculty_id,)
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]
