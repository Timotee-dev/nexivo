from django.urls import path

from coupons.views import CouponDetailView, CouponListCreateView, ValidateCouponView

app_name = "coupons"

urlpatterns = [
    path("", CouponListCreateView.as_view(), name="coupon_list"),
    path("validate/", ValidateCouponView.as_view(), name="coupon_validate"),
    path("<uuid:pk>/", CouponDetailView.as_view(), name="coupon_detail"),
]
