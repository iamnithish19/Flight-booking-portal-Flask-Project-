# Airvoyage — Flight Booking Portal (Flask Project)

> **Airvoyage** is a web-based flight booking application developed using Python and Flask. It allows users to search domestic and international flights, check live status, track routes, select seats, book tickets for multiple passengers, and download QR-coded boarding passes.

Search → live API → real-time results → details → login/register → passengers → booking → confirmation → My bookings.
Flight schedule/status always comes from an external API at request time. Users, bookings, passengers and a
**snapshot of the booked flight** are stored in database.

## 1. Setup

### Running with Flask (Recommended)
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000/

### Running with Django (Original)
```bash
python manage.py runserver
```
Open http://127.0.0.1:8000/

## 2. API setup (AeroDataBox recommended)
1. Create an account on **RapidAPI** (or **API.Market**) and subscribe to the *AeroDataBox* API. It has a free/basic tier; check the quota on the plan page (I could not verify the exact number).
2. Put the key in `.env`:
   ```env
   FLIGHT_API_PROVIDER=aerodatabox
   FLIGHT_API_KEY=your_api_key_here
   FLIGHT_API_AUTH_STYLE=rapidapi        # or: apimarket
   ```
3. Restart the server. The key is read only in `config/settings.py` and used only in `flights/services/*`; it is never in templates/JS/HTML. `.env` is git-ignored.

**Alternative:** `FLIGHT_API_PROVIDER=aviationstack` (free plan = HTTP only, ~100 requests/month).

### API research summary
| | AeroDataBox | Aviationstack |
|---|---|---|
| Live/current data | Yes: airport departure/arrival boards (FIDS) by current/relative time, plus flight-status endpoints. Live status/estimates only for airports it tracks | Yes: real-time flights endpoint on all plans |
| Auth | `X-RapidAPI-Key` + `X-RapidAPI-Host` (RapidAPI) or an API.Market key | `access_key` query parameter |
| Format | REST / JSON | REST / JSON |
| Route search | Departure board at origin filtered by destination (12 h window per call, so 2 calls per day-search) | `dep_iata` + `arr_iata` filters |
| Terminal / gate / estimated / actual | Yes, when the airport publishes them | Yes (departure and arrival objects) |
| Free tier | Exists; exact quota not verified | ~100 requests/month, HTTP only |
| Caveat | Board items describe the origin leg; arrival times load on the Details page | `flight_date` filtering isn't on every plan, so results are also filtered by date locally |

Because quotas are small, each real API response is cached for `FLIGHT_API_CACHE_SECONDS` (default 30 s),
auto-refresh is **opt-in** (checkbox, 60 s, only while the tab is visible) and the Refresh button pauses 4 s after use.

### Swapping APIs later
Implement `FlightProvider` (`search()` and `details()` returning `Flight` dicts, see `flights/services/base.py`),
register it in `_build_provider()` in `flights/services/flight_api.py`, set `FLIGHT_API_PROVIDER`. Views/templates don't change.

## 3. Project layout
```
config/settings.py         env-driven settings (TIME_ZONE default Asia/Kolkata, USE_TZ=True)
flights/models.py          Booking (flight snapshot + JSON), Passenger
flights/forms.py           search form (IATA parsing, date rules), passengers, contact, register
flights/views.py           home, search, api_search (AJAX), detail, book_start, passengers, confirmation, my_bookings
flights/services/          base.py, aerodatabox.py, aviationstack.py, flight_api.py (search_live_flights), airports.py
flights/templatetags/      time/status helpers (status shown exactly as the API returns it)
templates/, static/        UI: sky hero + glass search, teal result cards, dark booking-summary pages
flights/tests.py           mocked-HTTP tests
```
"Now" comes from `django.utils.timezone`; the default search date is `timezone.localdate()`; nothing is hard-coded.
Flight times are shown as local wall-clock time at each airport, as the API reports them.

## 4. Testing
```bash
python manage.py test
```
Covers parsing, destination filtering, status/delay display, the API-down message (no fake data), missing key,
the AJAX endpoint, form validation, and the full login → passengers → booking → My bookings flow.

**Live smoke test (needs your key):** search Chennai (MAA) → Delhi (DEL) for today/tomorrow, open *Details*,
tick *Auto-refresh*, and watch "Last updated" change without a page reload. With a bad/missing key you should see:
"Unable to retrieve live flight information. Please try again in a few moments."

## 5. Known limits
* Tests use payloads shaped from the provider docs; **they have not been run against the live APIs**. If a field name differs in your plan's responses, only `_normalise()` in the adapter needs adjusting.
* Flight-status APIs don't supply fares or seat maps, so prices and seat selection from the video are not shown (nothing is invented).
* The return date is saved on the booking and offers a "Search return flights" shortcut after confirming the outbound flight.
