# Phase 11 (docs/todo.md): Address loses its free-text location trio and
# gains Wilaya/Commune foreign keys.
#
# Order matters and is deliberate — this file is NOT what `makemigrations`
# would generate on its own (it emits RemoveField *before* AddField, which
# would destroy `city`/`state_province` before their values could be copied):
#
#   1. add the new nullable FKs,
#   2. copy every matchable address over (RunPython below),
#   3. only then drop the old columns.
#
# Matching is best-effort and accent/case-insensitive against both the French
# and Arabic names. An address whose free text matches nothing keeps NULLs —
# the API refuses *new* writes without a wilaya, but legacy rows are never
# silently pointed at the wrong commune.

import unicodedata

from django.db import migrations, models
import django.db.models.deletion


def _norm(text):
    """Accent- and case-insensitive comparison key."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.lower().split())


def match_addresses_to_geography(apps, schema_editor):
    Address = apps.get_model("users", "Address")
    Wilaya = apps.get_model("geography", "Wilaya")
    Commune = apps.get_model("geography", "Commune")

    wilaya_by_name = {}
    for wilaya in Wilaya.objects.all():
        wilaya_by_name[_norm(wilaya.name_fr)] = wilaya
        wilaya_by_name[_norm(wilaya.name_ar)] = wilaya

    commune_in_wilaya = {}
    communes_by_name = {}
    for commune in Commune.objects.select_related("wilaya"):
        commune_in_wilaya[(commune.wilaya_id, _norm(commune.name_fr))] = commune
        communes_by_name.setdefault(_norm(commune.name_fr), []).append(commune)

    updated = 0
    for address in Address.objects.all().iterator():
        wilaya = wilaya_by_name.get(_norm(address.state_province)) or wilaya_by_name.get(
            _norm(address.city)
        )
        commune = None
        if wilaya is not None:
            commune = commune_in_wilaya.get((wilaya.id, _norm(address.city)))
        if commune is None:
            candidates = communes_by_name.get(_norm(address.city), [])
            if len(candidates) == 1:  # unambiguous country-wide match
                commune = candidates[0]
                wilaya = wilaya or commune.wilaya
        if wilaya is not None or commune is not None:
            address.wilaya = wilaya
            address.commune = commune
            address.save(update_fields=["wilaya", "commune"])
            updated += 1

    if updated:
        print(f"  matched {updated} address(es) to wilaya/commune")


class Migration(migrations.Migration):

    dependencies = [
        ("geography", "0001_initial"),
        ("users", "0005_alter_user_managers"),
    ]

    operations = [
        migrations.AddField(
            model_name="address",
            name="wilaya",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="addresses",
                to="geography.wilaya",
            ),
        ),
        migrations.AddField(
            model_name="address",
            name="commune",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="addresses",
                to="geography.commune",
            ),
        ),
        migrations.AlterField(
            model_name="address",
            name="country",
            field=models.CharField(blank=True, default="DZ", max_length=100),
        ),
        migrations.RunPython(
            match_addresses_to_geography, migrations.RunPython.noop, elidable=False
        ),
        migrations.RemoveField(model_name="address", name="city"),
        migrations.RemoveField(model_name="address", name="postal_code"),
        migrations.RemoveField(model_name="address", name="state_province"),
    ]
