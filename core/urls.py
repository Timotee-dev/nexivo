from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
admin.site.site_header = "⬡ Nexora Admin"
admin.site.site_title = "Nexora"
admin.site.index_title = "Platform Control"
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('services.urls')),
    path('accounts/', include('accounts.urls')),
    path('bookings/', include('bookings.urls')),
    path('payments/', include('payments.urls')),
    path('dashboard/', include('dashboard.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
