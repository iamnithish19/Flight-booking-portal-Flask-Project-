"""Dual-Backend Models & Data Layer for Airvoyage Flask application.
Supports MongoDB Atlas (when available) with seamless persistent SQLite fallback (db.sqlite3).
"""
import json
import os
import re
import secrets
import sqlite3
from datetime import datetime, timezone, date
from pathlib import Path
from bson import ObjectId
from flask_login import UserMixin
from flights.services.mongo import get_mongo_db, is_mongo_available

BASE_DIR = Path(__file__).resolve().parent.parent
SQLITE_DB_PATH = BASE_DIR / "db.sqlite3"


def _sqlite_conn():
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _safe_object_id(val):
    try:
        return ObjectId(val)
    except Exception:
        return val


def re_escape(s: str) -> str:
    return re.escape(s)


class User(UserMixin):
    def __init__(self, doc):
        self.doc = doc
        self.id = str(doc.get("_id", doc.get("id", "")))
        self.username = doc.get("username", "")
        self.email = doc.get("email", "")
        self.first_name = doc.get("first_name", "")
        self.last_name = doc.get("last_name", "")
        self._is_active = doc.get("is_active", True)
        self.is_superuser = doc.get("is_superuser", False)
        self.is_staff = doc.get("is_staff", False)
        self.date_joined = doc.get("date_joined")
        self.password_hash = doc.get("password", "")

    @property
    def is_active(self) -> bool:
        return self._is_active

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return False
        # 1. Django pbkdf2_sha256 verification
        try:
            from django.contrib.auth.hashers import check_password as dj_check
            return dj_check(password, self.password_hash)
        except Exception:
            pass
        # 2. Werkzeug hash verification
        from werkzeug.security import check_password_hash
        try:
            return check_password_hash(self.password_hash, password)
        except Exception:
            return False

    @property
    def profile(self):
        return get_or_create_user_profile(self)

    @property
    def bookings(self):
        return get_user_bookings(self)


class UserProfile:
    def __init__(self, doc, user=None):
        self.doc = doc
        self.id = str(doc.get("_id", doc.get("id", "")))
        self.user = user
        self.phone = doc.get("phone", "")
        self.date_of_birth = doc.get("date_of_birth")
        self.gender = doc.get("gender", "")
        self.nationality = doc.get("nationality", "India")
        self.passport_number = doc.get("passport_number", "")
        self.passport_expiry = doc.get("passport_expiry")
        self.frequent_flyer_number = doc.get("frequent_flyer_number", "")
        self.preferred_class = doc.get("preferred_class", "Economy")
        self.home_airport = doc.get("home_airport", "")
        self.address = doc.get("address", "")
        self.created_at = doc.get("created_at")
        self.updated_at = doc.get("updated_at")

    @property
    def full_name(self):
        if self.user:
            name = f"{self.user.first_name} {self.user.last_name}".strip()
            return name or self.user.username
        return "Traveler"

    @property
    def membership_tier(self):
        count = len(self.user.bookings) if self.user else 0
        if count >= 10:
            return {"name": "Platinum Voyager", "color": "#7c3aed", "bg": "#f5f3ff", "badge": "Platinum"}
        if count >= 5:
            return {"name": "Gold Club", "color": "#d97706", "bg": "#fffbeb", "badge": "Gold"}
        if count >= 2:
            return {"name": "Silver Flyer", "color": "#0284c7", "bg": "#f0f9ff", "badge": "Silver"}
        return {"name": "Standard Traveler", "color": "#4b5563", "bg": "#f3f4f6", "badge": "Standard"}


class Passenger:
    def __init__(self, doc):
        self.doc = doc
        self.id = str(doc.get("_id", doc.get("id", "")))
        self.first_name = doc.get("first_name", "")
        self.last_name = doc.get("last_name", "")
        self.date_of_birth = doc.get("date_of_birth")
        self.gender = doc.get("gender", "M")
        self.nationality = doc.get("nationality", "India")
        self.id_number = doc.get("id_number", "")
        self.passport_number = doc.get("passport_number", "")
        self.passport_expiry = doc.get("passport_expiry")
        self.seat_number = doc.get("seat_number", "")
        self.boarding_zone = doc.get("boarding_zone", "")
        self.sequence_number = doc.get("sequence_number", "")

    @property
    def formatted_name(self):
        last = (self.last_name or "").strip().upper() or "PASSENGER"
        first = (self.first_name or "").strip().upper() or "PRIMARY"
        title = "MR" if self.gender == "M" else ("MS" if self.gender == "F" else "")
        title_suffix = f"/{title}" if title else ""
        return f"{last}/{first}{title_suffix}"


class PassengerList(list):
    def all(self):
        return self


class Booking:
    def __init__(self, doc, passengers=None, user=None):
        self.doc = doc
        self.id = str(doc.get("_id", doc.get("id", "")))
        self.reference = doc.get("reference", "")
        self.booking_status = doc.get("booking_status", "confirmed")
        self.created_at = doc.get("created_at")
        self.contact_email = doc.get("contact_email", "")
        self.contact_phone = doc.get("contact_phone", "")
        self.passenger_count = doc.get("passenger_count", 1)
        ret_d = doc.get("return_date")
        if isinstance(ret_d, datetime):
            self.return_date = ret_d.date()
        elif isinstance(ret_d, str) and ret_d:
            try:
                self.return_date = date.fromisoformat(ret_d)
            except Exception:
                self.return_date = ret_d
        else:
            self.return_date = ret_d

        self.api_provider = doc.get("api_provider", "")
        self.airline_name = doc.get("airline_name", "")
        self.flight_number = doc.get("flight_number", "")
        self.dep_iata = doc.get("dep_iata", "")
        self.dep_airport = doc.get("dep_airport", "")
        self.arr_iata = doc.get("arr_iata", "")
        self.arr_airport = doc.get("arr_airport", "")

        dep_d = doc.get("dep_date")
        if isinstance(dep_d, datetime):
            self.dep_date = dep_d.date()
        elif isinstance(dep_d, str) and dep_d:
            try:
                self.dep_date = date.fromisoformat(dep_d)
            except Exception:
                self.dep_date = dep_d
        else:
            self.dep_date = dep_d
        self.scheduled_departure = doc.get("scheduled_departure")
        self.scheduled_arrival = doc.get("scheduled_arrival")
        self.dep_terminal = doc.get("dep_terminal", "")
        self.dep_gate = doc.get("dep_gate", "")
        self.aircraft = doc.get("aircraft", "")
        self.status_at_booking = doc.get("status_at_booking", "")
        self.snapshot = doc.get("snapshot", {})
        self.email_sent = doc.get("email_sent", False)
        self.travel_class = doc.get("travel_class", "economy")
        self.is_connecting = doc.get("is_connecting", False)
        self.stops_info = doc.get("stops_info", "Non-stop")
        if passengers is not None:
            self._passengers = passengers
        elif doc.get("passengers") and isinstance(doc.get("passengers"), list):
            # Load directly from MongoDB embedded documents (Zero secondary queries)
            self._passengers = [Passenger(p) for p in doc.get("passengers")]
        else:
            self._passengers = []
        self.user = user

    @property
    def passengers(self):
        return PassengerList(self._passengers)

    @property
    def has_embedded_passengers(self) -> bool:
        """True if this document utilizes the MongoDB Embedded Document pattern."""
        return bool(self.doc.get("passengers") and isinstance(self.doc.get("passengers"), list))

    def to_embedded_document(self) -> dict:
        """Returns the document formatted according to MongoDB Embedded Document design pattern."""
        dep_d = self.dep_date.isoformat() if hasattr(self.dep_date, "isoformat") else str(self.dep_date or "")
        ret_d = self.return_date.isoformat() if hasattr(self.return_date, "isoformat") else (str(self.return_date) if self.return_date else None)
        created_at_str = self.created_at.isoformat() if hasattr(self.created_at, "isoformat") else str(self.created_at or "")
        sched_dep_str = self.scheduled_departure.isoformat() if hasattr(self.scheduled_departure, "isoformat") else str(self.scheduled_departure or "")
        sched_arr_str = self.scheduled_arrival.isoformat() if hasattr(self.scheduled_arrival, "isoformat") else str(self.scheduled_arrival or "")

        embedded_passengers = []
        for p in self._passengers:
            p_dob = p.date_of_birth.isoformat() if hasattr(p.date_of_birth, "isoformat") else str(p.date_of_birth or "")
            p_exp = p.passport_expiry.isoformat() if hasattr(p.passport_expiry, "isoformat") else (str(p.passport_expiry) if p.passport_expiry else None)
            embedded_passengers.append({
                "_id": str(getattr(p, "id", "")),
                "first_name": p.first_name,
                "last_name": p.last_name,
                "formatted_name": p.formatted_name,
                "date_of_birth": p_dob,
                "gender": p.gender,
                "nationality": p.nationality,
                "id_number": p.id_number,
                "passport_number": p.passport_number,
                "passport_expiry": p_exp,
                "seat_number": p.seat_number,
                "boarding_zone": p.boarding_zone,
                "sequence_number": p.sequence_number,
            })

        return {
            "_id": str(self.id),
            "reference": self.reference,
            "booking_status": self.booking_status,
            "created_at": created_at_str,
            "contact": {
                "email": self.contact_email,
                "phone": self.contact_phone,
            },
            "flight_details": {
                "flight_number": self.flight_number,
                "airline_name": self.airline_name,
                "aircraft": self.aircraft,
                "travel_class": self.travel_class,
                "status_at_booking": self.status_at_booking,
                "api_provider": self.api_provider,
            },
            "route": {
                "origin": {
                    "iata": self.dep_iata,
                    "airport": self.dep_airport,
                    "terminal": self.dep_terminal,
                    "gate": self.dep_gate,
                    "date": dep_d,
                    "scheduled_time": sched_dep_str,
                },
                "destination": {
                    "iata": self.arr_iata,
                    "airport": self.arr_airport,
                    "scheduled_time": sched_arr_str,
                },
                "stops": self.stops_info,
                "is_connecting": self.is_connecting,
                "return_date": ret_d,
            },
            "passenger_count": self.passenger_count,
            "passengers": embedded_passengers,
            "pattern_type": "MongoDB Embedded Document (Denormalized Subdocuments)",
        }

    @property
    def get_booking_status_display(self):
        return "Confirmed" if self.booking_status == "confirmed" else "Cancelled"


def hash_password(password: str) -> str:
    try:
        from django.contrib.auth.hashers import make_password
        return make_password(password)
    except Exception:
        from werkzeug.security import generate_password_hash
        return generate_password_hash(password)


def get_user_by_id(user_id: str) -> User | None:
    if is_mongo_available():
        try:
            db = get_mongo_db()
            doc = db.auth_user.find_one({"_id": _safe_object_id(user_id)})
            if doc:
                return User(doc)
        except Exception:
            pass
    # SQLite fallback
    try:
        conn = _sqlite_conn()
        row = conn.execute("SELECT * FROM auth_user WHERE id = ?", (user_id,)).fetchone()
        if row:
            d = dict(row)
            d["_id"] = d["id"]
            return User(d)
    except Exception:
        pass
    return None


def get_user_by_username(username: str) -> User | None:
    if is_mongo_available():
        try:
            db = get_mongo_db()
            doc = db.auth_user.find_one({"username": {"$regex": f"^{re_escape(username)}$", "$options": "i"}})
            if doc:
                return User(doc)
        except Exception:
            pass
    # SQLite fallback
    try:
        conn = _sqlite_conn()
        row = conn.execute("SELECT * FROM auth_user WHERE LOWER(username) = LOWER(?)", (username.strip(),)).fetchone()
        if row:
            d = dict(row)
            d["_id"] = d["id"]
            return User(d)
    except Exception:
        pass
    return None


def get_user_by_email(email: str) -> User | None:
    if is_mongo_available():
        try:
            db = get_mongo_db()
            doc = db.auth_user.find_one({"email": {"$regex": f"^{re_escape(email)}$", "$options": "i"}})
            if doc:
                return User(doc)
        except Exception:
            pass
    # SQLite fallback
    try:
        conn = _sqlite_conn()
        row = conn.execute("SELECT * FROM auth_user WHERE LOWER(email) = LOWER(?)", (email.strip(),)).fetchone()
        if row:
            d = dict(row)
            d["_id"] = d["id"]
            return User(d)
    except Exception:
        pass
    return None


def create_user(username: str, email: str, password: str, first_name: str = "", last_name: str = "") -> User:
    if is_mongo_available():
        try:
            db = get_mongo_db()
            now = datetime.now(timezone.utc)
            hashed = hash_password(password)
            user_doc = {
                "username": username.strip(),
                "email": email.strip().lower(),
                "password": hashed,
                "first_name": first_name.strip(),
                "last_name": last_name.strip(),
                "is_active": True,
                "is_staff": False,
                "is_superuser": False,
                "date_joined": now,
                "last_login": None,
            }
            res = db.auth_user.insert_one(user_doc)
            user = User(db.auth_user.find_one({"_id": res.inserted_id}))
            get_or_create_user_profile(user)
            return user
        except Exception:
            pass
    # SQLite fallback
    conn = _sqlite_conn()
    now_str = datetime.now(timezone.utc).isoformat()
    hashed = hash_password(password)
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO auth_user (username, email, password, first_name, last_name, is_active, is_staff, is_superuser, date_joined)
           VALUES (?, ?, ?, ?, ?, 1, 0, 0, ?)""",
        (username.strip(), email.strip().lower(), hashed, first_name.strip(), last_name.strip(), now_str)
    )
    user_id = cur.lastrowid
    conn.commit()
    row = conn.execute("SELECT * FROM auth_user WHERE id = ?", (user_id,)).fetchone()
    d = dict(row)
    d["_id"] = d["id"]
    user = User(d)
    get_or_create_user_profile(user)
    return user


def get_or_create_user_profile(user: User) -> UserProfile:
    if is_mongo_available():
        try:
            db = get_mongo_db()
            u_id = _safe_object_id(user.id)
            doc = db.flights_userprofile.find_one({"user_id": u_id})
            if not doc:
                now = datetime.now(timezone.utc)
                doc = {
                    "user_id": u_id,
                    "phone": "",
                    "date_of_birth": None,
                    "gender": "",
                    "nationality": "India",
                    "passport_number": "",
                    "passport_expiry": None,
                    "frequent_flyer_number": "",
                    "preferred_class": "Economy",
                    "home_airport": "",
                    "address": "",
                    "created_at": now,
                    "updated_at": now,
                }
                res = db.flights_userprofile.insert_one(doc)
                doc = db.flights_userprofile.find_one({"_id": res.inserted_id})
            return UserProfile(doc, user=user)
        except Exception:
            pass
    # SQLite fallback
    conn = _sqlite_conn()
    row = conn.execute("SELECT * FROM flights_userprofile WHERE user_id = ?", (user.id,)).fetchone()
    if not row:
        now_str = datetime.now(timezone.utc).isoformat()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO flights_userprofile (
                user_id, phone, gender, nationality, passport_number,
                frequent_flyer_number, preferred_class, home_airport, address, created_at, updated_at
            ) VALUES (?, '', 'M', 'India', '', '', 'Economy', '', '', ?, ?)""",
            (user.id, now_str, now_str)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM flights_userprofile WHERE id = ?", (cur.lastrowid,)).fetchone()
    d = dict(row)
    d["_id"] = d["id"]
    return UserProfile(d, user=user)


def update_user_profile(user: User, data: dict):
    if is_mongo_available():
        try:
            db = get_mongo_db()
            now = datetime.now(timezone.utc)
            u_id = _safe_object_id(user.id)
            db.auth_user.update_one(
                {"_id": u_id},
                {"$set": {
                    "first_name": data.get("first_name", user.first_name),
                    "last_name": data.get("last_name", user.last_name),
                    "email": data.get("email", user.email),
                }}
            )
            dob = data.get("date_of_birth")
            if isinstance(dob, date) and not isinstance(dob, datetime):
                dob = datetime.combine(dob, datetime.min.time())
            exp = data.get("passport_expiry")
            if isinstance(exp, date) and not isinstance(exp, datetime):
                exp = datetime.combine(exp, datetime.min.time())

            db.flights_userprofile.update_one(
                {"user_id": u_id},
                {"$set": {
                    "phone": data.get("phone", ""),
                    "date_of_birth": dob,
                    "gender": data.get("gender", ""),
                    "nationality": data.get("nationality", "India"),
                    "passport_number": data.get("passport_number", ""),
                    "passport_expiry": exp,
                    "preferred_class": data.get("preferred_class", "Economy"),
                    "home_airport": data.get("home_airport", ""),
                    "frequent_flyer_number": data.get("frequent_flyer_number", ""),
                    "address": data.get("address", ""),
                    "updated_at": now,
                }},
                upsert=True
            )
            return
        except Exception:
            pass
    # SQLite fallback
    conn = _sqlite_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE auth_user SET first_name = ?, last_name = ?, email = ? WHERE id = ?",
        (data.get("first_name", user.first_name), data.get("last_name", user.last_name), data.get("email", user.email), user.id)
    )
    dob = data.get("date_of_birth")
    dob_str = dob.isoformat() if hasattr(dob, "isoformat") else str(dob or "")
    exp = data.get("passport_expiry")
    exp_str = exp.isoformat() if hasattr(exp, "isoformat") else str(exp or "")
    now_str = datetime.now(timezone.utc).isoformat()
    cur.execute(
        """UPDATE flights_userprofile SET phone = ?, date_of_birth = ?, gender = ?, nationality = ?,
           passport_number = ?, passport_expiry = ?, preferred_class = ?, home_airport = ?,
           frequent_flyer_number = ?, address = ?, updated_at = ? WHERE user_id = ?""",
        (data.get("phone", ""), dob_str, data.get("gender", ""), data.get("nationality", "India"),
         data.get("passport_number", ""), exp_str, data.get("preferred_class", "Economy"),
         data.get("home_airport", ""), data.get("frequent_flyer_number", ""), data.get("address", ""),
         now_str, user.id)
    )
    conn.commit()


def generate_reference() -> str:
    while True:
        ref = secrets.token_hex(4).upper()
        if is_mongo_available():
            try:
                db = get_mongo_db()
                if not db.flights_booking.find_one({"reference": ref}):
                    return ref
                continue
            except Exception:
                pass
        # SQLite check
        try:
            conn = _sqlite_conn()
            if not conn.execute("SELECT 1 FROM flights_booking WHERE reference = ?", (ref,)).fetchone():
                return ref
        except Exception:
            return ref


def create_booking(user: User, flight: dict, pax_count: int, contact_email: str,
                   contact_phone: str, passengers_data: list, return_date_val=None,
                   travel_class: str = "economy") -> Booking:
    now = datetime.now(timezone.utc)
    ref = generate_reference()

    dep_d = flight.get("dep_date")
    if isinstance(dep_d, str):
        dep_d = datetime.combine(date.fromisoformat(dep_d), datetime.min.time())
    elif isinstance(dep_d, date) and not isinstance(dep_d, datetime):
        dep_d = datetime.combine(dep_d, datetime.min.time())

    sched_dep = flight.get("scheduled_departure")
    if isinstance(sched_dep, str) and sched_dep:
        try: sched_dep = datetime.fromisoformat(sched_dep)
        except Exception: sched_dep = None

    sched_arr = flight.get("scheduled_arrival")
    if isinstance(sched_arr, str) and sched_arr:
        try: sched_arr = datetime.fromisoformat(sched_arr)
        except Exception: sched_arr = None

    ret_d = None
    if return_date_val:
        if isinstance(return_date_val, str):
            ret_d = datetime.combine(date.fromisoformat(return_date_val), datetime.min.time())
        elif isinstance(return_date_val, date) and not isinstance(return_date_val, datetime):
            ret_d = datetime.combine(return_date_val, datetime.min.time())
        else:
            ret_d = return_date_val

    if is_mongo_available():
        try:
            db = get_mongo_db()
            b_oid = ObjectId()
            pax_embedded = []
            pax_legacy = []
            pax_objs = []

            for p in passengers_data:
                p_oid = ObjectId()
                p_dob = p.get("date_of_birth")
                if isinstance(p_dob, str) and p_dob:
                    p_dob = datetime.combine(date.fromisoformat(p_dob), datetime.min.time())
                elif isinstance(p_dob, date) and not isinstance(p_dob, datetime):
                    p_dob = datetime.combine(p_dob, datetime.min.time())

                p_exp = p.get("passport_expiry")
                if isinstance(p_exp, str) and p_exp:
                    p_exp = datetime.combine(date.fromisoformat(p_exp), datetime.min.time())
                elif isinstance(p_exp, date) and not isinstance(p_exp, datetime):
                    p_exp = datetime.combine(p_exp, datetime.min.time())

                p_subdoc = {
                    "_id": p_oid,
                    "first_name": p.get("first_name", ""),
                    "last_name": p.get("last_name", ""),
                    "date_of_birth": p_dob,
                    "gender": p.get("gender", "M"),
                    "nationality": p.get("nationality", "India"),
                    "id_number": p.get("id_number", ""),
                    "passport_number": p.get("passport_number", ""),
                    "passport_expiry": p_exp,
                    "seat_number": p.get("seat_number", ""),
                    "boarding_zone": p.get("boarding_zone", "Zone 3"),
                    "sequence_number": p.get("sequence_number", "0026"),
                }
                pax_embedded.append(p_subdoc)
                pax_objs.append(Passenger(p_subdoc))

                leg_doc = dict(p_subdoc)
                leg_doc["booking_id"] = b_oid
                pax_legacy.append(leg_doc)

            booking_doc = {
                "_id": b_oid,
                "user_id": _safe_object_id(user.id),
                "reference": ref,
                "booking_status": "confirmed",
                "created_at": now,
                "contact_email": contact_email,
                "contact_phone": contact_phone,
                "passenger_count": pax_count,
                "return_date": ret_d,
                "api_provider": flight.get("provider", "ixigo"),
                "airline_name": flight.get("airline_name", ""),
                "flight_number": flight.get("flight_number", ""),
                "dep_iata": flight.get("dep_iata", ""),
                "dep_airport": flight.get("dep_airport", ""),
                "arr_iata": flight.get("arr_iata", ""),
                "arr_airport": flight.get("arr_airport", ""),
                "dep_date": dep_d,
                "scheduled_departure": sched_dep,
                "scheduled_arrival": sched_arr,
                "dep_terminal": str(flight.get("dep_terminal") or ""),
                "dep_gate": str(flight.get("dep_gate") or ""),
                "aircraft": flight.get("aircraft", ""),
                "status_at_booking": flight.get("status", "Scheduled"),
                "snapshot": flight,
                "email_sent": False,
                "travel_class": travel_class,
                "is_connecting": flight.get("is_connecting", False),
                "stops_info": flight.get("stops", "Non-stop"),
                # MongoDB Embedded Document: Subdocuments array
                "passengers": pax_embedded,
                # MongoDB Embedded Document: Route subdocument
                "route": {
                    "origin": {
                        "iata": flight.get("dep_iata", ""),
                        "airport": flight.get("dep_airport", ""),
                        "terminal": str(flight.get("dep_terminal") or ""),
                        "gate": str(flight.get("dep_gate") or ""),
                        "date": dep_d,
                        "scheduled_time": sched_dep,
                    },
                    "destination": {
                        "iata": flight.get("arr_iata", ""),
                        "airport": flight.get("arr_airport", ""),
                        "scheduled_time": sched_arr,
                    },
                    "stops": flight.get("stops", "Non-stop"),
                    "is_connecting": flight.get("is_connecting", False),
                },
                # MongoDB Embedded Document: Flight details subdocument
                "flight_details": {
                    "airline_name": flight.get("airline_name", ""),
                    "flight_number": flight.get("flight_number", ""),
                    "aircraft": flight.get("aircraft", ""),
                    "travel_class": travel_class,
                    "status": flight.get("status", "Scheduled"),
                    "provider": flight.get("provider", "ixigo"),
                }
            }
            db.flights_booking.insert_one(booking_doc)

            # Dual-write for backward compatibility with external queries
            if pax_legacy:
                try:
                    db.flights_passenger.insert_many(pax_legacy)
                except Exception:
                    pass

            return Booking(booking_doc, passengers=pax_objs, user=user)
        except Exception:
            pass

    # SQLite fallback
    conn = _sqlite_conn()
    cur = conn.cursor()
    # Embed passenger details into snapshot for SQLite fallback consistency
    flight_snapshot = dict(flight)
    flight_snapshot["embedded_passengers"] = [
        {
            "first_name": p.get("first_name", ""),
            "last_name": p.get("last_name", ""),
            "date_of_birth": str(p.get("date_of_birth") or ""),
            "gender": p.get("gender", "M"),
            "nationality": p.get("nationality", "India"),
            "id_number": p.get("id_number", ""),
            "passport_number": p.get("passport_number", ""),
            "passport_expiry": str(p.get("passport_expiry") or ""),
            "seat_number": p.get("seat_number", ""),
            "boarding_zone": p.get("boarding_zone", "Zone 3"),
            "sequence_number": p.get("sequence_number", "0026"),
        }
        for p in passengers_data
    ]
    cur.execute(
        """INSERT INTO flights_booking (
            user_id, reference, booking_status, created_at, contact_email, contact_phone,
            passenger_count, return_date, api_provider, airline_name, flight_number,
            dep_iata, dep_airport, arr_iata, arr_airport, dep_date, scheduled_departure,
            scheduled_arrival, dep_terminal, dep_gate, aircraft, status_at_booking,
            snapshot, email_sent, travel_class, is_connecting, stops_info
        ) VALUES (?, ?, 'confirmed', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)""",
        (
            user.id, ref, now.isoformat(), contact_email, contact_phone,
            pax_count, ret_d.isoformat() if ret_d else None, flight.get("provider", "ixigo"),
            flight.get("airline_name", ""), flight.get("flight_number", ""),
            flight.get("dep_iata", ""), flight.get("dep_airport", ""),
            flight.get("arr_iata", ""), flight.get("arr_airport", ""),
            dep_d.date().isoformat() if hasattr(dep_d, "date") else str(dep_d or ""),
            sched_dep.isoformat() if sched_dep else None,
            sched_arr.isoformat() if sched_arr else None,
            str(flight.get("dep_terminal") or ""), str(flight.get("dep_gate") or ""),
            flight.get("aircraft", ""), flight.get("status", "Scheduled"),
            json.dumps(flight_snapshot), travel_class,
            1 if flight.get("is_connecting") else 0,
            flight.get("stops", "Non-stop")
        )
    )
    b_id = cur.lastrowid
    pax_objs = []
    for p in passengers_data:
        p_dob = p.get("date_of_birth")
        p_dob_str = (p_dob.isoformat() if hasattr(p_dob, "isoformat") else str(p_dob or "")).strip() or "2000-01-01"
        p_exp = p.get("passport_expiry")
        p_exp_str = p_exp.isoformat() if hasattr(p_exp, "isoformat") else (str(p_exp) if p_exp else None)

        cur.execute(
            """INSERT INTO flights_passenger (
                booking_id, first_name, last_name, date_of_birth, gender, nationality,
                id_number, passport_number, passport_expiry, seat_number, boarding_zone, sequence_number
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                b_id, p.get("first_name", ""), p.get("last_name", ""), p_dob_str,
                p.get("gender", "M"), p.get("nationality", "India"), p.get("id_number", ""),
                p.get("passport_number", ""), p_exp_str, p.get("seat_number", ""),
                p.get("boarding_zone", "Zone 3"), p.get("sequence_number", "0026")
            )
        )
        p_dict = dict(p)
        p_dict["_id"] = cur.lastrowid
        p_dict["booking_id"] = b_id
        pax_objs.append(Passenger(p_dict))
    conn.commit()

    b_row = conn.execute("SELECT * FROM flights_booking WHERE id = ?", (b_id,)).fetchone()
    b_dict = dict(b_row)
    b_dict["_id"] = b_dict["id"]
    try: b_dict["snapshot"] = json.loads(b_dict["snapshot"])
    except Exception: b_dict["snapshot"] = flight_snapshot
    return Booking(b_dict, passengers=pax_objs, user=user)


def get_booking_by_reference(reference: str, user: User = None) -> Booking | None:
    if is_mongo_available():
        try:
            db = get_mongo_db()
            q = {"reference": reference.strip().upper()}
            if user and not user.is_superuser:
                q["user_id"] = _safe_object_id(user.id)
            b_doc = db.flights_booking.find_one(q)
            if b_doc:
                # 1. MongoDB Embedded Document pattern: read directly from embedded subdocuments
                if b_doc.get("passengers") and isinstance(b_doc["passengers"], list):
                    passengers = [Passenger(d) for d in b_doc["passengers"]]
                else:
                    # Fallback to secondary collection for legacy documents
                    p_docs = list(db.flights_passenger.find({"booking_id": b_doc["_id"]}))
                    passengers = [Passenger(d) for d in p_docs]
                return Booking(b_doc, passengers=passengers, user=user)
        except Exception:
            pass
    # SQLite fallback
    try:
        conn = _sqlite_conn()
        if user and not user.is_superuser:
            row = conn.execute("SELECT * FROM flights_booking WHERE UPPER(reference) = UPPER(?) AND user_id = ?", (reference.strip(), user.id)).fetchone()
        else:
            row = conn.execute("SELECT * FROM flights_booking WHERE UPPER(reference) = UPPER(?)", (reference.strip(),)).fetchone()
        if not row:
            return None
        b_doc = dict(row)
        b_doc["_id"] = b_doc["id"]
        if isinstance(b_doc.get("snapshot"), str):
            try: b_doc["snapshot"] = json.loads(b_doc["snapshot"])
            except Exception: b_doc["snapshot"] = {}
        p_rows = conn.execute("SELECT * FROM flights_passenger WHERE booking_id = ?", (b_doc["id"],)).fetchall()
        p_objs = []
        for pr in p_rows:
            pd = dict(pr)
            pd["_id"] = pd["id"]
            p_objs.append(Passenger(pd))
        return Booking(b_doc, passengers=p_objs, user=user)
    except Exception:
        return None


def get_user_bookings(user: User) -> list[Booking]:
    if is_mongo_available():
        try:
            db = get_mongo_db()
            cursor = db.flights_booking.find({"user_id": _safe_object_id(user.id)}).sort("created_at", -1)
            bookings = []
            for b_doc in cursor:
                # 1. MongoDB Embedded Document pattern: read directly from embedded subdocuments (Zero extra DB roundtrips)
                if b_doc.get("passengers") and isinstance(b_doc["passengers"], list):
                    passengers = [Passenger(d) for d in b_doc["passengers"]]
                else:
                    p_docs = list(db.flights_passenger.find({"booking_id": b_doc["_id"]}))
                    passengers = [Passenger(d) for d in p_docs]
                bookings.append(Booking(b_doc, passengers=passengers, user=user))
            return bookings
        except Exception:
            pass
    # SQLite fallback
    try:
        conn = _sqlite_conn()
        rows = conn.execute("SELECT * FROM flights_booking WHERE user_id = ? ORDER BY created_at DESC", (user.id,)).fetchall()
        bookings = []
        for row in rows:
            b_doc = dict(row)
            b_doc["_id"] = b_doc["id"]
            if isinstance(b_doc.get("snapshot"), str):
                try: b_doc["snapshot"] = json.loads(b_doc["snapshot"])
                except Exception: b_doc["snapshot"] = {}
            p_rows = conn.execute("SELECT * FROM flights_passenger WHERE booking_id = ?", (b_doc["id"],)).fetchall()
            p_objs = []
            for pr in p_rows:
                pd = dict(pr)
                pd["_id"] = pd["id"]
                p_objs.append(Passenger(pd))
            bookings.append(Booking(b_doc, passengers=p_objs, user=user))
        return bookings
    except Exception:
        return []


def cancel_booking_by_reference(reference: str, user: User = None) -> bool:
    """Cancels a booking by reference in both MongoDB Atlas and SQLite fallback."""
    ref_clean = reference.strip().upper()
    cancelled = False

    if is_mongo_available():
        try:
            db = get_mongo_db()
            q = {"reference": ref_clean}
            if user and not user.is_superuser:
                q["user_id"] = _safe_object_id(user.id)
            res = db.flights_booking.update_one(q, {"$set": {"booking_status": "cancelled"}})
            if res.modified_count > 0 or res.matched_count > 0:
                cancelled = True
        except Exception:
            pass

    # SQLite fallback
    try:
        conn = _sqlite_conn()
        if user and not user.is_superuser:
            cur = conn.execute(
                "UPDATE flights_booking SET booking_status = 'cancelled' WHERE UPPER(reference) = ? AND user_id = ?",
                (ref_clean, user.id)
            )
        else:
            cur = conn.execute(
                "UPDATE flights_booking SET booking_status = 'cancelled' WHERE UPPER(reference) = ?",
                (ref_clean,)
            )
        conn.commit()
        if cur.rowcount > 0:
            cancelled = True
    except Exception:
        pass

    return cancelled
