"""
Custom super-admin dashboard, server-rendered (Django templates), sitting
alongside the default Django admin at /dashboard/. Pulls from the same
analytics service used by the API so numbers are always consistent between
the JSON API and this view.
"""

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render

from analytics.services import platform_dashboard, platform_revenue_timeseries
from payments.models import Payment
from payouts.models import Payout


@staff_member_required
def dashboard_view(request):
    data = platform_dashboard()
    timeseries = platform_revenue_timeseries(days=30)

    context = {
        "data": data,
        "timeseries_labels": [str(row["day"]) for row in timeseries],
        "timeseries_revenue": [float(row["platform_revenue"] or 0) for row in timeseries],
        "timeseries_volume": [float(row["gross_volume"] or 0) for row in timeseries],
        "flagged_payments": Payment.objects.filter(flagged_for_review=True).select_related("customer")[:10],
        "pending_payouts": Payout.objects.filter(status=Payout.Status.SCHEDULED).select_related("host")[:10],
        "held_payouts": Payout.objects.filter(status=Payout.Status.HELD).select_related("host")[:10],
    }
    return render(request, "admin_dashboard/dashboard.html", context)
