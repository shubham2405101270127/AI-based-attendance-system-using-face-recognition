"""
Master seed script — run ONCE after Feature 2 files are in place.
Populates: 5 departments, 5 subjects each, 5 faculty each = 125 combinations.
Safe to re-run (INSERT OR IGNORE).

Run from inside your attendance_system folder:
    python scripts/seed_master.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.database import init_db, DB_PATH
import aiosqlite

# ── Master data ───────────────────────────────────────────────────────────────

DEPARTMENTS = [
    ("01", "BCA"),
    ("03", "BTech"),
    ("05", "BDes"),
    ("07", "BPharm"),
    ("09", "MBA"),
]

SUBJECTS = {
    "01": [
        "Data Structures",
        "Web Technologies",
        "Python Programming",
        "Database Management",
        "Computer Networks",
    ],
    "03": [
        "Engineering Mathematics",
        "Digital Electronics",
        "Operating Systems",
        "Machine Learning",
        "Embedded Systems",
    ],
    "05": [
        "Design Thinking",
        "Typography & Layout",
        "UI/UX Design",
        "Motion Graphics",
        "Brand Identity",
    ],
    "07": [
        "Pharmacology",
        "Pharmaceutical Chemistry",
        "Anatomy & Physiology",
        "Drug Delivery Systems",
        "Clinical Pharmacy",
    ],
    "09": [
        "Business Strategy",
        "Financial Management",
        "Marketing Management",
        "Human Resource Management",
        "Operations Research",
    ],
}

# faculty_id, name, dept_code
FACULTY = {
    "01": [
        ("FAC001", "Prof. Anita Sharma"),
        ("FAC002", "Prof. Rajesh Mehta"),
        ("FAC003", "Prof. Priya Nair"),
        ("FAC004", "Prof. Suresh Iyer"),
        ("FAC005", "Prof. Kavita Patel"),
    ],
    "03": [
        ("FAC006", "Dr. Vikram Singh"),
        ("FAC007", "Dr. Neha Gupta"),
        ("FAC008", "Dr. Arjun Rao"),
        ("FAC009", "Dr. Sunita Joshi"),
        ("FAC010", "Dr. Amit Verma"),
    ],
    "05": [
        ("FAC011", "Prof. Riya Kapoor"),
        ("FAC012", "Prof. Sameer Das"),
        ("FAC013", "Prof. Meena Pillai"),
        ("FAC014", "Prof. Tarun Bose"),
        ("FAC015", "Prof. Zara Khan"),
    ],
    "07": [
        ("FAC016", "Dr. Rohit Desai"),
        ("FAC017", "Dr. Swati Kulkarni"),
        ("FAC018", "Dr. Manoj Tiwari"),
        ("FAC019", "Dr. Anjali Sen"),
        ("FAC020", "Dr. Preeti Yadav"),
    ],
    "09": [
        ("FAC021", "Prof. Kiran Agarwal"),
        ("FAC022", "Prof. Deepak Malhotra"),
        ("FAC023", "Prof. Sneha Reddy"),
        ("FAC024", "Prof. Nitin Jain"),
        ("FAC025", "Prof. Pooja Bhatt"),
    ],
}

# ── Seed function ─────────────────────────────────────────────────────────────

async def seed():
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:

        # Departments
        for code, name in DEPARTMENTS:
            await db.execute(
                "INSERT OR IGNORE INTO departments (code, name) VALUES (?,?)",
                (code, name)
            )

        # Subjects
        for dept_code, subjects in SUBJECTS.items():
            for subj in subjects:
                await db.execute(
                    "INSERT OR IGNORE INTO subjects (name, dept_code) VALUES (?,?)",
                    (subj, dept_code)
                )

        # Faculty
        for dept_code, members in FACULTY.items():
            for fac_id, name in members:
                await db.execute(
                    """INSERT OR IGNORE INTO faculty
                       (faculty_id, name, dept_code) VALUES (?,?,?)""",
                    (fac_id, name, dept_code)
                )

        await db.commit()

    print("✓ Seed complete:")
    print(f"  {len(DEPARTMENTS)} departments")
    print(f"  {sum(len(v) for v in SUBJECTS.values())} subjects")
    print(f"  {sum(len(v) for v in FACULTY.values())} faculty members")
    print("\nYou can now start a live session and select dept → subject → faculty.")

asyncio.run(seed())
