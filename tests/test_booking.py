"""Calendar booking — atomicity, idempotency, conflict detection, release (ADR-0009)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from ops_copilot.db.database import get_conn
from ops_copilot.tools.calendar_tool import (
    class_dates,
    get_faculty_month_view,
    release_booking,
    try_book,
)

# Deterministic launch ~2 months out — beyond all seed calendar rows (which live
# in "next month"), so happy-path bookings never collide with seed data.
LAUNCH_DATE = (date.today().replace(day=1) + timedelta(days=62)).replace(day=5)
LAUNCH = LAUNCH_DATE.strftime("%B %d, %Y")
DAYS = ["Monday", "Wednesday", "Friday"]


def _batches_for(seeded_db, faculty_id: str) -> int:
    conn = get_conn(seeded_db)
    n = conn.execute(
        "SELECT current_batches FROM faculty WHERE id = ?", (faculty_id,)
    ).fetchone()["current_batches"]
    conn.close()
    return n


class TestClassDates:
    def test_dates_on_class_days_within_window(self):
        launch = date(2026, 6, 1)  # a Monday
        dates = class_dates(launch, duration_weeks=2, class_days=["Monday"])
        assert all(d.weekday() == 0 for d in dates)
        assert dates[0] == launch
        assert len(dates) == 3  # 2 weeks → 3 Mondays inclusive of end week

    def test_unknown_day_names_ignored(self):
        dates = class_dates(date(2026, 6, 1), 1, ["Monday", "Funday"])
        assert all(d.weekday() == 0 for d in dates)


class TestTryBook:
    def test_books_and_counts(self, seeded_db):
        before = _batches_for(seeded_db, "F001")

        res = try_book("F001", LAUNCH, 4, DAYS, "SSC Foundation Batch", "sess-1")
        assert res["ok"], res
        assert res["slots_booked"] > 0

        conn = get_conn(seeded_db)
        rows = conn.execute(
            "SELECT COUNT(*) AS n FROM faculty_calendar WHERE session_id = 'sess-1' "
            "AND status = 'booked'"
        ).fetchone()["n"]
        conn.close()
        assert _batches_for(seeded_db, "F001") == before + 1
        assert rows == res["slots_booked"]

    def test_idempotent_same_session(self, seeded_db):
        before = _batches_for(seeded_db, "F001")
        first = try_book("F001", LAUNCH, 4, DAYS, "SSC Batch", "sess-2")
        assert first["ok"] and not first["idempotent_hit"]

        again = try_book("F001", LAUNCH, 4, DAYS, "SSC Batch", "sess-2")
        assert again["ok"] and again["idempotent_hit"]

        conn = get_conn(seeded_db)
        rows = conn.execute(
            "SELECT COUNT(*) AS n FROM faculty_calendar WHERE session_id = 'sess-2'"
        ).fetchone()["n"]
        conn.close()
        assert rows == first["slots_booked"]  # no duplicate rows
        assert _batches_for(seeded_db, "F001") == before + 1  # bumped exactly once

    def test_conflict_when_blocked_date_hits_class_day(self, seeded_db):
        # Deterministic: place a blocked date on a Monday 40 days out, book Mondays
        launch = datetime.now() + timedelta(days=30)
        blocked = launch + timedelta(days=(0 - launch.weekday()) % 7 + 7)  # a Monday
        conn = get_conn(seeded_db)
        conn.execute(
            "INSERT OR IGNORE INTO faculty_calendar (faculty_id, date, status, notes) "
            "VALUES ('F004', ?, 'blocked', 'test conflict')", (blocked.date().isoformat(),)
        )
        conn.close()

        res = try_book("F004", launch.strftime("%B %d, %Y"), 4, ["Monday"],
                       "Clash Batch", "sess-3")
        assert not res["ok"]
        assert res["reason"] == "conflict"
        assert res["conflict_date"] == blocked.date().isoformat()

    def test_double_booking_prevented(self, seeded_db):
        first = try_book("F001", LAUNCH, 4, DAYS, "Batch A", "sess-4")
        assert first["ok"]
        # different session, same window → must conflict
        res = try_book("F001", LAUNCH, 4, DAYS, "Batch B", "sess-5")
        assert not res["ok"]
        assert res["reason"] == "conflict"

    def test_capacity_enforced(self, seeded_db):
        conn = get_conn(seeded_db)
        conn.execute("UPDATE faculty SET current_batches = max_batches WHERE id = 'F001'")
        conn.close()
        res = try_book("F001", LAUNCH, 4, DAYS, "Batch C", "sess-6")
        assert not res["ok"]
        assert res["reason"] == "at_capacity"

    def test_missing_faculty(self, seeded_db):
        res = try_book("F999", LAUNCH, 4, DAYS, "Ghost", "sess-7")
        assert not res["ok"]
        assert res["reason"] == "faculty_not_found"

    def test_atomic_rollback_on_midway_failure(self, seeded_db):
        """A blocked date late in the window must leave zero partial bookings."""
        before = _batches_for(seeded_db, "F004")
        launch = datetime.now() + timedelta(days=30)
        late = launch + timedelta(days=20)
        while late.weekday() not in {0, 2, 4}:  # align to a Mon/Wed/Fri class day
            late += timedelta(days=1)
        conn = get_conn(seeded_db)
        conn.execute(
            "INSERT OR IGNORE INTO faculty_calendar (faculty_id, date, status, notes) "
            "VALUES ('F004', ?, 'blocked', 'late conflict')", (late.date().isoformat(),)
        )
        conn.close()

        res = try_book("F004", launch.strftime("%B %d, %Y"), 4, DAYS, "Rollback", "sess-8")
        assert not res["ok"], "late blocked date must cause failure"
        assert res["reason"] == "conflict"

        conn = get_conn(seeded_db)
        leftover = conn.execute(
            "SELECT COUNT(*) AS n FROM faculty_calendar WHERE session_id = 'sess-8'"
        ).fetchone()["n"]
        conn.close()
        assert leftover == 0, "partial booking leaked after rollback"
        assert _batches_for(seeded_db, "F004") == before  # workload untouched


class TestRelease:
    def test_release_frees_slots_and_workload(self, seeded_db):
        before = _batches_for(seeded_db, "F001")
        res = try_book("F001", LAUNCH, 4, DAYS, "Temp", "sess-rel")
        assert res["ok"]
        assert _batches_for(seeded_db, "F001") == before + 1

        out = release_booking("sess-rel")
        assert "F001" in out["faculty_ids"]

        conn = get_conn(seeded_db)
        rows = conn.execute(
            "SELECT COUNT(*) AS n FROM faculty_calendar WHERE session_id = 'sess-rel'"
        ).fetchone()["n"]
        conn.close()
        assert rows == 0
        assert _batches_for(seeded_db, "F001") == before

    def test_release_idempotent(self, seeded_db):
        release_booking("sess-nothing")
        release_booking("sess-nothing")  # must not raise


class TestMonthView:
    def test_view_shape(self, seeded_db):
        view = get_faculty_month_view("F001", 2026, 6)
        assert view["days_in_month"] == 30
        assert len(view["days"]) == 30
        assert all(d["status"] in ("available", "blocked", "booked") for d in view["days"])
        assert view["available_count"] + view["blocked_count"] + view["booked_count"] == 30
