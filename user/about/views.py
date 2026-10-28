from django.shortcuts import render
from django.views.decorators.cache import never_cache


@never_cache
def about(request):
    context = {}
    if request.user.is_authenticated:
        from user.user_profile.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        context['profile'] = profile
    return render(request, "about.html", context)