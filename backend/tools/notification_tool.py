"""
Notification Tool — simulates sending email / Slack DMs to faculty
and receiving their willingness confirmation.

In production this would integrate with:
  - SendGrid / SMTP for email
  - Slack Web API bot for DMs
  - A webhook / reply endpoint to receive responses

Mock logic keeps it deterministic so demos are predictable.
"""
import time

# In-memory store of sent notifications and received responses
# In production: a DB table or message queue (e.g. Redis)
_NOTIFICATION_LOG: dict[str, dict] = {}

# Deterministic mock responses per faculty ID
_MOCK_RESPONSES: dict[str, dict] = {
    # Govt exam faculty
    "F001": {"status": "confirmed",   "message": "Yes, absolutely! Monday / Wednesday / Friday works perfectly for me."},
    "F002": {"status": "confirmed",   "message": "Happy to take this batch. The schedule suits me well."},
    "F003": {"status": "conditional", "message": "I can do it, but need the start time shifted 30 mins earlier."},
    "F004": {"status": "confirmed",   "message": "Count me in! Looking forward to it."},
    "F005": {"status": "conditional", "message": "Available, but may need a substitute for the first two sessions."},
    # NEET faculty
    "F006": {"status": "confirmed",   "message": "Absolutely, Biology is my passion. Happy to lead this batch!"},
    "F007": {"status": "confirmed",   "message": "Physics for both NEET and JEE — count me in. Schedule works great."},
    "F008": {"status": "confirmed",   "message": "Chemistry batch sounds great. I'm available and excited to teach."},
    "F009": {"status": "conditional", "message": "I can join, but would prefer mornings instead of evening slots."},
    "F010": {"status": "confirmed",   "message": "Physical Chemistry is my specialty — happy to take this up."},
    "F011": {"status": "confirmed",   "message": "Yes, the weekend slots work perfectly for me."},
    # JEE faculty
    "F012": {"status": "confirmed",   "message": "Mathematics — absolutely yes! I'm free and enthusiastic about this."},
    "F013": {"status": "confirmed",   "message": "JEE Physics is what I love. Confirmed and ready!"},
    "F014": {"status": "conditional", "message": "Available, but need Sunday off due to another commitment."},
    "F015": {"status": "confirmed",   "message": "Coordinate Geometry and Vectors — my strongest areas. Happy to join!"},
    "F016": {"status": "confirmed",   "message": "Early morning slot is perfect for me. Looking forward to it."},
}


def send_faculty_notification(
    faculty_id: str,
    faculty_name: str,
    batch_name: str,
    launch_date: str,
    schedule_summary: str,
    channel: str = "email",   # "email" | "slack"
) -> dict:
    """
    Simulates dispatching an email or Slack DM to a faculty member
    requesting willingness confirmation for a batch.

    Returns a send-receipt dict.
    """
    body = (
        f"Hi {faculty_name},\n\n"
        f"We are planning to launch '{batch_name}' on {launch_date}.\n"
        f"Proposed schedule: {schedule_summary}\n\n"
        f"Please confirm if you are available and willing to lead this batch.\n\n"
        f"Regards,\nAdda247 Operations Team"
    )

    receipt = {
        "faculty_id":     faculty_id,
        "faculty_name":   faculty_name,
        "channel":        channel,
        "status":         "sent",
        "message_preview": body[:140] + "…",
        "sent_at":        time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    _NOTIFICATION_LOG[faculty_id] = {"status": "pending", "receipt": receipt, "response": None}
    return receipt


def get_faculty_response(faculty_id: str, faculty_name: str) -> dict:
    """
    Simulates polling for the faculty member's reply.

    In production: poll a webhook endpoint, Slack Event API,
    or email reply parser.

    Returns a response dict with:
      status  — "confirmed" | "conditional" | "unavailable"
      message — teacher's reply text
    """
    mock = _MOCK_RESPONSES.get(faculty_id, {
        "status": "confirmed",
        "message": "Yes, I'm available for this batch.",
    })

    response = {
        **mock,
        "faculty_id":    faculty_id,
        "faculty_name":  faculty_name,
        "responded_at":  time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    if faculty_id in _NOTIFICATION_LOG:
        _NOTIFICATION_LOG[faculty_id]["response"] = response
        _NOTIFICATION_LOG[faculty_id]["status"] = "responded"

    return response


def get_notification_log() -> dict:
    """Returns the full log of sent notifications and responses (for debugging)."""
    return _NOTIFICATION_LOG
