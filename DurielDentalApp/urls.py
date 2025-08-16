from django.urls import path
from . import views

app_name = 'DurielDentalApp'
urlpatterns = [
    path('', views.placeholder, name='placeholder'),
]
