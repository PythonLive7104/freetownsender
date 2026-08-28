from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.mixins import WorkspaceScopedMixin

from .matcher import _find
from .models import Watch, WatchHit, WatchMailbox
from .poller import poll_watch_mailbox, test_connection
from .serializers import WatchHitSerializer, WatchMailboxSerializer, WatchSerializer


class WatchMailboxViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    queryset = WatchMailbox.objects.all()
    serializer_class = WatchMailboxSerializer

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        """Check the login works and report which folders would be read."""
        return Response(test_connection(self.get_object()))

    @action(detail=True, methods=["post"])
    def poll(self, request, pk=None):
        """Read this mailbox now instead of waiting for the next cycle."""
        mailbox = self.get_object()
        try:
            scanned = poll_watch_mailbox(mailbox)
            return Response({"ok": True, "scanned": scanned, "error": ""})
        except Exception as exc:  # noqa: BLE001
            WatchMailbox.objects.filter(pk=mailbox.pk).update(last_error=str(exc)[:2000])
            return Response({"ok": False, "scanned": 0, "error": str(exc)}, status=400)


class WatchViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    queryset = Watch.objects.prefetch_related("mailboxes").all()
    serializer_class = WatchSerializer

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        """Try this watch's keywords against sample text, so a user can confirm the
        watch does what they think before waiting for real mail."""
        watch = self.get_object()
        subject = request.data.get("subject", "")
        body = request.data.get("body", "")
        for keyword in watch.keyword_list:
            if watch.match_subject and _find(keyword, subject, watch.case_sensitive):
                return Response({"matched": True, "keyword": keyword, "where": "subject"})
            if watch.match_body and _find(keyword, body, watch.case_sensitive):
                return Response({"matched": True, "keyword": keyword, "where": "body"})
        return Response({"matched": False, "keyword": None, "where": None})


class WatchHitViewSet(WorkspaceScopedMixin, mixins.ListModelMixin,
                      mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """Read-only log of what matched, newest first. Filterable by ?watch=<id>."""

    queryset = WatchHit.objects.select_related("watch", "mailbox").all()
    serializer_class = WatchHitSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        watch_id = self.request.query_params.get("watch")
        if watch_id:
            qs = qs.filter(watch_id=watch_id)
        return qs[:200]
