from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect
from functools import wraps

def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            if request.user.role not in roles:
                return redirect('DurielMedicApp:dashboard')  # or show permission denied page
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


