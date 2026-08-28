"""Read-only IMAP polling for watched mailboxes.

Entirely separate from the auto-reply engine. This module can open a connection,
select folders READ-ONLY, fetch, and match — and that is all it can do. It has no
SMTP import, creates no EmailMessage rows, and never touches Rule or ReplyTemplate,
so a monitored mailbox cannot be replied to no matter how the rules are configured.

Header parsing, body extraction and folder listing are borrowed from the mail engine
rather than reimplemented, so both paths decode mail identically. The dependency runs
one way only — the engine knows nothing about checks.
"""
import email
import imaplib

from django.utils import timezone

from apps.automation.engine import (
    FIRST_RUN_LIMIT,
    _decode,
    _extract_body,
    _list_folders,
    _quote_folder,
    _uidvalidity,
    detect_spam_folders,
)
from apps.security.models import SystemEvent

from .matcher import scan_message
from .models import WatchHit, WatchMailbox

# RFC 6154 special-use flag first, display names only as a fallback for older servers.
_SENT_FLAGS = {"\\sent"}
_SENT_NAMES = {
    "sent", "sent items", "sent mail", "sent messages", "outbox",
    "[gmail]/sent mail", "[google mail]/sent mail",
    "inbox.sent", "inbox/sent",
}
_UNSELECTABLE = "\\noselect"


def detect_sent_folders(conn) -> list[str]:
    """Find the account's Sent folder(s), by special-use flag then by name."""
    by_flag, by_name = [], []
    for name, flags in _list_folders(conn):
        if _UNSELECTABLE in flags:
            continue
        if flags & _SENT_FLAGS:
            by_flag.append(name)
        elif name.lower() in _SENT_NAMES:
            by_name.append(name)
    return by_flag or by_name


def connect(mailbox: WatchMailbox):
    """Open an authenticated IMAP connection to a watched mailbox."""
    if mailbox.imap_use_ssl:
        conn = imaplib.IMAP4_SSL(mailbox.imap_host, mailbox.imap_port)
    else:
        conn = imaplib.IMAP4(mailbox.imap_host, mailbox.imap_port)
    conn.login(mailbox.login_username, mailbox.password)
    return conn


def folders_for(mailbox: WatchMailbox, conn) -> list[str]:
    """Which folders this mailbox wants read, de-duplicated, order preserved."""
    wanted: list[str] = []
    if mailbox.scan_inbox:
        wanted.append("INBOX")
    if mailbox.scan_sent:
        try:
            wanted += detect_sent_folders(conn)
        except Exception as exc:  # noqa: BLE001
            SystemEvent.log("checks", f"Could not list folders on {mailbox.name}: {exc}",
                            "warning", workspace=mailbox.workspace)
    if mailbox.scan_spam:
        try:
            wanted += detect_spam_folders(conn)
        except Exception:  # noqa: BLE001
            pass
    wanted += mailbox.extra_folder_list

    seen, ordered = set(), []
    for folder in wanted:
        if folder.lower() not in seen:
            seen.add(folder.lower())
            ordered.append(folder)
    return ordered


def test_connection(mailbox: WatchMailbox) -> dict:
    """Verify login and report which folders would be read. Sends nothing."""
    result = {"ok": False, "folders": [], "error": ""}
    try:
        conn = connect(mailbox)
        try:
            result["folders"] = folders_for(mailbox, conn)
            result["ok"] = True
        finally:
            try:
                conn.logout()
            except Exception:  # noqa: BLE001
                pass
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    return result


def _direction_for(folder: str, sent_folders: set[str]) -> str:
    """Mail in a Sent folder is outgoing; everything else is incoming."""
    return (WatchHit.Direction.OUTGOING if folder.lower() in sent_folders
            else WatchHit.Direction.INCOMING)


def _scan_folder(mailbox: WatchMailbox, conn, folder: str, cursors: dict,
                 sent_folders: set[str]) -> int:
    """Read what is new in one folder and hand each message to the matcher."""
    # readonly=True: the server is told not to change \Seen flags, so monitoring a
    # campaign manager's inbox never marks his unread mail as read.
    typ, _ = conn.select(_quote_folder(folder), readonly=True)
    if typ != "OK":
        raise RuntimeError(f"SELECT failed ({typ})")

    state = cursors.get(folder) or {}
    last_uid = int(state.get("uid") or 0)
    uidvalidity = _uidvalidity(conn)
    # A changed UIDVALIDITY means the server renumbered the folder, so the stored UID
    # points at nothing (RFC 3501 §2.3.1.1). Restart rather than skip mail.
    if uidvalidity and state.get("uidvalidity") not in (None, uidvalidity):
        last_uid = 0

    criterion = f"UID {last_uid + 1}:*" if last_uid else "ALL"
    typ, data = conn.uid("search", None, criterion)
    if typ != "OK":
        raise RuntimeError(f"SEARCH failed ({typ})")
    uids = [int(u) for u in data[0].split()] if data and data[0] else []
    if not last_uid:
        # First run takes only the most recent few. Without this, adding a mailbox
        # would alert on every campaign in its entire history.
        uids = uids[-FIRST_RUN_LIMIT:]

    direction = _direction_for(folder, sent_folders)
    scanned, highest = 0, last_uid
    for uid in uids:
        # "UID n:*" returns the highest UID even when it is below n.
        if uid <= last_uid:
            continue
        typ, msg_data = conn.uid("fetch", str(uid), "(RFC822)")
        if typ != "OK" or not msg_data or not msg_data[0]:
            continue
        msg = email.message_from_bytes(msg_data[0][1])
        scan_message(
            mailbox,
            direction=direction,
            subject=_decode(msg.get("Subject", "")),
            body=_extract_body(msg),
            from_addr=_decode(msg.get("From", "")),
            to_addr=_decode(msg.get("To", "")),
            folder=folder,
            message_id=(msg.get("Message-ID") or "").strip(),
        )
        scanned += 1
        highest = max(highest, uid)

    cursors[folder] = {"uid": highest, "uidvalidity": uidvalidity}
    return scanned


def poll_watch_mailbox(mailbox: WatchMailbox) -> int:
    """Read every watched folder on one mailbox. Returns messages scanned."""
    cursors = dict(mailbox.folder_cursors or {})
    errors: list[str] = []
    scanned = 0

    conn = connect(mailbox)
    try:
        sent_folders = set()
        if mailbox.scan_sent:
            try:
                sent_folders = {f.lower() for f in detect_sent_folders(conn)}
            except Exception:  # noqa: BLE001
                pass

        for folder in folders_for(mailbox, conn):
            try:
                scanned += _scan_folder(mailbox, conn, folder, cursors, sent_folders)
            except Exception as exc:  # noqa: BLE001
                # One unreadable folder must not cost the rest of the mailbox.
                errors.append(f"{folder}: {exc}")
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass

    mailbox.folder_cursors = cursors
    mailbox.last_polled_at = timezone.now()
    mailbox.last_error = "; ".join(errors)
    mailbox.save(update_fields=["folder_cursors", "last_polled_at", "last_error"])
    return scanned


def poll_all(workspace=None) -> dict:
    """Poll every active watched mailbox. One failure never stops the others."""
    qs = WatchMailbox.objects.filter(is_active=True)
    if workspace is not None:
        qs = qs.filter(workspace=workspace)

    totals = {"mailboxes": 0, "scanned": 0, "errors": 0}
    for mailbox in qs:
        totals["mailboxes"] += 1
        try:
            totals["scanned"] += poll_watch_mailbox(mailbox)
        except Exception as exc:  # noqa: BLE001
            totals["errors"] += 1
            WatchMailbox.objects.filter(pk=mailbox.pk).update(
                last_error=str(exc)[:2000], last_polled_at=timezone.now()
            )
            SystemEvent.log("checks", f"Watch poll failed for {mailbox.name}: {exc}",
                            "error", workspace=mailbox.workspace)
    return totals
