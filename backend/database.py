"""
database.py — SQLite setup for the Operations Copilot.

Tables:
  faculty    — teacher profiles
  lms_state  — LMS platform config
  crm_data   — historical enrollment/demand data
  courses    — all courses the company offers

Safe to call init_db() multiple times (INSERT OR IGNORE).
"""
import json
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "ops_copilot.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── Schema ────────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS faculty (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    expertise         TEXT NOT NULL,   -- JSON array  e.g. ["SSC","Railway"]
    subjects          TEXT NOT NULL,   -- JSON array  e.g. ["Quant","Reasoning"]
    available_days    TEXT NOT NULL,   -- JSON array
    time_slot         TEXT NOT NULL,
    current_batches   INTEGER NOT NULL DEFAULT 0,
    max_batches       INTEGER NOT NULL DEFAULT 2,
    rating            REAL    NOT NULL DEFAULT 4.5,
    students_taught   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS lms_state (
    id                 INTEGER PRIMARY KEY DEFAULT 1,
    total_capacity     INTEGER NOT NULL,
    current_enrollment INTEGER NOT NULL,
    active_batches     INTEGER NOT NULL,
    max_batches        INTEGER NOT NULL,
    setup_time_days    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS crm_data (
    subject_area             TEXT PRIMARY KEY,
    avg_enrollment           INTEGER NOT NULL,
    min_enrollment           INTEGER NOT NULL,
    max_enrollment           INTEGER NOT NULL,
    current_leads            INTEGER NOT NULL,
    top_channels             TEXT NOT NULL,  -- JSON array
    best_launch_months       TEXT NOT NULL,  -- JSON array
    avg_revenue_per_student  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS courses (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    category    TEXT NOT NULL,
    subject_area TEXT NOT NULL,
    description TEXT NOT NULL,
    duration_weeks INTEGER NOT NULL DEFAULT 16,
    price       INTEGER NOT NULL DEFAULT 2999
);

CREATE TABLE IF NOT EXISTS faculty_calendar (
    faculty_id  TEXT NOT NULL,
    date        TEXT NOT NULL,   -- ISO format YYYY-MM-DD
    status      TEXT NOT NULL DEFAULT 'blocked',  -- 'blocked' | 'booked'
    notes       TEXT,
    PRIMARY KEY (faculty_id, date)
);
"""

# ── Seed — Faculty ────────────────────────────────────────────────────────────

FACULTY_SEED = [
    # ── Existing govt-exam faculty ─────────────────────────────────────
    {
        "id": "F001", "name": "Rakesh Kumar Sir",
        "expertise": ["SSC", "Railway"],
        "subjects": ["Quant", "Reasoning"],
        "available_days": ["Monday", "Wednesday", "Friday"],
        "time_slot": "7:00 PM – 9:00 PM",
        "current_batches": 1, "max_batches": 2, "rating": 4.8, "students_taught": 45000,
    },
    {
        "id": "F002", "name": "Priya Sharma Ma'am",
        "expertise": ["Banking", "SSC"],
        "subjects": ["English", "Reasoning"],
        "available_days": ["Tuesday", "Thursday", "Saturday"],
        "time_slot": "6:00 PM – 8:00 PM",
        "current_batches": 1, "max_batches": 2, "rating": 4.9, "students_taught": 38000,
    },
    {
        "id": "F003", "name": "Amit Verma Sir",
        "expertise": ["UPSC", "SSC"],
        "subjects": ["GK", "Current Affairs"],
        "available_days": ["Monday", "Wednesday", "Saturday"],
        "time_slot": "5:00 PM – 7:00 PM",
        "current_batches": 2, "max_batches": 2, "rating": 4.7, "students_taught": 52000,
    },
    {
        "id": "F004", "name": "Neha Singh Ma'am",
        "expertise": ["Banking", "UPSC"],
        "subjects": ["English", "Descriptive"],
        "available_days": ["Tuesday", "Thursday", "Friday"],
        "time_slot": "8:00 PM – 10:00 PM",
        "current_batches": 0, "max_batches": 2, "rating": 4.6, "students_taught": 21000,
    },
    {
        "id": "F005", "name": "Rohit Gupta Sir",
        "expertise": ["Railway", "SSC"],
        "subjects": ["Quant", "Science"],
        "available_days": ["Monday", "Thursday", "Saturday"],
        "time_slot": "7:00 PM – 9:00 PM",
        "current_batches": 1, "max_batches": 3, "rating": 4.5, "students_taught": 29000,
    },

    # ── NEET faculty ───────────────────────────────────────────────────
    {
        "id": "F006", "name": "Dr. Ananya Krishnan Ma'am",
        "expertise": ["NEET"],
        "subjects": ["Botany", "Zoology"],
        "available_days": ["Monday", "Wednesday", "Friday"],
        "time_slot": "6:00 PM – 8:00 PM",
        "current_batches": 1, "max_batches": 2, "rating": 4.9, "students_taught": 31000,
    },
    {
        "id": "F007", "name": "Vikram Nair Sir",
        "expertise": ["NEET", "JEE"],
        "subjects": ["Physics", "Modern Physics"],
        "available_days": ["Tuesday", "Thursday", "Saturday"],
        "time_slot": "7:00 PM – 9:00 PM",
        "current_batches": 1, "max_batches": 3, "rating": 4.8, "students_taught": 42000,
    },
    {
        "id": "F008", "name": "Dr. Sunita Patel Ma'am",
        "expertise": ["NEET"],
        "subjects": ["Organic Chemistry", "Inorganic Chemistry"],
        "available_days": ["Monday", "Wednesday", "Saturday"],
        "time_slot": "5:00 PM – 7:00 PM",
        "current_batches": 0, "max_batches": 2, "rating": 4.7, "students_taught": 27000,
    },
    {
        "id": "F009", "name": "Arjun Mehta Sir",
        "expertise": ["NEET"],
        "subjects": ["Human Physiology", "Genetics", "Ecology"],
        "available_days": ["Tuesday", "Friday", "Sunday"],
        "time_slot": "8:00 AM – 10:00 AM",
        "current_batches": 1, "max_batches": 2, "rating": 4.6, "students_taught": 19000,
    },
    {
        "id": "F010", "name": "Dr. Kavya Reddy Ma'am",
        "expertise": ["NEET", "JEE"],
        "subjects": ["Physical Chemistry", "Electrochemistry"],
        "available_days": ["Monday", "Thursday", "Saturday"],
        "time_slot": "6:00 PM – 8:00 PM",
        "current_batches": 0, "max_batches": 2, "rating": 4.8, "students_taught": 35000,
    },
    {
        "id": "F011", "name": "Suresh Rao Sir",
        "expertise": ["NEET"],
        "subjects": ["Biomolecules", "Cell Biology", "Biotechnology"],
        "available_days": ["Wednesday", "Friday", "Sunday"],
        "time_slot": "9:00 AM – 11:00 AM",
        "current_batches": 1, "max_batches": 2, "rating": 4.5, "students_taught": 15000,
    },

    # ── JEE faculty ────────────────────────────────────────────────────
    {
        "id": "F012", "name": "Rajesh Pandey Sir",
        "expertise": ["JEE"],
        "subjects": ["Calculus", "Algebra", "Trigonometry"],
        "available_days": ["Monday", "Wednesday", "Friday"],
        "time_slot": "7:00 PM – 9:00 PM",
        "current_batches": 1, "max_batches": 2, "rating": 4.9, "students_taught": 48000,
    },
    {
        "id": "F013", "name": "Sanjay Kapoor Sir",
        "expertise": ["JEE"],
        "subjects": ["Electrodynamics", "Optics", "Waves"],
        "available_days": ["Tuesday", "Thursday", "Saturday"],
        "time_slot": "6:00 PM – 8:00 PM",
        "current_batches": 0, "max_batches": 2, "rating": 4.8, "students_taught": 39000,
    },
    {
        "id": "F014", "name": "Dr. Pradeep Shukla Sir",
        "expertise": ["JEE", "NEET"],
        "subjects": ["Inorganic Chemistry", "Chemical Bonding"],
        "available_days": ["Monday", "Thursday", "Sunday"],
        "time_slot": "5:00 PM – 7:00 PM",
        "current_batches": 1, "max_batches": 2, "rating": 4.7, "students_taught": 33000,
    },
    {
        "id": "F015", "name": "Aditya Srivastava Sir",
        "expertise": ["JEE"],
        "subjects": ["Coordinate Geometry", "Vectors", "3D Geometry"],
        "available_days": ["Tuesday", "Friday", "Saturday"],
        "time_slot": "8:00 PM – 10:00 PM",
        "current_batches": 1, "max_batches": 3, "rating": 4.8, "students_taught": 56000,
    },
    {
        "id": "F016", "name": "Meera Iyer Ma'am",
        "expertise": ["JEE"],
        "subjects": ["Thermodynamics", "Mechanics", "Fluid Mechanics"],
        "available_days": ["Monday", "Wednesday", "Saturday"],
        "time_slot": "7:00 AM – 9:00 AM",
        "current_batches": 0, "max_batches": 2, "rating": 4.6, "students_taught": 22000,
    },
]

# ── Seed — LMS State ──────────────────────────────────────────────────────────

LMS_SEED = {
    "total_capacity": 50000,
    "current_enrollment": 42500,
    "active_batches": 23,
    "max_batches": 30,
    "setup_time_days": 3,
}

# ── Seed — CRM Historical Data ────────────────────────────────────────────────

CRM_SEED = [
    {
        "subject_area": "SSC",
        "avg_enrollment": 13500, "min_enrollment": 9000, "max_enrollment": 18000,
        "current_leads": 8400,
        "top_channels": ["YouTube Organic", "Google Ads", "WhatsApp Broadcast"],
        "best_launch_months": ["January", "July", "October"],
        "avg_revenue_per_student": 2499,
    },
    {
        "subject_area": "Banking",
        "avg_enrollment": 9200, "min_enrollment": 6000, "max_enrollment": 13000,
        "current_leads": 5600,
        "top_channels": ["YouTube Organic", "Facebook Ads", "Referral"],
        "best_launch_months": ["February", "August", "November"],
        "avg_revenue_per_student": 2999,
    },
    {
        "subject_area": "UPSC",
        "avg_enrollment": 5500, "min_enrollment": 3000, "max_enrollment": 8000,
        "current_leads": 3200,
        "top_channels": ["Organic Search", "YouTube", "Telegram"],
        "best_launch_months": ["June", "January"],
        "avg_revenue_per_student": 5999,
    },
    {
        "subject_area": "Railway",
        "avg_enrollment": 11000, "min_enrollment": 7000, "max_enrollment": 15000,
        "current_leads": 6800,
        "top_channels": ["YouTube", "WhatsApp", "Google Ads"],
        "best_launch_months": ["March", "September"],
        "avg_revenue_per_student": 1999,
    },
    {
        "subject_area": "NEET",
        "avg_enrollment": 8500, "min_enrollment": 5000, "max_enrollment": 12000,
        "current_leads": 7200,
        "top_channels": ["YouTube Organic", "Instagram Ads", "Telegram", "Google Ads"],
        "best_launch_months": ["April", "October", "January"],
        "avg_revenue_per_student": 6999,
    },
    {
        "subject_area": "JEE",
        "avg_enrollment": 7800, "min_enrollment": 4500, "max_enrollment": 11000,
        "current_leads": 6500,
        "top_channels": ["YouTube Organic", "Google Ads", "Telegram", "Referral"],
        "best_launch_months": ["April", "November", "January"],
        "avg_revenue_per_student": 7499,
    },
]

# ── Seed — Courses ────────────────────────────────────────────────────────────

COURSES_SEED = [
    # Government Exams
    {
        "id": "C001", "name": "SSC Foundation Batch",
        "category": "Government", "subject_area": "SSC",
        "description": "Complete preparation for SSC CGL, CHSL, CPO and MTS exams.",
        "duration_weeks": 16, "price": 2499,
    },
    {
        "id": "C002", "name": "Banking Foundation Batch",
        "category": "Government", "subject_area": "Banking",
        "description": "Covers IBPS PO, SBI PO, RBI Grade B and Clerk exams end-to-end.",
        "duration_weeks": 20, "price": 2999,
    },
    {
        "id": "C003", "name": "UPSC Prelims Batch",
        "category": "Government", "subject_area": "UPSC",
        "description": "GS Paper I & II strategy, Current Affairs and answer writing for IAS aspirants.",
        "duration_weeks": 48, "price": 5999,
    },
    {
        "id": "C004", "name": "Railway Foundation Batch",
        "category": "Government", "subject_area": "Railway",
        "description": "Tailored for RRB NTPC, Group D and ALP/Technician examinations.",
        "duration_weeks": 12, "price": 1999,
    },
    {
        "id": "C005", "name": "SSC Advanced Batch",
        "category": "Government", "subject_area": "SSC",
        "description": "Advanced level practice and mock series for SSC CGL Tier II & III.",
        "duration_weeks": 8, "price": 1799,
    },
    {
        "id": "C006", "name": "Banking Advanced Batch",
        "category": "Government", "subject_area": "Banking",
        "description": "Mains-level deep dive for IBPS PO/SBI PO with interview prep.",
        "duration_weeks": 12, "price": 3499,
    },
    # Medical
    {
        "id": "C007", "name": "NEET Foundation Batch",
        "category": "Medical", "subject_area": "NEET",
        "description": "Full-year NEET UG preparation — Physics, Chemistry and Biology.",
        "duration_weeks": 48, "price": 6999,
    },
    {
        "id": "C008", "name": "NEET Crash Course",
        "category": "Medical", "subject_area": "NEET",
        "description": "Intensive 3-month revision batch for NEET UG repeaters.",
        "duration_weeks": 12, "price": 3999,
    },
    {
        "id": "C009", "name": "NEET Biology Specialist",
        "category": "Medical", "subject_area": "NEET",
        "description": "Focused Biology batch covering Botany and Zoology in detail.",
        "duration_weeks": 20, "price": 2999,
    },
    # Engineering
    {
        "id": "C010", "name": "JEE Main Batch",
        "category": "Engineering", "subject_area": "JEE",
        "description": "Complete JEE Main preparation with PCM and problem-solving sessions.",
        "duration_weeks": 48, "price": 7499,
    },
    {
        "id": "C011", "name": "JEE Advanced Batch",
        "category": "Engineering", "subject_area": "JEE",
        "description": "Rigorous JEE Advanced preparation with IIT-level problem sets.",
        "duration_weeks": 32, "price": 9999,
    },
    {
        "id": "C012", "name": "JEE Crash Course",
        "category": "Engineering", "subject_area": "JEE",
        "description": "High-intensity 3-month batch for JEE repeaters targeting top NITs/IITs.",
        "duration_weeks": 12, "price": 4999,
    },
]

# ── Seed — Faculty Calendar (blocked / booked dates) ─────────────────────────
# Dates are relative to roughly next month (July 2026) for demo realism.
# In production these come from Google Calendar / Outlook sync.

import datetime as _dt
_TODAY = _dt.date.today()
_NM    = (_TODAY.replace(day=1) + _dt.timedelta(days=32)).replace(day=1)  # first of next month

def _d(offset_days: int) -> str:
    """Return ISO date string offset from start of next month."""
    return (_NM + _dt.timedelta(days=offset_days)).isoformat()

CALENDAR_SEED = [
    # F001 Rakesh Kumar — on leave first week of next month
    {"faculty_id": "F001", "date": _d(0),  "status": "blocked", "notes": "Personal leave"},
    {"faculty_id": "F001", "date": _d(1),  "status": "blocked", "notes": "Personal leave"},
    {"faculty_id": "F001", "date": _d(2),  "status": "blocked", "notes": "Personal leave"},
    {"faculty_id": "F001", "date": _d(3),  "status": "blocked", "notes": "Personal leave"},
    {"faculty_id": "F001", "date": _d(4),  "status": "blocked", "notes": "Personal leave"},

    # F002 Priya Sharma — exam duty mid-month
    {"faculty_id": "F002", "date": _d(14), "status": "blocked", "notes": "IBPS invigilator duty"},
    {"faculty_id": "F002", "date": _d(15), "status": "blocked", "notes": "IBPS invigilator duty"},

    # F006 Dr. Ananya Krishnan — existing batch booked
    {"faculty_id": "F006", "date": _d(7),  "status": "booked",  "notes": "NEET Bio Specialist Batch"},
    {"faculty_id": "F006", "date": _d(9),  "status": "booked",  "notes": "NEET Bio Specialist Batch"},
    {"faculty_id": "F006", "date": _d(11), "status": "booked",  "notes": "NEET Bio Specialist Batch"},
    {"faculty_id": "F006", "date": _d(14), "status": "booked",  "notes": "NEET Bio Specialist Batch"},
    {"faculty_id": "F006", "date": _d(16), "status": "booked",  "notes": "NEET Bio Specialist Batch"},

    # F012 Rajesh Pandey — conference out of town
    {"faculty_id": "F012", "date": _d(5),  "status": "blocked", "notes": "MathFest conference"},
    {"faculty_id": "F012", "date": _d(6),  "status": "blocked", "notes": "MathFest conference"},
    {"faculty_id": "F012", "date": _d(7),  "status": "blocked", "notes": "MathFest conference"},

    # F015 Aditya Srivastava — existing batch
    {"faculty_id": "F015", "date": _d(1),  "status": "booked",  "notes": "JEE Advanced Batch"},
    {"faculty_id": "F015", "date": _d(4),  "status": "booked",  "notes": "JEE Advanced Batch"},
    {"faculty_id": "F015", "date": _d(8),  "status": "booked",  "notes": "JEE Advanced Batch"},
    {"faculty_id": "F015", "date": _d(11), "status": "booked",  "notes": "JEE Advanced Batch"},
]


# ── Init ──────────────────────────────────────────────────────────────────────

def init_db():
    """Create tables and insert seed data. Safe to call multiple times."""
    conn = get_conn()
    cur = conn.cursor()
    cur.executescript(SCHEMA)

    # Faculty
    for f in FACULTY_SEED:
        cur.execute(
            """INSERT OR IGNORE INTO faculty
               (id, name, expertise, subjects, available_days, time_slot,
                current_batches, max_batches, rating, students_taught)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                f["id"], f["name"],
                json.dumps(f["expertise"]), json.dumps(f["subjects"]),
                json.dumps(f["available_days"]), f["time_slot"],
                f["current_batches"], f["max_batches"],
                f["rating"], f["students_taught"],
            ),
        )

    # LMS state (single row)
    cur.execute(
        """INSERT OR IGNORE INTO lms_state
           (id, total_capacity, current_enrollment, active_batches, max_batches, setup_time_days)
           VALUES (1,?,?,?,?,?)""",
        (
            LMS_SEED["total_capacity"], LMS_SEED["current_enrollment"],
            LMS_SEED["active_batches"], LMS_SEED["max_batches"],
            LMS_SEED["setup_time_days"],
        ),
    )

    # CRM data
    for c in CRM_SEED:
        cur.execute(
            """INSERT OR IGNORE INTO crm_data
               (subject_area, avg_enrollment, min_enrollment, max_enrollment,
                current_leads, top_channels, best_launch_months, avg_revenue_per_student)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                c["subject_area"],
                c["avg_enrollment"], c["min_enrollment"], c["max_enrollment"],
                c["current_leads"],
                json.dumps(c["top_channels"]), json.dumps(c["best_launch_months"]),
                c["avg_revenue_per_student"],
            ),
        )

    # Courses
    for c in COURSES_SEED:
        cur.execute(
            """INSERT OR IGNORE INTO courses
               (id, name, category, subject_area, description, duration_weeks, price)
               VALUES (?,?,?,?,?,?,?)""",
            (
                c["id"], c["name"], c["category"], c["subject_area"],
                c["description"], c["duration_weeks"], c["price"],
            ),
        )

    # Calendar events
    for e in CALENDAR_SEED:
        cur.execute(
            """INSERT OR IGNORE INTO faculty_calendar (faculty_id, date, status, notes)
               VALUES (?,?,?,?)""",
            (e["faculty_id"], e["date"], e["status"], e.get("notes")),
        )

    conn.commit()
    conn.close()
    print(f"[DB] Initialized: {DB_PATH}")


# ── Quick CLI check ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    conn = get_conn()
    print(f"\n-- Faculty ({conn.execute('SELECT COUNT(*) FROM faculty').fetchone()[0]} rows) --")
    for r in conn.execute("SELECT id, name, expertise, rating FROM faculty ORDER BY id"):
        print(f"  {r['id']} | {r['name']:<30} | {r['expertise']:<20} | ⭐ {r['rating']}")
    print(f"\n-- Courses ({conn.execute('SELECT COUNT(*) FROM courses').fetchone()[0]} rows) --")
    for r in conn.execute("SELECT id, name, category, price FROM courses ORDER BY category, id"):
        print(f"  {r['id']} | {r['name']:<35} | {r['category']:<15} | ₹{r['price']:,}")
    print(f"\n-- CRM Subjects: {[r[0] for r in conn.execute('SELECT subject_area FROM crm_data')]} --")
    conn.close()
