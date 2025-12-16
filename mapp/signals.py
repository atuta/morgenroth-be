from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.utils import timezone

from mapp.models import CustomUser, StatutoryDeduction, HourlyRateSnapshot, StatutoryDeductionSnapshot

@receiver(pre_save, sender=StatutoryDeduction)
def track_statutory_deduction_change(sender, instance, **kwargs):
    if not instance.pk:
        return  # new record handled elsewhere if needed

    try:
        old = StatutoryDeduction.objects.get(pk=instance.pk)
    except StatutoryDeduction.DoesNotExist:
        return

    if old.percentage == instance.percentage:
        return  # no change

    now = timezone.now()

    # Close previous active snapshot
    StatutoryDeductionSnapshot.objects.filter(
        deduction=instance,
        effective_to__isnull=True
    ).update(effective_to=now)

    # Create new snapshot
    StatutoryDeductionSnapshot.objects.create(
        deduction=instance,
        percentage=instance.percentage,
        effective_from=now,
    )

@receiver(pre_save, sender=CustomUser)
def track_hourly_rate_change(sender, instance, **kwargs):
    if not instance.pk:
        return  # new user, handle elsewhere if needed

    try:
        old = CustomUser.objects.get(pk=instance.pk)
    except CustomUser.DoesNotExist:
        return

    if old.hourly_rate == instance.hourly_rate:
        return  # no change, do nothing

    now = timezone.now()

    # Close previous active snapshot
    HourlyRateSnapshot.objects.filter(
        user=instance,
        effective_to__isnull=True
    ).update(effective_to=now)

    # Create new snapshot
    HourlyRateSnapshot.objects.create(
        user=instance,
        hourly_rate=instance.hourly_rate,
        currency=instance.hourly_rate_currency,
        effective_from=now,
    )
