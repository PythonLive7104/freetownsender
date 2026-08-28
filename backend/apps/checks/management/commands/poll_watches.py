"""Read watched mailboxes and record keyword matches.

    python manage.py poll_watches

`run_engine` already does this every tick; this command exists for setups that run
the checks on their own schedule, and for testing a poll by hand.
"""
from django.core.management.base import BaseCommand

from apps.checks.poller import poll_all


class Command(BaseCommand):
    help = "Poll watched mailboxes for keyword matches."

    def handle(self, *args, **options):
        totals = poll_all()
        self.stdout.write(self.style.SUCCESS(
            f"mailboxes={totals['mailboxes']} scanned={totals['scanned']} errors={totals['errors']}"
        ))
