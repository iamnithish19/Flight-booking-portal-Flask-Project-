"""Airvoyage Flight Portal - Flask Application.
Seamless real-time flight search, seat mapping, booking, profile management, and boarding pass generator.
"""
from __future__ import annotations

import os
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    get_flashed_messages,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

# Services and helpers
from flights.services.airports import AIRPORTS, is_international_route, label, parse_code
from flights.services.boarding_pass import (
    generate_boarding_passes_pdf,
    generate_qr_data_uri,
    resolve_airline_profile,
)
from flights.services.flight_api import FlightAPIError, get_flight_details, search_live_flights
from flights.services.flight_tracker import compute_live_flight_telemetry
from flights.services.cancellation import evaluate_cancellation_policy
from flights.services.seatmap import calculate_boarding_zone, get_flight_seat_map
from flights.services.airlines_data import (
    DOMESTIC_ONLY_AIRLINES,
    BOTH_DOMESTIC_INTL_AIRLINES,
    FOREIGN_AIRLINES_BY_REGION,
    ALL_AIRLINES,
)
from flights.flask_forms import (
    ContactForm,
    FlightSearchForm,
    LoginForm,
    PassengerFormSet,
    RegisterForm,
    UserProfileEditForm,
)
from flights.flask_models import (
    User,
    cancel_booking_by_reference,
    create_booking,
    create_user,
    get_booking_by_reference,
    get_or_create_user_profile,
    get_user_by_id,
    get_user_by_username,
    get_user_bookings,
    update_user_profile,
)
from flights.services.mongo import check_mongo_connection, is_mongo_available
from flights.services.membership import find_member_details, get_all_members

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.environ.get("DJANGO_SECRET_KEY") or os.environ.get("SECRET_KEY") or "airvoyage-flask-secret-key-1902"
app.config["TEMPLATES_AUTO_RELOAD"] = True

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to continue."
login_manager.login_message_category = "info"


@login_manager.user_loader
def load_user(user_id):
    return get_user_by_id(user_id)


API_DOWN_MESSAGE = (
    "Unable to retrieve live flight information. Please try again in a few moments."
)


# --------------------------------------------------------------------------
# Template Filters & Context
# --------------------------------------------------------------------------
def _parse_dt(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


@app.template_filter("isotime")
def isotime(value):
    dt = _parse_dt(value)
    return dt.strftime("%H:%M") if dt else "—"


@app.template_filter("isodate")
def isodate(value):
    dt = _parse_dt(value)
    return dt.strftime("%d %b %Y") if dt else "—"


@app.template_filter("status_label")
def status_label(raw):
    if not raw:
        return "Status unavailable"
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(raw)).replace("_", " ")
    return text[:1].upper() + text[1:].lower()


@app.template_filter("status_class")
def status_class(raw):
    return "status-" + re.sub(r"[^a-z]", "", str(raw or "unknown").lower())


@app.template_filter("localclock")
def localclock(value):
    dt = _parse_dt(value)
    return dt.strftime("%H:%M:%S") if dt else "—"


@app.template_filter("inr_format")
def inr_format(value):
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


@app.template_filter("pluralize")
def pluralize(val, arg="s"):
    try:
        count = int(val)
    except (ValueError, TypeError):
        count = len(val) if hasattr(val, "__len__") else 0
    return "" if count == 1 else arg


@app.template_filter("date")
def date_filter(val, fmt="Y-m-d"):
    if not val:
        return ""
    dt = _parse_dt(val)
    if not dt:
        return str(val)
    if fmt == "Y-m-d":
        return dt.strftime("%Y-%m-%d")
    if fmt in ("d M Y", "d M Y"):
        return dt.strftime("%d %b %Y")
    if fmt == "D, d M":
        return dt.strftime("%a, %d %b")
    if fmt == "D, d M Y":
        return dt.strftime("%a, %d %b %Y")

    trans = {
        "Y": "%Y", "y": "%y", "m": "%m", "d": "%d",
        "M": "%b", "F": "%B", "D": "%a", "l": "%A",
        "H": "%H", "i": "%M", "s": "%S"
    }
    for dj_k, py_k in trans.items():
        fmt = re.sub(r'(?<!%)\b' + dj_k + r'\b', py_k, fmt)
    try:
        return dt.strftime(fmt)
    except Exception:
        return str(val)


@app.template_filter("slugify")
def slugify(value):
    if not value:
        return ""
    s = str(value).lower().strip()
    return re.sub(r"[^\w\s-]", "", s).replace(" ", "-")


@app.context_processor
def inject_globals():
    class FlashMessage:
        def __init__(self, tag, text):
            self.tags = tag
            self.text = text
        def __str__(self):
            return self.text

    flashed = get_flashed_messages(with_categories=True)
    msgs = [FlashMessage(cat if cat != "message" else "info", msg) for cat, msg in flashed]

    return {
        "SITE_NAME": os.environ.get("SITE_NAME", "Airvoyage"),
        "airports": AIRPORTS,
        "today": date.today(),
        "refresh_seconds": max(30, int(os.environ.get("FLIGHT_AUTO_REFRESH_SECONDS", "60"))),
        "messages": msgs,
        "user": current_user,
        "csrf_token": lambda: "",
        "delay_minutes": delay_minutes_calc,
    }


def delay_minutes_calc(flight, leg="dep"):
    sched = _parse_dt(flight.get(f"scheduled_{'departure' if leg == 'dep' else 'arrival'}"))
    new = _parse_dt(flight.get(f"actual_{'departure' if leg == 'dep' else 'arrival'}")
                    or flight.get(f"estimated_{'departure' if leg == 'dep' else 'arrival'}"))
    if not sched or not new:
        return ""
    if sched.tzinfo is not None and new.tzinfo is None:
        new = new.replace(tzinfo=sched.tzinfo)
    elif sched.tzinfo is None and new.tzinfo is not None:
        sched = sched.replace(tzinfo=new.tzinfo)
    m = round((new - sched).total_seconds() / 60)
    return f"{m:+d} min" if m else "on time"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _ctx(**extra):
    return {
        "airports": AIRPORTS,
        "refresh_seconds": max(30, int(os.environ.get("FLIGHT_AUTO_REFRESH_SECONDS", "60"))),
        **extra,
    }


def _recent_enough(flight, now):
    dt = _parse_dt(flight.get("estimated_departure") or flight.get("scheduled_departure") or "")
    if dt is None:
        return True
    if dt.tzinfo is not None and now.tzinfo is None:
        dt = dt.replace(tzinfo=None)
    elif dt.tzinfo is None and now.tzinfo is not None:
        now = now.replace(tzinfo=None)
    return dt >= now - timedelta(hours=2)


def _run_search(form, force=False, show_all=False):
    d = form.cleaned_data
    travel_class = d.get("travel_class", "economy")
    fare_type = d.get("fare_type", "regular")
    result = search_live_flights(
        d["source"], d["destination"], d["departure_date"],
        travel_class=travel_class, fare_type=fare_type, force=force
    )
    flights = result["flights"]
    now = datetime.now()
    hidden = 0
    if d["departure_date"] == date.today() and not show_all:
        kept = [f for f in flights if _recent_enough(f, now)]
        hidden, flights = len(flights) - len(kept), kept
    return flights, result["fetched_at"], hidden


def _query(form_data, **extra):
    q = {
        "source": form_data["source"],
        "destination": form_data["destination"],
        "departure_date": form_data["departure_date"].isoformat() if hasattr(form_data["departure_date"], "isoformat") else str(form_data["departure_date"]),
        "passengers": form_data["passengers"],
        "travel_class": form_data.get("travel_class", "economy"),
        "fare_type": form_data.get("fare_type", "regular"),
        **extra,
    }
    if form_data.get("return_date"):
        ret = form_data["return_date"]
        q["return_date"] = ret.isoformat() if hasattr(ret, "isoformat") else str(ret)
    return urlencode(q)


def _build_date_ribbon(source, destination, dep_date, passengers, travel_class="economy", fare_type="regular"):
    today = date.today()
    start = max(today, dep_date - timedelta(days=2))
    ribbon = []
    for i in range(6):
        d = start + timedelta(days=i)
        days_ahead = (d - today).days
        rate = 4499 + (900 if days_ahead <= 0 else (450 if days_ahead == 1 else 0)) + ((hash(str(d)) % 5) * 120)
        q = urlencode({
            "source": source,
            "destination": destination,
            "departure_date": d.isoformat(),
            "passengers": passengers,
            "travel_class": travel_class,
            "fare_type": fare_type,
        })
        ribbon.append({
            "date": d,
            "is_selected": (d == dep_date),
            "fare": rate,
            "url": f"/search/?{q}",
        })
    return ribbon


def _flight_params():
    try:
        number = request.args["number"].upper()
        dep_date = date.fromisoformat(request.args["date"])
        pax = max(1, min(9, int(request.args.get("pax", 1))))
        travel_class = request.args.get("travel_class", "economy")
        fare_type = request.args.get("fare_type", "regular")
    except (KeyError, ValueError):
        return None
    raw_source = request.args.get("source", "").strip()
    raw_dest = request.args.get("dest", "") or request.args.get("destination", "")
    raw_dest = raw_dest.strip()
    source_code = parse_code(raw_source) or (raw_source.upper() if len(raw_source) == 3 else None)
    dest_code = parse_code(raw_dest) or (raw_dest.upper() if len(raw_dest) == 3 else None)
    return {
        "number": number,
        "date": dep_date,
        "source": source_code,
        "dest": dest_code,
        "pax": pax,
        "ret": request.args.get("ret", ""),
        "travel_class": travel_class,
        "fare_type": fare_type,
    }


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@app.route("/")
def home():
    form = FlightSearchForm(initial={"departure_date": date.today(), "passengers": 1})
    return render_template("flights/home.html", **_ctx(form=form, today=date.today()))


@app.route("/search/", methods=["GET"])
@app.route("/search", methods=["GET"])
def search():
    form = FlightSearchForm(data=request.args)
    if not form.is_valid():
        return render_template("flights/home.html", **_ctx(form=form, today=date.today())), 400

    d = form.cleaned_data
    error = None
    flights = []
    fetched_at = None
    hidden = 0
    show_all = request.args.get("show_all") == "1"

    try:
        flights, fetched_at, hidden = _run_search(form, show_all=show_all)
    except FlightAPIError:
        error = API_DOWN_MESSAGE

    date_ribbon = _build_date_ribbon(
        d["source"], d["destination"], d["departure_date"], d["passengers"],
        travel_class=d.get("travel_class", "economy"), fare_type=d.get("fare_type", "regular")
    )
    ctx = _ctx(
        form=form,
        flights=flights,
        error=error,
        hidden=hidden,
        show_all=show_all,
        fetched_at=fetched_at,
        now=datetime.now(),
        src_label=label(d["source"]),
        dst_label=label(d["destination"]),
        query=_query(d),
        pax=d["passengers"],
        departure_date=d["departure_date"],
        return_date=d.get("return_date"),
        api_query=_query(d, **({"show_all": "1"} if show_all else {})),
        date_ribbon=date_ribbon,
    )
    return render_template("flights/results.html", **ctx)


@app.route("/api/flights/", methods=["GET"])
@app.route("/api/flights", methods=["GET"])
def api_search():
    form = FlightSearchForm(data=request.args)
    if not form.is_valid():
        return jsonify({"error": "Invalid search."}), 400

    try:
        flights, fetched_at, hidden = _run_search(
            form, force=request.args.get("force") == "1",
            show_all=request.args.get("show_all") == "1"
        )
    except FlightAPIError:
        return jsonify({"error": API_DOWN_MESSAGE}), 503

    d = form.cleaned_data
    html = render_template(
        "flights/_results_list.html",
        flights=flights,
        query=_query(d),
        pax=d["passengers"],
        hidden=hidden,
    )
    updated = _parse_dt(fetched_at) or datetime.now()
    return jsonify({
        "html": html,
        "count": len(flights),
        "hidden": hidden,
        "last_updated": updated.strftime("%H:%M:%S"),
    })


@app.route("/flight/", methods=["GET"])
@app.route("/flight", methods=["GET"])
def flight_detail():
    p = _flight_params()
    if not p:
        return redirect(url_for("home"))
    flight, error = None, None
    travel_class = p.get("travel_class", "economy")
    fare_type = p.get("fare_type", "regular")

    try:
        flight = get_flight_details(
            p["number"], p["date"], source=p["source"], destination=p["dest"],
            travel_class=travel_class, fare_type=fare_type, force=request.args.get("force") == "1"
        )
        if not flight:
            error = "The live API has no record of this flight for that date."
    except FlightAPIError:
        error = API_DOWN_MESSAGE

    book_qs = urlencode({
        "number": p["number"],
        "date": p["date"].isoformat(),
        "source": p["source"] or "",
        "dest": p["dest"] or "",
        "pax": p["pax"],
        "ret": p["ret"],
        "travel_class": travel_class,
        "fare_type": fare_type,
    })
    telemetry = compute_live_flight_telemetry(flight) if flight else None
    return render_template(
        "flights/detail.html",
        **_ctx(
            flight=flight,
            telemetry=telemetry,
            error=error,
            pax=p["pax"],
            travel_class=travel_class,
            fare_type=fare_type,
            book_qs=book_qs,
        )
    )


@app.route("/api/flight/tracking", methods=["GET"])
def api_flight_tracking():
    p = _flight_params()
    if not p:
        raw_source = request.args.get("source", "").strip()
        raw_dest = request.args.get("dest", "") or request.args.get("destination", "").strip()
        source_code = parse_code(raw_source) or (raw_source.upper() if len(raw_source) == 3 else "DEL")
        dest_code = parse_code(raw_dest) or (raw_dest.upper() if len(raw_dest) == 3 else "BOM")
        date_str = request.args.get("date", "")
        try:
            dep_date = date.fromisoformat(date_str) if date_str else date.today()
        except Exception:
            dep_date = date.today()
        p = {
            "number": request.args.get("number", "AV101").upper(),
            "date": dep_date,
            "source": source_code,
            "dest": dest_code,
            "pax": 1,
            "travel_class": request.args.get("travel_class", "economy"),
            "fare_type": request.args.get("fare_type", "regular"),
        }

    flight = None
    try:
        flight = get_flight_details(
            p["number"], p["date"], source=p["source"], destination=p["dest"],
            travel_class=p.get("travel_class", "economy"), fare_type=p.get("fare_type", "regular")
        )
    except Exception:
        pass

    if not flight:
        is_future = hasattr(p["date"], "isoformat") and p["date"] > date.today()
        flight = {
            "flight_number": p["number"] or "AV101",
            "airline_name": "Airvoyage",
            "dep_iata": p["source"] or "DEL",
            "arr_iata": p["dest"] or "BOM",
            "dep_date": p["date"].isoformat() if hasattr(p["date"], "isoformat") else str(p["date"]),
            "status": "Scheduled" if is_future else "In Flight",
        }

    telemetry = compute_live_flight_telemetry(flight)
    return jsonify(telemetry)


@app.route("/book/start/", methods=["GET"])
@app.route("/book/start", methods=["GET"])
@login_required
def book_start():
    p = _flight_params()
    if not p:
        return redirect(url_for("home"))
    travel_class = p.get("travel_class", "economy")
    fare_type = p.get("fare_type", "regular")

    try:
        flight = get_flight_details(
            p["number"], p["date"], source=p["source"], destination=p["dest"],
            travel_class=travel_class, fare_type=fare_type
        )
    except FlightAPIError:
        flash(API_DOWN_MESSAGE, "error")
        return redirect(f"/flight/?{request.query_string.decode('utf-8')}")

    if not flight:
        flash("That flight could not be found in the live data. Please search again.", "error")
        return redirect(url_for("home"))

    session["selected_flight"] = {
        "flight": flight,
        "pax": p["pax"],
        "return_date": p["ret"],
        "travel_class": travel_class,
        "fare_type": fare_type,
    }
    return redirect(url_for("passengers"))


@app.route("/book/passengers/", methods=["GET", "POST"])
@app.route("/book/passengers", methods=["GET", "POST"])
@login_required
def passengers():
    sel = session.get("selected_flight")
    if not sel:
        flash("Pick a flight first.", "info")
        return redirect(url_for("home"))

    flight, pax = sel["flight"], sel["pax"]
    travel_class = sel.get("travel_class", "economy")
    dep_date_val = date.fromisoformat(flight["dep_date"])
    is_intl = is_international_route(flight["dep_iata"], flight["arr_iata"])

    seat_map = get_flight_seat_map(flight["flight_number"], dep_date_val, travel_class=travel_class)
    booked_set = set(seat_map["booked_seats"])
    available_list = seat_map["available_seats"]

    if request.method == "POST":
        contact = ContactForm(data=request.form)
        formset = PassengerFormSet(data=request.form, pax_count=pax, is_international=is_intl, prefix="p")

        if contact.is_valid() and formset.is_valid():
            passengers_data = []
            used_seats = set()
            id_seed = abs(hash(flight["flight_number"])) % 1000

            for idx, f in enumerate(formset):
                chosen_seat = (f.cleaned_data.get("seat_number") or "").strip().upper()
                if not chosen_seat or chosen_seat in booked_set or chosen_seat in used_seats:
                    candidate = next((s for s in available_list if s not in used_seats and s not in booked_set), None)
                    chosen_seat = candidate or f"3{idx+1}A"

                used_seats.add(chosen_seat)
                zone = calculate_boarding_zone(chosen_seat)
                seq = f"{(idx + 1 + id_seed) % 180 + 1:04d}"

                pax_dict = dict(f.cleaned_data)
                pax_dict["seat_number"] = chosen_seat
                pax_dict["boarding_zone"] = zone
                pax_dict["sequence_number"] = seq
                passengers_data.append(pax_dict)

            booking = create_booking(
                user=current_user,
                flight=flight,
                pax_count=pax,
                contact_email=contact.cleaned_data["contact_email"],
                contact_phone=contact.cleaned_data["contact_phone"],
                passengers_data=passengers_data,
                return_date_val=sel.get("return_date"),
                travel_class=travel_class,
            )

            session.pop("selected_flight", None)
            return redirect(url_for("confirmation", reference=booking.reference))
    else:
        profile = current_user.profile
        contact = ContactForm(initial={
            "contact_email": current_user.email,
            "contact_phone": profile.phone or "",
        })

        assigned_defaults = []
        used_initial = set()
        for _ in range(pax):
            candidate = next((s for s in available_list if s not in used_initial), "30A")
            used_initial.add(candidate)
            assigned_defaults.append(candidate)

        initial_pax = [{
            "first_name": current_user.first_name,
            "last_name": current_user.last_name,
            "date_of_birth": profile.date_of_birth,
            "gender": profile.gender or "M",
            "nationality": profile.nationality or "India",
            "passport_number": profile.passport_number or "",
            "passport_expiry": profile.passport_expiry,
            "seat_number": assigned_defaults[0] if assigned_defaults else "30A",
        }]
        for idx in range(1, pax):
            initial_pax.append({
                "nationality": "India",
                "seat_number": assigned_defaults[idx] if idx < len(assigned_defaults) else f"3{idx}B",
            })
        formset = PassengerFormSet(initial=initial_pax, pax_count=pax, is_international=is_intl, prefix="p")

    fare_type = sel.get("fare_type", "regular")
    return render_template("flights/passengers.html", **_ctx(
        flight=flight,
        pax=pax,
        contact=contact,
        formset=formset,
        is_international=is_intl,
        travel_class=travel_class,
        fare_type=fare_type,
        seat_map=seat_map,
        seat_map_json=json.dumps(seat_map),
    ))


@app.route("/booking/<reference>/")
@app.route("/booking/<reference>")
@login_required
def confirmation(reference):
    booking = get_booking_by_reference(reference, current_user)
    if not booking:
        flash("Booking not found.", "error")
        return redirect(url_for("my_bookings"))

    cfg = resolve_airline_profile(booking.flight_number, booking.airline_name)
    return_qs = ""
    if booking.return_date:
        ret_str = booking.return_date.isoformat() if hasattr(booking.return_date, "isoformat") else str(booking.return_date)
        return_qs = urlencode({
            "source": booking.arr_iata,
            "destination": booking.dep_iata,
            "departure_date": ret_str,
            "passengers": booking.passenger_count,
            "travel_class": booking.travel_class,
        })
    cancellation_policy = evaluate_cancellation_policy(booking, is_member=True)
    return render_template(
        "flights/confirmation.html",
        **_ctx(booking=booking, cfg=cfg, return_qs=return_qs, cancellation_policy=cancellation_policy)
    )


@app.route("/booking/<reference>/boarding-pass/pdf/")
@app.route("/booking/<reference>/boarding-pass/pdf")
@login_required
def boarding_pass_pdf(reference):
    booking = get_booking_by_reference(reference, current_user)
    if not booking:
        flash("Booking not found.", "error")
        return redirect(url_for("my_bookings"))

    pdf_buffer = generate_boarding_passes_pdf(booking)
    filename = f"BoardingPass_{booking.reference}_{booking.flight_number.replace(' ', '')}.pdf"
    inline = request.args.get("inline") == "1"
    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=not inline,
        download_name=filename,
    )


@app.route("/booking/<reference>/boarding-pass/")
@app.route("/booking/<reference>/boarding-pass")
@login_required
def boarding_pass_view(reference):
    booking = get_booking_by_reference(reference, current_user)
    if not booking:
        flash("Booking not found.", "error")
        return redirect(url_for("my_bookings"))

    cfg = resolve_airline_profile(booking.flight_number, booking.airline_name)
    passengers_list = list(booking.passengers)
    if not passengers_list:
        from flights.flask_models import Passenger
        passengers_list = [Passenger({
            "first_name": current_user.first_name or "PRIMARY",
            "last_name": current_user.last_name or "PASSENGER",
            "gender": "M",
            "seat_number": "8A",
            "boarding_zone": "Zone 3",
            "sequence_number": "0026",
        })]

    sched_dep = _parse_dt(booking.scheduled_departure)
    if sched_dep:
        boarding_time = (sched_dep - timedelta(minutes=45)).strftime("%H:%M hrs")
        dep_time = sched_dep.strftime("%H:%M")
    else:
        boarding_time = "07:45 hrs"
        dep_time = "08:30"

    raw_dep_term = str(booking.dep_terminal or "1").strip()
    dep_term_num = raw_dep_term.lstrip("Tt").strip() or "1"
    dep_term = f"T{dep_term_num}"

    snapshot = booking.snapshot if isinstance(booking.snapshot, dict) else {}
    raw_arr_term = str(snapshot.get("arr_terminal") or "2").strip()
    arr_term_num = raw_arr_term.lstrip("Tt").strip() or "2"
    arr_term = f"T{arr_term_num}"

    pax_cards = []
    for idx, p in enumerate(passengers_list):
        seat = p.seat_number or f"{8 + idx}{['A','B','C','D','E','F'][idx % 6]}"
        zone = p.boarding_zone or f"Zone {1 if idx == 0 else 3}"
        seq = p.sequence_number or f"{(idx + 1) * 26:04d}"
        pax_name = p.formatted_name

        ref_str = (booking.reference or "").ljust(7)
        flt_str = (booking.flight_number or "").replace(" ", "")
        qr_payload = (
            f"M1{pax_name[:20].ljust(20)} E{ref_str} "
            f"{booking.dep_iata or ''}{booking.arr_iata or ''}{flt_str} "
            f"{seat.ljust(4)}{seq.ljust(4)}"
        )
        small_qr_payload = f"M1{pax_name[:15]} {booking.reference} {seat}"

        qr_data_uri = generate_qr_data_uri(qr_payload, box_size=4)
        small_qr_data_uri = generate_qr_data_uri(small_qr_payload, box_size=3)

        pax_cards.append({
            "pax": p,
            "name": pax_name,
            "seat": seat,
            "zone": zone,
            "seq": seq,
            "qr_data_uri": qr_data_uri,
            "small_qr_data_uri": small_qr_data_uri,
        })

    return render_template(
        "flights/boarding_pass.html",
        **_ctx(
            booking=booking,
            cfg=cfg,
            pax_cards=pax_cards,
            dep_term=dep_term,
            dep_term_num=dep_term_num,
            arr_term=arr_term,
            arr_term_num=arr_term_num,
            boarding_time=boarding_time,
            dep_time=dep_time,
        )
    )


@app.route("/my-bookings/")
@app.route("/my-bookings")
@login_required
def my_bookings():
    bookings = get_user_bookings(current_user)
    for b in bookings:
        b.cancellation_policy = evaluate_cancellation_policy(b, is_member=True)
    return render_template("flights/my_bookings.html", **_ctx(bookings=bookings, today=date.today()))


@app.route("/profile/")
@app.route("/profile")
@login_required
def profile():
    user_prof = current_user.profile
    user_bookings = get_user_bookings(current_user)
    today = date.today()

    upcoming_bookings = []
    past_bookings = []
    for b in user_bookings:
        b_date = b.dep_date.date() if isinstance(b.dep_date, datetime) else b.dep_date
        if b_date and b_date >= today:
            upcoming_bookings.append(b)
        else:
            past_bookings.append(b)

    return render_template(
        "flights/profile.html",
        **_ctx(
            profile=user_prof,
            user=current_user,
            total_bookings=len(user_bookings),
            upcoming_count=len(upcoming_bookings),
            past_count=len(past_bookings),
            recent_bookings=user_bookings[:5],
            today=today,
        )
    )


@app.route("/profile/edit/", methods=["GET", "POST"])
@app.route("/profile/edit", methods=["GET", "POST"])
@login_required
def profile_edit():
    user_prof = current_user.profile
    if request.method == "POST":
        form = UserProfileEditForm(data=request.form, user=current_user, profile=user_prof)
        if form.is_valid():
            update_user_profile(current_user, form.cleaned_data)
            flash("Your profile has been updated successfully!", "success")
            return redirect(url_for("profile"))
    else:
        form = UserProfileEditForm(user=current_user, profile=user_prof)

    return render_template("flights/profile_edit.html", **_ctx(form=form, profile=user_prof))


@app.route("/airlines/")
@app.route("/airlines")
def airlines_directory():
    return render_template(
        "flights/airlines_directory.html",
        **_ctx(
            domestic_only=DOMESTIC_ONLY_AIRLINES,
            both_domestic_intl=BOTH_DOMESTIC_INTL_AIRLINES,
            foreign_by_region=FOREIGN_AIRLINES_BY_REGION,
            total_airlines_count=len(ALL_AIRLINES),
        )
    )


@app.route("/login/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    next_url = request.args.get("next") or request.form.get("next") or ""
    form = LoginForm(data=request.form if request.method == "POST" else None)

    if request.method == "POST" and form.is_valid():
        try:
            user = get_user_by_username(form.cleaned_data["username"])
            if user and user.check_password(form.cleaned_data["password"]):
                login_user(user)
                flash("Logged in successfully!", "success")
                if next_url and next_url.startswith("/"):
                    return redirect(next_url)
                return redirect(url_for("home"))
            else:
                form.non_field_errors.append("Please enter a correct username and password. Note that both fields may be case-sensitive.")
        except Exception as e:
            flash(f"Database error: {e}. Please ensure your IP is whitelisted in MongoDB Atlas.", "error")

    return render_template("registration/login.html", form=form, next=next_url)


@app.route("/logout/", methods=["GET", "POST"])
@app.route("/logout", methods=["GET", "POST"])
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("home"))


@app.route("/register/", methods=["GET", "POST"])
@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    next_url = request.args.get("next") or request.form.get("next") or ""
    form = RegisterForm(data=request.form if request.method == "POST" else None)

    if request.method == "POST" and form.is_valid():
        try:
            user = create_user(
                username=form.cleaned_data["username"],
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password"],
            )
            login_user(user)
            flash("Your account has been created successfully!", "success")
            if next_url and next_url.startswith("/"):
                return redirect(next_url)
            return redirect(url_for("home"))
        except Exception as e:
            flash(f"Database connection error: {e}. Please check MongoDB Atlas Network Access (IP Whitelist).", "error")

    return render_template("registration/register.html", form=form, next=next_url)


# --------------------------------------------------------------------------
# Architecture & Concepts Documentation Routes
# --------------------------------------------------------------------------
@app.route("/concepts/", methods=["GET"])
@app.route("/concepts", methods=["GET"])
@app.route("/docs/", methods=["GET"])
@app.route("/docs", methods=["GET"])
def concepts():
    """Renders the comprehensive, interactive concepts and system architecture documentation."""
    mongo_status = check_mongo_connection()
    provider = os.environ.get("FLIGHT_API_PROVIDER", "ixigo")
    cache_ttl = os.environ.get("FLIGHT_API_CACHE_SECONDS", "30")
    use_mongo = os.environ.get("USE_MONGODB", "1").lower() in ("1", "true", "yes")

    return render_template(
        "concepts.html",
        **_ctx(
            mongo_status=mongo_status,
            active_provider=provider,
            cache_ttl=cache_ttl,
            use_mongo=use_mongo,
            current_time=datetime.now(timezone.utc),
        ),
    )


@app.route("/api/concepts/mongodb-schema", methods=["GET"])
@app.route("/api/concepts/schema", methods=["GET"])
def api_concepts_schema():
    """Returns sample live MongoDB Embedded Document schema and comparison with Relational."""
    sample_booking_doc = {
        "_id": "6704b2a38c11e7215b2e3f89",
        "reference": "AV-7F9B10",
        "booking_status": "confirmed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "contact": {
            "email": "traveler@airvoyage.com",
            "phone": "+91 98401 23456",
        },
        "flight_details": {
            "flight_number": "6E 2145",
            "airline_name": "IndiGo",
            "aircraft": "Airbus A321neo",
            "travel_class": "economy",
            "status_at_booking": "On Time",
            "api_provider": os.environ.get("FLIGHT_API_PROVIDER", "ixigo"),
        },
        "route": {
            "origin": {
                "iata": "DEL",
                "airport": "Indira Gandhi International Airport",
                "terminal": "T3",
                "gate": "41A",
                "date": date.today().isoformat(),
                "scheduled_time": "08:15",
            },
            "destination": {
                "iata": "BOM",
                "airport": "Chhatrapati Shivaji Maharaj International",
                "scheduled_time": "10:35",
            },
            "stops": "Non-stop",
            "is_connecting": False,
        },
        "passenger_count": 2,
        "passengers": [
            {
                "_id": "6704b2a38c11e7215b2e3f8a",
                "first_name": "Nithish",
                "last_name": "Sankaranarayanan",
                "formatted_name": "SANKARANARAYANAN/NITHISH/MR",
                "date_of_birth": "2003-02-19",
                "gender": "M",
                "nationality": "India",
                "id_number": "2410-4051-9988",
                "passport_number": "Z8912340",
                "seat_number": "12A",
                "boarding_zone": "Zone 2",
                "sequence_number": "0018",
            },
            {
                "_id": "6704b2a38c11e7215b2e3f8b",
                "first_name": "Aarav",
                "last_name": "Sharma",
                "formatted_name": "SHARMA/AARAV/MR",
                "date_of_birth": "2002-09-14",
                "gender": "M",
                "nationality": "India",
                "id_number": "1122-3344-5566",
                "passport_number": "Z7834190",
                "seat_number": "12B",
                "boarding_zone": "Zone 2",
                "sequence_number": "0019",
            },
        ],
        "pattern_type": "MongoDB Embedded Document (Denormalized Subdocuments)",
        "benefits": [
            "Atomic single-document ACID transactions without two-phase commit",
            "Eliminates N+1 query overhead (0 JOIN round-trips)",
            "Self-contained flight and passenger snapshot immutability",
            "Native JSON/BSON querying of nested passengers and route properties",
        ],
    }

    relational_comparison = {
        "relational_approach": {
            "tables": [
                {
                    "table": "flights_booking",
                    "columns": ["id (PK)", "user_id (FK)", "reference", "airline_name", "flight_number", "dep_iata", "arr_iata", "created_at"],
                },
                {
                    "table": "flights_passenger",
                    "columns": ["id (PK)", "booking_id (FK -> flights_booking.id)", "first_name", "last_name", "seat_number", "boarding_zone"],
                },
            ],
            "query_complexity": "Requires SQL JOIN (SELECT * FROM flights_booking b JOIN flights_passenger p ON p.booking_id = b.id) or 2 round-trips.",
            "join_cost": "High with multi-table indexing and relational locks across tables.",
        },
        "mongodb_embedded_approach": {
            "collection": "flights_booking",
            "structure": "Single document containing an array of passenger subdocuments + route subdocument.",
            "query_complexity": "db.flights_booking.findOne({reference: 'AV-7F9B10'}) — retrieves booking and all passengers in a single disk read.",
            "join_cost": "Zero (0 joins, 0 latency overhead).",
        },
    }

    return jsonify({
        "success": True,
        "embedded_document": sample_booking_doc,
        "comparison": relational_comparison,
    })


@app.route("/api/concepts/system-status", methods=["GET"])
def api_concepts_system_status():
    """Live diagnostic check of MongoDB Atlas, SQLite, active API provider, and system components."""
    conn_info = check_mongo_connection()
    is_available = is_mongo_available(force_refresh=True)

    return jsonify({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": {
            "mongo_connected": is_available,
            "engine_in_use": "MongoDB Atlas (NoSQL Embedded Docs)" if is_available else "SQLite Fallback (Relational db.sqlite3)",
            "details": conn_info,
        },
        "flight_api": {
            "provider": os.environ.get("FLIGHT_API_PROVIDER", "ixigo"),
            "cache_ttl_seconds": int(os.environ.get("FLIGHT_API_CACHE_SECONDS", "30")),
            "auto_refresh_interval": int(os.environ.get("FLIGHT_AUTO_REFRESH_SECONDS", "60")),
        },
        "features": {
            "embedded_documents_active": True,
            "dual_database_fallback": True,
            "boarding_pass_qr_generation": True,
            "seat_map_matrix": True,
        },
    })


@app.route("/api/booking/<reference>/embedded-json", methods=["GET"])
def api_booking_embedded_json(reference):
    """Returns the MongoDB Embedded Document representation of a confirmed booking."""
    b = get_booking_by_reference(reference, user=current_user if current_user.is_authenticated else None)
    if not b:
        return jsonify({"error": "Booking not found"}), 404
    return jsonify({
        "success": True,
        "booking": b.to_embedded_document()
    })


# --------------------------------------------------------------------------
# Cancel Ticket & Booking Management
# --------------------------------------------------------------------------
@app.route("/booking/<reference>/cancel", methods=["POST"])
@app.route("/booking/<reference>/cancel/", methods=["POST"])
def cancel_booking(reference):
    """Cancels a booking by reference with instant refund processing."""
    user = current_user if current_user.is_authenticated else None
    booking = get_booking_by_reference(reference, user=user)
    if not booking:
        flash(f"Booking {reference} could not be found.", "error")
        return redirect(url_for("my_bookings") if current_user.is_authenticated else url_for("home"))

    if booking.booking_status == "cancelled":
        flash(f"Booking {reference} is already cancelled.", "info")
        return redirect(url_for("confirmation", reference=reference))

    policy = evaluate_cancellation_policy(booking, is_member=True)
    success = cancel_booking_by_reference(reference, user=user)
    if success:
        if policy.get("dgca_eligible"):
            flash(
                f"Ticket {reference} ({booking.flight_number}) has been cancelled successfully under DGCA 2026 Mandate "
                f"(48-hr look-in window / {policy['actual_lead_days']}d departure lead). 100% full refund with ₹0 cancellation fee "
                f"initiated to original payment method.",
                "success"
            )
        else:
            flash(
                f"Ticket {reference} ({booking.flight_number}) has been cancelled successfully under Regular Member "
                f"zero-cancellation protection. 100% full refund initiated to original payment method.",
                "success"
            )
    else:
        flash(f"Could not cancel booking {reference}. Please contact customer support.", "error")

    return redirect(url_for("confirmation", reference=reference))


# --------------------------------------------------------------------------
# Regular Membership Offer & Live Passenger Lookup
# --------------------------------------------------------------------------
@app.route("/membership-offers/", methods=["GET"])
@app.route("/membership-offers", methods=["GET"])
@app.route("/offers/", methods=["GET"])
@app.route("/offers", methods=["GET"])
def membership_offers():
    """Showcases the Regular Membership Offer and allows fetching passenger details from MongoDB."""
    search_q = request.args.get("q", "").strip()
    searched_member = find_member_details(search_q) if search_q else None
    all_members = get_all_members()

    return render_template(
        "flights/membership_offers.html",
        **_ctx(
            search_q=search_q,
            searched_member=searched_member,
            all_members=all_members,
        ),
    )


@app.route("/api/membership/lookup", methods=["GET", "POST"])
def api_membership_lookup():
    """API endpoint to fetch passenger details and regular membership offer from MongoDB."""
    q = request.args.get("q") or request.form.get("q") or ""
    if not q and request.is_json:
        q = request.json.get("q", "")
    if not q:
        return jsonify({"success": False, "error": "Query required (Name, Email, Phone, or Booking ID)"}), 400

    member = find_member_details(q.strip())
    if not member:
        return jsonify({"success": True, "found": False, "message": f"No passenger record found matching '{q}'"}), 200

    return jsonify({
        "success": True,
        "found": True,
        "member": member,
    })


@app.route("/api/membership/all-members", methods=["GET"])
def api_membership_all_members():
    """API returning all passengers inserted in MongoDB with their membership offer."""
    members = get_all_members()
    return jsonify({
        "success": True,
        "count": len(members),
        "members": members,
    })
@app.route("/health")
def health_check():
    """Health check endpoint for cloud deployment platforms (Render, Railway, etc.)."""
    return jsonify({
        "status": "healthy",
        "service": "Airvoyage Flight Portal",
        "mongo_available": is_mongo_available(),
    }), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true", "yes")
    print(f"Starting Airvoyage Flight Portal on http://127.0.0.1:{port} (debug={debug})")
    app.run(host="0.0.0.0", port=port, debug=debug)
