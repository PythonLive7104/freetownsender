from rest_framework import serializers

from .models import Config


class ConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = Config
        fields = [
            "auto_reply_enabled", "reply_delay_minutes", "poll_interval_seconds",
            "signature", "reply_once_per_thread", "updated_at",
        ]
        read_only_fields = ["updated_at"]
