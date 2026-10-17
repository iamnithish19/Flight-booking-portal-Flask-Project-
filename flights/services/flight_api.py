"""Single entry point used by the views. Swap providers via FLIGHT_API_PROVIDER, or add a new
FlightProvider subclass and register it in PROVIDERS - views/templates never change."""
from __future__ import annotations

import os
import hashlib
from datetime import date as date_cls, datetime, timezone

from .aerodatabox import AeroDataBoxProvider
from .aviationstack import AviationstackProvider
from .base import FlightAPIError, FlightAPINotConfigured, FlightProvider
from .ixigo import IxigoProvider

__all__ = ["search_live_flights", "get_flight_details", "FlightAPIError", "FlightAPINotConfigured"]

_MEM_CACHE: dict = {}


def _get_setting(name: str, default: str = "") -> str:
    try:
        from django.conf import settings
        return str(getattr(settings, name, os.environ.get(name, default)))
    except Exception:
        return os.environ.get(name, default)


def _build_provider() -> FlightProvider:
    name = _get_setting("FLIGHT_API_PROVIDER", "ixigo").lower()
    if name == "ixigo":
        return IxigoProvider()
    if name == "aerodatabox":
        return AeroDataBoxProvider(
            _get_setting("FLIGHT_API_KEY", ""),
            _get_setting("FLIGHT_API_AUTH_STYLE", "rapidapi"),
            _get_setting("FLIGHT_API_BASE_URL", ""),
            float(_get_setting("FLIGHT_API_TIMEOUT", "12")),
        )
    if name == "aviationstack":
        return AviationstackProvider(
            _get_setting("FLIGHT_API_KEY", ""),
            _get_setting("FLIGHT_API_BASE_URL", ""),
            float(_get_setting("FLIGHT_API_TIMEOUT", "12")),
        )
    raise FlightAPINotConfigured(f"Unknown FLIGHT_API_PROVIDER '{name}'.")


def _cached(key_parts, fetch, force=False):
    """Cache a *real* API response briefly. `fetched_at` is when the API was actually called."""
    now_dt = datetime.now(timezone.utc)
    key = "flightapi:" + hashlib.sha1("|".join(map(str, key_parts)).encode()).hexdigest()
    try:
        cache_seconds = int(_get_setting("FLIGHT_API_CACHE_SECONDS", "30"))
    except (ValueError, TypeError):
        cache_seconds = 30

    if not force:
        try:
            from django.core.cache import cache
            if hit := cache.get(key):
                return hit
        except Exception:
            if key in _MEM_CACHE:
                val, exp = _MEM_CACHE[key]
                if now_dt.timestamp() < exp:
                    return val

    result = {"flights": fetch(), "fetched_at": now_dt.isoformat()}
    if cache_seconds > 0:
        try:
            from django.core.cache import cache
            cache.set(key, result, cache_seconds)
        except Exception:
            _MEM_CACHE[key] = (result, now_dt.timestamp() + cache_seconds)
    return result


def _sort_key(f):
    return f.get("scheduled_departure") or "9999"


def search_live_flights(
    source: str,
    destination: str,
    date: date_cls,
    travel_class: str = "economy",
    fare_type: str = "regular",
    force: bool = False
) -> dict:
    """Return {'flights': [normalised flight dicts], 'fetched_at': iso}. Raises FlightAPIError on failure."""
    provider = _build_provider()
    import inspect
    search_kwargs = {}
    sig = inspect.signature(provider.search).parameters
    if "travel_class" in sig:
        search_kwargs["travel_class"] = travel_class
    if "fare_type" in sig:
        search_kwargs["fare_type"] = fare_type

    result = _cached((provider.name, "search", source, destination, date, travel_class, fare_type),
                     lambda: sorted(provider.search(source, destination, date, **search_kwargs), key=_sort_key), force)
    return result


def get_flight_details(
    flight_number: str,
    date: date_cls,
    source: str | None = None,
    destination: str | None = None,
    travel_class: str = "economy",
    fare_type: str = "regular",
    force: bool = False
):
    """Return the matching normalised flight dict (with arrival data if the API has it) or None."""
    provider = _build_provider()
    import inspect
    sig = inspect.signature(provider.details).parameters
    details_kwargs = {}
    if "travel_class" in sig:
        details_kwargs["travel_class"] = travel_class
    if "fare_type" in sig:
        details_kwargs["fare_type"] = fare_type
    if "source" in sig:
        details_kwargs["source"] = source
    if "destination" in sig:
        details_kwargs["destination"] = destination

    result = _cached((provider.name, "details", flight_number, date, source, destination, travel_class, fare_type),
                     lambda: provider.details(flight_number, date, **details_kwargs), force)
    flights = result["flights"]
    if source:
        matches = [f for f in flights if f.get("dep_iata") == source]
        if matches:
            flights = matches
    if destination:
        matches = [f for f in flights if f.get("arr_iata") == destination]
        if matches:
            flights = matches
    return (flights[0] | {"fetched_at": result["fetched_at"]}) if flights else None
