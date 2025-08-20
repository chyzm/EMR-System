from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth import logout
from django.conf import settings
from django.utils import timezone

class AutoLogoutMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if not request.user.is_authenticated:
            return
        try:
            last_activity = request.session['last_activity']
            if (timezone.now() - last_activity).seconds > getattr(settings, 'AUTO_LOGOUT_DELAY', 300):
                logout(request)
        except KeyError:
            pass
        request.session['last_activity'] = timezone.now()
