from django.urls import path
from . import views

urlpatterns = [
    path('order_management/', views.order_management, name="order_management"),
    path('orders/', views.order_management, name="orders"),
    path('order_details/<str:order_number>/', views.order_details, name="order_details"),
    path('order_details/', views.order_details, name="order_details_default"),
    path('order_status_update/<str:order_number>/', views.update_order_status, name="update_order_status"),
    path('order_status_update/', views.update_order_status, name="update_order_status_post"),
    path('order_return_refund/<int:item_id>/', views.approve_return_refund, name="approve_return_refund"),
    path('order_return_reject/<int:item_id>/', views.reject_return_request, name="reject_return_request"),
    path('order_return_refund_all/<str:order_number>/', views.approve_all_returns_for_order, name="approve_all_returns_for_order"),
    path('order_return_reject_all/<str:order_number>/', views.reject_all_returns_for_order, name="reject_all_returns_for_order"),
]
