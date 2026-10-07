"""
URL configuration for wegnex project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

# Short-path aliases so /admin_login/ and /admin_dashboard/ work directly
from admin_panel.wegnex_admin import views as admin_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('', include('user.account.urls')),
    path('', include('user.user_profile.urls')),
    path('',include('user.address_page.urls')),
    path('',include('user.product_list.urls')),
    path('',include('user.category.urls')),
    path('admin_panel/',include('admin_panel.category_management.urls')),
    path('admin_panel/product_management/', include('admin_panel.product_management.urls')),
    path('admin_panel/', include('admin_panel.wegnex_admin.urls')),
    path('admin_login/', admin_views.admin_login,     name='admin_login_short'),
    path('admin_dashboard/', admin_views.admin_dashboard, name='admin_dashboard_short'),
    path('admin_logout/', admin_views.admin_logout,   name='admin_logout_short'),
    
    
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

