import json
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.forms import formset_factory
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET, require_POST

from .forms import ContactForm, FlightSearchForm, PassengerForm, RegisterForm, UserProfileEditForm
from .models import Booking, Passenger, UserProfile
from .services.airports import AIRPORTS, is_international_route, label, parse_code
from .services.boarding_pass import (
    generate_boarding_passes_pdf,
    generate_qr_data_uri,
    resolve_airline_profile,
)
from .services.flight_api import FlightAPIError, get_flight_details, search_live_flights
from .services.seatmap import calculate_boarding_zone, get_flight_seat_map

API_DOWN_MESSAGE = ("Unable to retrieve live flight information. "
                    "Please try again in a few moments.")


def _ctx(**extra):
    return {"airports": AIRPORTS, "refresh_seconds": settings.FLIGHT_AUTO_REFRESH_SECONDS, **extra}


def _recent_enough(flight, now):
    """True unless the flight left more than 2h ago (based on API timestamps)."""
    dt = parse_datetime(flight.get("estimated_departure") or flight.get("scheduled_departure") or "")
    return dt is None or dt >= now - timedelta(hours=2)


def _run_search(form, force=False, show_all=False):
    """Call the live API; returns (flights, fetched_at, hidden_count)."""
    d = form.cleaned_data
    travel_class = d.get("travel_class", "economy")
    fare_type = d.get("fare_type", "regular")
    result = search_live_flights(d["source"], d["destination"], d["departure_date"], travel_class=travel_class, fare_type=fare_type, force=force)
    flights, now = result["flights"], timezone.now()
    hidden = 0
    if d["departure_date"] == timezone.localdate() and not show_all:
        kept = [f for f in flights if _recent_enough(f, now)]
        hidden, flights = len(flights) - len(kept), kept
    return flights, result["fetched_at"], hidden


def _query(form_data, **extra):
    q = {"source": form_data["source"], "destination": form_data["destination"],
         "departure_date": form_data["departure_date"].isoformat(),
         "passengers": form_data["passengers"],
         "travel_class": form_data.get("travel_class", "economy"),
         "fare_type": form_data.get("fare_type", "regular"),
         **extra}
    if form_data.get("return_date"):
        q["return_date"] = form_data["return_date"].isoformat()
    return urlencode(q)


def home(request):
    form = FlightSearchForm(initial={"departure_date": timezone.localdate(), "passengers": 1})
    return render(request, "flights/home.html", _ctx(form=form, today=timezone.localdate()))


def _build_date_ribbon(source, destination, dep_date, passengers, travel_class="economy", fare_type="regular"):
    today = timezone.localdate()
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


@require_GET
def search(request):
    form = FlightSearchForm(request.GET)
    if not form.is_valid():
        return render(request, "flights/home.html", _ctx(form=form, today=timezone.localdate()), status=400)
    d, error, flights, fetched_at, hidden = form.cleaned_data, None, [], None, 0
    show_all = request.GET.get("show_all") == "1"
    try:
        flights, fetched_at, hidden = _run_search(form, show_all=show_all)
    except FlightAPIError:
        error = API_DOWN_MESSAGE
    date_ribbon = _build_date_ribbon(
        d["source"], d["destination"], d["departure_date"], d["passengers"],
        travel_class=d.get("travel_class", "economy"), fare_type=d.get("fare_type", "regular")
    )
    ctx = _ctx(
        form=form, flights=flights, error=error, hidden=hidden, show_all=show_all,
        fetched_at=fetched_at, now=timezone.now(), src_label=label(d["source"]), dst_label=label(d["destination"]),
        query=_query(d), pax=d["passengers"], departure_date=d["departure_date"], return_date=d.get("return_date"),
        api_query=_query(d, **({"show_all": "1"} if show_all else {})), date_ribbon=date_ribbon,
    )
    return render(request, "flights/results.html", ctx)


@require_GET
def api_search(request):
    """AJAX endpoint: returns the re-rendered results list so the page never reloads."""
    form = FlightSearchForm(request.GET)
    if not form.is_valid():
        return JsonResponse({"error": "Invalid search."}, status=400)
    try:
        flights, fetched_at, hidden = _run_search(form, force=request.GET.get("force") == "1",
                                                 show_all=request.GET.get("show_all") == "1")
    except FlightAPIError:
        return JsonResponse({"error": API_DOWN_MESSAGE}, status=503)
    d = form.cleaned_data
    html = render_to_string("flights/_results_list.html",
                            {"flights": flights, "query": _query(d), "pax": d["passengers"], "hidden": hidden}, request)
    updated = parse_datetime(fetched_at)
    return JsonResponse({"html": html, "count": len(flights), "hidden": hidden,
                         "last_updated": timezone.localtime(updated).strftime("%H:%M:%S")})


def _flight_params(request):
    try:
        number = request.GET["number"].upper()
        dep_date = date.fromisoformat(request.GET["date"])
        pax = max(1, min(9, int(request.GET.get("pax", 1))))
        travel_class = request.GET.get("travel_class", "economy")
        fare_type = request.GET.get("fare_type", "regular")
    except (KeyError, ValueError):
        return None
    raw_source = request.GET.get("source", "").strip()
    raw_dest = request.GET.get("dest", "") or request.GET.get("destination", "")
    raw_dest = raw_dest.strip()
    source_code = parse_code(raw_source) or (raw_source.upper() if raw_source else None)
    dest_code = parse_code(raw_dest) or (raw_dest.upper() if raw_dest else None)
    return {
        "number": number,
        "date": dep_date,
        "source": source_code,
        "dest": dest_code,
        "pax": pax,
        "ret": request.GET.get("ret", ""),
        "travel_class": travel_class,
        "fare_type": fare_type,
    }


@require_GET
def flight_detail(request):
    p = _flight_params(request)
    if not p:
        return redirect("home")
    flight, error = None, None
    travel_class = p.get("travel_class", "economy")
    fare_type = p.get("fare_type", "regular")
    try:
        flight = get_flight_details(
            p["number"], p["date"], source=p["source"], destination=p["dest"],
            travel_class=travel_class, fare_type=fare_type, force=request.GET.get("force") == "1"
        )
        if not flight:
            error = "The live API has no record of this flight for that date."
    except FlightAPIError:
        error = API_DOWN_MESSAGE
    book_qs = urlencode({"number": p["number"], "date": p["date"].isoformat(), "source": p["source"] or "",
                         "dest": p["dest"] or "", "pax": p["pax"], "ret": p["ret"], "travel_class": travel_class,
                         "fare_type": fare_type})
    return render(request, "flights/detail.html", _ctx(flight=flight, error=error, pax=p["pax"], travel_class=travel_class, fare_type=fare_type, book_qs=book_qs))


@login_required
def book_start(request):
    """Re-fetches the flight server-side (never trusts client-supplied flight data) and stores it in the session."""
    p = _flight_params(request)
    if not p:
        return redirect("home")
    travel_class = p.get("travel_class", "economy")
    fare_type = p.get("fare_type", "regular")
    try:
        flight = get_flight_details(
            p["number"], p["date"], source=p["source"], destination=p["dest"],
            travel_class=travel_class, fare_type=fare_type
        )
    except FlightAPIError:
        messages.error(request, API_DOWN_MESSAGE)
        return redirect(f"/flight/?{request.META['QUERY_STRING']}")
    if not flight:
        messages.error(request, "That flight could not be found in the live data. Please search again.")
        return redirect("home")
    request.session["selected_flight"] = {
        "flight": flight,
        "pax": p["pax"],
        "return_date": p["ret"],
        "travel_class": travel_class,
        "fare_type": fare_type,
    }
    return redirect("passengers")


@login_required
def passengers(request):
    sel = request.session.get("selected_flight")
    if not sel:
        messages.info(request, "Pick a flight first.")
        return redirect("home")
    flight, pax = sel["flight"], sel["pax"]
    travel_class = sel.get("travel_class", "economy")
    dep_date_val = date.fromisoformat(flight["dep_date"])
    is_intl = is_international_route(flight["dep_iata"], flight["arr_iata"])
    PassengerFormSet = formset_factory(PassengerForm, extra=0, min_num=pax, max_num=pax, validate_min=True, validate_max=True)

    # Fetch complete seat map with real MongoDB occupancy and baseline occupancy
    seat_map = get_flight_seat_map(flight["flight_number"], dep_date_val, travel_class=travel_class)
    booked_set = set(seat_map["booked_seats"])
    available_list = seat_map["available_seats"]

    if request.method == "POST":
        contact = ContactForm(request.POST)
        formset = PassengerFormSet(request.POST, form_kwargs={"is_international": is_intl}, prefix="p")
        if contact.is_valid() and formset.is_valid():
            with transaction.atomic():
                booking = Booking.objects.create(
                    user=request.user, passenger_count=pax,
                    return_date=date.fromisoformat(sel["return_date"]) if sel.get("return_date") else None,
                    contact_email=contact.cleaned_data["contact_email"], contact_phone=contact.cleaned_data["contact_phone"],
                    api_provider=flight["provider"], airline_name=flight["airline_name"], flight_number=flight["flight_number"],
                    dep_iata=flight["dep_iata"], dep_airport=flight["dep_airport"], arr_iata=flight["arr_iata"],
                    arr_airport=flight["arr_airport"], dep_date=dep_date_val,
                    scheduled_departure=parse_datetime(flight["scheduled_departure"] or ""),
                    scheduled_arrival=parse_datetime(flight["scheduled_arrival"] or ""),
                    dep_terminal=flight["dep_terminal"], dep_gate=flight["dep_gate"], aircraft=flight["aircraft"],
                    status_at_booking=flight["status"], snapshot=flight,
                    travel_class=travel_class,
                    is_connecting=flight.get("is_connecting", False),
                    stops_info=flight.get("stops", "Non-stop"),
                )
                pax_objs = []
                id_seed = abs(hash(str(booking.reference or booking.id))) % 1000
                used_seats = set()

                for idx, f in enumerate(formset):
                    chosen_seat = (f.cleaned_data.get("seat_number") or "").strip().upper()
                    # If seat not chosen, already booked, or duplicated within same booking, find next available unbooked seat
                    if not chosen_seat or chosen_seat in booked_set or chosen_seat in used_seats:
                        candidate = next((s for s in available_list if s not in used_seats and s not in booked_set), None)
                        chosen_seat = candidate or f"3{idx+1}A"

                    used_seats.add(chosen_seat)
                    zone = calculate_boarding_zone(chosen_seat)
                    seq = f"{(idx + 1 + id_seed) % 180 + 1:04d}"

                    pax_data = dict(f.cleaned_data)
                    pax_data["seat_number"] = chosen_seat
                    pax_objs.append(Passenger(
                        booking=booking,
                        boarding_zone=zone,
                        sequence_number=seq,
                        **pax_data,
                    ))
                Passenger.objects.bulk_create(pax_objs)

            del request.session["selected_flight"]
            return redirect("confirmation", reference=booking.reference)
    else:
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        contact = ContactForm(initial={
            "contact_email": request.user.email,
            "contact_phone": profile.phone or "",
        })

        # Suggest default available unbooked seats
        assigned_defaults = []
        used_initial = set()
        for _ in range(pax):
            candidate = next((s for s in available_list if s not in used_initial), f"30A")
            used_initial.add(candidate)
            assigned_defaults.append(candidate)

        initial_pax = [{
            "first_name": request.user.first_name,
            "last_name": request.user.last_name,
            "date_of_birth": profile.date_of_birth,
            "gender": profile.gender,
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
        formset = PassengerFormSet(initial=initial_pax, form_kwargs={"is_international": is_intl}, prefix="p")
        fare_type = sel.get("fare_type", "regular")

    return render(request, "flights/passengers.html", _ctx(
        flight=flight, pax=pax, contact=contact, formset=formset,
        is_international=is_intl, travel_class=travel_class, fare_type=fare_type,
        seat_map=seat_map, seat_map_json=json.dumps(seat_map),
    ))


@login_required
def confirmation(request, reference):
    booking = get_object_or_404(Booking.objects.prefetch_related("passengers"), reference=reference, user=request.user)
    cfg = resolve_airline_profile(booking.flight_number, booking.airline_name)
    return_qs = ""
    if booking.return_date:
        return_qs = urlencode({"source": booking.arr_iata, "destination": booking.dep_iata,
                               "departure_date": booking.return_date.isoformat(), "passengers": booking.passenger_count,
                               "travel_class": booking.travel_class})
    return render(request, "flights/confirmation.html", _ctx(booking=booking, cfg=cfg, return_qs=return_qs))


@login_required
def boarding_pass_pdf(request, reference):
    """Streams the authentic vector boarding pass PDF for download or inline view."""
    booking = get_object_or_404(Booking.objects.prefetch_related("passengers"), reference=reference, user=request.user)
    pdf_buffer = generate_boarding_passes_pdf(booking)
    filename = f"BoardingPass_{booking.reference}_{booking.flight_number.replace(' ', '')}.pdf"
    inline = request.GET.get("inline") == "1"
    response = FileResponse(pdf_buffer, content_type="application/pdf")
    response["Content-Disposition"] = f"{'inline' if inline else 'attachment'}; filename=\"{filename}\""
    return response


@login_required
def boarding_pass_view(request, reference):
    """Renders a digital web version of the boarding pass coupon card."""
    booking = get_object_or_404(Booking.objects.prefetch_related("passengers"), reference=reference, user=request.user)
    cfg = resolve_airline_profile(booking.flight_number, booking.airline_name)
    passengers = list(booking.passengers.all()) if hasattr(booking.passengers, "all") else list(booking.passengers)

    if not passengers:
        from .models import Passenger
        first_name = "PRIMARY"
        last_name = "PASSENGER"
        if hasattr(booking, "user") and booking.user:
            first_name = getattr(booking.user, "first_name", "") or "PRIMARY"
            last_name = getattr(booking.user, "last_name", "") or "PASSENGER"
        passengers = [Passenger(
            first_name=first_name,
            last_name=last_name,
            gender="M",
            seat_number="8A",
            boarding_zone="Zone 3",
            sequence_number="0026",
        )]

    sched_dep = booking.scheduled_departure
    if sched_dep and isinstance(sched_dep, str):
        try:
            sched_dep = datetime.fromisoformat(sched_dep)
        except Exception:
            sched_dep = None
    if sched_dep:
        local_dep = timezone.localtime(sched_dep) if timezone.is_aware(sched_dep) else sched_dep
        boarding_time = (local_dep - timedelta(minutes=45)).strftime("%H:%M hrs")
        dep_time = local_dep.strftime("%H:%M")
    else:
        boarding_time = "07:45 hrs"
        dep_time = "08:30"

    raw_dep_term = str(booking.dep_terminal or "1").strip()
    dep_term_num = raw_dep_term.lstrip("Tt").strip() or "1"
    dep_term = f"T{dep_term_num}"

    snapshot = booking.snapshot if isinstance(getattr(booking, "snapshot", None), dict) else {}
    raw_arr_term = str(snapshot.get("arr_terminal") or "2").strip()
    arr_term_num = raw_arr_term.lstrip("Tt").strip() or "2"
    arr_term = f"T{arr_term_num}"

    pax_cards = []
    for idx, p in enumerate(passengers):
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

    return render(request, "flights/boarding_pass.html", _ctx(
        booking=booking,
        cfg=cfg,
        pax_cards=pax_cards,
        dep_term=dep_term,
        dep_term_num=dep_term_num,
        arr_term=arr_term,
        arr_term_num=arr_term_num,
        boarding_time=boarding_time,
        dep_time=dep_time,
    ))



@login_required
def my_bookings(request):
    bookings = request.user.bookings.prefetch_related("passengers")
    return render(request, "flights/my_bookings.html", _ctx(bookings=bookings, today=timezone.localdate()))


@login_required
def profile_view(request):
    """View user profile details, travel identity, preferences, and booking stats."""
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    bookings = request.user.bookings.prefetch_related("passengers")
    today = timezone.localdate()
    upcoming_bookings = [b for b in bookings if b.dep_date >= today]
    past_bookings = [b for b in bookings if b.dep_date < today]

    return render(request, "flights/profile.html", _ctx(
        profile=profile,
        user=request.user,
        total_bookings=bookings.count(),
        upcoming_count=len(upcoming_bookings),
        past_count=len(past_bookings),
        recent_bookings=bookings[:5],
        today=today,
    ))


@login_required
def profile_edit_view(request):
    """Edit user profile, personal details, contact, and passport information."""
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        form = UserProfileEditForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile has been updated successfully!")
            return redirect("profile")
    else:
        form = UserProfileEditForm(instance=profile)

    return render(request, "flights/profile_edit.html", _ctx(
        form=form,
        profile=profile,
    ))


def register(request):
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.save())
        return redirect(request.GET.get("next") or "home")
    return render(request, "registration/register.html", {"form": form})


def airlines_directory(request):
    """Directory and dividance guide for all airlines operating in India."""
    from .services.airlines_data import (
        DOMESTIC_ONLY_AIRLINES,
        BOTH_DOMESTIC_INTL_AIRLINES,
        FOREIGN_AIRLINES_BY_REGION,
        ALL_AIRLINES,
    )
    return render(request, "flights/airlines_directory.html", _ctx(
        domestic_only=DOMESTIC_ONLY_AIRLINES,
        both_domestic_intl=BOTH_DOMESTIC_INTL_AIRLINES,
        foreign_by_region=FOREIGN_AIRLINES_BY_REGION,
        total_airlines_count=len(ALL_AIRLINES),
    ))
