from django.urls import path

from reviews.views import (
    AdminFlaggedReviewsView,
    AdminModerateReviewView,
    EventReviewsView,
    FlagReviewView,
    HostRespondToReviewView,
    MyReviewsView,
    ReviewDetailView,
)

app_name = "reviews"

urlpatterns = [
    path("mine/", MyReviewsView.as_view(), name="my_reviews"),
    path("event/<uuid:event_id>/", EventReviewsView.as_view(), name="event_reviews"),
    path("admin/flagged/", AdminFlaggedReviewsView.as_view(), name="admin_flagged"),
    path("admin/<uuid:pk>/moderate/", AdminModerateReviewView.as_view(), name="admin_moderate"),
    path("<uuid:pk>/", ReviewDetailView.as_view(), name="review_detail"),
    path("<uuid:review_id>/respond/", HostRespondToReviewView.as_view(), name="host_respond"),
    path("<uuid:review_id>/flag/", FlagReviewView.as_view(), name="flag_review"),
]
