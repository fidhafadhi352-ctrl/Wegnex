from django.urls import path
from . import views

urlpatterns = [
    path('category_management/', views.category_management, name='category_management'),
    path('category_management/add/', views.add_category, name='add_category'),
    path('category_management/edit/<int:category_id>/', views.edit_category, name='edit_category'),
    path('category_management/delete/<int:category_id>/', views.delete_category, name='delete_category'),
    path('category_management/restore/<int:category_id>/', views.restore_category, name='restore_category'),
    path('category_management/toggle-status/<int:category_id>/', views.toggle_category_status, name='toggle_category_status'),
]
