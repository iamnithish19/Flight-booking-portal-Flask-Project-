from datetime import timedelta

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone

from .models import Passenger, UserProfile
from .services.airports import NATIONALITY_CHOICES, parse_code
from .services.concessions import CONCESSION_CHOICES, CONCESSION_REGULAR

CLASS_CHOICES = [
    ("economy", "Economy"),
    ("premium_economy", "Premium Economy"),
    ("business", "Business Class"),
    ("first", "First Class"),
]


class FlightSearchForm(forms.Form):
    source = forms.CharField(label="From", max_length=60)
    destination = forms.CharField(label="To", max_length=60)
    departure_date = forms.DateField(label="Departure date", widget=forms.DateInput(attrs={"type": "date"}))
    return_date = forms.DateField(label="Return date", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    passengers = forms.IntegerField(label="Passengers", min_value=1, max_value=9, initial=1)
    travel_class = forms.ChoiceField(label="Class", choices=CLASS_CHOICES, initial="economy", required=False)
    fare_type = forms.ChoiceField(label="Special Fare", choices=CONCESSION_CHOICES, initial=CONCESSION_REGULAR, required=False)

    def _airport(self, field):
        code = parse_code(self.cleaned_data[field])
        if not code:
            raise forms.ValidationError("Choose an airport from the list, e.g. Chennai (MAA).")
        return code

    def clean_source(self):
        return self._airport("source")

    def clean_destination(self):
        return self._airport("destination")

    def clean_departure_date(self):
        d, today = self.cleaned_data["departure_date"], timezone.localdate()
        if d < today:
            raise forms.ValidationError("Departure date can't be in the past.")
        if d > today + timedelta(days=330):
            raise forms.ValidationError("Choose a date within the next 330 days.")
        return d

    def clean(self):
        data = super().clean()
        if data.get("source") and data.get("source") == data.get("destination"):
            self.add_error("destination", "Destination must differ from the origin.")
        if data.get("return_date") and data.get("departure_date") and data["return_date"] < data["departure_date"]:
            self.add_error("return_date", "Return date can't be before the departure date.")
        return data


class ContactForm(forms.Form):
    contact_email = forms.EmailField(label="Contact email")
    contact_phone = forms.CharField(label="Phone", max_length=20, required=False)


class PassengerForm(forms.ModelForm):
    nationality = forms.ChoiceField(
        label="Nationality",
        choices=NATIONALITY_CHOICES,
        initial="India",
        required=False,
        widget=forms.Select(attrs={"class": "nationality-select"})
    )
    passport_number = forms.CharField(
        label="Passport Number",
        max_length=40,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Passport Number (e.g. Z1234567)", "class": "passport-field"})
    )
    passport_expiry = forms.DateField(
        label="Passport Expiry",
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "passport-field"})
    )
    seat_number = forms.CharField(
        label="Seat Number",
        max_length=10,
        required=False,
        widget=forms.HiddenInput(attrs={"class": "pax-seat-input"})
    )

    class Meta:
        model = Passenger
        fields = ["first_name", "last_name", "date_of_birth", "gender", "nationality", "id_number", "passport_number", "passport_expiry", "seat_number"]
        widgets = {"date_of_birth": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, is_international: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_international = is_international

    def clean_nationality(self):
        return self.cleaned_data.get("nationality") or "India"

    def clean_date_of_birth(self):
        d = self.cleaned_data["date_of_birth"]
        if d > timezone.localdate():
            raise forms.ValidationError("Date of birth can't be in the future.")
        return d

    def clean(self):
        cleaned_data = super().clean()
        nationality = cleaned_data.get("nationality") or "India"
        passport_num = (cleaned_data.get("passport_number") or "").strip()

        # International route or foreign national: Passport required!
        if self.is_international or nationality != "India":
            if not passport_num:
                self.add_error("passport_number", "Passport number is required for international travel.")
        return cleaned_data


class RegisterForm(UserCreationForm):
    username = forms.CharField(
        label="Username",
        max_length=150,
        required=True,
        help_text="Required. 150 characters or fewer. Any format is accepted.",
    )
    email = forms.EmailField(required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def _get_validation_exclusions(self):
        exclude = super()._get_validation_exclusions()
        exclude.add("username")
        return exclude

    def clean_username(self):
        uname = self.cleaned_data.get("username", "").strip()
        if not uname:
            raise forms.ValidationError("This field is required.")
        if User.objects.filter(username__iexact=uname).exists():
            raise forms.ValidationError("A user with that username already exists.")
        return uname

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user


class UserProfileEditForm(forms.ModelForm):
    first_name = forms.CharField(
        label="First Name",
        max_length=60,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "First Name", "class": "form-control"}),
    )
    last_name = forms.CharField(
        label="Last Name",
        max_length=60,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Last Name", "class": "form-control"}),
    )
    email = forms.EmailField(
        label="Email Address",
        required=True,
        widget=forms.EmailInput(attrs={"placeholder": "Email Address", "class": "form-control"}),
    )
    nationality = forms.ChoiceField(
        label="Nationality",
        choices=NATIONALITY_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    class Meta:
        model = UserProfile
        fields = [
            "phone",
            "date_of_birth",
            "gender",
            "nationality",
            "passport_number",
            "passport_expiry",
            "preferred_class",
            "home_airport",
            "frequent_flyer_number",
            "address",
        ]
        widgets = {
            "phone": forms.TextInput(attrs={"placeholder": "+91 98765 43210", "class": "form-control"}),
            "date_of_birth": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "gender": forms.Select(attrs={"class": "form-control"}),
            "passport_number": forms.TextInput(attrs={"placeholder": "Passport Number (e.g. Z1234567)", "class": "form-control"}),
            "passport_expiry": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "preferred_class": forms.Select(attrs={"class": "form-control"}),
            "home_airport": forms.TextInput(attrs={"placeholder": "Chennai (MAA)", "class": "form-control"}),
            "frequent_flyer_number": forms.TextInput(attrs={"placeholder": "e.g. AI-88231", "class": "form-control"}),
            "address": forms.TextInput(attrs={"placeholder": "City / Full Address", "class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and hasattr(self.instance, "user") and self.instance.user:
            self.fields["first_name"].initial = self.instance.user.first_name
            self.fields["last_name"].initial = self.instance.user.last_name
            self.fields["email"].initial = self.instance.user.email

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if not email:
            raise forms.ValidationError("Email address is required.")
        user = getattr(self.instance, "user", None)
        if user and User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
            raise forms.ValidationError("This email is already in use by another account.")
        return email

    def save(self, commit=True):
        profile = super().save(commit=False)
        user = profile.user
        user.first_name = self.cleaned_data.get("first_name", "").strip()
        user.last_name = self.cleaned_data.get("last_name", "").strip()
        user.email = self.cleaned_data.get("email", "").strip().lower()
        if commit:
            user.save()
            profile.save()
        return profile

