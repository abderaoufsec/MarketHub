"""Automated pre-publish checks (Phase 17).

A listing is scanned *before* it can go live. Three outcomes are possible:

* ``block``  - never publish; the seller gets ``listing_blocked`` with the
  offending codes (weapons, drugs, a phone number in the description).
* ``review`` - publish into the moderation queue (``PENDING_REVIEW``) even
  when ``LISTINGS_REQUIRE_MODERATION`` is off: a known scam template or a
  copied photo is suspicious, not automatically fatal.
* ``info``   - recorded on ``Product.moderation_flags`` but does not change
  the status (duplicate *text* across sellers is common for identical items).

The checks are intentionally cheap and deterministic; a false positive must
cost a moderator a glance, never silently hide a legitimate ad.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from statistics import median

from django.conf import settings

from .blocklists import blocklist_flags, extract_contacts

SEVERITY_BLOCK = "block"
SEVERITY_REVIEW = "review"
SEVERITY_INFO = "info"

#: Multilingual banned keywords. Word-boundary matching is used for Latin
#: phrases; Arabic is matched as a normalized substring (word boundaries are
#: not portable there).
BANNED_KEYWORDS = (
    "arme",
    "armes",
    "weapon",
    "firearm",
    "pistol",
    "fusil",
    "kalashnikov",
    "drogue",
    "drogues",
    "cocaine",
    "cocaïne",
    "heroine",
    "héroïne",
    "ecstasy",
    "methamphetamine",
    "faux papiers",
    "faux documents",
    "fausse carte",
    "fake papers",
    "fake documents",
    "counterfeit documents",
    "وثائق مزورة",
    "جواز مزور",
    "سلاح",
    "أسلحة",
    "مخدرات",
    "كوكايين",
    "هيروين",
)

PROHIBITED_CATEGORY_KEYWORDS = (
    "arme",
    "weapon",
    "drogue",
    "drug",
    "tabac",
    "tobacco",
    "alcool",
    "alcohol",
    "contrefaçon",
    "counterfeit",
    "document",
    "سلاح",
    "أسلحة",
    "مخدرات",
    "تبغ",
)

SCAM_TEMPLATES = (
    "western union",
    "moneygram",
    "paiement à l'avance",
    "paiement d'avance",
    "payer d'abord",
    "virement avant livraison",
    "bitcoin only",
    "crypto only",
    "usdt only",
    "paypal gift",
    "الدفع مسبقا",
    "الدفع مقدما",
    "تحويل مسبق",
    "ويسترن يونيون",
    "بيتكوين فقط",
    "لا يوجد دفع عند الاستلام",
)


@dataclass(frozen=True)
class TrustIssue:
    code: str
    message: str
    severity: str
    field: str = ""
    details: dict = dataclass_field(default_factory=dict)

    def as_dict(self) -> dict:
        payload = {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
        }
        if self.field:
            payload["field"] = self.field
        if self.details:
            payload["details"] = self.details
        return payload


@dataclass
class CheckResult:
    issues: list[TrustIssue]

    @property
    def blocking(self) -> list[TrustIssue]:
        return [issue for issue in self.issues if issue.severity == SEVERITY_BLOCK]

    @property
    def requiring_review(self) -> list[TrustIssue]:
        return [issue for issue in self.issues if issue.severity == SEVERITY_REVIEW]

    @property
    def warnings(self) -> list[TrustIssue]:
        return [issue for issue in self.issues if issue.severity == SEVERITY_INFO]

    @property
    def should_review(self) -> bool:
        return bool(self.requiring_review)

    def as_dicts(self) -> list[dict]:
        return [issue.as_dict() for issue in self.issues]


def _contains_keyword(text: str, keyword: str) -> bool:
    lowered = (text or "").casefold()
    needle = keyword.casefold()
    if any(ord(char) > 127 for char in needle):
        return needle in lowered
    return bool(re.search(rf"(?<![\w]){re.escape(needle)}(?![\w])", lowered))


def _category_names(product) -> str:
    parts: list[str] = []
    category = getattr(product, "category", None)
    while category is not None:
        parts.extend(
            [
                category.slug or "",
                category.name_fr or "",
                category.name_en or "",
                category.name_ar or "",
            ]
        )
        category = category.parent
    return " ".join(parts)


def _scan_text(product, issues: list[TrustIssue]) -> None:
    text = f"{product.name or ''}\n{product.description or ''}"
    hits = [keyword for keyword in BANNED_KEYWORDS if _contains_keyword(text, keyword)]
    if hits:
        issues.append(
            TrustIssue(
                code="banned_keyword",
                message="The listing contains a prohibited item or keyword.",
                severity=SEVERITY_BLOCK,
                field="description",
                details={"keywords": hits},
            )
        )

    scams = [phrase for phrase in SCAM_TEMPLATES if _contains_keyword(text, phrase)]
    if scams:
        issues.append(
            TrustIssue(
                code="scam_template",
                message="The listing matches a known scam payment pattern.",
                severity=SEVERITY_REVIEW,
                field="description",
                details={"phrases": scams},
            )
        )


def _scan_contacts(product, issues: list[TrustIssue]) -> None:
    contacts = extract_contacts(f"{product.name or ''}\n{product.description or ''}")
    if contacts["phones"] or contacts["emails"] or contacts["bank_accounts"]:
        issues.append(
            TrustIssue(
                code="contact_in_description",
                message="Keep phone numbers, e-mail addresses and bank details out of the description.",
                severity=SEVERITY_BLOCK,
                field="description",
                details={key: value for key, value in contacts.items() if value},
            )
        )

    flags = blocklist_flags(f"{product.name or ''}\n{product.description or ''}")
    if flags:
        issues.append(
            TrustIssue(
                code="blocklisted_contact",
                message="A contact in this listing is on the shared blocklist.",
                severity=SEVERITY_BLOCK,
                field="description",
                details={"matches": flags},
            )
        )

    seller = getattr(product, "seller", None)
    seller_phone = getattr(seller, "phone_number", None)
    if seller_phone and blocklist_flags(seller_phone):
        issues.append(
            TrustIssue(
                code="blocklisted_seller",
                message="This seller's phone number is on the shared blocklist.",
                severity=SEVERITY_BLOCK,
                field="seller",
                details={"phone_number": seller_phone},
            )
        )


def _scan_category(product, issues: list[TrustIssue]) -> None:
    names = _category_names(product)
    hits = [
        keyword for keyword in PROHIBITED_CATEGORY_KEYWORDS if _contains_keyword(names, keyword)
    ]
    if hits:
        issues.append(
            TrustIssue(
                code="prohibited_category",
                message="This category is not allowed on MarketHub.",
                severity=SEVERITY_BLOCK,
                field="category",
                details={"keywords": hits},
            )
        )


def _scan_price(product, issues: list[TrustIssue]) -> None:
    from apps.products.models import ListingStatus, PriceMode, Product

    if product.price_mode not in (PriceMode.FIXED, PriceMode.NEGOTIABLE):
        return
    price = product.base_price or 0
    if price <= 0 or product.category_id is None:
        return

    peer_prices = list(
        Product.objects.filter(
            category_id=product.category_id,
            status=ListingStatus.ACTIVE,
            base_price__gt=0,
        )
        .exclude(pk=product.pk)
        .values_list("base_price", flat=True)[:200]
    )
    if len(peer_prices) < 5:
        return
    typical = median(float(value) for value in peer_prices)
    if typical <= 0:
        return
    ratio = float(price) / typical
    if ratio < settings.TRUST_PRICE_ANOMALY_FACTOR:
        issues.append(
            TrustIssue(
                code="price_anomaly",
                message="The price is far below similar listings and will be reviewed.",
                severity=SEVERITY_REVIEW,
                field="base_price",
                details={
                    "price": str(product.base_price),
                    "typical_price": round(typical, 2),
                    "ratio": round(ratio, 3),
                },
            )
        )


def _normalized_description(value: str) -> str:
    return " ".join((value or "").casefold().split())


def _scan_duplicate_text(product, issues: list[TrustIssue]) -> None:
    from apps.products.models import ListingStatus, Product

    body = _normalized_description(product.description)
    if len(body) < 40:
        return
    duplicate = (
        Product.objects.filter(
            status=ListingStatus.ACTIVE,
            category_id=product.category_id,
            description__iexact=product.description,
        )
        .exclude(pk=product.pk)
        .only("id", "name")
        .first()
    )
    if duplicate:
        issues.append(
            TrustIssue(
                code="duplicate_text",
                message="Another live listing has the same description.",
                severity=SEVERITY_INFO,
                field="description",
                details={"listing_id": duplicate.pk, "listing_name": duplicate.name},
            )
        )


def _hamming_distance(left: str, right: str) -> int:
    try:
        return bin(int(left, 16) ^ int(right, 16)).count("1")
    except (TypeError, ValueError):
        return 64


def _scan_images(product, issues: list[TrustIssue]) -> None:
    from apps.products.models import ProductImage

    hashes = [
        image.upload.phash
        for image in product.images.all()
        if image.upload_id and image.upload and image.upload.phash
    ]
    if not hashes:
        return

    candidates = (
        ProductImage.objects.filter(
            product__status="ACTIVE",
            upload__phash__gt="",
        )
        .exclude(product=product)
        .select_related("product", "upload")
        .order_by("-id")[:500]
    )
    for candidate in candidates:
        candidate_hash = candidate.upload.phash if candidate.upload_id else ""
        if not candidate_hash:
            continue
        if any(_hamming_distance(mine, candidate_hash) <= 6 for mine in hashes):
            issues.append(
                TrustIssue(
                    code="duplicate_image",
                    message="A photo in this listing matches another live listing.",
                    severity=SEVERITY_REVIEW,
                    field="images",
                    details={
                        "listing_id": candidate.product_id,
                        "listing_name": candidate.product.name,
                    },
                )
            )
            return


def run_pre_publish_checks(product) -> CheckResult:
    """Run every Phase 17 gate for ``product``.

    Duplicate *titles* are handled by the existing seller-scoped detector
    (``apps.products.duplicates``); this adds the checks that detector cannot
    express: prohibited content, contact leakage, blocklists, price outliers,
    copied descriptions and copied photos.
    """
    issues: list[TrustIssue] = []
    _scan_text(product, issues)
    _scan_contacts(product, issues)
    _scan_category(product, issues)
    _scan_price(product, issues)
    _scan_duplicate_text(product, issues)
    _scan_images(product, issues)
    return CheckResult(issues=issues)
