from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("signup/", views.signup, name="signup"),
    path("login/", views.login_view, name="login"),
    path("otp/", views.otp_view, name="otp"),
    path("resend-otp/", views.resend_otp, name="resend_otp"),
    path("logout/", views.logout_view, name="logout"),
    path("forgotpass/", views.forgot_view, name="forgotpass"),
    path("resetpass/", views.resetpass_view, name="resetpass"),
]