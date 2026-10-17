"""Provider-neutral flight model + errors. Every provider adapter returns `Flight` dicts."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Optional


class FlightAPIError(Exception):
    """Live API unreachable, rejected the request, or returned something unusable."""


class FlightAPINotConfigured(FlightAPIError):
    """No API key / unknown provider."""


@dataclass
class Flight:
    provider: str
    flight_number: str = ""
    airline_name: str = ""
    airline_iata: str = ""
    dep_iata: str = ""
    dep_airport: str = ""
    arr_iata: str = ""
    arr_airport: str = ""
    dep_date: str = ""  # local calendar date at the departure airport (YYYY-MM-DD)
    scheduled_departure: Optional[str] = None  # ISO-8601 with the airport's own UTC offset
    estimated_departure: Optional[str] = None
    actual_departure: Optional[str] = None
    scheduled_arrival: Optional[str] = None
    estimated_arrival: Optional[str] = None
    actual_arrival: Optional[str] = None
    status: str = ""  # exactly what the provider returned (never invented)
    dep_terminal: str = ""
    dep_gate: str = ""
    arr_terminal: str = ""
    arr_gate: str = ""
    aircraft: str = ""
    price: int = 0
    duration_minutes: int = 0
    duration_str: str = ""
    stops: str = "Non-stop"
    badge: str = ""
    baggage: str = "15 kg Check-in · 7 kg Cabin"
    meal: str = "Buy on Board"
    refundable: bool = True
    is_connecting: bool = False
    layover_airport: str = ""
    layover_minutes: int = 0
    stops_info: str = ""
    travel_class: str = "Economy"
    prices_by_class: Optional[dict] = None
    airline_scope: str = "both_domestic_intl"
    airline_scope_label: str = "Mainline Carrier"
    fare_type: str = "regular"
    concession_name: str = ""
    concession_badge: str = ""
    original_price: int = 0
    concession_savings: int = 0
    doc_required: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def iso(value) -> Optional[str]:
    """Normalise a provider timestamp string to ISO-8601 (keeps the original UTC offset)."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).strip().replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None


class FlightProvider(ABC):
    """Implement these two methods to plug in another flight-data API."""

    name = "base"

    @abstractmethod
    def search(self, source: str, destination: str, date) -> list[dict]:
        """Return Flight dicts for flights source->destination on `date` (a datetime.date)."""

    @abstractmethod
    def details(self, flight_number: str, date) -> list[dict]:
        """Return Flight dicts (with arrival data where the API has it) for one flight number/date."""
