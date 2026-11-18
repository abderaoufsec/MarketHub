"""Safety-centre content (Phase 17), written for fr/en/ar.

Deliberately static Python rather than a CMS: the content must ship with the
release, be reviewable in code, and never depend on a database row that a
deploy can forget to seed. The API returns one language at a time (the same
``Accept-Language`` the rest of the site uses).
"""

from __future__ import annotations

from django.utils import timezone
from django.utils.translation import get_language

CONTENT = {
    "fr": {
        "title": "Centre de sécurité",
        "intro": "Quelques réflexes simples suffisent à éviter la grande majorité des arnaques.",
        "sections": [
            {
                "id": "advance-payment",
                "title": "Ne payez jamais à l'avance",
                "body": "Un vendeur sérieux ne vous demandera pas de payer avant d'avoir vu l'article.",
                "bullets": [
                    "Refusez les virements, mandats et coupons avant la remise en main propre.",
                    "Méfiez-vous des demandes de paiement par Western Union, MoneyGram ou crypto.",
                    "Pour une livraison, privilégiez le paiement à la réception (COD).",
                ],
            },
            {
                "id": "safe-meetup",
                "title": "Rencontrez-vous dans un lieu sûr",
                "body": "Choisissez un endroit public, fréquenté et bien éclairé, de jour si possible.",
                "bullets": [
                    "Prévenez un proche du lieu et de l'heure du rendez-vous.",
                    "Ne montez jamais dans un véhicule inconnu et ne vous isolez pas.",
                    "Vérifiez l'article sur place avant de payer.",
                ],
            },
            {
                "id": "check-item",
                "title": "Vérifiez l'article et le vendeur",
                "body": "Les badges indiquent ce que MarketHub a pu vérifier, pas une garantie absolue.",
                "bullets": [
                    "Préférez les profils avec téléphone vérifié ou identité vérifiée.",
                    "Demandez des photos récentes et une facture si l'article est sous garantie.",
                    "Un prix anormalement bas doit vous alerter.",
                ],
            },
            {
                "id": "off-platform",
                "title": "Gardez la conversation sur MarketHub",
                "body": "Les messages et offres conservés sur la plateforme nous permettent d'intervenir en cas de litige.",
                "bullets": [
                    "N'envoyez pas d'argent à un contact rencontré hors de la plateforme.",
                    "Signalez tout message qui vous pousse à quitter MarketHub.",
                    "Ne partagez jamais de code de vérification ou de mot de passe.",
                ],
            },
            {
                "id": "report",
                "title": "Signalez les comportements suspects",
                "body": "Un signalement est examiné par un modérateur ; les cas urgents ont une échéance plus courte.",
                "bullets": [
                    "Signalez l'annonce, le profil ou le message concerné.",
                    "Bloquez immédiatement un contact menaçant ou insistant.",
                    "Conservez les preuves (messages, photos, reçus).",
                ],
            },
            {
                "id": "payment-methods",
                "title": "Choisissez un paiement traçable",
                "body": "Un paiement remis contre l'article reste la méthode la plus sûre pour les petites annonces.",
                "bullets": [
                    "Évitez les espèces envoyées par transporteur ou par un tiers.",
                    "Pour les montants élevés, demandez un reçu et notez l'identité du vendeur.",
                    "En cas de doute, interrompez la transaction.",
                ],
            },
        ],
    },
    "en": {
        "title": "Safety centre",
        "intro": "A few simple habits prevent the vast majority of scams.",
        "sections": [
            {
                "id": "advance-payment",
                "title": "Never pay in advance",
                "body": "A genuine seller will not ask for money before you have seen the item.",
                "bullets": [
                    "Refuse transfers, money orders and vouchers before a hand-over.",
                    "Be wary of Western Union, MoneyGram or crypto-only payment requests.",
                    "For delivery, prefer cash on delivery (COD).",
                ],
            },
            {
                "id": "safe-meetup",
                "title": "Meet in a safe place",
                "body": "Choose a public, busy, well-lit place, in daylight when possible.",
                "bullets": [
                    "Tell someone where you are going and when.",
                    "Never get into a stranger's vehicle or go somewhere isolated.",
                    "Inspect the item on the spot before paying.",
                ],
            },
            {
                "id": "check-item",
                "title": "Check the item and the seller",
                "body": "Badges show what MarketHub could verify; they are not an absolute guarantee.",
                "bullets": [
                    "Prefer profiles with a verified phone or verified ID.",
                    "Ask for recent photos and the receipt if the item is under warranty.",
                    "An unusually low price is a warning sign.",
                ],
            },
            {
                "id": "off-platform",
                "title": "Keep the conversation on MarketHub",
                "body": "Messages and offers kept on the platform let us act if something goes wrong.",
                "bullets": [
                    "Do not send money to a contact you met off-platform.",
                    "Report any message that pushes you away from MarketHub.",
                    "Never share a verification code or password.",
                ],
            },
            {
                "id": "report",
                "title": "Report suspicious behaviour",
                "body": "A moderator reviews every report; urgent cases have a shorter deadline.",
                "bullets": [
                    "Report the listing, profile or message involved.",
                    "Block a threatening or persistent contact immediately.",
                    "Keep the evidence (messages, photos, receipts).",
                ],
            },
            {
                "id": "payment-methods",
                "title": "Use a traceable payment",
                "body": "Paying against the item remains the safest method for classifieds.",
                "bullets": [
                    "Avoid cash sent through a carrier or a third party.",
                    "For large amounts, ask for a receipt and note the seller's identity.",
                    "If in doubt, stop the transaction.",
                ],
            },
        ],
    },
    "ar": {
        "title": "مركز الأمان",
        "intro": "بعض العادات البسيطة تكفي لتجنب غالبية عمليات النصب.",
        "sections": [
            {
                "id": "advance-payment",
                "title": "لا تدفع أبدا مقدما",
                "body": "البائع الجاد لا يطلب المال قبل أن ترى السلعة.",
                "bullets": [
                    "ارفض التحويلات والحوالات والقسائم قبل التسليم يدا بيد.",
                    "احذر طلبات الدفع عبر ويسترن يونيون أو موني غرام أو العملات الرقمية فقط.",
                    "عند التوصيل، فضل الدفع عند الاستلام.",
                ],
            },
            {
                "id": "safe-meetup",
                "title": "التق في مكان آمن",
                "body": "اختر مكانا عاما ومزدحما وجيد الإضاءة، ويفضل نهارا.",
                "bullets": [
                    "أخبر شخصا تثق به بمكان وموعد اللقاء.",
                    "لا تركب سيارة شخص غريب ولا تذهب إلى مكان معزول.",
                    "افحص السلعة في المكان قبل الدفع.",
                ],
            },
            {
                "id": "check-item",
                "title": "تحقق من السلعة والبائع",
                "body": "الشارات توضح ما تمكنت MarketHub من التحقق منه، وليست ضمانا مطلقا.",
                "bullets": [
                    "فضل الملفات التي تحمل هاتفا موثقا أو هوية موثقة.",
                    "اطلب صورا حديثة وفاتورة إذا كانت السلعة تحت الضمان.",
                    "السعر المنخفض بشكل غير طبيعي علامة تحذير.",
                ],
            },
            {
                "id": "off-platform",
                "title": "أبق المحادثة داخل MarketHub",
                "body": "الرسائل والعروض المحفوظة على المنصة تسمح لنا بالتدخل عند حدوث خلاف.",
                "bullets": [
                    "لا ترسل مالا إلى جهة تعرفت عليها خارج المنصة.",
                    "أبلغ عن أي رسالة تدفعك لمغادرة MarketHub.",
                    "لا تشارك رمز التحقق أو كلمة المرور مع أي شخص.",
                ],
            },
            {
                "id": "report",
                "title": "أبلغ عن السلوك المشبوه",
                "body": "يراجع المشرف كل إبلاغ، وللحالات العاجلة مهلة أقصر.",
                "bullets": [
                    "أبلغ عن الإعلان أو الملف أو الرسالة المعنية.",
                    "احظر فورا أي جهة تهددك أو تلح عليك.",
                    "احتفظ بالأدلة: الرسائل والصور والإيصالات.",
                ],
            },
            {
                "id": "payment-methods",
                "title": "اختر وسيلة دفع قابلة للتتبع",
                "body": "الدفع مقابل السلعة يبقى الطريقة الأكثر أمانا في الإعلانات المبوبة.",
                "bullets": [
                    "تجنب إرسال النقود عبر شركة نقل أو شخص وسيط.",
                    "للمبالغ الكبيرة، اطلب إيصالا ودون هوية البائع.",
                    "عند الشك، أوقف المعاملة.",
                ],
            },
        ],
    },
}


def language_code() -> str:
    """The active language, folded onto the three languages we author."""
    code = (get_language() or "fr").split("-")[0].lower()
    return code if code in CONTENT else "fr"


def safety_center_payload() -> dict:
    language = language_code()
    payload = CONTENT[language]
    return {
        "language": language,
        "updated_at": timezone.now().date().isoformat(),
        "title": payload["title"],
        "intro": payload["intro"],
        "sections": payload["sections"],
    }
