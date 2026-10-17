"""Special passenger concessions and discounted fare programs.
Includes:
1. Students (Base fare discount + Extra check-in baggage allowance)
2. Doctors & Nurses (Medical Heroes special fare discount)
3. Senior Citizens (Age 60+ special fare discount)
4. Regular (Standard adult fare)
"""
from __future__ import annotations

import re
from typing import Dict, Optional, Tuple

CONCESSION_REGULAR = "regular"
CONCESSION_REGULAR_MEMBER = "regular_member"
CONCESSION_STUDENT = "student"
CONCESSION_DOCTOR_NURSE = "doctor_nurse"
CONCESSION_SENIOR_CITIZEN = "senior_citizen"

CONCESSION_CHOICES = [
    (CONCESSION_REGULAR, "Regular Fare"),
    (CONCESSION_REGULAR_MEMBER, "Regular Member Offer (15% OFF + Free Seat)"),
    (CONCESSION_STUDENT, "Student (Discount + Extra 10kg Baggage)"),
    (CONCESSION_DOCTOR_NURSE, "Doctors & Nurses (Medical Heroes)"),
    (CONCESSION_SENIOR_CITIZEN, "Senior Citizen (Aged 60+)"),
]

CONCESSION_PROFILES: Dict[str, dict] = {
    CONCESSION_REGULAR: {
        "code": CONCESSION_REGULAR,
        "name": "Regular Fare",
        "short_name": "Regular",
        "badge": "",
        "discount_pct": 0,
        "discount_multiplier": 1.0,
        "extra_baggage_kg": 0,
        "description": "Standard adult fare with default baggage and meal privileges.",
        "doc_required": "",
        "icon": "👤",
    },
    CONCESSION_REGULAR_MEMBER: {
        "code": CONCESSION_REGULAR_MEMBER,
        "name": "Regular Membership Offer",
        "short_name": "Member Offer",
        "badge": "⭐ Regular Member Offer (15% OFF + Free Seat)",
        "discount_pct": 15,
        "discount_multiplier": 0.85,
        "extra_baggage_kg": 10,
        "description": "Exclusive fare discount for registered Airvoyage Regular Members with complimentary preferred seat selection and +10kg extra baggage.",
        "doc_required": "Airvoyage Regular Member ID or verified registered phone/email at check-in.",
        "icon": "⭐",
    },
    CONCESSION_STUDENT: {
        "code": CONCESSION_STUDENT,
        "name": "Student Concession",
        "short_name": "Student",
        "badge": "🎓 Student Concession (12% OFF + Extra 10kg Baggage)",
        "discount_pct": 12,
        "discount_multiplier": 0.88,
        "extra_baggage_kg": 10,
        "description": "Exclusive fare discount for students aged 12+ with +10 kg complimentary check-in baggage.",
        "doc_required": "Valid Student Photo ID Card from recognized school/college/university required at airport check-in.",
        "icon": "🎓",
    },
    CONCESSION_DOCTOR_NURSE: {
        "code": CONCESSION_DOCTOR_NURSE,
        "name": "Doctors & Nurses Special",
        "short_name": "Medical Heroes",
        "badge": "🩺 Medical Heroes (10% OFF)",
        "discount_pct": 10,
        "discount_multiplier": 0.90,
        "extra_baggage_kg": 0,
        "description": "Dedicated special fare honoring registered doctors, physicians, and certified nurses.",
        "doc_required": "Valid Medical Council registration number, nursing council ID, or hospital staff badge required at check-in.",
        "icon": "🩺",
    },
    CONCESSION_SENIOR_CITIZEN: {
        "code": CONCESSION_SENIOR_CITIZEN,
        "name": "Senior Citizen Concession",
        "short_name": "Senior Citizen (60+)",
        "badge": "👴 Senior Citizen (15% OFF)",
        "discount_pct": 15,
        "discount_multiplier": 0.85,
        "extra_baggage_kg": 0,
        "description": "Special fare discount for passengers who have attained 60 years of age on date of travel.",
        "doc_required": "Government photo ID with date of birth (Aadhaar, Passport, or Senior Citizen Card) proving age 60+ required at airport check-in.",
        "icon": "👴",
    },
}


def get_concession_profile(fare_type: Optional[str]) -> dict:
    key = (fare_type or "").strip().lower()
    return CONCESSION_PROFILES.get(key, CONCESSION_PROFILES[CONCESSION_REGULAR])


def adjust_baggage_for_concession(base_baggage: str, extra_kg: int) -> str:
    """Enhance baggage description with student extra allowance, e.g.:
    '15 kg Check-in · 7 kg Cabin' -> '25 kg Check-in (Includes 10 kg Student Allowance) · 7 kg Cabin'
    """
    if extra_kg <= 0:
        return base_baggage

    # Match check-in kg number
    m = re.search(r"(\d+)\s*kg\s*check-in", base_baggage, re.IGNORECASE)
    if m:
        orig_kg = int(m.group(1))
        new_kg = orig_kg + extra_kg
        replacement = f"{new_kg} kg Check-in (Includes {extra_kg} kg Student Allowance)"
        return base_baggage[:m.start()] + replacement + base_baggage[m.end():]

    return f"{base_baggage} · +{extra_kg} kg Student Baggage"


def calculate_concession_fare(
    base_price: int,
    fare_type: Optional[str] = "regular",
    base_baggage: str = "15 kg Check-in · 7 kg Cabin",
) -> Tuple[int, int, str, dict]:
    """Returns (final_price, savings, adjusted_baggage, concession_meta)."""
    prof = get_concession_profile(fare_type)
    if prof["code"] == CONCESSION_REGULAR or prof["discount_pct"] <= 0:
        return base_price, 0, base_baggage, prof

    mult = prof["discount_multiplier"]
    discounted_raw = int(round((base_price * mult) / 10.0) * 10) - 1
    if discounted_raw % 10 == 9 and discounted_raw % 100 != 99:
        discounted_raw = (discounted_raw // 10) * 10

    final_price = max(999, discounted_raw)
    savings = max(0, base_price - final_price)
    adjusted_baggage = adjust_baggage_for_concession(base_baggage, prof["extra_baggage_kg"])

    return final_price, savings, adjusted_baggage, prof
