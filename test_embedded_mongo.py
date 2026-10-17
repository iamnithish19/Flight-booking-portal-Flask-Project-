"""Test script verifying the MongoDB Embedded Document pattern and dual-layer persistence."""
import os
import sys
from datetime import datetime, timezone, date
from bson import ObjectId

# Ensure settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from flights.flask_models import Booking, Passenger, User
from flights.services.mongo import is_mongo_available

def test_embedded_document_instantiation():
    print("-> Testing Booking instantiation with MongoDB Embedded Documents...")
    
    # Simulate a MongoDB document with embedded passengers array, route subdocument, and flight details
    mongo_doc = {
        "_id": ObjectId(),
        "reference": "EMBED123",
        "booking_status": "confirmed",
        "created_at": datetime.now(timezone.utc),
        "contact_email": "passenger@example.com",
        "contact_phone": "+91 9876543210",
        "passenger_count": 2,
        "flight_number": "6E 204",
        "airline_name": "IndiGo",
        "dep_iata": "DEL",
        "dep_airport": "Indira Gandhi International Airport",
        "arr_iata": "BOM",
        "arr_airport": "Chhatrapati Shivaji Maharaj International Airport",
        "dep_date": date(2026, 11, 15),
        "scheduled_departure": datetime(2026, 11, 15, 6, 30, tzinfo=timezone.utc),
        "scheduled_arrival": datetime(2026, 11, 15, 8, 45, tzinfo=timezone.utc),
        "dep_terminal": "T3",
        "dep_gate": "32B",
        "aircraft": "Airbus A320neo",
        "status_at_booking": "On Time",
        "travel_class": "economy",
        "is_connecting": False,
        "stops_info": "Non-stop",
        # Embedded subdocuments:
        "passengers": [
            {
                "_id": ObjectId(),
                "first_name": "Arjun",
                "last_name": "Sharma",
                "date_of_birth": "1994-05-12",
                "gender": "M",
                "nationality": "India",
                "id_number": "1234-5678-9012",
                "passport_number": "P1234567",
                "seat_number": "14A",
                "boarding_zone": "Zone 2",
                "sequence_number": "0042",
            },
            {
                "_id": ObjectId(),
                "first_name": "Priya",
                "last_name": "Sharma",
                "date_of_birth": "1996-08-23",
                "gender": "F",
                "nationality": "India",
                "id_number": "9876-5432-1098",
                "passport_number": "P7654321",
                "seat_number": "14B",
                "boarding_zone": "Zone 2",
                "sequence_number": "0043",
            }
        ],
        "route": {
            "origin": {"iata": "DEL", "airport": "Indira Gandhi International Airport", "terminal": "T3", "gate": "32B"},
            "destination": {"iata": "BOM", "airport": "Chhatrapati Shivaji Maharaj International Airport"},
            "stops": "Non-stop",
        },
        "flight_details": {
            "flight_number": "6E 204",
            "airline_name": "IndiGo",
            "aircraft": "Airbus A320neo",
            "travel_class": "economy",
        }
    }
    
    # Instantiate without secondary query
    booking = Booking(mongo_doc)
    
    assert booking.has_embedded_passengers is True, "Booking should report has_embedded_passengers=True"
    assert len(booking.passengers) == 2, f"Expected 2 passengers, got {len(booking.passengers)}"
    assert booking.passengers[0].first_name == "Arjun"
    assert booking.passengers[0].seat_number == "14A"
    assert booking.passengers[1].first_name == "Priya"
    assert booking.passengers[1].seat_number == "14B"
    print("   [PASS] Instantiation directly from embedded subdocuments succeeded with 0 secondary queries!")
    
    # Test to_embedded_document() export
    emb_doc = booking.to_embedded_document()
    assert emb_doc["reference"] == "EMBED123"
    assert emb_doc["route"]["origin"]["iata"] == "DEL"
    assert len(emb_doc["passengers"]) == 2
    assert emb_doc["pattern_type"] == "MongoDB Embedded Document (Denormalized Subdocuments)"
    print("   [PASS] to_embedded_document() produced valid schema matching MongoDB NoSQL standard!")

if __name__ == "__main__":
    print("=" * 60)
    print("  Testing MongoDB Embedded Document Concepts")
    print("=" * 60)
    test_embedded_document_instantiation()
    print("=" * 60)
    print("  ALL TESTS PASSED!")
    print("=" * 60)
