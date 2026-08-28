"""Tests for the auto-reply engine's repeat-reply guard.

The behaviour under test is invisible when it works and embarrassing when it does
not — the failure mode is a customer receiving the same automated reply repeatedly.
"""
from django.test import TestCase
from django.utils import timezone

from apps.automation.engine import _already_answered, _maybe_schedule_reply
from apps.automation.models import Config
from apps.mail.models import EmailMessage, normalize_subject
from apps.mailboxes.models import Mailbox
from apps.rules.models import ReplyTemplate, Rule
from apps.workspaces.models import Workspace


class Base(TestCase):
    def setUp(self):
        self.ws = Workspace.objects.create(name="Acme")
        self.config = Config.load(self.ws)
        self.mailbox = Mailbox.objects.create(
            workspace=self.ws, name="Sales", email_address="sales@acme.com",
            username="sales@acme.com", imap_host="imap", imap_port=993,
            smtp_host="smtp", smtp_port=587,
        )
        self.template = ReplyTemplate.objects.create(
            workspace=self.ws, name="Standard",
            subject="Re: {{original_subject}}", body="Hi {{sender_name}}",
        )
        self.rule = Rule.objects.create(
            workspace=self.ws, name="Inquiries", match_type="contains",
            match_value="Inquiry", template=self.template, priority=100,
        )

    def receive(self, subject, from_addr="jane@example.com"):
        """Record an incoming email the way the poller would."""
        return EmailMessage.objects.create(
            workspace=self.ws, mailbox=self.mailbox,
            direction=EmailMessage.Direction.INCOMING,
            status=EmailMessage.Status.RECEIVED,
            subject=subject, thread_key=normalize_subject(subject),
            from_addr=from_addr, to_addr=self.mailbox.email_address,
            received_at=timezone.now(),
        )

    def replies(self):
        return EmailMessage.objects.filter(direction=EmailMessage.Direction.OUTGOING)


class RepliesOncePerThread(Base):
    def test_first_email_gets_a_reply(self):
        incoming = self.receive("Project Inquiry")
        _maybe_schedule_reply(self.mailbox, incoming, self.config)
        self.assertEqual(self.replies().count(), 1)

    def test_same_sender_same_subject_is_not_answered_twice(self):
        first = self.receive("Project Inquiry")
        _maybe_schedule_reply(self.mailbox, first, self.config)
        second = self.receive("Project Inquiry")
        _maybe_schedule_reply(self.mailbox, second, self.config)
        self.assertEqual(self.replies().count(), 1)

    def test_re_prefix_counts_as_the_same_thread(self):
        first = self.receive("Project Inquiry")
        _maybe_schedule_reply(self.mailbox, first, self.config)
        follow_up = self.receive("Re: Project Inquiry")
        _maybe_schedule_reply(self.mailbox, follow_up, self.config)
        self.assertEqual(self.replies().count(), 1)

    def test_different_capitalisation_is_the_same_thread(self):
        first = self.receive("Project Inquiry")
        _maybe_schedule_reply(self.mailbox, first, self.config)
        again = self.receive("PROJECT INQUIRY")
        _maybe_schedule_reply(self.mailbox, again, self.config)
        self.assertEqual(self.replies().count(), 1)

    def test_a_different_sender_still_gets_a_reply(self):
        _maybe_schedule_reply(self.mailbox, self.receive("Project Inquiry"), self.config)
        other = self.receive("Project Inquiry", from_addr="bob@example.com")
        _maybe_schedule_reply(self.mailbox, other, self.config)
        self.assertEqual(self.replies().count(), 2)

    def test_sender_address_is_compared_case_insensitively(self):
        _maybe_schedule_reply(self.mailbox, self.receive("Project Inquiry"), self.config)
        same_person = self.receive("Project Inquiry", from_addr="JANE@example.com")
        _maybe_schedule_reply(self.mailbox, same_person, self.config)
        self.assertEqual(self.replies().count(), 1)

    def test_a_different_subject_still_gets_a_reply(self):
        _maybe_schedule_reply(self.mailbox, self.receive("Project Inquiry"), self.config)
        other = self.receive("Second Inquiry about pricing")
        _maybe_schedule_reply(self.mailbox, other, self.config)
        self.assertEqual(self.replies().count(), 2)

    def test_the_guard_can_be_switched_off(self):
        self.config.reply_once_per_thread = False
        self.config.save()
        _maybe_schedule_reply(self.mailbox, self.receive("Project Inquiry"), self.config)
        _maybe_schedule_reply(self.mailbox, self.receive("Project Inquiry"), self.config)
        self.assertEqual(self.replies().count(), 2)


class WhichPastRepliesCount(Base):
    def test_a_failed_reply_does_not_block_a_retry(self):
        first = self.receive("Project Inquiry")
        _maybe_schedule_reply(self.mailbox, first, self.config)
        self.replies().update(status=EmailMessage.Status.FAILED)

        second = self.receive("Project Inquiry")
        _maybe_schedule_reply(self.mailbox, second, self.config)
        self.assertEqual(self.replies().count(), 2,
                         "a delivery failure must not silence the rule for good")

    def test_a_still_scheduled_reply_blocks_a_duplicate(self):
        first = self.receive("Project Inquiry")
        _maybe_schedule_reply(self.mailbox, first, self.config)
        self.assertEqual(self.replies().get().status, EmailMessage.Status.SCHEDULED)

        # A second email arriving during the reply delay must not queue a second copy.
        second = self.receive("Project Inquiry")
        _maybe_schedule_reply(self.mailbox, second, self.config)
        self.assertEqual(self.replies().count(), 1)

    def test_a_sent_reply_blocks_a_duplicate(self):
        _maybe_schedule_reply(self.mailbox, self.receive("Project Inquiry"), self.config)
        self.replies().update(status=EmailMessage.Status.SENT)
        _maybe_schedule_reply(self.mailbox, self.receive("Project Inquiry"), self.config)
        self.assertEqual(self.replies().count(), 1)


class ScopedCorrectly(Base):
    def test_a_different_rule_is_tracked_separately(self):
        _maybe_schedule_reply(self.mailbox, self.receive("Project Inquiry"), self.config)
        incoming = self.receive("Project Inquiry")
        other_rule = Rule.objects.create(
            workspace=self.ws, name="Other", match_type="contains",
            match_value="Inquiry", template=self.template, priority=50,
        )
        self.assertFalse(_already_answered(self.mailbox, incoming, other_rule))

    def test_another_mailbox_answers_independently(self):
        _maybe_schedule_reply(self.mailbox, self.receive("Project Inquiry"), self.config)
        second_box = Mailbox.objects.create(
            workspace=self.ws, name="Support", email_address="support@acme.com",
            username="support@acme.com", imap_host="i", imap_port=993,
            smtp_host="s", smtp_port=587,
        )
        incoming = EmailMessage.objects.create(
            workspace=self.ws, mailbox=second_box,
            direction=EmailMessage.Direction.INCOMING,
            status=EmailMessage.Status.RECEIVED,
            subject="Project Inquiry", thread_key=normalize_subject("Project Inquiry"),
            from_addr="jane@example.com", to_addr=second_box.email_address,
            received_at=timezone.now(),
        )
        self.assertFalse(_already_answered(second_box, incoming, self.rule))


class TemplateSubjectIndependence(Base):
    """The guard must hold even when the reply's own subject is unrelated.

    This is the case a naive implementation gets wrong: keying on the reply's
    thread_key works only while templates start with "Re: {{original_subject}}".
    """

    def test_template_with_its_own_subject_still_replies_only_once(self):
        self.template.subject = "Thanks for getting in touch"
        self.template.save()

        first = self.receive("Project Inquiry")
        _maybe_schedule_reply(self.mailbox, first, self.config)
        reply = self.replies().get()
        self.assertNotEqual(reply.thread_key, first.thread_key,
                            "precondition: the reply's own subject is unrelated")

        second = self.receive("Project Inquiry")
        _maybe_schedule_reply(self.mailbox, second, self.config)
        self.assertEqual(self.replies().count(), 1)
