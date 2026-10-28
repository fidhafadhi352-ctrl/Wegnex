from django.urls import path
from . import views

urlpatterns = [
    path("coupon/", views.coupon, name="coupon"),
    path("coupon/create/", views.create_coupon, name="create_coupon"),
    path("coupon/delete/<int:coupon_id>/", views.delete_coupon, name="delete_coupon"),
]
