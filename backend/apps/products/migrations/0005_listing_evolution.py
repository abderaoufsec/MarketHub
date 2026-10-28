# Phase 13 of docs/todo.md — evolve Product into the unified Listing model.
#
# Ordering matters and is deliberate (this file is hand-ordered, like the
# Phase 11 address-geography migration):
#
#   1. Add every new column *nullable* / with defaults, so a table that still
#      holds pre-Phase-13 rows can be read at every step;
#   2. make ``store`` nullable (a classified has no store);
#   3. backfill what the new columns mean for those rows:
#        seller        ← the store's owner (every old row was a store product)
#        listing_type  → STORE_PRODUCT (the column default already says so)
#        status        → ACTIVE      (the column default already says so)
#        slug          ← slugify(name) so /l/<slug>-<id> links work from day one
#        published_at  ← created_at  (they went live when they were created)
#        expires_at    → stays NULL: store SKUs are governed by inventory and
#                        is_available, not by ad windows; only wizard-published
#                        listings get an expiry (lifecycle.publish stamps it);
#   4. tighten ``seller`` to NOT NULL — every creation path in the codebase
#      now sets it, and an ownerless listing cannot be managed, paid out or
#      moderated. A row surviving step 3 without seller or store would mean
#      something outside this codebase wrote to the table; the migration
#      failing loudly is the correct outcome for that.
#
# The class keeps the name ``Product`` (Phase 0 decision #2: one catalog, one
# search index); "listing" is the domain term the fields above encode.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone
from django.utils.text import slugify


def backfill_listing_fields(apps, schema_editor):
    Product = apps.get_model("products", "Product")
    Store = apps.get_model("stores", "Store")

    # seller ← store owner. One statement (the ORM cannot update through the
    # join); table names come from the models, not string literals.
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE {Product._meta.db_table} AS p
            SET seller_id = s.owner_id
            FROM {Store._meta.db_table} AS s
            WHERE p.store_id = s.id AND p.seller_id IS NULL
            """
        )

    now = timezone.now()
    for product in Product.objects.filter(seller__isnull=False).iterator():
        updates = {}
        if not product.slug:
            slug = slugify(product.name)[:230].strip("-")
            updates["slug"] = slug or None
        if product.published_at is None and product.status == "ACTIVE":
            updates["published_at"] = product.created_at or now
        if updates:
            Product.objects.filter(pk=product.pk).update(**updates)


def unbackfill_listing_fields(apps, schema_editor):
    """Reverse: forget the Phase 13 bookkeeping, keep the data itself.

    ``seller`` is dropped back to nullable by the reverse AlterField, and the
    derived columns go back to NULL — nothing here invents information, so
    reversing only erases what this migration derived.
    """
    Product = apps.get_model("products", "Product")
    Product.objects.all().update(slug=None, published_at=None)


class Migration(migrations.Migration):

    # Non-atomic on purpose, and more than a convenience:
    #
    # Postgres refuses DDL ("cannot ALTER TABLE … because it has pending
    # trigger events") when the ALTER shares its transaction with the
    # backfill's UPDATEs — every FK that references `products` (inventory,
    # cart/order items, images, reviews) queues row triggers that the
    # rewrite of `SET NOT NULL` cannot coexist with. Committing each phase
    # on its own is exactly what the nullable-first ordering above was
    # designed for, so a crash mid-way leaves a database that resumes.
    atomic = False

    dependencies = [
        ("catalog", "0001_initial"),
        ("geography", "0001_initial"),
        ("products", "0004_product_category_fk"),
        ("stores", "0005_store_category_fk"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="commune",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="listings",
                to="geography.commune",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="contact_mode",
            field=models.CharField(
                choices=[
                    ("PHONE", "Phone"),
                    ("WHATSAPP", "WhatsApp"),
                    ("CHAT", "Chat"),
                    ("CHECKOUT", "Checkout"),
                ],
                default="CHECKOUT",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="currency",
            field=models.CharField(default="DZD", max_length=8),
        ),
        migrations.AddField(
            model_name="product",
            name="expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="product",
            name="listing_type",
            field=models.CharField(
                choices=[
                    ("STORE_PRODUCT", "Store product"),
                    ("FOR_SALE", "For sale"),
                    ("SERVICE", "Service"),
                    ("JOB", "Job"),
                    ("RENT", "Rent"),
                    ("WANTED", "Wanted"),
                ],
                default="STORE_PRODUCT",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="old_price",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name="product",
            name="price_mode",
            field=models.CharField(
                choices=[
                    ("FIXED", "Fixed"),
                    ("NEGOTIABLE", "Negotiable"),
                    ("ON_REQUEST", "On request"),
                    ("FREE", "Free"),
                    ("EXCHANGE", "Exchange"),
                ],
                default="FIXED",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="published_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        # Nullable in THIS file's order of operations; tightened to NOT NULL
        # after the backfill below (see the header).
        migrations.AddField(
            model_name="product",
            name="seller",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="listings",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="slug",
            field=models.SlugField(blank=True, max_length=250, null=True),
        ),
        migrations.AddField(
            model_name="product",
            name="sold_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="product",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Draft"),
                    ("PENDING_REVIEW", "Pending review"),
                    ("ACTIVE", "Active"),
                    ("EXPIRED", "Expired"),
                    ("SOLD", "Sold"),
                    ("REJECTED", "Rejected"),
                    ("ARCHIVED", "Archived"),
                ],
                default="ACTIVE",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="wilaya",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="listings",
                to="geography.wilaya",
            ),
        ),
        migrations.AlterField(
            model_name="product",
            name="store",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="products",
                to="stores.store",
            ),
        ),
        migrations.RunPython(backfill_listing_fields, unbackfill_listing_fields),
        migrations.AlterField(
            model_name="product",
            name="seller",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="listings",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(fields=["status", "-created_at"], name="products_status_newest"),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(
                fields=["seller", "status", "-created_at"], name="products_seller_status"
            ),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(fields=["status", "expires_at"], name="products_expiry"),
        ),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("listing_type", "STORE_PRODUCT"), _negated=True),
                    ("store__isnull", False),
                    _connector="OR",
                ),
                name="store_product_requires_store",
            ),
        ),
    ]
