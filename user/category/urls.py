from django.urls import path
from . import views

urlpatterns = [
    path('category/', views.category, name='category'),
    path('category/<int:category_id>/', views.category_products, name='category_products'),
]
