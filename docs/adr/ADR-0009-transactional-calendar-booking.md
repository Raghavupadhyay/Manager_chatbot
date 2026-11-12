# ADR-0009: Transactional calendar booking with auto-fallback ladder

**Status:** Accepted (2026-11-11)

## Context

Course launches must actually book the chosen faculty's calendar on approval.
Today booking effectively never happens: `reserve_faculty_slots()` exists but
is only referenced from an unreachable duplicate route (FastAPI matches the
first `POST /approve`), and the conflict check runs during *planning* while the
human may approve minutes or hours later — a classic TOCTOU race (another
session could book the same slots in between).

## Options considered

1. **Book during planning, release on rejection** — holds resources hostage
   while a human deliberates; needs TTL/release jobs.
2. **Re-check + book atomically at approval time** — conflicts are re-validated
   and booked inside one transaction at the moment of approval.
3. **Queue-based booking with a worker** — overkill for a single-process
   control plane.

## Decision

**Option 2 — atomic reservation at approval time, inside the graph:**

A `reserve_calendar` node runs immediately after the approval interrupt resumes:

1. **Re-check** calendar conflicts for the primary faculty over the batch
   window (fresh DB read; planning-time check is advisory only).
2. **Atomic booking** in a single `BEGIN IMMEDIATE` transaction:
   insert `booked` rows for every class date in the window (tagged with
   `session_id` + `reserved_at`), bump `faculty.current_batches`,
   commit — or roll back completely on any conflict.
3. **Auto-fallback ladder** if the primary is no longer bookable:
   secondary faculty → next candidates from the ranked shortlist (carried in
   graph state) → shifted start date (+1 week, re-checked). Every switch
   emits a `booking_diff` event so the approver sees what changed *after*
   their approval ("primary F001 taken by another session — auto-switched to
   F002, same schedule").
   All options exhausted → **escalation branch**: notify the ops manager,
   session ends in `needs_attention` — never a silent failure.
4. **Idempotency**: bookings are keyed by `session_id`; re-running approval
   (double-click/retry) finds the existing booking and returns it.

Schema changes to `faculty_calendar`: `session_id`, `reserved_at` columns and a
unique constraint preventing double-booking the same faculty/date. Release
path (reject/supersede) removes booked rows and decrements `current_batches`
in one transaction.

**Auto-approve hook (deferred):** if a later policy wants high-readiness plans
to book automatically, the reservation code is invoked from the same node —
no redesign needed (see ADR-0001).

## Consequences

- +: no silent failures, no double-booking, no TOCTOU window, approver
  retains control, bookings survive restarts (they're in SQLite, not memory).
- +: latency budget for booking ≤ 2 s p95 (measured via ADR-0002).
- −: fallback ladder adds code paths — covered by unit tests that simulate
  "primary taken between planning and approval".
- −: notifications remain simulated (mock tool) — booking is real, emails
  are not; documented in the tool module.
