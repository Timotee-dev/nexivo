from .models import Notification
def ctx(request):
    if request.user.is_authenticated:
        unread = Notification.objects.filter(user=request.user, is_read=False).count()
        notifs = Notification.objects.filter(user=request.user)[:6]
        return {'unread_count': unread, 'recent_notifs': notifs}
    return {'unread_count': 0, 'recent_notifs': []}
