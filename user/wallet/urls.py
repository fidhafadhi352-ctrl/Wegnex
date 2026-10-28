from django.urls import path
from . import views

urlpatterns = [
    path('wallet/', views.wallet, name="wallet"),
    path('wallet/razorpay/create_order/', views.wallet_create_order, name="wallet_create_order"),
    path('wallet/razorpay/verify/', views.wallet_verify_payment, name="wallet_verify_payment"),
]
