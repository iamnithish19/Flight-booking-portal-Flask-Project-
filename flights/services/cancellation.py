"""DGCA 2026 Ticket Cancellation & Refund Compliance Engine.

Implements the Directorate General of Civil Aviation (DGCA) Passenger Charter amendment
effective from March 26, 2026:
- 48-hour free look-in cancellation/amendment window from the time of booking.
- Zero cancellation fees / 100% full refund if:
  * Domestic flight with departure at least 7 days (168 hours) away from booking time.
  * International flight with departure at least 15 days (360 hours) away from booking time.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta, date
from typing import Any, Dict, Optional, Tuple

from .airports import is_international_route, get_airport_country_name


DGCA_RULE_EFFECTIVE_DATE = "2026-03-26"
DGCA_LOOKIN_HOURS = 48
DOMESTIC_MIN_DAYS_AHEAD = 7
INTERNATIONAL_MIN_DAYS_AHEAD = 15


def is_domestic_flight(dep_iata: str, arr_iata: str) -> bool:
    """Returns True if both origin and destination airports are within India."""
    return not is_international_route(dep_iata, arr_iata)


def _parse_datetime(val: Any) -> Optional[datetime]:
    if not val:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    if isinstance(val, date):
        return datetime(val.year, val.month, val.day, tzinfo=timezone.utc)
    if isinstance(val, str):
        val = val.strip()
        try:
            dt = datetime.fromisoformat(val)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(val, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue
    return None


def evaluate_cancellation_policy(
    booking: Any,
    now_dt: Optional[datetime] = None,
    is_member: bool = True
) -> dict:
    """Evaluates DGCA 2026 compliance and refund terms for a booking.

    Returns a comprehensive policy report dictionary.
    """
    if now_dt is None:
        now_dt = datetime.now(timezone.utc)
    elif now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)

    # Booking creation time
    created_raw = getattr(booking, "created_at", None)
    if not created_raw and isinstance(booking, dict):
        created_raw = booking.get("created_at")
    created_dt = _parse_datetime(created_raw) or (now_dt - timedelta(minutes=5))

    # Flight departure time
    dep_raw = getattr(booking, "scheduled_departure", None) or getattr(booking, "dep_date", None)
    if not dep_raw and isinstance(booking, dict):
        dep_raw = booking.get("scheduled_departure") or booking.get("dep_date")
    dep_dt = _parse_datetime(dep_raw) or (now_dt + timedelta(days=8))

    dep_iata = getattr(booking, "dep_iata", "") or (booking.get("dep_iata") if isinstance(booking, dict) else "") or "DEL"
    arr_iata = getattr(booking, "arr_iata", "") or (booking.get("arr_iata") if isinstance(booking, dict) else "") or "BOM"

    is_domestic = is_domestic_flight(dep_iata, arr_iata)
    required_lead_days = DOMESTIC_MIN_DAYS_AHEAD if is_domestic else INTERNATIONAL_MIN_DAYS_AHEAD

    # Lead time at booking (departure time - booking creation time)
    lead_time_seconds = max(0.0, (dep_dt - created_dt).total_seconds())
    lead_time_days = round(lead_time_seconds / 86400.0, 1)
    meets_lead_time = lead_time_days >= required_lead_days

    # Elapsed time since booking (now - booking creation time)
    elapsed_seconds = max(0.0, (now_dt - created_dt).total_seconds())
    elapsed_hours = round(elapsed_seconds / 3600.0, 1)
    is_within_48h = elapsed_hours <= DGCA_LOOKIN_HOURS
    hours_remaining_48h = max(0.0, round(DGCA_LOOKIN_HOURS - elapsed_hours, 1))

    # DGCA 2026 rule qualification
    dgca_eligible = is_within_48h and meets_lead_time

    # Time until departure from current clock
    secs_to_dep = (dep_dt - now_dt).total_seconds()
    hours_to_dep = round(secs_to_dep / 3600.0, 1)
    has_departed = secs_to_dep <= 0

    # Refund calculation
    if has_departed:
        cancellation_allowed = False
        refund_percent = 0.0
        reason = "Flight has already departed."
    elif dgca_eligible:
        cancellation_allowed = True
        refund_percent = 100.0
        reason = (
            f"Eligible under DGCA 2026 Mandate: Cancelled within 48-hour look-in period "
            f"({hours_remaining_48h}h remaining) for a {'domestic' if is_domestic else 'international'} "
            f"flight booked {lead_time_days} days before departure (minimum {required_lead_days} days required)."
        )
    elif is_member:
        # Regular Member benefit guarantees 100% refund up to 2 hours before departure
        if hours_to_dep >= 2.0:
            cancellation_allowed = True
            refund_percent = 100.0
            reason = "100% full refund guaranteed under Airvoyage Regular Member zero-fee protection."
        else:
            cancellation_allowed = False
            refund_percent = 0.0
            reason = "Cancellations must be requested at least 2 hours prior to scheduled departure."
    else:
        # Standard non-member policy outside DGCA look-in
        if hours_to_dep >= 24.0:
            cancellation_allowed = True
            refund_percent = 75.0
            reason = "Standard airline fare rules: 75% refund with standard cancellation processing fee."
        elif hours_to_dep >= 2.0:
            cancellation_allowed = True
            refund_percent = 50.0
            reason = "Standard airline fare rules: 50% refund for cancellation within 24 hours of departure."
        else:
            cancellation_allowed = False
            refund_percent = 0.0
            reason = "Non-refundable within 2 hours of departure."

    return {
        "dgca_rule_name": "DGCA 2026 Passenger Charter (Effective March 26, 2026)",
        "effective_date": DGCA_RULE_EFFECTIVE_DATE,
        "is_domestic": is_domestic,
        "flight_category": "Domestic" if is_domestic else "International",
        "required_lead_days": required_lead_days,
        "actual_lead_days": lead_time_days,
        "meets_lead_time": meets_lead_time,
        "elapsed_hours": elapsed_hours,
        "lookin_limit_hours": DGCA_LOOKIN_HOURS,
        "is_within_48h": is_within_48h,
        "hours_remaining_48h": hours_remaining_48h,
        "dgca_eligible": dgca_eligible,
        "has_departed": has_departed,
        "hours_to_dep": hours_to_dep,
        "cancellation_allowed": cancellation_allowed,
        "refund_percent": refund_percent,
        "fee_waived": (refund_percent == 100.0),
        "reason": reason,
        "summary_badge": "DGCA 2026 Free Cancel Active" if dgca_eligible else ("Member 100% Refund" if (is_member and cancellation_allowed) else "Standard Refund"),
    }
