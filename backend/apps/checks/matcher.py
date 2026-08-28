"""Keyword matching and alerting for watches.

Kept out of the mail engine so it can be exercised on its own, and so a fault here
can never take a poll down: `scan_message` swallows everything it raises.
"""
import re

from django.utils import timezone

from apps.notifications.models import TelegramConfig
from apps.notifications.telegram import notify

from .models import Watch, WatchHit

# How much of the surrounding text to keep so a hit is readable at a glance.
_EXCERPT_RADIUS = 90
_MAX_EXCERPT = 240


def _find(keyword: str, text: str, case_sensitive: bool):
    """Return (start, end) of the first occurrence of `keyword` in `text`, else None."""
    if not keyword or not text:
        return None
    flags = 0 if case_sensitive else re.IGNORECASE
    m = re.search(re.escape(keyword), text, flags)
    return (m.start(), m.end()) if m else None


def _excerpt(text: str, span) -> str:
    """A short window of `text` around `span`, with ellipses where it was cut."""
    start, end = span
    left = max(0, start - _EXCERPT_RADIUS)
    right = min(len(text), end + _EXCERPT_RADIUS)
    piece = text[left:right].strip()
    piece = re.sub(r"\s+", " ", piece)
    if left > 0:
        piece = "… " + piece
    if right < len(text):
        piece = piece + " …"
    return piece[:_MAX_EXCERPT]


def _alert(watch: Watch, hit: WatchHit) -> bool:
    """Send the Telegram alert for `hit` unless this watch is over its hourly cap.

    Returns True if a message was actually sent. When over the cap the hit is still
    recorded — only the notification is dropped — and counted so the next alert that
    does go out can report how many were missed.
    """
    if not watch.notify_telegram:
        return False

    # notify() silently does nothing when Telegram is off or the keyword event is
    # unticked. Checking here keeps the hit's `notified` flag honest and stops a
    # workspace with no Telegram burning through its hourly alert budget.
    cfg = TelegramConfig.load(watch.workspace)
    if not (cfg.enabled and cfg.notify_on_keyword):
        return False

    if watch.alerts_sent_last_hour() >= watch.max_alerts_per_hour:
        Watch.objects.filter(pk=watch.pk).update(suppressed_count=watch.suppressed_count + 1)
        return False

    arrow = "📤 sent" if hit.direction == WatchHit.Direction.OUTGOING else "📥 received"
    who = hit.to_addr if hit.direction == WatchHit.Direction.OUTGOING else hit.from_addr
    lines = [
        f"🔎 <b>{watch.name}</b> — matched “{hit.keyword}”",
        f"{arrow} · {hit.mailbox.name}",
        f"<b>{hit.subject or '(no subject)'}</b>",
    ]
    if who:
        lines.append(("to " if hit.direction == WatchHit.Direction.OUTGOING else "from ") + who)
    if hit.excerpt:
        lines.append(f"\n<i>{hit.excerpt}</i>")

    # Anything suppressed while over the cap is reported on the first alert after the
    # window clears, so a quiet hour never hides that a burst happened.
    if watch.suppressed_count:
        lines.append(f"\n(+{watch.suppressed_count} more matched while alerts were paused)")
        Watch.objects.filter(pk=watch.pk).update(suppressed_count=0)

    notify(watch.workspace, "keyword", "\n".join(lines))
    return True


def scan_message(mailbox, *, direction: str, subject: str, body: str,
                 from_addr: str = "", to_addr: str = "", folder: str = "",
                 message_id: str = "", occurred_at=None) -> int:
    """Check one message against every active watch. Returns the number of hits logged.

    Never raises: a watch problem must not stop mail being polled or answered.
    """
    try:
        watches = (
            Watch.objects.filter(workspace=mailbox.workspace, is_active=True)
            .prefetch_related("mailboxes")
        )
        logged = 0
        for watch in watches:
            if direction == WatchHit.Direction.INCOMING and not watch.watch_incoming:
                continue
            if direction == WatchHit.Direction.OUTGOING and not watch.watch_outgoing:
                continue
            if not watch.covers(mailbox):
                continue

            # One hit per message per watch: the first keyword that matches wins,
            # otherwise a message mentioning three keywords fires three alerts.
            if message_id and watch.hits.filter(message_id=message_id).exists():
                continue

            hit = None
            for keyword in watch.keyword_list:
                if watch.match_subject:
                    span = _find(keyword, subject or "", watch.case_sensitive)
                    if span:
                        hit = (keyword, "subject", _excerpt(subject, span))
                        break
                if watch.match_body:
                    span = _find(keyword, body or "", watch.case_sensitive)
                    if span:
                        hit = (keyword, "body", _excerpt(body, span))
                        break
            if not hit:
                continue

            keyword, where, excerpt = hit
            row = WatchHit.objects.create(
                workspace=mailbox.workspace, watch=watch, mailbox=mailbox,
                direction=direction, keyword=keyword, matched_in=where,
                subject=(subject or "")[:998], from_addr=(from_addr or "")[:320],
                to_addr=(to_addr or "")[:998], folder=folder[:255],
                message_id=(message_id or "")[:512], excerpt=excerpt,
                occurred_at=occurred_at or timezone.now(),
            )
            if _alert(watch, row):
                WatchHit.objects.filter(pk=row.pk).update(notified=True)
            logged += 1
        return logged
    except Exception:  # noqa: BLE001
        return 0
