from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    
    

    # Auth
    path('accounts/', include('django.contrib.auth.urls')),

    # Core/shared functionality
    path('core/', include('core.urls')),

    # Specialty clinics
    path('eye/', include('DurielEyeApp.urls')),
    path('dental/', include('DurielDentalApp.urls')),

    # General hospital app
    path('', include('DurielMedicApp.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
