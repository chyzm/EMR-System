"""
One-off diagnostic for "SMTPDataError 550 5.7.1 Reject for policy reason".

Run on the production server (PythonAnywhere Bash console):
    cd ~/emr && python3.10 scripts/diag_contact_email.py

Sends up to 4 labelled "[DIAG]" emails to info@durielmedic.com.ng using the
production EMAIL_* settings, and reports which ones the SMTP server accepts.
Delete this file when done.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "DurielMedic.settings")

import django

django.setup()

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from django.utils.html import strip_tags

TO = ["info@durielmedic.com.ng"]
FROM = settings.DEFAULT_FROM_EMAIL

print("HOST %s:%s TLS=%s SSL=%s USER=%s FROM=%s" % (
    settings.EMAIL_HOST, settings.EMAIL_PORT, settings.EMAIL_USE_TLS,
    settings.EMAIL_USE_SSL, settings.EMAIL_HOST_USER, FROM))

ctx = {
    "name": "Diag Test", "email": "somto.diag@gmail.com", "phone": "08000000000",
    "practice": "Hospital", "message": "Diagnostic test of the website contact form. Please ignore.",
    "website_url": "https://durielmedic.pythonanywhere.com/", "company_name": "Duriel Tech Solutions",
}
html = render_to_string("emails/admin_contact_notification.html", ctx)

cases = [
    ("1 plain text, no reply-to", "Diagnostic test 1. Please ignore.", None, None),
    ("2 contact HTML, no reply-to", strip_tags(html), html, None),
    ("3 contact HTML, reply-to visitor", strip_tags(html), html, [ctx["email"]]),
    ("4 plain text, reply-to visitor", "Diagnostic test 4. Please ignore.", None, [ctx["email"]]),
]

for label, body, alt, reply_to in cases:
    conn = get_connection(timeout=30)  # production EMAIL_* settings, fresh per message
    msg = EmailMultiAlternatives(f"[DIAG] {label}", body, FROM, TO, reply_to=reply_to, connection=conn)
    if alt:
        msg.attach_alternative(alt, "text/html")
    try:
        msg.send(fail_silently=False)
        print("ACCEPTED:", label)
    except Exception as e:
        print("REJECTED:", label, "->", repr(e))
