"""Flask Form helpers for Airvoyage flight portal.
Provides full HTML rendering and validation compatible with the existing templates.
"""
from datetime import date, datetime, timedelta
import re
from markupsafe import Markup
from flights.services.airports import AIRPORTS, NATIONALITY_CHOICES, parse_code
from flights.services.concessions import CONCESSION_CHOICES, CONCESSION_REGULAR

CLASS_CHOICES = [
    ("economy", "Economy"),
    ("premium_economy", "Premium Economy"),
    ("business", "Business Class"),
    ("first", "First Class"),
]

GENDER_CHOICES = [
    ("M", "Male"),
    ("F", "Female"),
    ("X", "Other / unspecified"),
]


class FormField:
    def __init__(self, name, label="", value="", errors=None, field_type="text",
                 required=False, placeholder="", css_class="", choices=None, attrs=None):
        self.name = name
        self.label = label
        self.value = value or ""
        self.errors = errors or []
        self.field_type = field_type
        self.required = required
        self.placeholder = placeholder
        self.css_class = css_class
        self.choices = choices or []
        self.attrs = attrs or {}

    @property
    def id_for_label(self):
        return f"id_{self.name.replace('-', '_')}"

    def __html__(self):
        attrs_str = ""
        for k, v in self.attrs.items():
            attrs_str += f' {k}="{Markup.escape(v)}"'
        if self.placeholder:
            attrs_str += f' placeholder="{Markup.escape(self.placeholder)}"'
        if self.css_class:
            attrs_str += f' class="{Markup.escape(self.css_class)}"'
        if self.required:
            attrs_str += " required"

        val_esc = Markup.escape(str(self.value) if self.value is not None else "")

        if self.field_type == "select":
            html = f'<select name="{Markup.escape(self.name)}" id="{self.id_for_label}"{attrs_str}>'
            for opt_val, opt_label in self.choices:
                sel = ' selected' if str(self.value) == str(opt_val) else ''
                html += f'<option value="{Markup.escape(opt_val)}"{sel}>{Markup.escape(opt_label)}</option>'
            html += '</select>'
            return Markup(html)

        if self.field_type == "hidden":
            return Markup(f'<input type="hidden" name="{Markup.escape(self.name)}" id="{self.id_for_label}" value="{val_esc}"{attrs_str}>')

        return Markup(f'<input type="{self.field_type}" name="{Markup.escape(self.name)}" id="{self.id_for_label}" value="{val_esc}"{attrs_str}>')

    def __str__(self):
        return self.__html__()


class FlightSearchForm:
    def __init__(self, data=None, initial=None):
        self.data = data or {}
        self.initial = initial or {}
        self.errors = {}
        self.non_field_errors = []
        self.cleaned_data = {}
        self._init_fields()

    def _val(self, key, default=""):
        if self.data and key in self.data:
            return self.data.get(key, default)
        return self.initial.get(key, default)

    def _init_fields(self):
        self.source = FormField("source", "From", self._val("source"))
        self.destination = FormField("destination", "To", self._val("destination"))
        self.departure_date = FormField("departure_date", "Departure date", self._val("departure_date"), field_type="date")
        self.return_date = FormField("return_date", "Return date", self._val("return_date"), field_type="date")
        self.passengers = FormField("passengers", "Passengers", self._val("passengers", 1), field_type="number")
        self.travel_class = FormField("travel_class", "Class", self._val("travel_class", "economy"), choices=CLASS_CHOICES)
        self.fare_type = FormField("fare_type", "Special Fare", self._val("fare_type", "regular"), choices=CONCESSION_CHOICES)

    def is_valid(self):
        self.errors = {}
        self.non_field_errors = []
        self.cleaned_data = {}

        src_raw = (self.data.get("source") or "").strip()
        dst_raw = (self.data.get("destination") or "").strip()
        src_code = parse_code(src_raw) or (src_raw.upper() if len(src_raw) == 3 else None)
        dst_code = parse_code(dst_raw) or (dst_raw.upper() if len(dst_raw) == 3 else None)

        if not src_code:
            self.errors["source"] = ["Choose a valid origin airport from the list."]
            self.source.errors = self.errors["source"]
        if not dst_code:
            self.errors["destination"] = ["Choose a valid destination airport from the list."]
            self.destination.errors = self.errors["destination"]

        if src_code and dst_code and src_code == dst_code:
            self.errors["destination"] = ["Destination must differ from origin."]
            self.destination.errors = self.errors["destination"]

        dep_raw = self.data.get("departure_date") or ""
        try:
            dep_date = date.fromisoformat(str(dep_raw))
            today = date.today()
            if dep_date < today:
                self.errors["departure_date"] = ["Departure date can't be in the past."]
                self.departure_date.errors = self.errors["departure_date"]
            elif dep_date > today + timedelta(days=330):
                self.errors["departure_date"] = ["Choose a date within the next 330 days."]
                self.departure_date.errors = self.errors["departure_date"]
        except (ValueError, TypeError):
            self.errors["departure_date"] = ["Enter a valid departure date."]
            self.departure_date.errors = self.errors["departure_date"]
            dep_date = date.today()

        ret_date = None
        ret_raw = self.data.get("return_date") or ""
        if ret_raw:
            try:
                ret_date = date.fromisoformat(str(ret_raw))
                if ret_date < dep_date:
                    self.errors["return_date"] = ["Return date can't be before departure date."]
                    self.return_date.errors = self.errors["return_date"]
            except (ValueError, TypeError):
                self.errors["return_date"] = ["Enter a valid return date."]
                self.return_date.errors = self.errors["return_date"]

        try:
            pax = max(1, min(9, int(self.data.get("passengers", 1))))
        except (ValueError, TypeError):
            pax = 1

        travel_class = (self.data.get("travel_class") or "economy").lower()
        fare_type = (self.data.get("fare_type") or "regular").lower()

        if not self.errors:
            self.cleaned_data = {
                "source": src_code,
                "destination": dst_code,
                "departure_date": dep_date,
                "return_date": ret_date,
                "passengers": pax,
                "travel_class": travel_class,
                "fare_type": fare_type,
            }
            return True
        return False


class ContactForm:
    def __init__(self, data=None, initial=None):
        self.data = data or {}
        self.initial = initial or {}
        self.errors = {}
        self.cleaned_data = {}
        email_val = self.data.get("contact_email") if "contact_email" in self.data else self.initial.get("contact_email", "")
        phone_val = self.data.get("contact_phone") if "contact_phone" in self.data else self.initial.get("contact_phone", "")

        self.contact_email = FormField("contact_email", "Contact email", email_val, field_type="email", required=True)
        self.contact_phone = FormField("contact_phone", "Phone", phone_val, field_type="text")
        self.fields = [self.contact_email, self.contact_phone]

    def __iter__(self):
        return iter(self.fields)

    def is_valid(self):
        self.errors = {}
        email = (self.data.get("contact_email") or "").strip()
        phone = (self.data.get("contact_phone") or "").strip()
        if not email or "@" not in email:
            self.errors["contact_email"] = ["Enter a valid email address."]
            self.contact_email.errors = self.errors["contact_email"]
        if not self.errors:
            self.cleaned_data = {
                "contact_email": email,
                "contact_phone": phone,
            }
            return True
        return False


class PassengerSingleForm:
    def __init__(self, prefix, data=None, initial=None, is_international=False):
        self.prefix = prefix
        self.data = data or {}
        self.initial = initial or {}
        self.is_international = is_international
        self.errors = {}
        self.cleaned_data = {}
        self._init_fields()

    def _val(self, field_name, default=""):
        k = f"{self.prefix}-{field_name}"
        if self.data and k in self.data:
            return self.data.get(k, default)
        return self.initial.get(field_name, default)

    def _init_fields(self):
        p = self.prefix
        dob_val = self._val("date_of_birth", "")
        if hasattr(dob_val, "strftime"):
            dob_val = dob_val.strftime("%Y-%m-%d")
        exp_val = self._val("passport_expiry", "")
        if hasattr(exp_val, "strftime"):
            exp_val = exp_val.strftime("%Y-%m-%d")

        self.first_name = FormField(f"{p}-first_name", "First name", self._val("first_name"), required=True, attrs={"maxlength": "60"})
        self.last_name = FormField(f"{p}-last_name", "Last name", self._val("last_name"), required=True, attrs={"maxlength": "60"})
        self.date_of_birth = FormField(f"{p}-date_of_birth", "Date of birth", dob_val, field_type="date", required=True)
        self.gender = FormField(f"{p}-gender", "Gender", self._val("gender", "M"), field_type="select", choices=GENDER_CHOICES, required=True)
        self.nationality = FormField(f"{p}-nationality", "Nationality", self._val("nationality", "India"), field_type="select", choices=NATIONALITY_CHOICES, css_class="nationality-select")
        self.id_number = FormField(f"{p}-id_number", "Government ID / Aadhaar", self._val("id_number"), attrs={"maxlength": "30"})
        self.passport_number = FormField(f"{p}-passport_number", "Passport Number", self._val("passport_number"), placeholder="Passport Number (e.g. Z1234567)", css_class="passport-field", attrs={"maxlength": "40"})
        self.passport_expiry = FormField(f"{p}-passport_expiry", "Passport Expiry Date", exp_val, field_type="date", css_class="passport-field")
        self.seat_number = FormField(f"{p}-seat_number", "Seat Number", self._val("seat_number", "30A"), field_type="hidden", css_class="pax-seat-input")

    def is_valid(self):
        self.errors = {}
        first = (self.data.get(f"{self.prefix}-first_name") or "").strip()
        last = (self.data.get(f"{self.prefix}-last_name") or "").strip()
        gender = (self.data.get(f"{self.prefix}-gender") or "M").strip()
        nat = (self.data.get(f"{self.prefix}-nationality") or "India").strip()
        id_num = (self.data.get(f"{self.prefix}-id_number") or "").strip()
        passport_num = (self.data.get(f"{self.prefix}-passport_number") or "").strip()
        seat = (self.data.get(f"{self.prefix}-seat_number") or "").strip().upper()

        if not first:
            self.errors["first_name"] = ["First name is required."]
            self.first_name.errors = self.errors["first_name"]
        if not last:
            self.errors["last_name"] = ["Last name is required."]
            self.last_name.errors = self.errors["last_name"]

        dob_raw = self.data.get(f"{self.prefix}-date_of_birth") or ""
        dob = None
        if dob_raw:
            try:
                dob = date.fromisoformat(str(dob_raw))
                if dob > date.today():
                    self.errors["date_of_birth"] = ["Date of birth cannot be in the future."]
                    self.date_of_birth.errors = self.errors["date_of_birth"]
            except Exception:
                self.errors["date_of_birth"] = ["Enter a valid date of birth."]
                self.date_of_birth.errors = self.errors["date_of_birth"]
        else:
            self.errors["date_of_birth"] = ["Date of birth is required."]
            self.date_of_birth.errors = self.errors["date_of_birth"]

        exp_raw = self.data.get(f"{self.prefix}-passport_expiry") or ""
        exp_date = None
        if exp_raw:
            try:
                exp_date = date.fromisoformat(str(exp_raw))
            except Exception:
                pass

        if (self.is_international or nat != "India") and not passport_num:
            self.errors["passport_number"] = ["Passport number is required for international travel."]
            self.passport_number.errors = self.errors["passport_number"]

        if not self.errors:
            self.cleaned_data = {
                "first_name": first,
                "last_name": last,
                "date_of_birth": dob,
                "gender": gender,
                "nationality": nat,
                "id_number": id_num,
                "passport_number": passport_num,
                "passport_expiry": exp_date,
                "seat_number": seat or "30A",
            }
            return True
        return False


class PassengerFormSet:
    def __init__(self, data=None, initial=None, pax_count=1, is_international=False, prefix="p"):
        self.prefix = prefix
        self.pax_count = pax_count
        self.is_international = is_international
        self.forms = []
        self.non_form_errors = []
        initial_list = initial or []

        for i in range(pax_count):
            init_item = initial_list[i] if i < len(initial_list) else {}
            p_prefix = f"{prefix}-{i}"
            form = PassengerSingleForm(p_prefix, data=data, initial=init_item, is_international=is_international)
            self.forms.append(form)

    def __iter__(self):
        return iter(self.forms)

    def __len__(self):
        return len(self.forms)

    @property
    def management_form(self):
        return Markup(f'<input type="hidden" name="{self.prefix}-TOTAL_FORMS" value="{self.pax_count}">'
                      f'<input type="hidden" name="{self.prefix}-INITIAL_FORMS" value="{self.pax_count}">')

    def is_valid(self):
        all_ok = True
        for form in self.forms:
            if not form.is_valid():
                all_ok = False
        return all_ok


class UserProfileEditForm:
    def __init__(self, data=None, user=None, profile=None):
        self.data = data or {}
        self.user = user
        self.profile = profile
        self.errors = {}
        self.non_field_errors = []
        self.cleaned_data = {}
        self._init_fields()

    def _val(self, key, default=""):
        if self.data and key in self.data:
            return self.data.get(key, default)
        if self.user and hasattr(self.user, key):
            return getattr(self.user, key, default)
        if self.profile and hasattr(self.profile, key):
            v = getattr(self.profile, key, default)
            if hasattr(v, "strftime"):
                return v.strftime("%Y-%m-%d")
            return v or default
        return default

    def _init_fields(self):
        self.first_name = FormField("first_name", "First Name", self._val("first_name"), css_class="form-control", placeholder="First Name", attrs={"maxlength": "60"})
        self.last_name = FormField("last_name", "Last Name", self._val("last_name"), css_class="form-control", placeholder="Last Name", attrs={"maxlength": "60"})
        self.email = FormField("email", "Email Address", self._val("email"), field_type="email", required=True, css_class="form-control", placeholder="Email Address")
        self.phone = FormField("phone", "Phone Number", self._val("phone"), css_class="form-control", placeholder="+91 98765 43210")
        self.date_of_birth = FormField("date_of_birth", "Date of Birth", self._val("date_of_birth"), field_type="date", css_class="form-control")
        self.gender = FormField("gender", "Gender", self._val("gender"), field_type="select", choices=[("", "Select Gender")] + GENDER_CHOICES, css_class="form-control")
        self.nationality = FormField("nationality", "Nationality", self._val("nationality", "India"), field_type="select", choices=NATIONALITY_CHOICES, css_class="form-control")
        self.passport_number = FormField("passport_number", "Passport Number", self._val("passport_number"), css_class="form-control", placeholder="Passport Number (e.g. Z1234567)")
        self.passport_expiry = FormField("passport_expiry", "Passport Expiry Date", self._val("passport_expiry"), field_type="date", css_class="form-control")
        self.preferred_class = FormField("preferred_class", "Default Cabin Class", self._val("preferred_class", "Economy"), field_type="select", choices=[("Economy", "Economy"), ("Premium Economy", "Premium Economy"), ("Business Class", "Business Class"), ("First Class", "First Class")], css_class="form-control")
        self.home_airport = FormField("home_airport", "Home Airport", self._val("home_airport"), css_class="form-control", placeholder="Chennai (MAA)")
        self.frequent_flyer_number = FormField("frequent_flyer_number", "Frequent Flyer / Loyalty ID", self._val("frequent_flyer_number"), css_class="form-control", placeholder="e.g. AI-88231")
        self.address = FormField("address", "City / Residential Address", self._val("address"), css_class="form-control", placeholder="City / Full Address")

    def is_valid(self):
        self.errors = {}
        email = (self.data.get("email") or "").strip().lower()
        if not email or "@" not in email:
            self.errors["email"] = ["Valid email address is required."]
            self.email.errors = self.errors["email"]

        dob_raw = self.data.get("date_of_birth") or ""
        dob = None
        if dob_raw:
            try:
                dob = date.fromisoformat(str(dob_raw))
            except Exception:
                pass

        exp_raw = self.data.get("passport_expiry") or ""
        exp = None
        if exp_raw:
            try:
                exp = date.fromisoformat(str(exp_raw))
            except Exception:
                pass

        if not self.errors:
            self.cleaned_data = {
                "first_name": (self.data.get("first_name") or "").strip(),
                "last_name": (self.data.get("last_name") or "").strip(),
                "email": email,
                "phone": (self.data.get("phone") or "").strip(),
                "date_of_birth": dob,
                "gender": (self.data.get("gender") or "").strip(),
                "nationality": (self.data.get("nationality") or "India").strip(),
                "passport_number": (self.data.get("passport_number") or "").strip(),
                "passport_expiry": exp,
                "preferred_class": (self.data.get("preferred_class") or "Economy").strip(),
                "home_airport": (self.data.get("home_airport") or "").strip(),
                "frequent_flyer_number": (self.data.get("frequent_flyer_number") or "").strip(),
                "address": (self.data.get("address") or "").strip(),
            }
            return True
        return False


class LoginForm:
    def __init__(self, data=None):
        self.data = data or {}
        self.errors = {}
        self.non_field_errors = []
        self.cleaned_data = {}

    def is_valid(self):
        self.errors = {}
        username = (self.data.get("username") or "").strip()
        password = self.data.get("password") or ""
        if not username:
            self.errors["username"] = ["This field is required."]
        if not password:
            self.errors["password"] = ["This field is required."]
        if not self.errors:
            self.cleaned_data = {"username": username, "password": password}
            return True
        return False

    @property
    def as_p(self):
        u_val = Markup.escape(self.data.get("username", ""))
        err_u = "".join(f'<ul class="errorlist"><li>{Markup.escape(e)}</li></ul>' for e in self.errors.get("username", []))
        err_p = "".join(f'<ul class="errorlist"><li>{Markup.escape(e)}</li></ul>' for e in self.errors.get("password", []))
        non_f = "".join(f'<ul class="errorlist nonfield"><li>{Markup.escape(e)}</li></ul>' for e in self.non_field_errors)
        html = (
            f'{non_f}'
            f'<p>{err_u}<label for="id_username">Username:</label> <input type="text" name="username" value="{u_val}" autofocus required id="id_username"></p>'
            f'<p>{err_p}<label for="id_password">Password:</label> <input type="password" name="password" required id="id_password"></p>'
        )
        return Markup(html)


class RegisterForm:
    def __init__(self, data=None):
        self.data = data or {}
        self.errors = {}
        self.non_field_errors = []
        self.cleaned_data = {}

    def is_valid(self):
        from flights.flask_models import get_user_by_username, get_user_by_email
        self.errors = {}
        username = (self.data.get("username") or "").strip()
        email = (self.data.get("email") or "").strip().lower()
        password = self.data.get("password1") or self.data.get("password") or ""
        password_conf = self.data.get("password2") or self.data.get("password_confirm") or ""

        if not username:
            self.errors["username"] = ["This field is required."]
        elif get_user_by_username(username):
            self.errors["username"] = ["A user with that username already exists."]

        if not email or "@" not in email:
            self.errors["email"] = ["Enter a valid email address."]
        elif get_user_by_email(email):
            self.errors["email"] = ["An account with this email already exists."]

        if not password:
            self.errors["password1"] = ["This field is required."]
        elif len(password) < 4:
            self.errors["password1"] = ["Password must be at least 4 characters long."]

        if password and password_conf and password != password_conf:
            self.errors["password2"] = ["The two password fields didn't match."]

        if not self.errors:
            self.cleaned_data = {
                "username": username,
                "email": email,
                "password": password,
            }
            return True
        return False

    @property
    def as_p(self):
        u_val = Markup.escape(self.data.get("username", ""))
        e_val = Markup.escape(self.data.get("email", ""))
        err_u = "".join(f'<ul class="errorlist"><li>{Markup.escape(e)}</li></ul>' for e in self.errors.get("username", []))
        err_e = "".join(f'<ul class="errorlist"><li>{Markup.escape(e)}</li></ul>' for e in self.errors.get("email", []))
        err_p1 = "".join(f'<ul class="errorlist"><li>{Markup.escape(e)}</li></ul>' for e in self.errors.get("password1", []))
        err_p2 = "".join(f'<ul class="errorlist"><li>{Markup.escape(e)}</li></ul>' for e in self.errors.get("password2", []))
        non_f = "".join(f'<ul class="errorlist nonfield"><li>{Markup.escape(e)}</li></ul>' for e in self.non_field_errors)
        html = (
            f'{non_f}'
            f'<p>{err_u}<label for="id_username">Username:</label> <input type="text" name="username" value="{u_val}" required id="id_username"><span class="helptext">Required. 150 characters or fewer. Any format is accepted.</span></p>'
            f'<p>{err_e}<label for="id_email">Email address:</label> <input type="email" name="email" value="{e_val}" required id="id_email"></p>'
            f'<p>{err_p1}<label for="id_password1">Password:</label> <input type="password" name="password1" required id="id_password1"></p>'
            f'<p>{err_p2}<label for="id_password2">Password confirmation:</label> <input type="password" name="password2" required id="id_password2"><span class="helptext">Enter the same password as before, for verification.</span></p>'
        )
        return Markup(html)

