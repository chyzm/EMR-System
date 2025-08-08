# from django.core.management.base import BaseCommand
# from django.utils import timezone
# from datetime import date
# from django.urls import reverse
# from DurielMedicApp.models import Billing, Notification

# class Command(BaseCommand):
#     help = 'Checks for overdue bills and creates notifications'

#     def handle(self, *args, **options):
#         overdue_bills = Billing.objects.filter(
#             due_date__lt=date.today(),
#             status__in=['PENDING', 'PARTIAL']
#         )
        
#         for bill in overdue_bills:
#             Notification.objects.create(
#                 user=bill.patient.created_by,
#                 message=f"Overdue bill for {bill.patient.full_name} - ₦{bill.get_balance()}",
#                 link=reverse('DurielMedicApp:view_bill', kwargs={'pk': bill.pk})
#             )
        
#         self.stdout.write(self.style.SUCCESS(f'Created notifications for {overdue_bills.count()} overdue bills'))