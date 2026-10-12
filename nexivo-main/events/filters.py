import django_filters
from django.db.models import Q

from events.models import Event


class EventFilter(django_filters.FilterSet):
    """
    Powers /api/v1/events/?category=&event_type=&city=&min_price=&max_price=
    &start_after=&start_before=&is_featured=&status=
    """

    category = django_filters.CharFilter(field_name="category__slug", lookup_expr="iexact")
    event_type = django_filters.CharFilter(field_name="event_type", lookup_expr="iexact")
    city = django_filters.CharFilter(field_name="city", lookup_expr="icontains")
    state = django_filters.CharFilter(field_name="state", lookup_expr="icontains")
    country = django_filters.CharFilter(field_name="country", lookup_expr="icontains")

    start_after = django_filters.DateTimeFilter(field_name="start_datetime", lookup_expr="gte")
    start_before = django_filters.DateTimeFilter(field_name="start_datetime", lookup_expr="lte")

    min_price = django_filters.NumberFilter(method="filter_min_price")
    max_price = django_filters.NumberFilter(method="filter_max_price")
    is_free = django_filters.BooleanFilter(method="filter_is_free")

    is_featured = django_filters.BooleanFilter(field_name="is_featured")
    host = django_filters.UUIDFilter(field_name="host__id")

    class Meta:
        model = Event
        fields = [
            "category", "event_type", "city", "state", "country",
            "start_after", "start_before", "min_price", "max_price",
            "is_free", "is_featured", "host",
        ]

    def filter_min_price(self, queryset, name, value):
        return queryset.filter(ticket_types__price__gte=value).distinct()

    def filter_max_price(self, queryset, name, value):
        return queryset.filter(ticket_types__price__lte=value).distinct()

    def filter_is_free(self, queryset, name, value):
        if value:
            return queryset.filter(ticket_types__is_free=True).distinct()
        return queryset.filter(ticket_types__is_free=False).distinct()
