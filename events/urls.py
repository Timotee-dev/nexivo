from django.urls import path

from events.views import (
    CategoryDetailView,
    CategoryListCreateView,
    EventDetailView,
    EventGalleryView,
    EventGoLiveView,
    EventListView,
    EventModerationView,
    EventPublishView,
    FeaturedEventsView,
    MyEventsView,
    NearbyEventsView,
    RecommendedEventsView,
    TicketTypeDetailView,
    TicketTypeListCreateView,
    ToggleFavoriteView,
    TrendingEventsView,
    UpcomingEventsView,
)

app_name = "events"

urlpatterns = [
    path("categories/", CategoryListCreateView.as_view(), name="category_list"),
    path("categories/<slug:slug>/", CategoryDetailView.as_view(), name="category_detail"),

    path("mine/", MyEventsView.as_view(), name="my_events"),
    path("trending/", TrendingEventsView.as_view(), name="trending"),
    path("upcoming/", UpcomingEventsView.as_view(), name="upcoming"),
    path("featured/", FeaturedEventsView.as_view(), name="featured"),
    path("nearby/", NearbyEventsView.as_view(), name="nearby"),
    path("recommended/", RecommendedEventsView.as_view(), name="recommended"),

    path("", EventListView.as_view(), name="event_list"),
    path("<slug:slug>/", EventDetailView.as_view(), name="event_detail"),
    path("<slug:slug>/publish/", EventPublishView.as_view(), name="event_publish"),
    path("<slug:slug>/go-live/", EventGoLiveView.as_view(), name="event_go_live"),
    path("<slug:slug>/moderate/", EventModerationView.as_view(), name="event_moderate"),
    path("<slug:slug>/favorite/", ToggleFavoriteView.as_view(), name="event_favorite"),
    path("<slug:slug>/gallery/", EventGalleryView.as_view(), name="event_gallery"),
    path("<slug:slug>/ticket-types/", TicketTypeListCreateView.as_view(), name="ticket_type_list"),
    path("ticket-types/<uuid:pk>/", TicketTypeDetailView.as_view(), name="ticket_type_detail"),
]
