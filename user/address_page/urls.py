from django.urls import path
from . import views

urlpatterns = [
    path('address/', views.address, name="address"),
    path('add_address/', views.add_address, name="add_address"),
    path('edit_address/<int:address_id>/', views.edit_address, name="edit_address"),
    path('edit_address/', views.address, name="edit_address_fallback"),
    path('delete_address/<int:address_id>/', views.delete_address, name="delete_address"),
    path('delete_address/', views.address, name="delete_address_fallback"),
    path('set_default_address/<int:address_id>/', views.set_default_address, name="set_default_address"),
]