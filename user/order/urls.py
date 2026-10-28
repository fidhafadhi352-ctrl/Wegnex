from django.urls import path
from . import views

urlpatterns = [
    path('order/', views.order, name="order"),
    path('orders/', views.order, name="orders"),
    path('order_view/', views.order_view, name="order_view"),
    path('order_view/<str:order_number>/', views.order_view, name="order_view_detail"),
    path('order_view/cancel-item/<int:item_id>/', views.cancel_order_item, name="cancel_order_item"),
    path('download-invoice/<str:order_number>/', views.download_invoice_pdf, name="download_invoice_pdf"),
]
