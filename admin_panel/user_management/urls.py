from django.urls import path
from . import views

urlpatterns = [
    path('user_management/',views.user_management,name="user_management"),
    path('admin_user/',views.admin_user,name="admin_user"),
]
