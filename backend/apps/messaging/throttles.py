"""Phase 16 throttles: one rate per abuse-sensitive chat action."""

from apps.users.throttles import ClassScopedRateThrottle


class ConversationCreateRateThrottle(ClassScopedRateThrottle):
    scope = "conversation_create"


class MessageRateThrottle(ClassScopedRateThrottle):
    scope = "message"


class OfferRateThrottle(ClassScopedRateThrottle):
    scope = "offer"


class ReportRateThrottle(ClassScopedRateThrottle):
    scope = "report"
