from django.urls import path
from . import views

urlpatterns = [
    path('product_list/', views.product_list, name='product_list'),
    path('product/<int:product_id>/', views.product_detail, name='product_detail'),
    path('product_details/<int:product_id>/', views.product_details, name='product_details_with_id'),
    path('product_details/', views.product_details, name='product_details'),
    path('product_filter/', views.product_filter, name='product_filter'),
]