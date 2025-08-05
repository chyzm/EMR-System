# DurielMedicApp/utils.py

def admin_check(user):
    return user.is_authenticated and user.role == 'ADMIN'  # adjust based on your roles
