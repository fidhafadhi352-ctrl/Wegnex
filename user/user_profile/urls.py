from django.urls import path
from . import views


urlpatterns = [
    path("profile/",views.profile_view,name="profile"),
    path("editprofile/",views.editprofile_view,name="editprofile"),
    path("changepass/",views.changepass_view,name="changepass"),
    path("profile-forgotpass/",views.forgotpass_view,name="profile_forgotpass"),
    path("verify-reset-otp/",views.verify_reset_otp_view,name="verify_reset_otp"),
    path("resend-reset-otp/",views.resend_reset_otp,name="resend_reset_otp"),
    path("resetprofilepass/",views.resetprofilepass_view,name="resetprofilepass"),
    path("otpprofile/",views.otpprofile_view,name="otpprofile"),
    path("resend-profile-otp/",views.resend_profile_otp,name="resend_profile_otp"),
    path("logout/",views.logout_view,name="logout"),
]
