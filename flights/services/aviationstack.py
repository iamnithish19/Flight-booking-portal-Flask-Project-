"""Aviationstack adapter (https://aviationstack.com). Access key is sent as a query parameter
from the server only. The free plan is HTTP-only and ~100 calls/month, and date filtering
(`flight_date`) is not available on every plan, so results are also filtered by date locally."""
from __future__ import annotations

import requests

from .base import Flight, FlightAPIError, FlightAPINotConfigured, FlightProvider, iso


class AviationstackProvider(FlightProvider):
    name = "aviationstack"

    def __init__(self, api_key, base_url="", timeout=12):
        if not api_key:
            raise FlightAPINotConfigured("FLIGHT_API_KEY is not set.")
        self.key = api_key
        self.base = (base_url or "http://api.aviationstack.com/v1").rstrip("/")
        self.timeout = timeout

    def _get(self, params):
        try:
            r = requests.get(f"{self.base}/flights", params={"access_key": self.key, "limit": 100, **params},
                             timeout=self.timeout)
            data = r.json()
        except (requests.RequestException, ValueError) as exc:
            raise FlightAPIError(f"Aviationstack unreachable or invalid: {exc}") from exc
        if "error" in data:
            raise FlightAPIError(f"Aviationstack error: {data['error'].get('code', 'unknown')}")
        return data.get("data") or []

    def _normalise(self, row):
        dep, arr = row.get("departure") or {}, row.get("arrival") or {}
        airline, fl, ac = row.get("airline") or {}, row.get("flight") or {}, row.get("aircraft") or {}
        return Flight(
            provider=self.name,
            flight_number=(fl.get("iata") or "").replace(" ", ""),
            airline_name=airline.get("name") or "",
            airline_iata=airline.get("iata") or "",
            dep_iata=(dep.get("iata") or "").upper(), dep_airport=dep.get("airport") or "",
            arr_iata=(arr.get("iata") or "").upper(), arr_airport=arr.get("airport") or "",
            dep_date=row.get("flight_date") or "",
            scheduled_departure=iso(dep.get("scheduled")), estimated_departure=iso(dep.get("estimated")),
            actual_departure=iso(dep.get("actual")),
            scheduled_arrival=iso(arr.get("scheduled")), estimated_arrival=iso(arr.get("estimated")),
            actual_arrival=iso(arr.get("actual")),
            status=row.get("flight_status") or "",
            dep_terminal=dep.get("terminal") or "", dep_gate=dep.get("gate") or "",
            arr_terminal=arr.get("terminal") or "", arr_gate=arr.get("gate") or "",
            aircraft=ac.get("iata") or ac.get("icao") or "",
        ).to_dict()

    def search(self, source, destination, date):
        rows = self._get({"dep_iata": source, "arr_iata": destination})
        return [f for f in map(self._normalise, rows) if f["dep_date"] == date.isoformat()]

    def details(self, flight_number, date):
        rows = self._get({"flight_iata": flight_number.replace(" ", "")})
        return [f for f in map(self._normalise, rows) if f["dep_date"] == date.isoformat()]
