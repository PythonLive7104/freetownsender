import re

from django.db import models
from django.utils import timezone

from apps.mailboxes.crypto import decrypt, encrypt


class WatchMailbox(models.Model):
    """A mailbox monitored by Checks, kept deliberately separate from Mailbox.

    Two reasons it is not the same table:

    1. Safety. A Rule with no mailboxes selected applies to *every* Mailbox in the
       workspace, so a campaign manager's inbox living in that list could be
       auto-replied to on his behalf. Nothing here is reachable by the reply engine.
    2. Intent. These are accounts being observed, not accounts being operated. There
       are no SMTP fields because a watch never sends — it only ever reads.
    """

    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE,
                                  related_name="watch_mailboxes")
    name = models.CharField(max_length=200)
    email_address = models.EmailField()
    username = models.CharField(max_length=200, blank=True, default="")
    password_encrypted = models.TextField(blank=True, default="")

    imap_host = models.CharField(max_length=255)
    imap_port = models.PositiveIntegerField(default=993)
    imap_use_ssl = models.BooleanField(default=True)

    # Which folders to read. Sent is the one that shows a campaign going out.
    scan_inbox = models.BooleanField(default=True)
    scan_sent = models.BooleanField(default=True)
    scan_spam = models.BooleanField(default=False)
    extra_folders = models.CharField(max_length=500, blank=True, default="")

    is_active = models.BooleanField(default=True)
    folder_cursors = models.JSONField(default=dict, blank=True)
    last_polled_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "watched mailbox"
        verbose_name_plural = "watched mailboxes"

    def __str__(self):
        return f"{self.name} <{self.email_address}>"

    @property
    def password(self) -> str:
        return decrypt(self.password_encrypted)

    @password.setter
    def password(self, value: str):
        self.password_encrypted = encrypt(value or "")

    @property
    def login_username(self) -> str:
        """Providers almost always want the full address; users leave this blank
        expecting that. Same fallback the auto-reply mailboxes use."""
        return self.username or self.email_address

    @property
    def extra_folder_list(self) -> list[str]:
        return [f.strip() for f in (self.extra_folders or "").split(",") if f.strip()]


class Watch(models.Model):
    """A keyword watch across some or all of a workspace's mailboxes.

    Distinct from a Rule: a Rule answers mail, a Watch only observes it. Nothing a
    Watch does can send, alter or delete a message — it records what matched and
    raises a Telegram alert.
    """

    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE, related_name="watches")
    name = models.CharField(max_length=200)

    # Comma- or newline-separated. Stored as typed so the user sees their own list.
    keywords = models.TextField(help_text="Comma or newline separated.")

    # Empty means every mailbox in the workspace, including ones added later —
    # which is what "watch all our company mailboxes" should keep meaning.
    mailboxes = models.ManyToManyField(WatchMailbox, blank=True, related_name="watches")

    match_subject = models.BooleanField(default=True)
    match_body = models.BooleanField(default=True)
    case_sensitive = models.BooleanField(default=False)

    # Incoming catches campaign responses; outgoing catches the campaign going out.
    watch_incoming = models.BooleanField(default=True)
    watch_outgoing = models.BooleanField(default=True)

    notify_telegram = models.BooleanField(default=True)
    # A campaign can draw hundreds of replies in minutes. Past this many alerts in a
    # rolling hour the watch goes quiet and counts what it suppressed, reporting the
    # total on the next alert instead of flooding the phone.
    max_alerts_per_hour = models.PositiveIntegerField(default=20)
    suppressed_count = models.PositiveIntegerField(default=0)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "watches"

    def __str__(self):
        return self.name

    @property
    def keyword_list(self) -> list[str]:
        """Keywords as a clean list, split on commas and newlines, blanks dropped."""
        return [k.strip() for k in re.split(r"[,\n]", self.keywords or "") if k.strip()]

    def covers(self, mailbox) -> bool:
        """True when this watch applies to `mailbox`. No selection means all of them."""
        if not self.mailboxes.exists():
            return True
        return self.mailboxes.filter(pk=mailbox.pk).exists()

    def alerts_sent_last_hour(self) -> int:
        since = timezone.now() - timezone.timedelta(hours=1)
        return self.hits.filter(notified=True, created_at__gte=since).count()


class WatchHit(models.Model):
    """One email that matched a watch.

    Deliberately self-contained rather than pointing at an EmailMessage: outgoing
    mail is scanned straight from the Sent folder and never enters the mail feed, so
    there is no row to point at. Keeping a snapshot also means a hit stays readable
    after the message it came from is gone.
    """

    class Direction(models.TextChoices):
        INCOMING = "incoming", "Incoming"
        OUTGOING = "outgoing", "Outgoing"

    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE, related_name="watch_hits")
    watch = models.ForeignKey(Watch, on_delete=models.CASCADE, related_name="hits")
    mailbox = models.ForeignKey(WatchMailbox, on_delete=models.CASCADE, related_name="hits")

    direction = models.CharField(max_length=10, choices=Direction.choices)
    keyword = models.CharField(max_length=200)
    matched_in = models.CharField(max_length=10, blank=True, default="")  # subject | body

    subject = models.CharField(max_length=998, blank=True, default="")
    from_addr = models.CharField(max_length=320, blank=True, default="")
    to_addr = models.CharField(max_length=998, blank=True, default="")
    folder = models.CharField(max_length=255, blank=True, default="")
    message_id = models.CharField(max_length=512, blank=True, default="", db_index=True)
    excerpt = models.TextField(blank=True, default="")

    notified = models.BooleanField(default=False)
    occurred_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["workspace", "-created_at"]),
            # The scanner asks "have I already logged this message for this watch?"
            # on every message it sees, so that lookup gets its own index.
            models.Index(fields=["watch", "message_id"]),
        ]

    def __str__(self):
        return f"{self.keyword} in {self.subject[:40]}"
