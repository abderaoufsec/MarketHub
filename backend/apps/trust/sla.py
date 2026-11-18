"""Report SLA arithmetic (Phase 17).

The queue is ordered by the deadline, not by arrival: a scam report with a
victim about to pay is not the same as a wrong-category report. The hours are
settings so support can tune them without a deploy.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.messaging.models import ReportReason

HIGH_RISK = {
    ReportReason.SCAM,
    ReportReason.COUNTERFEIT,
    ReportReason.IMPERSONATION,
    ReportReason.PROHIBITED_ITEM,
}
MEDIUM_RISK = {
    ReportReason.HARASSMENT,
    ReportReason.OFF_PLATFORM,
}


def sla_hours_for(reason: str) -> int:
    if reason in HIGH_RISK:
        return settings.TRUST_REPORT_SLA_HIGH_RISK_HOURS
    if reason in MEDIUM_RISK:
        return settings.TRUST_REPORT_SLA_MEDIUM_RISK_HOURS
    return settings.TRUST_REPORT_SLA_DEFAULT_HOURS


def sla_due_at(reason: str):
    return timezone.now() + timedelta(hours=sla_hours_for(reason))
