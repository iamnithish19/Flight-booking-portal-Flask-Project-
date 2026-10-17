import secrets

from django.conf import settings
from django.db import models


def new_reference():
    while True:
        ref = secrets.token_hex(4).upper()
        if not Booking.objects.filter(reference=ref).exists():
            return ref


class Booking(models.Model):
    """A booking keeps a frozen snapshot of the flight so history survives API changes.
    `booking_status` is the booking's own state, not the flight's live status."""

    class BookingStatus(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookings")
    reference = models.CharField(max_length=12, unique=True, default=new_reference, editable=False)
    booking_status = models.CharField(max_length=12, choices=BookingStatus.choices, default=BookingStatus.CONFIRMED)
    created_at = models.DateTimeField(auto_now_add=True)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=20, blank=True)
    passenger_count = models.PositiveSmallIntegerField(default=1)
    return_date = models.DateField(null=True, blank=True)

    # ---- flight snapshot (copied from the live API at booking time) ----
    api_provider = models.CharField(max_length=30)
    airline_name = models.CharField(max_length=120, blank=True)
    flight_number = models.CharField(max_length=12)
    dep_iata = models.CharField(max_length=3)
    dep_airport = models.CharField(max_length=160, blank=True)
    arr_iata = models.CharField(max_length=3)
    arr_airport = models.CharField(max_length=160, blank=True)
    dep_date = models.DateField()
    scheduled_departure = models.DateTimeField(null=True, blank=True)
    scheduled_arrival = models.DateTimeField(null=True, blank=True)
    dep_terminal = models.CharField(max_length=10, blank=True)
    dep_gate = models.CharField(max_length=10, blank=True)
    aircraft = models.CharField(max_length=80, blank=True)
    status_at_booking = models.CharField(max_length=40, blank=True)
    snapshot = models.JSONField(default=dict)
    email_sent = models.BooleanField(default=False)
    travel_class = models.CharField(max_length=30, default="economy")
    is_connecting = models.BooleanField(default=False)
    stops_info = models.CharField(max_length=120, blank=True, default="Non-stop")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} - {self.flight_number} {self.dep_iata}->{self.arr_iata}"


class Passenger(models.Model):
    GENDERS = [("F", "Female"), ("M", "Male"), ("X", "Other / unspecified")]
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="passengers")
    first_name = models.CharField(max_length=60)
    last_name = models.CharField(max_length=60)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=1, choices=GENDERS)
    nationality = models.CharField(max_length=80, default="India")
    id_number = models.CharField("Government ID / Aadhaar", max_length=30, blank=True)
    passport_number = models.CharField("Passport Number", max_length=40, blank=True)
    passport_expiry = models.DateField(null=True, blank=True)
    seat_number = models.CharField(max_length=10, blank=True)
    boarding_zone = models.CharField(max_length=10, blank=True)
    sequence_number = models.CharField(max_length=10, blank=True)

    @property
    def formatted_name(self):
        last = (self.last_name or "").strip().upper() or "PASSENGER"
        first = (self.first_name or "").strip().upper() or "PRIMARY"
        title = "MR" if self.gender == "M" else ("MS" if self.gender == "F" else "")
        title_suffix = f"/{title}" if title else ""
        return f"{last}/{first}{title_suffix}"

    def __str__(self):
        full = f"{self.first_name or ''} {self.last_name or ''}".strip()
        return full or "Passenger"


class UserProfile(models.Model):
    CLASS_CHOICES = [
        ("Economy", "Economy"),
        ("Premium Economy", "Premium Economy"),
        ("Business Class", "Business Class"),
        ("First Class", "First Class"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    phone = models.CharField("Phone Number", max_length=20, blank=True)
    date_of_birth = models.DateField("Date of Birth", null=True, blank=True)
    gender = models.CharField("Gender", max_length=1, choices=Passenger.GENDERS, blank=True)
    nationality = models.CharField("Nationality", max_length=80, default="India")
    passport_number = models.CharField("Passport Number", max_length=40, blank=True)
    passport_expiry = models.DateField("Passport Expiry Date", null=True, blank=True)
    frequent_flyer_number = models.CharField("Frequent Flyer ID", max_length=30, blank=True)
    preferred_class = models.CharField("Preferred Cabin Class", max_length=30, choices=CLASS_CHOICES, default="Economy")
    home_airport = models.CharField("Home / Departure Airport", max_length=30, blank=True)
    address = models.CharField("City / Address", max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}'s Profile"

    @property
    def full_name(self):
        name = f"{self.user.first_name} {self.user.last_name}".strip()
        return name or self.user.username

    @property
    def membership_tier(self):
        count = self.user.bookings.count()
        if count >= 10:
            return {"name": "Platinum Voyager", "color": "#7c3aed", "bg": "#f5f3ff", "badge": "Platinum"}
        if count >= 5:
            return {"name": "Gold Club", "color": "#d97706", "bg": "#fffbeb", "badge": "Gold"}
        if count >= 2:
            return {"name": "Silver Flyer", "color": "#0284c7", "bg": "#f0f9ff", "badge": "Silver"}
        return {"name": "Standard Traveler", "color": "#4b5563", "bg": "#f3f4f6", "badge": "Standard"}


from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_or_save_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)
    else:
        UserProfile.objects.get_or_create(user=instance)

