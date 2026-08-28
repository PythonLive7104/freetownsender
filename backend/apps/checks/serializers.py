from rest_framework import serializers

from .models import Watch, WatchHit, WatchMailbox


class WatchMailboxSerializer(serializers.ModelSerializer):
    """Read-only monitoring account. No SMTP fields exist — a watch never sends."""

    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    has_password = serializers.SerializerMethodField()
    username = serializers.CharField(required=False, allow_blank=True)
    hit_count = serializers.SerializerMethodField()

    class Meta:
        model = WatchMailbox
        fields = [
            "id", "name", "email_address", "username", "password", "has_password",
            "imap_host", "imap_port", "imap_use_ssl",
            "scan_inbox", "scan_sent", "scan_spam", "extra_folders",
            "is_active", "hit_count", "last_polled_at", "last_error",
            "created_at", "updated_at",
        ]
        read_only_fields = ["last_polled_at", "last_error", "created_at", "updated_at"]

    def get_has_password(self, obj) -> bool:
        return bool(obj.password_encrypted)

    def get_hit_count(self, obj) -> int:
        return obj.hits.count()

    def validate(self, attrs):
        # Blank username means "same as the address" — store it that way rather than
        # letting an empty login reach the server, which reports it confusingly.
        if not (attrs.get("username") or "").strip():
            email = attrs.get("email_address") or getattr(self.instance, "email_address", "")
            if email:
                attrs["username"] = email
        if not any([
            attrs.get("scan_inbox", getattr(self.instance, "scan_inbox", True)),
            attrs.get("scan_sent", getattr(self.instance, "scan_sent", True)),
            attrs.get("scan_spam", getattr(self.instance, "scan_spam", False)),
            (attrs.get("extra_folders") or getattr(self.instance, "extra_folders", "")).strip(),
        ]):
            raise serializers.ValidationError("Pick at least one folder to watch.")
        return attrs

    def create(self, validated_data):
        raw = validated_data.pop("password", "")
        obj = WatchMailbox(**validated_data)
        if raw:
            obj.password = raw
        obj.save()
        return obj

    def update(self, instance, validated_data):
        raw = validated_data.pop("password", "")
        for k, v in validated_data.items():
            setattr(instance, k, v)
        # A blank password on edit means "keep the existing one".
        if raw:
            instance.password = raw
        instance.save()
        return instance


class WatchSerializer(serializers.ModelSerializer):
    hit_count = serializers.SerializerMethodField()
    last_hit_at = serializers.SerializerMethodField()
    keyword_list = serializers.SerializerMethodField()

    class Meta:
        model = Watch
        fields = [
            "id", "name", "keywords", "keyword_list", "mailboxes",
            "match_subject", "match_body", "case_sensitive",
            "watch_incoming", "watch_outgoing",
            "notify_telegram", "max_alerts_per_hour",
            "is_active", "hit_count", "last_hit_at", "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_hit_count(self, obj) -> int:
        return obj.hits.count()

    def get_last_hit_at(self, obj):
        row = obj.hits.order_by("-created_at").first()
        return row.created_at if row else None

    def get_keyword_list(self, obj) -> list[str]:
        return obj.keyword_list

    def validate_keywords(self, value):
        # A watch with no keywords silently matches nothing, which looks like a bug.
        if not [k.strip() for k in value.replace("\n", ",").split(",") if k.strip()]:
            raise serializers.ValidationError("Add at least one keyword.")
        return value

    def validate(self, attrs):
        subject = attrs.get("match_subject", getattr(self.instance, "match_subject", True))
        body = attrs.get("match_body", getattr(self.instance, "match_body", True))
        if not subject and not body:
            raise serializers.ValidationError("Search the subject, the body, or both — not neither.")
        incoming = attrs.get("watch_incoming", getattr(self.instance, "watch_incoming", True))
        outgoing = attrs.get("watch_outgoing", getattr(self.instance, "watch_outgoing", True))
        if not incoming and not outgoing:
            raise serializers.ValidationError("Watch received mail, sent mail, or both — not neither.")
        return attrs

    def validate_mailboxes(self, value):
        # Guard against attaching another workspace's mailbox by id.
        request = self.context.get("request")
        if request and value:
            from apps.workspaces.services import active_workspace
            ws = active_workspace(request.user)
            allowed = set(WatchMailbox.objects.filter(workspace=ws).values_list("id", flat=True))
            for mb in value:
                if mb.id not in allowed:
                    raise serializers.ValidationError("That mailbox is not in this workspace.")
        return value


class WatchHitSerializer(serializers.ModelSerializer):
    watch_name = serializers.CharField(source="watch.name", read_only=True)
    mailbox_name = serializers.CharField(source="mailbox.name", read_only=True)

    class Meta:
        model = WatchHit
        fields = [
            "id", "watch", "watch_name", "mailbox", "mailbox_name",
            "direction", "keyword", "matched_in", "subject",
            "from_addr", "to_addr", "folder", "excerpt",
            "notified", "occurred_at", "created_at",
        ]
