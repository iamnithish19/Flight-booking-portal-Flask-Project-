"""AeroDataBox adapter (https://aerodatabox.com, via RapidAPI or API.Market).

Endpoints used:
  GET /flights/airports/iata/{code}/{fromLocal}/{toLocal}   (FIDS departures, <=12h window)
  GET /flights/number/{flightNumber}/{date}                 (single flight, both legs)
Departure-board items describe the queried airport's leg; arrival times come from `details()`.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta

import requests

from .airports import airport_name
from .base import Flight, FlightAPIError, FlightAPINotConfigured, FlightProvider, iso

BASES = {
    "rapidapi": "https://aerodatabox.p.rapidapi.com",
    "apimarket": "https://prod.api.market/api/v1/aedbx/aerodatabox",
}


class AeroDataBoxProvider(FlightProvider):
    name = "aerodatabox"

    def __init__(self, api_key, auth_style="rapidapi", base_url="", timeout=12):
        if not api_key:
            raise FlightAPINotConfigured("FLIGHT_API_KEY is not set.")
        if auth_style not in BASES:
            raise FlightAPINotConfigured(f"Unknown FLIGHT_API_AUTH_STYLE '{auth_style}'.")
        self.base = (base_url or BASES[auth_style]).rstrip("/")
        self.timeout = timeout
        if auth_style == "rapidapi":
            host = self.base.split("//", 1)[-1].split("/", 1)[0]
            self.headers = {"X-RapidAPI-Key": api_key, "X-RapidAPI-Host": host}
        else:
            self.headers = {"x-api-market-key": api_key}

    # -- HTTP -----------------------------------------------------------------
    def _get(self, path, params=None):
        try:
            r = requests.get(f"{self.base}{path}", headers=self.headers, params=params, timeout=self.timeout)
        except requests.RequestException as exc:
            raise FlightAPIError(f"AeroDataBox unreachable: {exc}") from exc
        if r.status_code in (204, 404):
            return None
        if r.status_code in (401, 403):
            raise FlightAPIError("AeroDataBox rejected the API key or plan.")
        if r.status_code == 429:
            raise FlightAPIError("AeroDataBox rate/quota limit reached.")
        if not r.ok:
            raise FlightAPIError(f"AeroDataBox returned HTTP {r.status_code}.")
        try:
            return r.json()
        except ValueError as exc:
            raise FlightAPIError("AeroDataBox returned invalid JSON.") from exc

    # -- Normalisation ----------------------------------------------------------
    @staticmethod
    def _t(obj, key):
        node = (obj or {}).get(key) or {}
        return iso(node.get("local")) if isinstance(node, dict) else None

    def _normalise(self, item, origin_iata=None) -> dict:
        if "departure" in item or "arrival" in item:  # full-flight shape
            dep, arr = item.get("departure") or {}, item.get("arrival") or {}
        else:  # departure-board shape: movement = queried airport, movement.airport = the other end
            mv = item.get("movement") or {}
            dep = {**mv, "airport": {"iata": origin_iata, "name": airport_name(origin_iata or "")}}
            arr = {"airport": mv.get("airport") or {}}
        dap, aap = dep.get("airport") or {}, arr.get("airport") or {}
        number = (item.get("number") or "").replace(" ", "")
        airline = item.get("airline") or {}
        sched_dep = self._t(dep, "scheduledTime")
        return Flight(
            provider=self.name,
            flight_number=number,
            airline_name=airline.get("name", ""),
            airline_iata=airline.get("iata", ""),
            dep_iata=(dap.get("iata") or "").upper(),
            dep_airport=dap.get("name", ""),
            arr_iata=(aap.get("iata") or "").upper(),
            arr_airport=aap.get("name", ""),
            dep_date=sched_dep[:10] if sched_dep else "",
            scheduled_departure=sched_dep,
            estimated_departure=self._t(dep, "revisedTime"),
            actual_departure=self._t(dep, "runwayTime"),
            scheduled_arrival=self._t(arr, "scheduledTime"),
            estimated_arrival=self._t(arr, "revisedTime"),
            actual_arrival=self._t(arr, "runwayTime"),
            status=item.get("status", ""),
            dep_terminal=str(dep.get("terminal") or ""),
            dep_gate=str(dep.get("gate") or ""),
            arr_terminal=str(arr.get("terminal") or ""),
            arr_gate=str(arr.get("gate") or ""),
            aircraft=(item.get("aircraft") or {}).get("model", ""),
        ).to_dict()

    # -- Public API -------------------------------------------------------------
    def search(self, source, destination, date):
        flights, seen = [], set()
        for start, end in ((time(0, 0), time(11, 59)), (time(12, 0), time(23, 59))):
            frm = datetime.combine(date, start).strftime("%Y-%m-%dT%H:%M")
            to = datetime.combine(date, end).strftime("%Y-%m-%dT%H:%M")
            data = self._get(
                f"/flights/airports/iata/{source}/{frm}/{to}",
                {"direction": "Departure", "withCancelled": "true", "withCodeshared": "false",
                 "withCargo": "false", "withPrivate": "false", "withLocation": "false"},
            )
            for item in (data or {}).get("departures", []):
                f = self._normalise(item, origin_iata=source)
                key = (f["flight_number"], f["scheduled_departure"])
                if f["arr_iata"] == destination and key not in seen:
                    seen.add(key)
                    flights.append(f)
        return flights

    def details(self, flight_number, date):
        data = self._get(f"/flights/number/{flight_number.replace(' ', '')}/{date.isoformat()}")
        if isinstance(data, dict):
            data = data.get("flights") or data.get("items") or []
        return [self._normalise(item) for item in (data or [])]
