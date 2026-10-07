from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.contrib.auth import authenticate, login, logout
from django.core.mail import send_mail
from django.utils import timezone
from datetime import timedelta
from django.conf import settings
from django.views.decorators.cache import never_cache
import random
import re

from django.db.models import Q
from .models import OTP, Category
from admin_panel.product_management.models import Product


@never_cache
def home(request):
    categories = Category.objects.filter(is_active=True, is_deleted=False)
    featured_products = Product.objects.filter(
        is_active=True,
        is_deleted=False,
    ).filter(
        Q(category__isnull=True) | Q(category__is_active=True, category__is_deleted=False)
    ).prefetch_related('variants__images')[:6]

    context = {
        'categories': categories,
        'featured_products': featured_products,
    }
    if request.user.is_authenticated:
        from user.user_profile.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        context['profile'] = profile
    return render(request, "home.html", context)


@never_cache
def signup(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        full_name = request.POST.get("full_name", "").strip()
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")

        if not full_name:
            messages.error(request, "Full name is required.")
            return render(request, "signup.html")

        if len(full_name) < 3:
            messages.error(request, "Full name must contain at least 3 characters.")
            return render(request, "signup.html")

        if not re.match(r"^[A-Za-z ]+$", full_name):
            messages.error(request, "Full name should contain only letters and spaces.")
            return render(request, "signup.html")

        if not email:
            messages.error(request, "Email address is required.")
            return render(request, "signup.html")

        try:
            validate_email(email)
        except ValidationError:
            messages.error(request, "Enter a valid email address.")
            return render(request, "signup.html")
        
        existing_user = User.objects.filter(email=email).first()
        if existing_user:
            if existing_user.is_active:
                messages.error(request, "An account with this email already exists. Please sign in.")
                return render(request, "signup.html")
            else:
                
                existing_user.first_name = full_name
                existing_user.set_password(password)
                existing_user.save()
                user = existing_user
        else:
            if not password:
                messages.error(request, "Password is required.")
                return render(request, "signup.html")

            if len(password) < 8:
                messages.error(request, "Password must contain at least 8 characters.")
                return render(request, "signup.html")

            if not re.search(r"[A-Z]", password):
                messages.error(request, "Password must contain at least one uppercase letter.")
                return render(request, "signup.html")

            if not re.search(r"[a-z]", password):
                messages.error(request, "Password must contain at least one lowercase letter.")
                return render(request, "signup.html")

            if not re.search(r"[0-9]", password):
                messages.error(request, "Password must contain at least one number.")
                return render(request, "signup.html")

            if not confirm_password:
                messages.error(request, "Please confirm your password.")
                return render(request, "signup.html")

            if password != confirm_password:
                messages.error(request, "Passwords do not match.")
                return render(request, "signup.html")

            username = email.split("@")[0]
            original_username = username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{original_username}{counter}"
                counter += 1

            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=full_name,
                is_active=False
            )

        if existing_user:
            if not password or len(password) < 8 or not re.search(r"[A-Z]", password) or not re.search(r"[a-z]", password) or not re.search(r"[0-9]", password):
                messages.error(request, "Password must contain min 8 characters with uppercase, lowercase, and a number.")
                return render(request, "signup.html")
            if password != confirm_password:
                messages.error(request, "Passwords do not match.")
                return render(request, "signup.html")
            
        otp_code = str(random.randint(100000, 999999))

        OTP.objects.filter(user=user, is_used=False).delete()

        OTP.objects.create(
            user=user,
            code=otp_code,
            is_used=False,
            expired_at=timezone.now() + timedelta(minutes=2)
        )

        try:
            send_mail(
                subject="WEGNEX - Email Verification OTP",
                message=f"""Hello {user.first_name},

Welcome to WEGNEX!

Your OTP for email verification is:

{otp_code}

This OTP is valid for 2 minutes.
Please do not share this OTP with anyone.

Regards,
WEGNEX Team
""",
                from_email=None,
                recipient_list=[email],
                fail_silently=False
            )
        except Exception as e:
            print(f"Error sending email: {e}")
            messages.error(request, "Failed to send verification email. Please check your network and try again.")
            return render(request, "signup.html")

        request.session["signup_user_id"] = user.id
        request.session["signup_email"] = email

        messages.success(request, f"Verification code sent to {email}.")
        return redirect("otp")

    return render(request, "signup.html")


@never_cache
def otp_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    user_id = request.session.get("signup_user_id")

    if not user_id:
        messages.error(request, "Signup session expired. Please sign up again.")
        return redirect("signup")

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        messages.error(request, "User not found. Please sign up again.")
        return redirect("signup")

    email = request.session.get("signup_email", user.email)

    if request.method == "POST":
        otp1 = request.POST.get("otp1", "").strip()
        otp2 = request.POST.get("otp2", "").strip()
        otp3 = request.POST.get("otp3", "").strip()
        otp4 = request.POST.get("otp4", "").strip()
        otp5 = request.POST.get("otp5", "").strip()
        otp6 = request.POST.get("otp6", "").strip()

        entered_otp = otp1 + otp2 + otp3 + otp4 + otp5 + otp6

        if len(entered_otp) != 6 or not entered_otp.isdigit():
            messages.error(request, "Please enter the complete 6-digit OTP.")
            return render(request, "otp.html", {"email": email})

        otp = OTP.objects.filter(
            user=user,
            code=entered_otp,
            is_used=False
        ).order_by("-created_at").first()

        if not otp:
            messages.error(request, "Invalid OTP. Please try again.")
            return render(request, "otp.html", {"email": email})

        if timezone.now() > otp.expired_at:
            messages.error(request, "OTP has expired. Please request a new code.")
            return render(request, "otp.html", {"email": email})

        otp.is_used = True
        otp.save()

        user.is_active = True
        user.save()

        if "signup_user_id" in request.session:
            del request.session["signup_user_id"]
        if "signup_email" in request.session:
            del request.session["signup_email"]

        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, f"Welcome to WEGNEX, {user.first_name}! Your account has been verified successfully.")

        return redirect("home")

    return render(request, "otp.html", {"email": email})


@never_cache
def resend_otp(request):
    if request.user.is_authenticated:
        return redirect("home")

    user_id = request.session.get("signup_user_id")

    if not user_id:
        messages.error(request, "Signup session expired. Please sign up again.")
        return redirect("signup")

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        messages.error(request, "User not found. Please sign up again.")
        return redirect("signup")

    OTP.objects.filter(user=user, is_used=False).delete()

    otp_code = str(random.randint(100000, 999999))
    OTP.objects.create(
        user=user,
        code=otp_code,
        is_used=False,
        expired_at=timezone.now() + timedelta(minutes=2)
    )

    try:
        send_mail(
            subject="WEGNEX - New Verification OTP",
            message=f"""Hello {user.first_name},

Your new verification OTP is:

{otp_code}

This OTP is valid for 2 minutes.

Regards,
WEGNEX Team
""",
            from_email=None,
            recipient_list=[user.email],
            fail_silently=False
        )
        messages.success(request, f"A new verification code has been sent to {user.email}.")
    except Exception as e:
        print(f"Error resending OTP: {e}")
        messages.error(request, "Failed to send verification email. Please try again.")

    return redirect("otp")


@never_cache
def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")

        if not email:
            messages.error(request, "Email address is required.")
            return render(request, "login.html")

        if not password:
            messages.error(request, "Password is required.")
            return render(request, "login.html")

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            messages.error(request, "Invalid email or password.")
            return render(request, "login.html")

        authenticated_user = authenticate(
            request,
            username=user.username,
            password=password
        )

        if authenticated_user is not None:
            if not authenticated_user.is_active:
                OTP.objects.filter(user=authenticated_user, is_used=False).delete()
                otp_code = str(random.randint(100000, 999999))
                OTP.objects.create(
                    user=authenticated_user,
                    code=otp_code,
                    is_used=False,
                    expired_at=timezone.now() + timedelta(minutes=2)
                )
                try:
                    send_mail(
                        subject="WEGNEX - Activate Your Account",
                        message=f"Hello {authenticated_user.first_name},\n\nYour OTP to verify your account is: {otp_code}\n\nValid for 2 minutes.\n\nRegards,\nWEGNEX Team",
                        from_email=None,
                        recipient_list=[authenticated_user.email],
                        fail_silently=False
                    )
                except Exception:
                    pass
                request.session["signup_user_id"] = authenticated_user.id
                request.session["signup_email"] = authenticated_user.email
                messages.error(request, "Your account is not verified yet. A verification code has been sent to your email.")
                return redirect("otp")

            login(request, authenticated_user)
            messages.success(request, f"Welcome back, {authenticated_user.first_name or authenticated_user.username}!")
            return redirect("home")

        messages.error(request, "Invalid email or password.")
        return render(request, "login.html")

    return render(request, "login.html")


@never_cache
def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect("login")


@never_cache
def forgot_view(request):
    if request.user.is_authenticated:
        return redirect("home")
    return render(request, "forgotpass.html")


@never_cache
def resetpass_view(request):
    if request.user.is_authenticated:
        return redirect("home")
    return render(request, "resetpass.html")