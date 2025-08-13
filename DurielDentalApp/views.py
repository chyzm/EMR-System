from django.shortcuts import render
from core.utils import log_action

# Create your views here.
from django.http import HttpResponse

def placeholder(request):
    return HttpResponse("Duriel Dental App is under construction.")
