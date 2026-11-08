"""
One-off diagnostic for "SMTPDataError 550 5.7.1 Reject for policy reason".

Run on the production server (PythonAnywhere Bash console):
    cd ~/EMR-System && python3.10 scripts/diag_contact_email.py

Sends a few labelled "[DIAG]" plain-text emails to info@durielmedic.com.ng using
the production EMAIL_* settings. Each test adds ONE piece of the real inquiry to a
message that is known to pass, so the rejected test shows what the filter dislikes.
Set DIAG_DRY=1 to print the tests without sending. Delete this file when done.
"""
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "DurielMedic.settings")

import django

django.setup()

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.template.loader import render_to_string

TO = ["info@durielmedic.com.ng"]
FROM = settings.DEFAULT_FROM_EMAIL
DRY = os.getenv("DIAG_DRY") == "1"

print("HOST %s:%s TLS=%s SSL=%s USER=%s" % (
    settings.EMAIL_HOST, settings.EMAIL_PORT, settings.EMAIL_USE_TLS,
    settings.EMAIL_USE_SSL, settings.EMAIL_HOST_USER))

# Is the deployed view the plain-text version?
with open(os.path.join(BASE, "core", "views.py"), encoding="utf-8") as fh:
    views_src = fh.read()
print("views.py uses plain-text inquiry template:", "admin_contact_notification.txt" in views_src)
print("plain-text template exists:",
      os.path.exists(os.path.join(BASE, "templates", "emails", "admin_contact_notification.txt")))

print("views.py links to durielmedic.com.ng:", "'website_url': 'https://durielmedic.com.ng/'" in views_src)

VISITOR = "somtochiokaro@gmail.com"
PA_URL = "https://durielmedic.pythonanywhere.com/"
SITE_URL = "https://durielmedic.com.ng/"
CONTROL = "Diagnostic test. Please ignore."
ctx = {
    "name": "Test Visitor", "email": VISITOR, "phone": "08031234567",
    "practice": "Hospital", "message": "I would like a demo of DurielMedic+ for my clinic.",
    "website_url": SITE_URL, "company_name": "Duriel Tech Solutions",
}
real_subject = "New Website Inquiry: Test Visitor - Hospital"
real_body = render_to_string("emails/admin_contact_notification.txt", ctx)
real_body_pa = render_to_string("emails/admin_contact_notification.txt", {**ctx, "website_url": PA_URL})

# (label, subject, body, reply_to)
cases = [
    ("A control", "[DIAG] A control", CONTROL, None),
    ("B + pythonanywhere URL", "[DIAG] B pa url", CONTROL + "\n\n" + PA_URL, None),
    ("C + durielmedic.com.ng URL", "[DIAG] C site url", CONTROL + "\n\n" + SITE_URL, None),
    ("D + visitor email in body", "[DIAG] D email", CONTROL + "\n\nEmail: " + VISITOR, None),
    ("E + phone number", "[DIAG] E phone", CONTROL + "\n\nPhone: 08031234567", None),
    ("F real subject", "[DIAG] " + real_subject, CONTROL, None),
    ("G full inquiry, durielmedic.com.ng link (what the view now sends)", "[DIAG] " + real_subject, real_body, [VISITOR]),
    ("H full inquiry, pythonanywhere link (old)", "[DIAG] " + real_subject, real_body_pa, [VISITOR]),
]

for label, subject, body, reply_to in cases:
    if DRY:
        print("WOULD SEND:", label, "| subject=%r | %d chars" % (subject, len(body)))
        continue
    conn = get_connection(timeout=30)  # production EMAIL_* settings, fresh per message
    msg = EmailMessage(subject, body, FROM, TO, reply_to=reply_to, connection=conn)
    try:
        msg.send(fail_silently=False)
        print("ACCEPTED:", label)
    except Exception as e:
        print("REJECTED:", label, "->", repr(e))
