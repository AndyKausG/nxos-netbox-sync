"""
Notification backends for netbox-sync.
Backend selected via NOTIFY_BACKEND env var: ntfy | none (default).
ntfy uses stdlib urllib only — no external SDK required.
"""
import os
import urllib.request
import urllib.error

NOTIFY_BACKEND = os.environ.get("NOTIFY_BACKEND", "none").lower()


def notify_team(message: str) -> bool:
    """Send a notification message to the configured backend."""
    if NOTIFY_BACKEND == "ntfy":
        return _ntfy_notify(message)
    return False


def fail_notification(fail_list, message_template, **kwargs) -> bool:
    """Send a notification if the fail_list is non-empty."""
    if len(fail_list) > 0 or kwargs:
        message = message_template.render(failed=fail_list, **kwargs)
        return notify_team(message)
    return False


def _ntfy_notify(message: str) -> bool:
    url = os.environ.get("NTFY_URL", "").rstrip("/")
    topic = os.environ.get("NTFY_TOPIC", "")
    if not url or not topic:
        print("NOTIFY_BACKEND=ntfy but NTFY_URL/NTFY_TOPIC not set.")
        return False
    try:
        req = urllib.request.Request(
            f"{url}/{topic}",
            data=message.encode(),
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except urllib.error.URLError as e:
        print(f"ntfy notification failed: {e}")
        return False
