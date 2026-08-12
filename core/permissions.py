ADMIN_ROLES = ('ADMIN',)
FRONT_DESK_ROLES = ('ADMIN', 'RECEPTIONIST')
GENERAL_CLINICAL_ROLES = ('DOCTOR',)
GENERAL_VITALS_ROLES = ('NURSE', 'DOCTOR')
EYE_CLINICAL_ROLES = ('DOCTOR', 'OPTOMETRIST')
DENTAL_CLINICAL_ROLES = ('DENTIST',)
PRESCRIBER_ROLES = ('DOCTOR', 'OPTOMETRIST', 'DENTIST')
PHARMACY_ROLES = ('ADMIN', 'PHARMACIST')


def has_role(user, *roles):
    return bool(getattr(user, 'is_authenticated', False)) and getattr(user, 'role', None) in roles


def is_admin_user(user):
    return bool(getattr(user, 'is_superuser', False)) or has_role(user, *ADMIN_ROLES)


def can_prescribe(user):
    return has_role(user, *PRESCRIBER_ROLES)


def can_manage_patient_demographics(user):
    return has_role(user, *FRONT_DESK_ROLES)


def can_view_patient(user):
    return has_role(
        user,
        'ADMIN',
        'DOCTOR',
        'DENTIST',
        'NURSE',
        'PHARMACIST',
        'RECEPTIONIST',
        'OPTOMETRIST',
        'PHYSIOTHERAPIST',
        'LAB_TECHNICIAN',
    )
