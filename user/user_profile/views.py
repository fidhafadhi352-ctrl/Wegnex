from django.shortcuts import render, redirect
from django.contrib.auth import logout
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.views.decorators.cache import never_cache
from datetime import timedelta
import random
import re

from .models import UserProfile
from user.account.models import OTP


@never_cache
def profile_view(request):
    if not request.user.is_authenticated:
        messages.error(request, "Please sign in to view your profile.")
        return redirect("login")

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    return render(request, "profile.html", {
        "user": request.user,
        "profile": profile,
    })


@never_cache
def editprofile_view(request):
    if not request.user.is_authenticated:
        messages.error(request, "Please sign in to edit your profile.")
        return redirect("login")

    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        full_name = request.POST.get("full_name", "").strip()
        phone_number = request.POST.get("phone_number", "").strip()
        email = request.POST.get("email", "").strip().lower()

        if not full_name:
            messages.error(request, "Full name is required.")
            return render(request, "edit_profile.html", {"user": request.user, "profile": profile})

        if len(full_name) < 3:
            messages.error(request, "Full name must be at least 3 characters long.")
            return render(request, "edit_profile.html", {"user": request.user, "profile": profile})

        if not re.match(r"^[A-Za-z ]+$", full_name):
            messages.error(request, "Full name should contain only letters and spaces.")
            return render(request, "edit_profile.html", {"user": request.user, "profile": profile})

        if not email:
            messages.error(request, "Email address is required.")
            return render(request, "edit_profile.html", {"user": request.user, "profile": profile})

        try:
            validate_email(email)
        except ValidationError:
            messages.error(request, "Please enter a valid email address.")
            return render(request, "edit_profile.html", {"user": request.user, "profile": profile})
        
        if phone_number:
            cleaned_phone = re.sub(r"[\s\-\(\)\+]", "", phone_number)
            if cleaned_phone.startswith("91") and len(cleaned_phone) == 12:
                cleaned_phone = cleaned_phone[2:]
            if not re.match(r"^[6-9]\d{9}$", cleaned_phone):
                messages.error(request, "Please enter a valid 10-digit mobile number (e.g. 9876543210).")
                return render(request, "edit_profile.html", {"user": request.user, "profile": profile})
            phone_number = cleaned_phone

        is_email_changed = (email != request.user.email.lower())

        if is_email_changed:
            if User.objects.filter(email=email).exclude(id=request.user.id).exists():
                messages.error(request, "This email address is already in use by another account.")
                return render(request, "edit_profile.html", {"user": request.user, "profile": profile})

        request.user.first_name = full_name
        request.user.save()

        profile.phone_number = phone_number

        if request.FILES.get("profile_picture"):
            uploaded_file = request.FILES["profile_picture"]
            if uploaded_file.size > 5 * 1024 * 1024:
                messages.error(request, "Profile picture size must not exceed 5 MB.")
                return render(request, "edit_profile.html", {"user": request.user, "profile": profile})
            if not uploaded_file.content_type.startswith("image/"):
                messages.error(request, "Please upload a valid image file (JPG, PNG, GIF, WEBP).")
                return render(request, "edit_profile.html", {"user": request.user, "profile": profile})

        remove_pic = (request.POST.get("remove_profile_picture") == "1")
        new_pic = request.FILES.get("profile_picture")

        if remove_pic and not new_pic:
            if profile.profile_picture:
                profile.profile_picture.delete(save=False)
            profile.profile_picture = None
        elif new_pic:
            if profile.profile_picture:
                profile.profile_picture.delete(save=False)
            profile.profile_picture = new_pic

        profile.save()

        if is_email_changed:
            otp_code = str(random.randint(100000, 999999))

            OTP.objects.filter(user=request.user, is_used=False).delete()

            OTP.objects.create(
                user=request.user,
                code=otp_code,
                is_used=False,
                expired_at=timezone.now() + timedelta(minutes=2)
            )

            request.session["pending_new_email"] = email

            try:
                send_mail(
                    subject="WEGNEX - Verify Your New Email Address",
                    message=f"""Hello {request.user.first_name or request.user.username},

You requested to change your WEGNEX account email to: {email}
Your 6-digit verification code is: {otp_code}

This code is valid for 2 minutes.
If you did not request this change, please ignore this email.

Regards,
WEGNEX Team
""",
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=False,
                )
            except Exception as e:
                print(f"Error sending OTP verification email: {e}")
                messages.error(request, "Failed to send verification email. Please check your network and try again.")
                return render(request, "edit_profile.html", {"user": request.user, "profile": profile})

            messages.success(request, f"Verification code sent to {email}. Please enter it to confirm your new email.")
            return redirect("otpprofile")

        messages.success(request, "Profile updated successfully!")
        return redirect("profile")

    return render(request, "edit_profile.html", {
        "user": request.user,
        "profile": profile,
    })


@never_cache
def changepass_view(request):
    if not request.user.is_authenticated:
        messages.error(request, "Please sign in to change your password.")
        return redirect("login")

    if request.method == "POST":
        current_password = request.POST.get("current_password", "")
        new_password = request.POST.get("new_password", "")
        confirm_password = request.POST.get("confirm_password", "")

        if not current_password:
            messages.error(request, "Current password is required.")
            return render(request, "change_profile_pass.html", {"user": request.user})

        if not request.user.check_password(current_password):
            messages.error(request, "Incorrect current password.")
            return render(request, "change_profile_pass.html", {"user": request.user})
        
        if not new_password:
            messages.error(request, "New password is required.")
            return render(request, "change_profile_pass.html", {"user": request.user})

        if len(new_password) < 8:
            messages.error(request, "New password must contain at least 8 characters.")
            return render(request, "change_profile_pass.html", {"user": request.user})

        if not re.search(r"[A-Z]", new_password):
            messages.error(request, "New password must contain at least one uppercase letter.")
            return render(request, "change_profile_pass.html", {"user": request.user})

        if not re.search(r"[a-z]", new_password):
            messages.error(request, "New password must contain at least one lowercase letter.")
            return render(request, "change_profile_pass.html", {"user": request.user})

        if not re.search(r"[0-9]", new_password):
            messages.error(request, "New password must contain at least one number.")
            return render(request, "change_profile_pass.html", {"user": request.user})

        if current_password == new_password:
            messages.error(request, "New password cannot be the same as your current password.")
            return render(request, "change_profile_pass.html", {"user": request.user})

        if not confirm_password:
            messages.error(request, "Please confirm your new password.")
            return render(request, "change_profile_pass.html", {"user": request.user})

        if new_password != confirm_password:
            messages.error(request, "New passwords do not match.")
            return render(request, "change_profile_pass.html", {"user": request.user})

        request.user.set_password(new_password)
        request.user.save()

        from django.contrib.auth import update_session_auth_hash
        update_session_auth_hash(request, request.user)

        messages.success(request, "Your password has been updated successfully!")
        return redirect("profile")

    return render(request, "change_profile_pass.html", {"user": request.user})


@never_cache
def forgotpass_view(request):
    default_email = request.user.email if request.user.is_authenticated else ""

    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()

        if not email:
            messages.error(request, "Please enter your registered email address.")
            return render(request, "forgot_profile_pass.html", {"default_email": default_email})

        try:
            validate_email(email)
        except ValidationError:
            messages.error(request, "Please enter a valid email address.")
            return render(request, "forgot_profile_pass.html", {"default_email": email})

        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if not user:
            messages.error(request, "No active account found with this email address.")
            return render(request, "forgot_profile_pass.html", {"default_email": email})

        otp_code = str(random.randint(100000, 999999))
        OTP.objects.filter(user=user, is_used=False).delete()
        OTP.objects.create(
            user=user,
            code=otp_code,
            is_used=False,
            expired_at=timezone.now() + timedelta(minutes=5)
        )

        try:
            send_mail(
                subject="WEGNEX - Password Reset Code",
                message=f"""Hello {user.first_name or user.username},

You requested to reset your WEGNEX account password.
Your 6-digit verification code is: {otp_code}

This code is valid for 5 minutes.
If you did not request this, please ignore this email.

Regards,
WEGNEX Team
""",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
        except Exception as e:
            print(f"Error sending password reset email: {e}")
            messages.error(request, f"Failed to send reset code: {e}")
            return render(request, "forgot_profile_pass.html", {"default_email": email})

        request.session["reset_pass_user_id"] = user.id
        request.session["reset_pass_email"] = email

        messages.success(request, f"A 6-digit reset code has been sent to {email}.")
        return redirect("verify_reset_otp")

    return render(request, "forgot_profile_pass.html", {"default_email": default_email})


@never_cache
def otpprofile_view(request):
    if not request.user.is_authenticated:
        messages.error(request, "Please sign in to verify your email.")
        return redirect("login")

    new_email = request.session.get("pending_new_email")
    if not new_email:
        messages.error(request, "No pending email change request found.")
        return redirect("editprofile")

    if request.method == "POST":
        otp1 = request.POST.get("otp1", "").strip()
        otp2 = request.POST.get("otp2", "").strip()
        otp3 = request.POST.get("otp3", "").strip()
        otp4 = request.POST.get("otp4", "").strip()
        otp5 = request.POST.get("otp5", "").strip()
        otp6 = request.POST.get("otp6", "").strip()

        entered_otp = otp1 + otp2 + otp3 + otp4 + otp5 + otp6

        if len(entered_otp) != 6 or not entered_otp.isdigit():
            messages.error(request, "Please enter the complete 6-digit verification code.")
            return render(request, "profile_otp_verify.html", {"new_email": new_email})

        otp = OTP.objects.filter(
            user=request.user,
            code=entered_otp,
            is_used=False
        ).order_by("-created_at").first()

        if not otp:
            messages.error(request, "Invalid verification code. Please check and try again.")
            return render(request, "profile_otp_verify.html", {"new_email": new_email})

        if timezone.now() > otp.expired_at:
            messages.error(request, "Verification code has expired. Please click 'Resend Code'.")
            return render(request, "profile_otp_verify.html", {"new_email": new_email})

        otp.is_used = True
        otp.save()

        if User.objects.filter(email=new_email).exclude(id=request.user.id).exists():
            messages.error(request, "This email address was claimed by another account. Please use a different email.")
            if "pending_new_email" in request.session:
                del request.session["pending_new_email"]
            return redirect("editprofile")

        request.user.email = new_email
        request.user.save()

        if "pending_new_email" in request.session:
            del request.session["pending_new_email"]

        messages.success(request, f"Your email address has been successfully updated to {new_email}!")
        return redirect("profile")

    return render(request, "profile_otp_verify.html", {"new_email": new_email})


@never_cache
def resend_profile_otp(request):
    if not request.user.is_authenticated:
        messages.error(request, "Please sign in to resend code.")
        return redirect("login")

    new_email = request.session.get("pending_new_email")
    if not new_email:
        messages.error(request, "No pending email change request found.")
        return redirect("editprofile")

    otp_code = str(random.randint(100000, 999999))
    OTP.objects.filter(user=request.user, is_used=False).delete()
    OTP.objects.create(
        user=request.user,
        code=otp_code,
        is_used=False,
        expired_at=timezone.now() + timedelta(minutes=2)
    )

    try:
        send_mail(
            subject="WEGNEX - Resend Email Verification Code",
            message=f"""Hello {request.user.first_name or request.user.username},

Your new 6-digit verification code is: {otp_code}

This code is valid for 2 minutes.

Regards,
WEGNEX Team
""",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[new_email],
            fail_silently=False,
        )
        messages.success(request, f"A new verification code has been sent to {new_email}.")
    except Exception as e:
        print(f"Error resending OTP: {e}")
        messages.error(request, "Failed to resend verification email. Please check your network and try again.")

    return redirect("otpprofile")


@never_cache
def verify_reset_otp_view(request):
    user_id = request.session.get("reset_pass_user_id")
    email = request.session.get("reset_pass_email", "")

    if not user_id:
        messages.error(request, "Session expired. Please start the reset process again.")
        return redirect("profile_forgotpass")

    try:
        user = User.objects.get(id=user_id, is_active=True)
    except User.DoesNotExist:
        messages.error(request, "User not found. Please try again.")
        return redirect("profile_forgotpass")

    if request.method == "POST":
        otp1 = request.POST.get("otp1", "").strip()
        otp2 = request.POST.get("otp2", "").strip()
        otp3 = request.POST.get("otp3", "").strip()
        otp4 = request.POST.get("otp4", "").strip()
        otp5 = request.POST.get("otp5", "").strip()
        otp6 = request.POST.get("otp6", "").strip()

        entered_otp = otp1 + otp2 + otp3 + otp4 + otp5 + otp6

        if len(entered_otp) != 6 or not entered_otp.isdigit():
            messages.error(request, "Please enter the complete 6-digit reset code.")
            return render(request, "verify_reset_otp.html", {"email": email})

        otp = OTP.objects.filter(
            user=user,
            code=entered_otp,
            is_used=False
        ).order_by("-created_at").first()

        if not otp:
            messages.error(request, "Invalid code. Please check and try again.")
            return render(request, "verify_reset_otp.html", {"email": email})

        if timezone.now() > otp.expired_at:
            messages.error(request, "Code has expired. Please request a new one.")
            return render(request, "verify_reset_otp.html", {"email": email})

        otp.is_used = True
        otp.save()

        
        request.session["reset_pass_verified"] = True

        return redirect("resetprofilepass")

    return render(request, "verify_reset_otp.html", {"email": email})


@never_cache
def resend_reset_otp(request):
    user_id = request.session.get("reset_pass_user_id")
    email = request.session.get("reset_pass_email", "")

    if not user_id or not email:
        messages.error(request, "Session expired. Please start the reset process again.")
        return redirect("profile_forgotpass")

    try:
        user = User.objects.get(id=user_id, is_active=True)
    except User.DoesNotExist:
        return redirect("profile_forgotpass")

    otp_code = str(random.randint(100000, 999999))
    OTP.objects.filter(user=user, is_used=False).delete()
    OTP.objects.create(
        user=user,
        code=otp_code,
        is_used=False,
        expired_at=timezone.now() + timedelta(minutes=5)
    )

    try:
        send_mail(
            subject="WEGNEX - Resend Password Reset Code",
            message=f"""Hello {user.first_name or user.username},

Your new 6-digit password reset code is: {otp_code}

This code is valid for 5 minutes.

Regards,
WEGNEX Team
""",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )
        messages.success(request, f"A new reset code has been sent to {email}.")
    except Exception as e:
        print(f"Error resending reset OTP: {e}")
        messages.error(request, "Failed to resend reset code. Please try again.")

    return redirect("verify_reset_otp")


@never_cache
def resetprofilepass_view(request):
    if not request.session.get("reset_pass_verified"):
        messages.error(request, "Please verify your identity first.")
        return redirect("profile_forgotpass")

    user_id = request.session.get("reset_pass_user_id")
    if not user_id:
        messages.error(request, "Session expired. Please start the reset process again.")
        return redirect("profile_forgotpass")

    try:
        user = User.objects.get(id=user_id, is_active=True)
    except User.DoesNotExist:
        messages.error(request, "User not found. Please try again.")
        return redirect("profile_forgotpass")

    if request.method == "POST":
        new_password = request.POST.get("new_password", "")
        confirm_password = request.POST.get("confirm_password", "")

        if not new_password:
            messages.error(request, "New password is required.")
            return render(request, "reset_profile_pass.html")

        if len(new_password) < 8:
            messages.error(request, "Password must contain at least 8 characters.")
            return render(request, "reset_profile_pass.html")

        if not re.search(r"[A-Z]", new_password):
            messages.error(request, "Password must contain at least one uppercase letter.")
            return render(request, "reset_profile_pass.html")

        if not re.search(r"[a-z]", new_password):
            messages.error(request, "Password must contain at least one lowercase letter.")
            return render(request, "reset_profile_pass.html")

        if not re.search(r"[0-9]", new_password):
            messages.error(request, "Password must contain at least one number.")
            return render(request, "reset_profile_pass.html")

        if not confirm_password:
            messages.error(request, "Please confirm your new password.")
            return render(request, "reset_profile_pass.html")

        if new_password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, "reset_profile_pass.html")

        user.set_password(new_password)
        user.save()

        for key in ["reset_pass_verified", "reset_pass_user_id", "reset_pass_email"]:
            request.session.pop(key, None)

        messages.success(request, "Your password has been reset successfully! Please sign in.")
        return redirect("login")

    return render(request, "reset_profile_pass.html")


@never_cache
def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect("login")