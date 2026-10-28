from django.urls import path
from . import views

urlpatterns = [
    path('offer/', views.offer, name="offer.html"),
    path('offer/list/', views.offer, name="offer"),
    path('offer/add/', views.add_offer, name="add_offer"),
    path('offer/edit/<int:offer_id>/', views.edit_offer, name="edit_offer"),
    path('offer/toggle/<int:offer_id>/', views.toggle_offer_status, name="toggle_offer_status"),
    path('offer/delete/<int:offer_id>/', views.delete_offer, name="delete_offer"),
]
