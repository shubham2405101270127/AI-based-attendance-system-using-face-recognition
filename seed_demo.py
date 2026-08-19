"""
Seed script: creates demo students and simulates attendance.
Run: python scripts/seed_demo.py
"""
import asyncio
import aiosqlite
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.models.database import init_db, DB_PATH

STUDENTS = [
    ("CS001", "Aarav Shah",    "aarav@demo.edu",  "Computer Science"),
    ("CS002", "Priya Mehta",   "priya@demo.edu",  "Computer Science"),
    ("CS003", "Rohan Patel",   "rohan@demo.edu",  "Computer Science"),
    ("CS004", "Sneha Gupta",   "sneha@demo.edu",  "Computer Science"),
    ("CS005", "Vikram Rao",    "vikram@demo.edu", "Computer Science"),
    ("CS006", "Ananya Singh",  "ananya@demo.edu", "Computer Science"),
    ("CS007", "Arjun Nair",    "arjun@demo.edu",  "Computer Science"),
    ("CS008", "Kavya Iyer",    "kavya@demo.edu",  "Computer Science"),
]

async def seed():
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        for sid, name, email, course in STUDENTS:
            await db.execute(
                "INSERT OR IGNORE INTO students (student_id,name,email,course) VALUES (?,?,?,?)",
                (sid, name, email, course)
            )
        await db.execute(
            "INSERT OR IGNORE INTO attendance_sessions (session_id,course,teacher,is_active) "
            "VALUES ('DEMO01','Computer Science','Dr. Demo',0)"
        )
        for sid, *_ in STUDENTS[:5]:
            await db.execute(
                "INSERT OR IGNORE INTO attendance_logs (session_id,student_id,confidence) VALUES (?,?,?)",
                ("DEMO01", sid, round(0.75 + abs(hash(sid)) % 20 / 100, 3))
            )
        await db.commit()
    print("Demo data seeded. 8 students enrolled, 1 demo session.")

asyncio.run(seed())
