from django.contrib import admin

from .models import Booking, Passenger


class PassengerInline(admin.TabularInline):
    model = Passenger
    extra = 0


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("reference", "user", "flight_number", "dep_iata", "arr_iata", "dep_date", "booking_status", "created_at")
    list_filter = ("booking_status", "api_provider", "dep_date")
    search_fields = ("reference", "flight_number", "user__username", "contact_email")
    readonly_fields = ("reference", "created_at", "snapshot")
    inlines = [PassengerInline]
