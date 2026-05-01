from sellers.models import Dispute, Order
def admin_badge_counts(request):
      if not (request.user.is_authenticated and request.user.is_staff):
          return {}
      return {
          'open_disputes_count': Dispute.objects.filter(
              status__in=['open', 'vendor_replied', 'under_review']
          ).count(),
          'pending_payouts_count': Order.objects.filter(
              payout_triggered=False,
              status__in=['delivered', 'completed']
           ).count(),
       }