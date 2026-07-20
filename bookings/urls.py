from django.urls import path

from bookings.views import (
    AllBookingsAdminView,
    BookingDetailView,
    CancelBookingView,
    CheckoutView,
    HostEventBookingsView,
    MyBookingsView,
)

app_name = "bookings"

urlpatterns = [
    path("checkout/", CheckoutView.as_view(), name="checkout"),
    path("mine/", MyBookingsView.as_view(), name="my_bookings"),
    path("admin/all/", AllBookingsAdminView.as_view(), name="admin_all"),
    path("event/<uuid:event_id>/", HostEventBookingsView.as_view(), name="host_event_bookings"),
    path("<str:booking_reference>/", BookingDetailView.as_view(), name="booking_detail"),
    path("<str:booking_reference>/cancel/", CancelBookingView.as_view(), name="booking_cancel"),
]
