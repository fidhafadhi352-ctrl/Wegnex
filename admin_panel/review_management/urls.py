from django.urls import path
from . import views

urlpatterns = [
    path('review_management/', views.review_management, name="review_management"),
    path('review_management/<int:review_id>/approve/', views.approve_review, name='approve_review'),
    path('review_management/<int:review_id>/pending/', views.set_pending_review, name='set_pending_review'),
    path('review_management/<int:review_id>/reject/', views.reject_review, name='reject_review'),
    path('review_management/<int:review_id>/delete/', views.delete_review, name='delete_review'),
]
