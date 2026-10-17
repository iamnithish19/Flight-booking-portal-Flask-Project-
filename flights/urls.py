from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("search/", views.search, name="search"),
    path("api/flights/", views.api_search, name="api_search"),
    path("flight/", views.flight_detail, name="flight_detail"),
    path("book/start/", views.book_start, name="book_start"),
    path("book/passengers/", views.passengers, name="passengers"),
    path("booking/<str:reference>/", views.confirmation, name="confirmation"),
    path("booking/<str:reference>/boarding-pass/", views.boarding_pass_view, name="boarding_pass_view"),
    path("booking/<str:reference>/boarding-pass/pdf/", views.boarding_pass_pdf, name="boarding_pass_pdf"),
    path("my-bookings/", views.my_bookings, name="my_bookings"),
    path("profile/", views.profile_view, name="profile"),
    path("profile/edit/", views.profile_edit_view, name="profile_edit"),
    path("airlines/", views.airlines_directory, name="airlines_directory"),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("register/", views.register, name="register"),
]
