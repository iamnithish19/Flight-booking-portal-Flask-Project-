"""Aircraft Cabin Seat Map Service
Provides cabin layouts, real database occupancy tracking, and deterministic baseline occupancy.
Modeled after Boeing 777 / Airbus A350 widebody layout matching airline cabin configurations.
"""
import hashlib
from typing import Any, Dict, List, Set


# Cabin Layout Definitions matching aircraft seat map:
# First Class: Rows 1-2, 1-2-1 layout (A | DG | K)
# Business Class: Rows 5-16, 1-2-1 layout (A | DG | K)
# Premium Economy: Rows 25-27, 2-4-2 layout (AC | DEFG | HK)
# Economy Class: Rows 30-42, 3-4-3 layout (ABC | DEFG | HJK)

CABIN_SECTIONS = [
    {
        "cabin": "first",
        "title": "First Class Suites",
        "subtitle": "Ultra-private suites with lie-flat beds",
        "rows": [1, 2],
        "columns": [
            {"col": "A", "type": "window", "group": "left"},
            {"col": "D", "type": "aisle", "group": "center"},
            {"col": "G", "type": "aisle", "group": "center"},
            {"col": "K", "type": "window", "group": "right"},
        ],
        "aisles_after": ["A", "G"],
    },
    {
        "cabin": "business",
        "title": "Business Class",
        "subtitle": "Direct aisle access & lie-flat seating",
        "rows": [5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 16],
        "columns": [
            {"col": "A", "type": "window", "group": "left"},
            {"col": "D", "type": "aisle", "group": "center"},
            {"col": "G", "type": "aisle", "group": "center"},
            {"col": "K", "type": "window", "group": "right"},
        ],
        "aisles_after": ["A", "G"],
    },
    {
        "cabin": "premium_economy",
        "title": "Premium Economy",
        "subtitle": "Extra 7\" legroom & priority boarding",
        "rows": [25, 26, 27],
        "columns": [
            {"col": "A", "type": "window", "group": "left"},
            {"col": "C", "type": "aisle", "group": "left"},
            {"col": "D", "type": "aisle", "group": "center"},
            {"col": "E", "type": "middle", "group": "center"},
            {"col": "F", "type": "middle", "group": "center"},
            {"col": "G", "type": "aisle", "group": "center"},
            {"col": "H", "type": "aisle", "group": "right"},
            {"col": "K", "type": "window", "group": "right"},
        ],
        "aisles_after": ["C", "G"],
    },
    {
        "cabin": "economy",
        "title": "Economy Class",
        "subtitle": "Ergonomic seating with personal IFE",
        "rows": [30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42],
        "columns": [
            {"col": "A", "type": "window", "group": "left"},
            {"col": "B", "type": "middle", "group": "left"},
            {"col": "C", "type": "aisle", "group": "left"},
            {"col": "D", "type": "aisle", "group": "center"},
            {"col": "E", "type": "middle", "group": "center"},
            {"col": "F", "type": "middle", "group": "center"},
            {"col": "G", "type": "aisle", "group": "center"},
            {"col": "H", "type": "aisle", "group": "right"},
            {"col": "J", "type": "middle", "group": "right"},
            {"col": "K", "type": "window", "group": "right"},
        ],
        "aisles_after": ["C", "G"],
        "exit_rows": [30, 41],
    },
]


def _get_deterministic_booked_seats(flight_number: str, dep_date_str: str) -> Set[str]:
    """Generates a stable, realistic set of occupied seats (approx 35%) for a flight."""
    seed_str = f"{flight_number}-{dep_date_str}-seatmap"
    seed_hash = hashlib.sha256(seed_str.encode()).hexdigest()
    
    occupied = set()
    for section in CABIN_SECTIONS:
        for r in section["rows"]:
            for c in section["columns"]:
                code = f"{r}{c['col']}"
                # Generate a deterministic pseudo-random score for this seat
                seat_hash = hashlib.sha256(f"{seed_hash}-{code}".encode()).hexdigest()
                score = int(seat_hash[:4], 16) % 100
                # Roughly 32% of seats are pre-occupied by other travelers
                # Keep exit rows and front rows slightly more occupied
                threshold = 45 if r in section.get("exit_rows", []) or r in (1, 5, 25, 30) else 30
                if score < threshold:
                    occupied.add(code)
    return occupied


def get_real_booked_seats_from_db(flight_number: str, dep_date) -> Set[str]:
    """Fetches all seats already booked in the database for this specific flight and date."""
    from .mongo import is_mongo_available
    if is_mongo_available():
        try:
            from .mongo import get_mongo_db
            from datetime import datetime, date, time
            db = get_mongo_db()
            if isinstance(dep_date, date) and not isinstance(dep_date, datetime):
                date_dt = datetime.combine(dep_date, time.min)
            else:
                date_dt = dep_date

            bookings = list(db.flights_booking.find({
                "flight_number": {"$regex": f"^{flight_number}$", "$options": "i"},
                "dep_date": date_dt,
                "booking_status": "confirmed"
            }, {"_id": 1}))

            b_ids = [b["_id"] for b in bookings]
            if b_ids:
                passengers = db.flights_passenger.find({
                    "booking_id": {"$in": b_ids},
                    "seat_number": {"$exists": True, "$ne": ""}
                }, {"seat_number": 1})
                return set(p["seat_number"].strip().upper() for p in passengers if p.get("seat_number"))
            return set()
        except Exception:
            pass

    # Direct SQLite query fallback
    try:
        import sqlite3
        from pathlib import Path
        db_path = Path(__file__).resolve().parent.parent.parent / "db.sqlite3"
        date_str = dep_date.isoformat() if hasattr(dep_date, "isoformat") else str(dep_date)
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            """SELECT p.seat_number FROM flights_passenger p
               JOIN flights_booking b ON p.booking_id = b.id
               WHERE LOWER(b.flight_number) = LOWER(?)
                 AND b.dep_date LIKE ?
                 AND b.booking_status = 'confirmed'
                 AND p.seat_number != ''""",
            (flight_number.strip(), f"{date_str[:10]}%")
        ).fetchall()
        return set(r[0].strip().upper() for r in rows if r[0])
    except Exception:
        return set()


def get_flight_seat_map(flight_number: str, dep_date, travel_class: str = "economy") -> Dict[str, Any]:
    """Builds the complete cabin layout with actual booked/available statuses."""
    date_str = dep_date.isoformat() if hasattr(dep_date, "isoformat") else str(dep_date)
    
    # 1. Real booked seats in MongoDB for this flight date
    real_db_booked = get_real_booked_seats_from_db(flight_number, dep_date)
    
    # 2. Baseline virtual booked seats (realistic plane occupancy)
    baseline_booked = _get_deterministic_booked_seats(flight_number, date_str)
    
    all_booked = real_db_booked.union(baseline_booked)
    
    sections = []
    available_seats_for_class = []

    for sec in CABIN_SECTIONS:
        is_current_class = (sec["cabin"] == travel_class) or (
            travel_class == "business" and sec["cabin"] in ("first", "business")
        )
        
        cabin_rows = []
        for r in sec["rows"]:
            is_exit = r in sec.get("exit_rows", [])
            row_seats = []
            for c in sec["columns"]:
                code = f"{r}{c['col']}"
                is_booked = code in all_booked
                
                seat_info = {
                    "code": code,
                    "row": r,
                    "col": c["col"],
                    "cabin": sec["cabin"],
                    "type": c["type"],
                    "is_exit": is_exit,
                    "is_booked": is_booked,
                    "is_current_class": is_current_class,
                }
                row_seats.append(seat_info)
                
                if is_current_class and not is_booked:
                    available_seats_for_class.append(code)

            cabin_rows.append({
                "row_number": r,
                "is_exit": is_exit,
                "seats": row_seats,
            })
            
        sections.append({
            "cabin": sec["cabin"],
            "title": sec["title"],
            "subtitle": sec["subtitle"],
            "aisles_after": sec["aisles_after"],
            "columns": sec["columns"],
            "rows": cabin_rows,
            "is_current_class": is_current_class,
        })

    return {
        "flight_number": flight_number,
        "dep_date": date_str,
        "travel_class": travel_class,
        "sections": sections,
        "booked_seats": sorted(list(all_booked)),
        "available_seats": available_seats_for_class,
    }


def calculate_boarding_zone(seat_code: str) -> str:
    """Calculates passenger boarding zone from seat row number."""
    if not seat_code:
        return "Zone 3"
    try:
        row_str = "".join(filter(str.isdigit, seat_code))
        row = int(row_str)
        if row <= 20:
            return "Zone 1"
        elif row <= 34:
            return "Zone 2"
        else:
            return "Zone 3"
    except Exception:
        return "Zone 3"
