from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


class EmailOrUsernameBackend(ModelBackend):
    """Authenticate by unique email, or by username when it is unambiguous."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        login_value = username or kwargs.get(get_user_model().USERNAME_FIELD)
        if not login_value or password is None:
            return None

        UserModel = get_user_model()
        lookup = Q(email__iexact=login_value)
        if '@' not in login_value:
            lookup |= Q(username__iexact=login_value)

        users = list(UserModel._default_manager.filter(lookup, is_active=True)[:2])
        if len(users) != 1:
            return None

        user = users[0]
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
