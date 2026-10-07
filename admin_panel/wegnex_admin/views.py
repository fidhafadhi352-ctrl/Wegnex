from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.contrib import messages
from django.views.decorators.cache import never_cache
from user.account.models import Category


@never_cache
def admin_login(request):

    if request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser):
        return redirect("admin_dashboard")

    if request.method == "POST":
        identifier = request.POST.get("email", "").strip() or request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        if not identifier:
            messages.error(request, "Email address or username is required.")
            return render(request, "admin_login.html")


        if not password:
            messages.error(request, "Password is required.")
            return render(request, "admin_login.html", {"identifier": identifier})

        user = User.objects.filter(email__iexact=identifier).first()
        if not user:
            user = User.objects.filter(username__iexact=identifier).first()

        if not user:
            messages.error(request, "Invalid administrator credentials.")
            return render(request, "admin_login.html", {"identifier": identifier})

        if not user.is_staff and not user.is_superuser:
            messages.error(request, "You are not authorized to access the administrator panel.")
            return render(request, "admin_login.html", {"identifier": identifier})
        
        if not user.is_active:
            messages.error(request, "This administrator account has been deactivated.")
            return render(request, "admin_login.html", {"identifier": identifier})

        if not user.check_password(password):
            messages.error(request, "Invalid administrator credentials.")
            return render(request, "admin_login.html", {"identifier": identifier})

        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        messages.success(request, f"Welcome back, {user.first_name or user.username}!")
        return redirect("admin_dashboard")

    return render(request, "admin_login.html")


@never_cache
def admin_logout(request):
    logout(request)
    messages.success(request, "You have been logged out of the administrator portal.")
    return redirect("admin_login")


@never_cache
def admin_dashboard(request):

    if not request.user.is_authenticated or (not request.user.is_staff and not request.user.is_superuser):
        messages.error(request, "Please log in with administrator privileges.")
        return redirect("admin_login")

    if not request.user.is_active:
        return redirect("admin_login")

   
    customers_qs = User.objects.filter(is_staff=False, is_superuser=False).select_related('profile')
    total_customers = customers_qs.count()
    active_users = customers_qs.filter(is_active=True).count()
    blocked_users = customers_qs.filter(is_active=False).count()

    recent_customers = customers_qs.order_by('-date_joined')[:8]

    categories_qs = Category.objects.filter(is_deleted=False).order_by('-created_at')
    total_categories = categories_qs.count()
    active_categories = categories_qs.filter(is_active=True).count()
    categories_list = categories_qs[:6]

    return render(request, "admin_dashboard.html", {
        "admin_user": request.user,
        "total_customers": total_customers,
        "active_users": active_users,
        "blocked_users": blocked_users,
        "recent_customers": recent_customers,
        "total_categories": total_categories,
        "active_categories": active_categories,
        "categories_list": categories_list,
    })

