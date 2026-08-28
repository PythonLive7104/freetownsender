"""Tests for keyword Checks.

Weighted towards the properties that must not break rather than the happy path:
watched mailboxes are read-only and invisible to the reply engine, one email yields
at most one alert per check, and a fault in a watch can never cost the mail engine.
"""
import email as email_mod
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.checks.matcher import scan_message
from apps.checks.models import Watch, WatchHit, WatchMailbox
from apps.mailboxes.models import Mailbox
from apps.notifications.models import TelegramConfig
from apps.workspaces.models import Workspace


class Base(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("owner", password="x")
        self.ws = Workspace.objects.create(name="Acme")
        self.wmb = WatchMailbox.objects.create(
            workspace=self.ws, name="Campaign manager",
            email_address="manager@acme.com", username="manager@acme.com",
            imap_host="imap.acme.com", imap_port=993,
        )

    def watch(self, **kw):
        defaults = dict(workspace=self.ws, name="Campaigns",
                        keywords="Promotion, Black Friday", notify_telegram=False)
        defaults.update(kw)
        return Watch.objects.create(**defaults)

    def send(self, subject="", body="", direction=WatchHit.Direction.INCOMING,
             message_id="", mailbox=None):
        return scan_message(mailbox or self.wmb, direction=direction, subject=subject,
                            body=body, message_id=message_id)


class KeywordMatching(Base):
    def test_matches_subject(self):
        w = self.watch()
        self.send(subject="Our July Promotion is live", message_id="<a@x>")
        hit = w.hits.get()
        self.assertEqual(hit.keyword, "Promotion")
        self.assertEqual(hit.matched_in, "subject")

    def test_matches_body(self):
        w = self.watch()
        self.send(subject="Hello", body="See our Black Friday deals", message_id="<b@x>")
        self.assertEqual(w.hits.get().matched_in, "body")

    def test_case_insensitive_by_default(self):
        w = self.watch()
        self.send(subject="a promotion offer", message_id="<c@x>")
        self.assertEqual(w.hits.count(), 1)

    def test_case_sensitive_when_asked(self):
        w = self.watch(case_sensitive=True)
        self.send(subject="a promotion offer", message_id="<d@x>")
        self.assertEqual(w.hits.count(), 0)
        self.send(subject="a Promotion offer", message_id="<e@x>")
        self.assertEqual(w.hits.count(), 1)

    def test_no_match_records_nothing(self):
        w = self.watch()
        self.send(subject="Invoice 4021", body="payment terms", message_id="<f@x>")
        self.assertEqual(w.hits.count(), 0)

    def test_keywords_split_on_commas_and_newlines(self):
        w = self.watch(keywords="Promotion,\n Black Friday \n\n newsletter,")
        self.assertEqual(w.keyword_list, ["Promotion", "Black Friday", "newsletter"])

    def test_substring_of_a_longer_word_still_matches(self):
        # "Promotion" inside "Promotions" is a real campaign reply; missing it would
        # be worse than the occasional loose match.
        w = self.watch()
        self.send(subject="Re: Promotions this week", message_id="<g@x>")
        self.assertEqual(w.hits.count(), 1)

    def test_regex_characters_in_a_keyword_are_literal(self):
        w = self.watch(keywords="50% off (limited)")
        self.send(subject="Get 50% off (limited) today", message_id="<h@x>")
        self.assertEqual(w.hits.count(), 1)

    def test_excerpt_captures_surrounding_text(self):
        w = self.watch()
        self.send(subject="hi", body="x" * 300 + " Black Friday " + "y" * 300, message_id="<i@x>")
        excerpt = w.hits.get().excerpt
        self.assertIn("Black Friday", excerpt)
        self.assertLess(len(excerpt), 300)

    def test_scope_can_be_narrowed_to_subject_only(self):
        w = self.watch(match_body=False)
        self.send(subject="hello", body="a Promotion inside", message_id="<j@x>")
        self.assertEqual(w.hits.count(), 0)


class OneAlertPerEmail(Base):
    def test_same_message_scanned_twice_logs_once(self):
        w = self.watch()
        self.send(subject="Promotion", message_id="<dup@x>")
        self.send(subject="Promotion", message_id="<dup@x>")
        self.assertEqual(w.hits.count(), 1)

    def test_two_keywords_in_one_email_produce_one_hit(self):
        w = self.watch()
        self.send(subject="Promotion and Black Friday together", message_id="<k@x>")
        self.assertEqual(w.hits.count(), 1)

    def test_separate_watches_each_get_their_own_hit(self):
        a = self.watch(name="A", keywords="Promotion")
        b = self.watch(name="B", keywords="Promotion")
        self.send(subject="Promotion", message_id="<l@x>")
        self.assertEqual(a.hits.count(), 1)
        self.assertEqual(b.hits.count(), 1)


class Targeting(Base):
    def test_empty_mailbox_list_means_all_including_later_additions(self):
        w = self.watch()
        added_later = WatchMailbox.objects.create(
            workspace=self.ws, name="New hire", email_address="new@acme.com",
            imap_host="h", imap_port=993)
        self.send(subject="Promotion", message_id="<m@x>", mailbox=added_later)
        self.assertEqual(w.hits.count(), 1)

    def test_selected_mailboxes_exclude_the_others(self):
        other = WatchMailbox.objects.create(
            workspace=self.ws, name="Other", email_address="other@acme.com",
            imap_host="h", imap_port=993)
        w = self.watch()
        w.mailboxes.add(self.wmb)
        self.send(subject="Promotion", message_id="<n@x>", mailbox=other)
        self.assertEqual(w.hits.count(), 0)
        self.send(subject="Promotion", message_id="<o@x>", mailbox=self.wmb)
        self.assertEqual(w.hits.count(), 1)

    def test_inactive_watch_is_ignored(self):
        w = self.watch(is_active=False)
        self.send(subject="Promotion", message_id="<p@x>")
        self.assertEqual(w.hits.count(), 0)

    def test_direction_toggles_are_respected(self):
        incoming_only = self.watch(name="in", watch_outgoing=False)
        outgoing_only = self.watch(name="out", watch_incoming=False)
        self.send(subject="Promotion", direction=WatchHit.Direction.OUTGOING, message_id="<q@x>")
        self.assertEqual(incoming_only.hits.count(), 0)
        self.assertEqual(outgoing_only.hits.count(), 1)

    def test_another_workspace_is_never_touched(self):
        other_ws = Workspace.objects.create(name="Other Co")
        theirs = WatchMailbox.objects.create(
            workspace=other_ws, name="Theirs", email_address="a@other.com",
            imap_host="h", imap_port=993)
        w = self.watch()
        self.send(subject="Promotion", message_id="<r@x>", mailbox=theirs)
        self.assertEqual(w.hits.count(), 0)


class AlertThrottling(Base):
    def setUp(self):
        super().setUp()
        cfg = TelegramConfig.load(self.ws)
        cfg.enabled = True
        cfg.chat_id = "1"
        cfg.bot_token = "t"
        cfg.save()

    @patch("apps.checks.matcher.notify")
    def test_every_match_is_logged_but_alerts_stop_at_the_cap(self, notify):
        w = self.watch(notify_telegram=True, max_alerts_per_hour=3)
        for i in range(6):
            self.send(subject=f"Promotion {i}", message_id=f"<cap{i}@x>")
        self.assertEqual(w.hits.count(), 6, "all matches must be recorded")
        self.assertEqual(w.hits.filter(notified=True).count(), 3)
        self.assertEqual(notify.call_count, 3)
        w.refresh_from_db()
        self.assertEqual(w.suppressed_count, 3)

    @patch("apps.checks.matcher.notify")
    def test_suppressed_total_is_reported_on_the_next_alert(self, notify):
        w = self.watch(notify_telegram=True, max_alerts_per_hour=1)
        self.send(subject="Promotion 1", message_id="<s1@x>")
        self.send(subject="Promotion 2", message_id="<s2@x>")
        w.refresh_from_db()
        self.assertEqual(w.suppressed_count, 1)

        # Age the sent alert out of the rolling hour so the next one is allowed.
        w.hits.filter(notified=True).update(
            created_at=timezone.now() - timezone.timedelta(hours=2))
        self.send(subject="Promotion 3", message_id="<s3@x>")
        self.assertIn("+1 more", notify.call_args[0][2])
        w.refresh_from_db()
        self.assertEqual(w.suppressed_count, 0, "counter resets once reported")

    @patch("apps.checks.matcher.notify")
    def test_no_alert_when_telegram_is_off(self, notify):
        cfg = TelegramConfig.load(self.ws)
        cfg.enabled = False
        cfg.save()
        w = self.watch(notify_telegram=True)
        self.send(subject="Promotion", message_id="<t@x>")
        self.assertEqual(w.hits.count(), 1, "the match is still recorded")
        self.assertFalse(w.hits.get().notified)
        notify.assert_not_called()

    @patch("apps.checks.matcher.notify")
    def test_telegram_off_does_not_consume_the_alert_budget(self, notify):
        cfg = TelegramConfig.load(self.ws)
        cfg.enabled = False
        cfg.save()
        w = self.watch(notify_telegram=True, max_alerts_per_hour=2)
        for i in range(5):
            self.send(subject=f"Promotion {i}", message_id=f"<u{i}@x>")
        w.refresh_from_db()
        self.assertEqual(w.suppressed_count, 0)

    @patch("apps.checks.matcher.notify")
    def test_watch_with_alerts_disabled_never_notifies(self, notify):
        w = self.watch(notify_telegram=False)
        self.send(subject="Promotion", message_id="<v@x>")
        self.assertEqual(w.hits.count(), 1)
        notify.assert_not_called()


class NeverBreaksTheMailEngine(Base):
    def test_a_failure_inside_scanning_is_swallowed(self):
        self.watch()
        with patch("apps.checks.matcher.WatchHit.objects.create",
                   side_effect=RuntimeError("database on fire")):
            # Must return normally: the caller is mid-poll and cannot be interrupted.
            self.assertEqual(self.send(subject="Promotion", message_id="<w@x>"), 0)

    def test_the_reply_engine_does_not_import_checks(self):
        from apps.automation import engine
        source = open(engine.__file__).read()
        self.assertNotIn("apps.checks", source,
                         "the mail engine must not depend on the checks app")

    def test_watched_mailboxes_are_invisible_to_the_reply_engine(self):
        # A Rule with no mailboxes applies to every Mailbox in the workspace. Watched
        # mailboxes live in a different table, so they can never be swept up by one.
        self.assertEqual(Mailbox.objects.filter(workspace=self.ws).count(), 0)
        self.assertEqual(WatchMailbox.objects.filter(workspace=self.ws).count(), 1)


class WatchMailboxModel(Base):
    def test_password_is_encrypted_at_rest(self):
        self.wmb.password = "hunter2"
        self.wmb.save()
        row = WatchMailbox.objects.get(pk=self.wmb.pk)
        self.assertEqual(row.password, "hunter2")
        self.assertNotIn("hunter2", row.password_encrypted)

    def test_blank_username_falls_back_to_the_address(self):
        self.wmb.username = ""
        self.assertEqual(self.wmb.login_username, "manager@acme.com")

    def test_explicit_username_wins(self):
        self.wmb.username = "custom"
        self.assertEqual(self.wmb.login_username, "custom")

    def test_extra_folders_parse_into_a_list(self):
        self.wmb.extra_folders = "Promotions, Archive ,"
        self.assertEqual(self.wmb.extra_folder_list, ["Promotions", "Archive"])

    def test_has_no_smtp_fields(self):
        names = {f.name for f in WatchMailbox._meta.get_fields()}
        self.assertFalse({n for n in names if "smtp" in n},
                         "a watched mailbox must have no way to send")


class Poller(Base):
    def test_sent_folder_is_detected_by_special_use_flag(self):
        from apps.checks.poller import detect_sent_folders
        with patch("apps.checks.poller._list_folders",
                   return_value=[("INBOX", set()), ("Weird Name", {"\\sent"})]):
            self.assertEqual(detect_sent_folders(None), ["Weird Name"])

    def test_sent_folder_falls_back_to_known_names(self):
        from apps.checks.poller import detect_sent_folders
        with patch("apps.checks.poller._list_folders",
                   return_value=[("INBOX", set()), ("[Gmail]/Sent Mail", set())]):
            self.assertEqual(detect_sent_folders(None), ["[Gmail]/Sent Mail"])

    def test_unselectable_folders_are_skipped(self):
        from apps.checks.poller import detect_sent_folders
        with patch("apps.checks.poller._list_folders",
                   return_value=[("[Gmail]", {"\\noselect", "\\sent"})]):
            self.assertEqual(detect_sent_folders(None), [])

    def test_mail_from_a_sent_folder_is_marked_outgoing(self):
        from apps.checks.poller import _direction_for
        self.assertEqual(_direction_for("Sent", {"sent"}), WatchHit.Direction.OUTGOING)
        self.assertEqual(_direction_for("INBOX", {"sent"}), WatchHit.Direction.INCOMING)

    def test_folder_selection_honours_the_toggles(self):
        from apps.checks.poller import folders_for
        self.wmb.scan_inbox = True
        self.wmb.scan_sent = False
        self.wmb.scan_spam = False
        self.wmb.extra_folders = "Promotions"
        self.assertEqual(folders_for(self.wmb, None), ["INBOX", "Promotions"])

    def test_duplicate_folders_are_collapsed(self):
        from apps.checks.poller import folders_for
        self.wmb.scan_sent = False
        self.wmb.extra_folders = "INBOX, inbox"
        self.assertEqual(folders_for(self.wmb, None), ["INBOX"])

    def test_folders_are_selected_read_only(self):
        # Monitoring must not mark a campaign manager's unread mail as read.
        import inspect

        from apps.checks import poller
        source = inspect.getsource(poller._scan_folder)
        self.assertIn("readonly=True", source)

    def test_poller_cannot_send(self):
        import inspect

        from apps.checks import poller
        source = inspect.getsource(poller)
        self.assertNotIn("smtplib", source)
        self.assertNotIn("send_message", source)


class RealMessageParsing(Base):
    """Feed the matcher genuinely encoded mail, not hand-built strings."""

    def test_encoded_subject_and_multipart_body_are_matched(self):
        from apps.automation.engine import _decode, _extract_body

        raw = (
            b"Subject: =?utf-8?B?T3VyIFByb21vdGlvbiBpcyBsaXZl?=\r\n"
            b"From: Manager <manager@acme.com>\r\n"
            b"To: list@acme.com\r\n"
            b"Message-ID: <encoded@acme.com>\r\n"
            b'Content-Type: multipart/alternative; boundary="b1"\r\n'
            b"\r\n"
            b"--b1\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n\r\n"
            b"Body mentions Black Friday here.\r\n"
            b"--b1--\r\n"
        )
        msg = email_mod.message_from_bytes(raw)
        w = self.watch()
        scan_message(self.wmb, direction=WatchHit.Direction.INCOMING,
                     subject=_decode(msg.get("Subject", "")),
                     body=_extract_body(msg),
                     from_addr=_decode(msg.get("From", "")),
                     to_addr=_decode(msg.get("To", "")),
                     folder="INBOX",
                     message_id=(msg.get("Message-ID") or "").strip())
        hit = w.hits.get()
        self.assertEqual(hit.keyword, "Promotion")
        self.assertEqual(hit.subject, "Our Promotion is live")
        self.assertEqual(hit.message_id, "<encoded@acme.com>")
