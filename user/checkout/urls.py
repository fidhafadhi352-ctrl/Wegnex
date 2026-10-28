from django.urls import path
from . import views

urlpatterns = [
    path('checkout/', views.checkout, name="checkout"),
    path('checkout/place_order/', views.place_order, name="place_order"),
    path('checkout/razorpay/create_order/', views.razorpay_create_order, name="razorpay_create_order"),
    path('checkout/razorpay/verify/', views.razorpay_verify_payment, name="razorpay_verify_payment"),
    path('checkout/razorpay/failed/', views.razorpay_payment_failed, name="razorpay_payment_failed"),
    path('order_success/<str:order_number>/', views.order_success, name="order_success"),
    path('order_fail/<str:order_number>/', views.order_fail, name="order_fail"),
    path('order_fail/', views.order_fail, name="order_fail_general"),
    path('order_detail/<str:order_number>/', views.order_detail, name="order_detail"),
    path('checkout/address/add/', views.add_checkout_address, name="add_checkout_address"),
    path('checkout/address/edit/<int:address_id>/', views.edit_checkout_address, name="edit_checkout_address"),
    path('checkout/address/delete/<int:address_id>/', views.delete_checkout_address, name="delete_checkout_address"),
    path('checkout/address/set_default/<int:address_id>/', views.set_default_checkout_address, name="set_default_checkout_address"),
    path('checkout/coupon/apply/', views.apply_coupon, name="apply_coupon"),
    path('checkout/coupon/remove/', views.remove_coupon, name="remove_coupon"),
]
