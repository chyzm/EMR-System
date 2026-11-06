from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class PublicPagesSitemap(Sitemap):
    protocol = "https"
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return [
            "core:home",
            "core:hospital_software",
            "core:eye_clinic_software",
            "core:dental_clinic_software",
            "core:contact_form",
            "core:terms",
            "core:privacy",
        ]

    def location(self, item):
        return reverse(item)