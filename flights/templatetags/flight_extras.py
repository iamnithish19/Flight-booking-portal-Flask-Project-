import re
from datetime import datetime

from django import template

register = template.Library()


def _parse(value):
    try:
        return datetime.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


@register.filter
def isotime(value):
    """Wall-clock time at the airport (the API's own offset is kept, not converted)."""
    dt = _parse(value)
    return dt.strftime("%H:%M") if dt else "—"


@register.filter
def isodate(value):
    dt = _parse(value) or _parse(f"{value}T00:00" if value and len(str(value)) == 10 else value)
    return dt.strftime("%d %b %Y") if dt else "—"


@register.filter
def status_label(raw):
    """Prettify the provider's own status string ('EnRoute' -> 'En route'); never substitutes one."""
    if not raw:
        return "Status unavailable"
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(raw)).replace("_", " ")
    return text[:1].upper() + text[1:].lower()


@register.filter
def status_class(raw):
    return "status-" + re.sub(r"[^a-z]", "", str(raw or "unknown").lower())


@register.simple_tag
def delay_minutes(flight, leg="dep"):
    """Minutes between scheduled and estimated/actual times, computed from API timestamps."""
    sched = _parse(flight.get(f"scheduled_{'departure' if leg == 'dep' else 'arrival'}"))
    new = _parse(flight.get(f"actual_{'departure' if leg == 'dep' else 'arrival'}")
                 or flight.get(f"estimated_{'departure' if leg == 'dep' else 'arrival'}"))
    if not sched or not new:
        return ""
    if sched.tzinfo is not None and new.tzinfo is None:
        new = new.replace(tzinfo=sched.tzinfo)
    elif sched.tzinfo is None and new.tzinfo is not None:
        sched = sched.replace(tzinfo=new.tzinfo)
    m = round((new - sched).total_seconds() / 60)
    return f"{m:+d} min" if m else "on time"


@register.filter
def localclock(value):
    """Server-local HH:MM:SS for an ISO timestamp (used for 'Last updated')."""
    from django.utils import timezone
    dt = _parse(value)
    return timezone.localtime(dt).strftime("%H:%M:%S") if dt else "—"


@register.filter
def inr_format(value):
    """Format an integer as Indian comma-separated currency."""
    if not value:
        return "4,999"
    try:
        val = int(value)
        s = str(val)
        if len(s) <= 3:
            return s
        last3 = s[-3:]
        remaining = s[:-3]
        groups = []
        while remaining:
            groups.append(remaining[-2:])
            remaining = remaining[:-2]
        groups.reverse()
        return ",".join(groups) + "," + last3
    except (ValueError, TypeError):
        return str(value)

