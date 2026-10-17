"""Tests mock the HTTP layer with payloads shaped like the provider docs. They verify our parsing,
error handling and booking flow - NOT the live API (run the live smoke test in the README for that)."""
from datetime import timedelta
from unittest import mock

import requests
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Booking
from .services.aerodatabox import AeroDataBoxProvider


class FakeResp:
    def __init__(self, payload, status=200):
        self._p, self.status_code, self.ok = payload, status, status < 400

    def json(self):
        return self._p


def board(day):
    mk = lambda num, hh, status, dest, **kw: {
        "number": num, "status": status, "airline": {"name": "IndiGo", "iata": "6E"},
        "aircraft": {"model": "Airbus A320"},
        "movement": {"airport": {"iata": dest, "name": dest + " Airport"},
                     "scheduledTime": {"local": f"{day} {hh}+05:30"}, "terminal": "4", "gate": "B7", **kw}}
    return {"departures": [
        mk("6E 2001", "16:30", "Delayed", "DEL", revisedTime={"local": f"{day} 17:05+05:30"}),
        mk("6E 555", "18:00", "Expected", "BOM"),  # other destination, must be filtered out
    ]}


@override_settings(FLIGHT_API_KEY="test-key", FLIGHT_API_PROVIDER="aerodatabox", FLIGHT_API_CACHE_SECONDS=0)
class LiveFlightTests(TestCase):
    def setUp(self):
        cache.clear()
        self.day = (timezone.localdate() + timedelta(days=1)).isoformat()  # tomorrow: no 'hide past' filter
        self.q = {"source": "Chennai (MAA)", "destination": "Delhi (DEL)", "departure_date": self.day, "passengers": 2}

    def _get(self, payload):
        return mock.patch("flights.services.aerodatabox.requests.get", return_value=FakeResp(payload))

    def test_normalises_and_filters_destination(self):
        with self._get(board(self.day)):
            res = self.client.get(reverse("search"), self.q)
        self.assertContains(res, "6E2001")
        self.assertNotContains(res, "6E555")
        self.assertContains(res, "Delayed")          # status exactly from API
        self.assertContains(res, "Est. 17:05 (+35 min)")
        self.assertNotContains(res, "test-key")      # key never reaches HTML

    def test_api_failure_shows_message_and_no_flights(self):
        with mock.patch("flights.services.aerodatabox.requests.get", side_effect=requests.ConnectionError("down")):
            res = self.client.get(reverse("search"), self.q)
        self.assertContains(res, "Unable to retrieve live flight information.")
        self.assertNotContains(res, "flight-card")

    @override_settings(FLIGHT_API_KEY="")
    def test_missing_key_treated_as_unavailable(self):
        res = self.client.get(reverse("search"), self.q)
        self.assertContains(res, "Unable to retrieve live flight information.")

    def test_ajax_endpoint_json_and_error(self):
        with self._get(board(self.day)):
            data = self.client.get(reverse("api_search"), self.q).json()
        self.assertEqual(data["count"], 1)
        self.assertIn("6E2001", data["html"])
        with mock.patch("flights.services.aerodatabox.requests.get", return_value=FakeResp({}, 500)):
            res = self.client.get(reverse("api_search"), self.q)
        self.assertEqual(res.status_code, 503)

    def test_form_validation(self):
        res = self.client.get(reverse("search"), {**self.q, "departure_date": "2020-01-01"})
        self.assertEqual(res.status_code, 400)
        res = self.client.get(reverse("search"), {**self.q, "destination": "MAA"})
        self.assertEqual(res.status_code, 400)

    def test_provider_normalise_full_flight_shape(self):
        p = AeroDataBoxProvider("k")
        f = p._normalise({"number": "AI 440", "status": "EnRoute", "airline": {"name": "Air India", "iata": "AI"},
                          "departure": {"airport": {"iata": "MAA", "name": "Chennai"}, "gate": "2",
                                        "scheduledTime": {"local": "2026-10-01 16:30+05:30"},
                                        "runwayTime": {"local": "2026-10-01 16:41+05:30"}},
                          "arrival": {"airport": {"iata": "DEL", "name": "Delhi"}, "terminal": "3",
                                      "scheduledTime": {"local": "2026-10-01 19:20+05:30"}}})
        self.assertEqual((f["flight_number"], f["dep_iata"], f["arr_iata"], f["arr_terminal"]), ("AI440", "MAA", "DEL", "3"))
        self.assertEqual(f["actual_departure"], "2026-10-01T16:41:00+05:30")


@override_settings(FLIGHT_API_CACHE_SECONDS=0)
class BookingFlowTests(TestCase):
    flight = {"provider": "aerodatabox", "flight_number": "6E2001", "airline_name": "IndiGo", "airline_iata": "6E",
              "dep_iata": "MAA", "dep_airport": "Chennai", "arr_iata": "DEL", "arr_airport": "Delhi",
              "dep_date": "2026-10-05", "scheduled_departure": "2026-10-05T16:30:00+05:30",
              "estimated_departure": None, "actual_departure": None, "scheduled_arrival": "2026-10-05T19:15:00+05:30",
              "estimated_arrival": None, "actual_arrival": None, "status": "Expected", "dep_terminal": "4",
              "dep_gate": "B7", "arr_terminal": "", "arr_gate": "", "aircraft": "Airbus A320",
              "fetched_at": "2026-10-02T11:00:00+00:00"}

    def test_full_flow_login_to_my_bookings(self):
        qs = "?number=6E2001&date=2026-10-05&source=MAA&dest=DEL&pax=2&ret=2026-10-09"
        res = self.client.get(reverse("book_start") + qs)
        self.assertEqual(res.status_code, 302)
        self.assertIn("/login/", res["Location"])           # must log in first
        User.objects.create_user("asha", "a@x.com", "pw-12345-Zq")
        self.client.login(username="asha", password="pw-12345-Zq")
        with mock.patch("flights.views.get_flight_details", return_value=dict(self.flight)):
            res = self.client.get(reverse("book_start") + qs)
        self.assertRedirects(res, reverse("passengers"))
        post = {"p-TOTAL_FORMS": 2, "p-INITIAL_FORMS": 0, "p-MIN_NUM_FORMS": 2, "p-MAX_NUM_FORMS": 2,
                "contact_email": "a@x.com", "contact_phone": "9999999999"}
        for i, n in enumerate(["Asha", "Ravi"]):
            post.update({f"p-{i}-first_name": n, f"p-{i}-last_name": "K", f"p-{i}-date_of_birth": "1990-01-01",
                         f"p-{i}-gender": "F", f"p-{i}-id_number": ""})
        res = self.client.post(reverse("passengers"), post)
        b = Booking.objects.get()
        self.assertRedirects(res, reverse("confirmation", args=[b.reference]))
        self.assertEqual((b.flight_number, b.passengers.count(), str(b.return_date)), ("6E2001", 2, "2026-10-09"))
        self.assertEqual(b.snapshot["dep_gate"], "B7")        # snapshot stored
        self.assertContains(self.client.get(reverse("my_bookings")), "6E2001")
        self.assertContains(self.client.get(reverse("confirmation", args=[b.reference])), "Search return flights")


@override_settings(FLIGHT_API_PROVIDER="ixigo", FLIGHT_API_CACHE_SECONDS=0)
class IxigoRealTimeFlightTests(TestCase):
    def test_ixigo_search_returns_realtime_flights(self):
        from .services.ixigo import IxigoProvider
        p = IxigoProvider()
        today = timezone.localdate()
        flights = p.search("MAA", "DEL", today)
        self.assertGreaterEqual(len(flights), 10)
        first = flights[0]
        self.assertEqual(first["dep_iata"], "MAA")
        self.assertEqual(first["arr_iata"], "DEL")
        self.assertIn("IndiGo", [f["airline_name"] for f in flights])
        self.assertIn("Air India", [f["airline_name"] for f in flights])
        self.assertGreater(first["price"], 1000)
        self.assertTrue(any(f["status"] in ("Boarding", "In Flight", "Scheduled", "On Time", "Departed", "Landed") for f in flights))

    def test_ixigo_details_returns_flight(self):
        from .services.ixigo import IxigoProvider
        p = IxigoProvider()
        today = timezone.localdate()
        flights = p.search("MAA", "DEL", today)
        target = flights[0]["flight_number"]
        details = p.details(target, today)
        self.assertTrue(len(details) > 0)
        self.assertEqual(details[0]["flight_number"], target)

    def test_ixigo_search_view_renders_cards_and_ribbon(self):
        today = timezone.localdate()
        res = self.client.get(reverse("search"), {
            "source": "Chennai (MAA)", "destination": "Delhi (DEL)",
            "departure_date": today.isoformat(), "passengers": 1, "show_all": "1"
        })
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "flight-card")
        self.assertContains(res, "date-ribbon-container")
        self.assertContains(res, "LIVE REAL-TIME FLIGHTS")
        self.assertContains(res, "₹")


class UserRegistrationTests(TestCase):
    def test_registration_accepts_any_username_format(self):
        from .forms import RegisterForm
        form = RegisterForm({
            "username": "Nithish Flyer #1 (VIP) & 2026!",
            "email": "nithish@example.com",
            "password1": "SecureFlightPass123!@#",
            "password2": "SecureFlightPass123!@#",
        })
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual(user.username, "Nithish Flyer #1 (VIP) & 2026!")

    def test_registration_view_renders_updated_help_text(self):
        res = self.client.get(reverse("register"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Any format is accepted.")
        self.assertNotContains(res, "Letters, digits and @/./+/-/_ only")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class BoardingPassTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="flyer_nithish", password="password123")
        self.today = timezone.localdate()
        self.booking = Booking.objects.create(
            user=self.user,
            passenger_count=2,
            contact_email="customer@example.com",
            contact_phone="9876543210",
            api_provider="ixigo",
            airline_name="IndiGo",
            flight_number="6E 2365",
            dep_iata="IXM",
            dep_airport="Madurai Airport",
            arr_iata="DEL",
            arr_airport="Indira Gandhi International",
            dep_date=self.today,
            dep_terminal="1",
            dep_gate="A3",
            snapshot={"arr_terminal": "2"},
        )
        from .models import Passenger
        self.p1 = Passenger.objects.create(
            booking=self.booking,
            first_name="Nithish",
            last_name="Sankara Narayanan",
            date_of_birth=self.today,
            gender="M",
            seat_number="8A",
            boarding_zone="Zone 3",
            sequence_number="0026",
        )
        self.p2 = Passenger.objects.create(
            booking=self.booking,
            first_name="Priya",
            last_name="Sundaram",
            date_of_birth=self.today,
            gender="F",
            seat_number="8B",
            boarding_zone="Zone 3",
            sequence_number="0027",
        )

    def test_airline_profile_resolution(self):
        from .services.boarding_pass import resolve_airline_profile
        airlines_to_test = [
            ("6E 2365", "IndiGo", "#001b94"),
            ("AI 804", "Air India", "#9A0002"),
            ("UK 810", "Vistara", "#4B1736"),
            ("QP 1301", "Akasa Air", "#E64A19"),
            ("SG 8169", "SpiceJet", "#DE1A22"),
            ("IX 2507", "Air India Express", "#E64010"),
            ("EK 542", "Emirates", "#D71921"),
            ("QR 570", "Qatar Airways", "#5C0632"),
            ("SQ 503", "Singapore Airlines", "#1D3762"),
            ("ZZ 999", "Unknown Airways", "#0F223D"),
        ]
        for flt, name, expected_primary in airlines_to_test:
            prof = resolve_airline_profile(flt, name)
            self.assertEqual(prof["primary"], expected_primary, f"Failed primary color for {name} ({flt})")
            self.assertTrue(len(prof["services"]) > 0)
            self.assertTrue(len(prof["meal"]) > 0)

    def test_pdf_generation_multi_page(self):
        from .services.boarding_pass import generate_boarding_passes_pdf
        pdf_buf = generate_boarding_passes_pdf(self.booking)
        raw_bytes = pdf_buf.getvalue()
        self.assertTrue(raw_bytes.startswith(b"%PDF"))
        
        # Verify 2 pages for 2 passengers
        fitz_module = None
        try:
            import pymupdf as fitz_module
        except ImportError:
            try:
                import fitz as fitz_module
            except ImportError:
                fitz_module = None

        if fitz_module is not None:
            doc = fitz_module.open(stream=raw_bytes, filetype="pdf")
            self.assertEqual(len(doc), 2)
        else:
            page_count = raw_bytes.count(b"/Type /Page") + raw_bytes.count(b"/Type/Page")
            self.assertGreaterEqual(page_count, 2)


    def test_views_endpoints(self):
        self.client.force_login(self.user)
        # View HTML coupon
        res = self.client.get(reverse("boarding_pass_view", kwargs={"reference": self.booking.reference}))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "IndiGo")
        self.assertContains(res, "8A")
        self.assertContains(res, "0026")

        # Download PDF endpoint
        res_pdf = self.client.get(reverse("boarding_pass_pdf", kwargs={"reference": self.booking.reference}))
        self.assertEqual(res_pdf.status_code, 200)
        self.assertEqual(res_pdf["Content-Type"], "application/pdf")
        self.assertIn(f"BoardingPass_{self.booking.reference}", res_pdf["Content-Disposition"])


@override_settings(FLIGHT_API_PROVIDER="ixigo", FLIGHT_API_CACHE_SECONDS=0)
class NewFeaturesTests(TestCase):
    def test_connecting_flights_generation(self):
        from .services.ixigo import IxigoProvider
        p = IxigoProvider()
        today = timezone.localdate()
        flights = p.search("MAA", "DEL", today)
        
        non_stop = [f for f in flights if not f.get("is_connecting")]
        connecting = [f for f in flights if f.get("is_connecting")]
        
        self.assertTrue(len(non_stop) > 0, "Should have non-stop flights")
        self.assertTrue(len(connecting) > 0, "Should have connecting flights")
        
        # Verify connecting flight attributes
        c_flight = connecting[0]
        self.assertTrue(c_flight["is_connecting"])
        self.assertIn("stop", c_flight["stops_info"].lower())
        self.assertIn(c_flight["layover_airport"], c_flight["stops_info"])
        self.assertTrue(c_flight["layover_minutes"] > 0)
        self.assertTrue(len(c_flight["layover_airport"]) == 3)

    def test_travel_class_fare_multipliers(self):
        from .services.ixigo import IxigoProvider, CLASS_MULTIPLIERS
        p = IxigoProvider()
        today = timezone.localdate()
        
        fl_econ = p.search("MAA", "DEL", today, travel_class="Economy")[0]
        fl_prem = p.search("MAA", "DEL", today, travel_class="Premium Economy")[0]
        fl_biz = p.search("MAA", "DEL", today, travel_class="Business Class")[0]
        fl_first = p.search("MAA", "DEL", today, travel_class="First Class")[0]
        
        self.assertEqual(fl_econ["travel_class"], "Economy")
        self.assertEqual(fl_prem["travel_class"], "Premium Economy")
        self.assertEqual(fl_biz["travel_class"], "Business Class")
        self.assertEqual(fl_first["travel_class"], "First Class")
        
        # Fare ordering: Economy < Premium Economy < Business Class < First Class
        self.assertLess(fl_econ["price"], fl_prem["price"])
        self.assertLess(fl_prem["price"], fl_biz["price"])
        self.assertLess(fl_biz["price"], fl_first["price"])

    def test_airports_coverage_and_international_detection(self):
        from .services.airports import (
            AIRPORT_REGISTRY,
            is_international_route,
            get_airport_country,
            get_airport_country_name,
        )
        # Check Indian commercial airports are present
        indian_airports = ["MAA", "DEL", "BOM", "BLR", "HYD", "CCU", "COK", "GOI", "IXB", "IXM", "PNQ", "TRV", "ATQ", "SXR", "IXC", "IDR"]
        for iata in indian_airports:
            self.assertIn(iata, AIRPORT_REGISTRY, f"Airport {iata} must be present in registry")
            self.assertEqual(get_airport_country(iata), "IN")
            self.assertEqual(get_airport_country_name(iata), "India")
            
        # Check international routes
        self.assertFalse(is_international_route("MAA", "DEL"))
        self.assertFalse(is_international_route("BOM", "IXM"))
        self.assertTrue(is_international_route("MAA", "DXB"))
        self.assertTrue(is_international_route("DEL", "LHR"))
        self.assertTrue(is_international_route("SIN", "BOM"))

    def test_passenger_form_conditional_passport_validation(self):
        from .forms import PassengerForm
        
        # 1. Domestic route with Indian national -> passport NOT required
        form_domestic_indian = PassengerForm(
            data={
                "first_name": "Nithish",
                "last_name": "Sankaran",
                "date_of_birth": "1995-05-15",
                "gender": "M",
                "nationality": "India",
                "passport_number": "",
            },
            is_international=False,
        )
        self.assertTrue(form_domestic_indian.is_valid(), form_domestic_indian.errors)
        
        # 2. International route with Indian national -> passport IS required
        form_intl_indian_missing_passport = PassengerForm(
            data={
                "first_name": "Nithish",
                "last_name": "Sankaran",
                "date_of_birth": "1995-05-15",
                "gender": "M",
                "nationality": "India",
                "passport_number": "",
            },
            is_international=True,
        )
        self.assertFalse(form_intl_indian_missing_passport.is_valid())
        self.assertIn("passport_number", form_intl_indian_missing_passport.errors)
        
        # 3. International route with Indian national + valid passport -> Valid
        form_intl_indian_valid = PassengerForm(
            data={
                "first_name": "Nithish",
                "last_name": "Sankaran",
                "date_of_birth": "1995-05-15",
                "gender": "M",
                "nationality": "India",
                "passport_number": "Z1234567",
            },
            is_international=True,
        )
        self.assertTrue(form_intl_indian_valid.is_valid(), form_intl_indian_valid.errors)
        
        # 4. Domestic route with foreign national -> passport IS required
        form_domestic_foreigner = PassengerForm(
            data={
                "first_name": "John",
                "last_name": "Smith",
                "date_of_birth": "1988-10-20",
                "gender": "M",
                "nationality": "United States",
                "passport_number": "",
            },
            is_international=False,
        )
        self.assertFalse(form_domestic_foreigner.is_valid())
        self.assertIn("passport_number", form_domestic_foreigner.errors)


class UserProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testflyer", email="flyer@example.com", password="password123")

    def test_profile_auto_created_signal(self):
        from .models import UserProfile
        self.assertTrue(hasattr(self.user, "profile"))
        self.assertIsInstance(self.user.profile, UserProfile)
        self.assertEqual(self.user.profile.nationality, "India")
        self.assertEqual(self.user.profile.preferred_class, "Economy")

    def test_profile_view_requires_login(self):
        res = self.client.get(reverse("profile"))
        self.assertEqual(res.status_code, 302)
        self.assertIn("/login/", res["Location"])

    def test_profile_view_authenticated(self):
        self.client.force_login(self.user)
        res = self.client.get(reverse("profile"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "testflyer")
        self.assertContains(res, "flyer@example.com")
        self.assertContains(res, "Edit Profile")

    def test_profile_edit_flow(self):
        self.client.force_login(self.user)
        # GET edit page
        res = self.client.get(reverse("profile_edit"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Edit Traveler Profile")

        # POST update
        post_data = {
            "first_name": "Nithish",
            "last_name": "Kumar",
            "email": "nithish.updated@example.com",
            "phone": "+91 9876543210",
            "date_of_birth": "1995-08-20",
            "gender": "M",
            "nationality": "India",
            "passport_number": "M9876543",
            "passport_expiry": "2032-12-31",
            "preferred_class": "Business Class",
            "home_airport": "Chennai (MAA)",
            "frequent_flyer_number": "AI-90021",
            "address": "Chennai, Tamil Nadu",
        }
        res_post = self.client.post(reverse("profile_edit"), post_data)
        self.assertEqual(res_post.status_code, 302)
        self.assertRedirects(res_post, reverse("profile"))

        # Verify database persisted updates
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Nithish")
        self.assertEqual(self.user.last_name, "Kumar")
        self.assertEqual(self.user.email, "nithish.updated@example.com")

        profile = self.user.profile
        self.assertEqual(profile.phone, "+91 9876543210")
        self.assertEqual(profile.passport_number, "M9876543")
        self.assertEqual(profile.preferred_class, "Business Class")
        self.assertEqual(profile.home_airport, "Chennai (MAA)")

        # Verify updated values appear on profile page
        res_after = self.client.get(reverse("profile"))
        self.assertEqual(res_after.status_code, 200)
        self.assertContains(res_after, "Nithish Kumar")
        self.assertContains(res_after, "M9876543")
        self.assertContains(res_after, "Business Class")
        self.assertContains(res_after, "+91 9876543210")


class AirlinesDividanceAndCountriesTests(TestCase):
    """Tests covering the 3 airline categories, cabotage laws, and newly added countries/airports."""

    def test_new_countries_and_airports(self):
        from .services.airports import (
            AIRPORT_REGISTRY,
            NATIONALITY_CHOICES,
            get_airport_country,
            get_airport_country_name,
            parse_code,
        )
        # Bhutan
        self.assertIn("PBH", AIRPORT_REGISTRY)
        self.assertEqual(get_airport_country("PBH"), "BT")
        self.assertEqual(get_airport_country_name("PBH"), "Bhutan")
        self.assertEqual(parse_code("Paro (PBH)"), "PBH")

        # Vietnam
        self.assertIn("HAN", AIRPORT_REGISTRY)
        self.assertIn("SGN", AIRPORT_REGISTRY)
        self.assertEqual(get_airport_country("HAN"), "VN")
        self.assertEqual(get_airport_country("SGN"), "VN")
        self.assertEqual(get_airport_country_name("HAN"), "Vietnam")

        # Nationalities
        nat_list = [code for code, name in NATIONALITY_CHOICES]
        self.assertIn("Bhutan", nat_list)
        self.assertIn("Vietnam", nat_list)
        self.assertIn("Maldives", nat_list)
        self.assertIn("Turkey", nat_list)
        self.assertIn("Indonesia", nat_list)

    def test_airline_dividance_categories(self):
        from .services.airlines_data import (
            DOMESTIC_ONLY_AIRLINES,
            BOTH_DOMESTIC_INTL_AIRLINES,
            ALL_FOREIGN_AIRLINES,
            FOREIGN_AIRLINES_BY_REGION,
            get_airline_by_iata,
            get_airline_scope,
            SCOPE_DOMESTIC_ONLY,
            SCOPE_BOTH_DOMESTIC_INTL,
            SCOPE_FOREIGN,
        )
        # Category 1: Domestic Only
        dom_iatas = [a["iata"] for a in DOMESTIC_ONLY_AIRLINES]
        self.assertIn("9I", dom_iatas)  # Alliance Air
        self.assertIn("S5", dom_iatas)  # Star Air
        self.assertIn("IC", dom_iatas)  # Fly91
        self.assertIn("I7", dom_iatas)  # IndiaOne Air
        self.assertEqual(get_airline_scope("Alliance Air"), SCOPE_DOMESTIC_ONLY)
        self.assertEqual(get_airline_scope("9I"), SCOPE_DOMESTIC_ONLY)

        # Category 2: Both Domestic and International
        both_iatas = [a["iata"] for a in BOTH_DOMESTIC_INTL_AIRLINES]
        self.assertIn("6E", both_iatas)  # IndiGo
        self.assertIn("AI", both_iatas)  # Air India
        self.assertIn("IX", both_iatas)  # Air India Express
        self.assertIn("SG", both_iatas)  # SpiceJet
        self.assertIn("QP", both_iatas)  # Akasa Air
        self.assertEqual(get_airline_scope("IndiGo"), SCOPE_BOTH_DOMESTIC_INTL)
        self.assertEqual(get_airline_scope("Air India"), SCOPE_BOTH_DOMESTIC_INTL)

        # Category 3: Foreign Airlines by Region
        self.assertIn("Middle East", FOREIGN_AIRLINES_BY_REGION)
        self.assertIn("Southeast & East Asia", FOREIGN_AIRLINES_BY_REGION)
        self.assertIn("Europe", FOREIGN_AIRLINES_BY_REGION)
        self.assertIn("North America", FOREIGN_AIRLINES_BY_REGION)
        self.assertIn("Neighbouring South Asia", FOREIGN_AIRLINES_BY_REGION)

        # Check key foreign carriers
        foreign_iatas = [a["iata"] for a in ALL_FOREIGN_AIRLINES]
        self.assertIn("EK", foreign_iatas)  # Emirates
        self.assertIn("QR", foreign_iatas)  # Qatar Airways
        self.assertIn("EY", foreign_iatas)  # Etihad Airways
        self.assertIn("G9", foreign_iatas)  # Air Arabia
        self.assertIn("GF", foreign_iatas)  # Gulf Air
        self.assertIn("FZ", foreign_iatas)  # flydubai
        self.assertIn("SV", foreign_iatas)  # Saudia
        self.assertIn("WY", foreign_iatas)  # Oman Air
        self.assertIn("SQ", foreign_iatas)  # Singapore Airlines
        self.assertIn("MH", foreign_iatas)  # Malaysia Airlines
        self.assertIn("TG", foreign_iatas)  # Thai Airways
        self.assertIn("CX", foreign_iatas)  # Cathay Pacific
        self.assertIn("JL", foreign_iatas)  # Japan Airlines
        self.assertIn("VN", foreign_iatas)  # Vietnam Airlines
        self.assertIn("BA", foreign_iatas)  # British Airways
        self.assertIn("LH", foreign_iatas)  # Lufthansa
        self.assertIn("AF", foreign_iatas)  # Air France
        self.assertIn("KL", foreign_iatas)  # KLM
        self.assertIn("VS", foreign_iatas)  # Virgin Atlantic
        self.assertIn("LX", foreign_iatas)  # Swiss
        self.assertIn("UA", foreign_iatas)  # United Airlines
        self.assertIn("AC", foreign_iatas)  # Air Canada
        self.assertIn("UL", foreign_iatas)  # SriLankan Airlines
        self.assertIn("BG", foreign_iatas)  # Biman Bangladesh Airlines
        self.assertIn("KB", foreign_iatas)  # Drukair
        self.assertEqual(get_airline_scope("Vietnam Airlines"), SCOPE_FOREIGN)
        self.assertEqual(get_airline_scope("Drukair"), SCOPE_FOREIGN)

    def test_cabotage_enforcement_on_domestic_routes(self):
        """Under Indian cabotage law, foreign airlines are strictly forbidden from domestic routes."""
        from .services.airlines_data import get_eligible_airlines_for_route, SCOPE_FOREIGN
        from .services.ixigo import IxigoProvider
        from django.utils import timezone

        eligible = get_eligible_airlines_for_route("IN", "IN")
        for a in eligible:
            self.assertNotEqual(a["scope"], SCOPE_FOREIGN, f"Foreign carrier {a['name']} leaked into domestic route under cabotage laws!")

        # Search domestic flights via IxigoProvider
        provider = IxigoProvider()
        flights = provider.search("DEL", "BOM", timezone.localdate() + timedelta(days=5))
        self.assertTrue(len(flights) > 0)
        for flt in flights:
            self.assertNotEqual(flt["airline_scope"], "foreign", f"Domestic flight {flt['flight_number']} operated by foreign carrier {flt['airline_name']} violating cabotage!")

    def test_international_route_selection(self):
        """International routes should feature foreign carriers & Indian mainline, but no domestic-only regional carriers."""
        from .services.airlines_data import get_eligible_airlines_for_route, SCOPE_DOMESTIC_ONLY
        from .services.ixigo import IxigoProvider
        from django.utils import timezone

        # India to Vietnam
        vn_eligible = get_eligible_airlines_for_route("IN", "VN")
        vn_iatas = [a["iata"] for a in vn_eligible]
        self.assertIn("VN", vn_iatas, "Vietnam Airlines must be eligible on India-Vietnam route")
        for a in vn_eligible:
            self.assertNotEqual(a["scope"], SCOPE_DOMESTIC_ONLY, "Domestic-only regional carrier cannot fly international!")

        # India to Bhutan
        bt_eligible = get_eligible_airlines_for_route("IN", "BT")
        bt_iatas = [a["iata"] for a in bt_eligible]
        self.assertIn("KB", bt_iatas, "Drukair must be eligible on India-Bhutan route")

        # Live search India to Paro, Bhutan
        provider = IxigoProvider()
        bt_flights = provider.search("DEL", "PBH", timezone.localdate() + timedelta(days=10))
        self.assertTrue(len(bt_flights) > 0)
        airline_names = [f["airline_name"] for f in bt_flights]
        self.assertIn("Drukair", airline_names)

    def test_airlines_directory_page(self):
        """Verify the /airlines/ directory route loads and contains all 3 categories."""
        res = self.client.get(reverse("airlines_directory"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Airlines Operating Only Domestic Flights in India")
        self.assertContains(res, "Airlines Operating Both Domestic &amp; International Flights")
        self.assertContains(res, "Airlines Operating Only Abroad / Into India")
        self.assertContains(res, "Alliance Air")
        self.assertContains(res, "Star Air")
        self.assertContains(res, "Fly91")
        self.assertContains(res, "IndiaOne Air")
        self.assertContains(res, "IndiGo")
        self.assertContains(res, "Air India")
        self.assertContains(res, "Vietnam Airlines")
        self.assertContains(res, "Drukair")
        self.assertContains(res, "Finnair")
        self.assertContains(res, "Turkish Airlines")
        self.assertContains(res, "Ethiopian Airlines")
        self.assertContains(res, "Qantas")
        self.assertContains(res, "Nepal Airlines")
        self.assertContains(res, "Maldivian")
        self.assertContains(res, "Cabotage")

    def test_bilateral_two_way_routes_matching(self):
        """Foreign airlines always make ways between their countries and India in both directions:
        e.g., London to Chennai AND Chennai to London feature British Airways / Virgin Atlantic + Air India / IndiGo.
        """
        from .services.airlines_data import get_eligible_airlines_for_route
        from .services.ixigo import IxigoProvider

        # 1. Outbound: London (GB) to Chennai (IN)
        outbound = get_eligible_airlines_for_route("GB", "IN")
        outbound_iatas = [a["iata"] for a in outbound[:6]]
        self.assertIn("BA", outbound_iatas, "British Airways must be in top bilateral carriers for London -> Chennai")
        self.assertIn("VS", outbound_iatas, "Virgin Atlantic must be in top bilateral carriers for London -> Chennai")
        self.assertIn("AI", outbound_iatas, "Air India must be in top bilateral carriers for London -> Chennai")

        # 2. Return: Chennai (IN) to London (GB)
        inbound = get_eligible_airlines_for_route("IN", "GB")
        inbound_iatas = [a["iata"] for a in inbound[:6]]
        self.assertIn("BA", inbound_iatas, "British Airways must be in top bilateral carriers for Chennai -> London (Return)")
        self.assertIn("VS", inbound_iatas, "Virgin Atlantic must be in top bilateral carriers for Chennai -> London (Return)")
        self.assertIn("AI", inbound_iatas, "Air India must be in top bilateral carriers for Chennai -> London (Return)")

        # Verify through Ixigo provider search
        provider = IxigoProvider()
        test_date = timezone.localdate() + timedelta(days=14)
        lon_to_maa = provider.search("LHR", "MAA", test_date)
        maa_to_lon = provider.search("MAA", "LHR", test_date)
        
        lon_to_maa_airlines = {f["airline_name"] for f in lon_to_maa}
        maa_to_lon_airlines = {f["airline_name"] for f in maa_to_lon}

        self.assertIn("British Airways", lon_to_maa_airlines)
        self.assertIn("British Airways", maa_to_lon_airlines)
        self.assertIn("Air India", lon_to_maa_airlines)
        self.assertIn("Air India", maa_to_lon_airlines)

    def test_extra_foreign_airlines_presence(self):
        """Verifies newly added airlines across Middle East, Asia, Europe, Africa, Oceania, South Asia."""
        from .services.airlines_data import get_airline_by_iata

        expected_new_carriers = [
            ("KU", "Kuwait Airways", "Kuwait"),
            ("J9", "Jazeera Airways", "Kuwait"),
            ("OV", "SalamAir", "Oman"),
            ("XY", "Flynas", "Saudi Arabia"),
            ("NH", "All Nippon Airways (ANA)", "Japan"),
            ("KE", "Korean Air", "South Korea"),
            ("OD", "Batik Air Malaysia", "Malaysia"),
            ("GA", "Garuda Indonesia", "Indonesia"),
            ("AY", "Finnair", "Finland"),
            ("LO", "LOT Polish Airlines", "Poland"),
            ("AZ", "ITA Airways", "Italy"),
            ("TK", "Turkish Airlines", "Turkey"),
            ("ET", "Ethiopian Airlines", "Ethiopia"),
            ("MS", "EgyptAir", "Egypt"),
            ("KQ", "Kenya Airways", "Kenya"),
            ("MK", "Air Mauritius", "Mauritius"),
            ("QF", "Qantas", "Australia"),
            ("RA", "Nepal Airlines", "Nepal"),
            ("Q2", "Maldivian", "Maldives"),
        ]

        for iata, name, country in expected_new_carriers:
            airline = get_airline_by_iata(iata)
            self.assertIsNotNone(airline, f"Airline {iata} ({name}) must be registered")
            self.assertEqual(airline["name"], name)
            self.assertEqual(airline["country"], country)

    def test_concession_fare_calculations(self):
        """Validates concession discounts and baggage enhancements for students, doctors/nurses, senior citizens."""
        from .services.concessions import (
            calculate_concession_fare,
            adjust_baggage_for_concession,
            CONCESSION_REGULAR,
            CONCESSION_STUDENT,
            CONCESSION_DOCTOR_NURSE,
            CONCESSION_SENIOR_CITIZEN,
        )

        base_fare = 10000
        base_baggage = "15 kg Check-in · 7 kg Cabin"

        # 1. Regular
        reg_fare, reg_sav, reg_bag, reg_meta = calculate_concession_fare(base_fare, CONCESSION_REGULAR, base_baggage)
        self.assertEqual(reg_fare, base_fare)
        self.assertEqual(reg_sav, 0)
        self.assertEqual(reg_bag, base_baggage)

        # 2. Student (12% OFF + 10kg extra baggage)
        stu_fare, stu_sav, stu_bag, stu_meta = calculate_concession_fare(base_fare, CONCESSION_STUDENT, base_baggage)
        self.assertLess(stu_fare, base_fare)
        self.assertTrue(stu_sav > 0)
        self.assertIn("25 kg Check-in (Includes 10 kg Student Allowance)", stu_bag)
        self.assertIn("Student", stu_meta["name"])
        self.assertTrue(len(stu_meta["doc_required"]) > 0)

        # 3. Doctors & Nurses (10% OFF Medical Heroes)
        med_fare, med_sav, med_bag, med_meta = calculate_concession_fare(base_fare, CONCESSION_DOCTOR_NURSE, base_baggage)
        self.assertLess(med_fare, base_fare)
        self.assertTrue(med_sav > 0)
        self.assertEqual(med_bag, base_baggage)  # No extra baggage, pure fare discount
        self.assertIn("Medical Heroes", med_meta["short_name"])

        # 4. Senior Citizen (15% OFF, Age 60+)
        sen_fare, sen_sav, sen_bag, sen_meta = calculate_concession_fare(base_fare, CONCESSION_SENIOR_CITIZEN, base_baggage)
        self.assertLess(sen_fare, base_fare)
        self.assertTrue(sen_sav > 0)
        self.assertIn("Senior Citizen", sen_meta["name"])
        self.assertIn("60", sen_meta["doc_required"])

    def test_search_with_concessions_flow(self):
        """End-to-end integration: search with student concession returns discounted flights and badge."""
        from django.utils import timezone
        target_date = (timezone.localdate() + timedelta(days=5)).isoformat()
        
        # Search with student concession
        res = self.client.get(reverse("search"), {
            "source": "Chennai (MAA)",
            "destination": "Delhi (DEL)",
            "departure_date": target_date,
            "passengers": 1,
            "travel_class": "economy",
            "fare_type": "student",
        })
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Student Concession")
        self.assertContains(res, "Includes 10 kg Student Allowance")
        self.assertContains(res, "Save ₹")




