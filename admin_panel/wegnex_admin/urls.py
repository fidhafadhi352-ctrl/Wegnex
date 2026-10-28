from django.urls import path
from . import views

urlpatterns = [
    path('', views.admin_dashboard, name="admin_root"),
    path('admin_login/', views.admin_login, name="admin_login"),
    path('admin_logout/', views.admin_logout, name="admin_logout"),
    path('admin_dashboard/', views.admin_dashboard, name="admin_dashboard"),
    path('sales_report/', views.sales_report,name="sales_report"),
    
   
      
]