from django.contrib import admin

from .models import Watch, WatchHit, WatchMailbox


@admin.register(Watch)
class WatchAdmin(admin.ModelAdmin):
    list_display = ("name", "workspace", "is_active", "watch_incoming", "watch_outgoing")
    list_filter = ("is_active", "workspace")


@admin.register(WatchHit)
class WatchHitAdmin(admin.ModelAdmin):
    list_display = ("keyword", "direction", "mailbox", "subject", "created_at")
    list_filter = ("direction", "notified")
    search_fields = ("keyword", "subject", "from_addr")


@admin.register(WatchMailbox)
class WatchMailboxAdmin(admin.ModelAdmin):
    list_display = ("name", "email_address", "workspace", "is_active", "last_polled_at")
    list_filter = ("is_active",)
