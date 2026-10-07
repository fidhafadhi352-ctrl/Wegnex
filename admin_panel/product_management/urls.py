from django.urls import path
from . import views

urlpatterns = [
    # Page 1 — Product list
    path('', views.product_list, name='admin_product_list'),
    path('add/', views.add_product, name='add_product'),
    path('edit/<int:product_id>/', views.edit_product, name='edit_product'),
    path('delete/<int:product_id>/', views.delete_product, name='delete_product'),
    path('toggle-status/<int:product_id>/', views.toggle_product_status, name='toggle_product_status'),
    path('json/<int:product_id>/', views.get_product_json, name='product_json'),

    # Page 2 — Variant management per product
    path('<int:product_id>/variants/', views.variant_management, name='variant_management'),
    path('<int:product_id>/variants/add/', views.add_variant, name='add_variant'),
    path('<int:product_id>/variants/edit/<int:variant_id>/', views.edit_variant, name='edit_variant'),
    path('<int:product_id>/variants/delete/<int:variant_id>/', views.delete_variant, name='delete_variant'),
    path('<int:product_id>/variants/toggle/<int:variant_id>/', views.toggle_variant_status, name='toggle_variant_status'),
    path('<int:product_id>/variants/set-default/<int:variant_id>/', views.set_default_variant, name='set_default_variant'),
]
