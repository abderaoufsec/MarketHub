from django.contrib import admin

from .models import Commune, Wilaya


@admin.register(Wilaya)
class WilayaAdmin(admin.ModelAdmin):
    list_display = ["code", "name_fr", "name_ar", "is_active", "commune_count"]
    list_filter = ["is_active"]
    search_fields = ["code", "name_fr", "name_ar"]
    ordering = ["code"]

    @admin.display(description="Communes")
    def commune_count(self, obj):
        return obj.communes.count()


@admin.register(Commune)
class CommuneAdmin(admin.ModelAdmin):
    list_display = ["code", "name_fr", "name_ar", "wilaya", "is_active"]
    list_filter = ["wilaya", "is_active"]
    search_fields = ["code", "name_fr", "name_ar", "wilaya__name_fr"]
    ordering = ["wilaya__code", "code"]
