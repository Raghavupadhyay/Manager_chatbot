"""Notification tool — simulated email/Slack dispatch and reply collection.

Mock logic is deterministic so demos and tests are predictable. In production:
SendGrid/SMTP for email, Slack Web API for DMs, webhook endpoint for replies.
"""
from __future__ import annotations

import time

_NOTIFICATION_LOG: dict[str, dict] = {}

_MOCK_RESPONSES: dict[str, dict] = {
    "F001": {"status": "confirmed",
             "message": "Yes, absolutely! Monday / Wednesday / Friday works for me."},
    "F002": {"status": "confirmed",
             "message": "Happy to take this batch. The schedule suits me well."},
    "F003": {"status": "conditional",
             "message": "I can do it, but need the start time shifted 30 mins earlier."},
    "F004": {"status": "confirmed",
             "message": "Count me in! Looking forward to it."},
    "F005": {"status": "conditional",
             "message": "Available, but may need a substitute for the first two sessions."},
    "F006": {"status": "confirmed",
             "message": "Absolutely, Biology is my passion. Happy to lead this batch!"},
    "F007": {"status": "confirmed",
             "message": "Physics for both NEET and JEE — count me in. Schedule is fine."},
    "F008": {"status": "confirmed",
             "message": "Chemistry batch sounds great. I'm available and excited to teach."},
    "F009": {"status": "conditional",
             "message": "I can join, but would prefer mornings instead of evening slots."},
    "F010": {"status": "confirmed",
             "message": "Physical Chemistry is my specialty — happy to take this up."},
    "F011": {"status": "confirmed",
             "message": "Yes, the weekend slots work perfectly for me."},
    "F012": {"status": "confirmed",
             "message": "Mathematics — absolutely yes! I'm free and enthusiastic."},
    "F013": {"status": "confirmed",
             "message": "JEE Physics is what I love. Confirmed and ready!"},
    "F014": {"status": "conditional",
             "message": "Available, but need Sunday off due to another commitment."},
    "F015": {"status": "confirmed",
             "message": "Coordinate Geometry and Vectors — my strongest areas. Happy to!"},
    "F016": {"status": "confirmed",
             "message": "Early morning slot is perfect for me. Looking forward to it."},
}

_ESCALATION_EMAIL = "ops-manager@adda247.example"


def send_faculty_notification(
    faculty_id: str,
    faculty_name: str,
    batch_name: str,
    launch_date: str,
    schedule_summary: str,
    channel: str = "email",
) -> dict:
    body = (
        f"Hi {faculty_name},\n\n"
        f"We are planning to launch '{batch_name}' on {launch_date}.\n"
        f"Proposed schedule: {schedule_summary}\n\n"
        f"Please confirm if you are available and willing to lead this batch.\n\n"
        f"Regards,\nAdda247 Operations Team"
    )
    receipt = {
        "faculty_id": faculty_id, "faculty_name": faculty_name, "channel": channel,
        "status": "sent", "message_preview": body[:140] + "…",
        "sent_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _NOTIFICATION_LOG[f"{faculty_id}:{batch_name}"] = {
        "status": "pending", "receipt": receipt, "response": None,
    }
    return receipt


def send_booking_confirmation(
    faculty_id: str,
    faculty_name: str,
    batch_name: str,
    first_class: str,
    last_class: str,
    slots_booked: int,
) -> dict:
    body = (
        f"Hi {faculty_name},\n\n"
        f"Your calendar has been booked for '{batch_name}': "
        f"{slots_booked} sessions from {first_class} to {last_class}.\n\n"
        f"Regards,\nAdda247 Operations Team"
    )
    receipt = {
        "faculty_id": faculty_id, "faculty_name": faculty_name, "channel": "email",
        "status": "sent", "message_preview": body[:140] + "…",
        "sent_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _NOTIFICATION_LOG[f"{faculty_id}:{batch_name}:booking"] = {"status": "sent", "receipt": receipt}
    return receipt


def send_escalation(batch_name: str, reason: str) -> dict:
    body = (
        f"ESCALATION — '{batch_name}' could not be auto-scheduled.\n"
        f"Reason: {reason}\nManual faculty assignment required."
    )
    receipt = {
        "to": _ESCALATION_EMAIL, "channel": "email", "status": "sent",
        "message_preview": body[:140] + "…",
        "sent_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _NOTIFICATION_LOG[f"escalation:{batch_name}"] = {"status": "sent", "receipt": receipt}
    return receipt


def get_faculty_response(faculty_id: str, faculty_name: str) -> dict:
    mock = _MOCK_RESPONSES.get(faculty_id, {
        "status": "confirmed", "message": "Yes, I'm available for this batch.",
    })
    response = {
        **mock, "faculty_id": faculty_id, "faculty_name": faculty_name,
        "responded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    for key, entry in _NOTIFICATION_LOG.items():
        if key.startswith(f"{faculty_id}:") and entry.get("status") == "pending":
            entry["response"] = response
            entry["status"] = "responded"
    return response


def get_notification_log() -> dict:
    return _NOTIFICATION_LOG
