from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.db.models import Avg

from .models import Review


@staff_member_required
def review_management(request):
    reviews = Review.objects.select_related('user', 'product').order_by('-id')

    total_reviews = reviews.count()
    avg_rating_val = reviews.aggregate(Avg('rating'))['rating__avg']
    avg_rating = round(avg_rating_val, 1) if avg_rating_val else 0.0
    pending_count = reviews.filter(status__iexact='pending').count()
    approved_count = reviews.filter(status__iexact='approved').count()
    rejected_count = reviews.filter(status__iexact='rejected').count()

    return render(
        request,
        "review_management.html",
        {
            "reviews": reviews,
            "total_reviews": total_reviews,
            "avg_rating": avg_rating,
            "pending_count": pending_count,
            "approved_count": approved_count,
            "rejected_count": rejected_count,
        }
    )


@staff_member_required
@require_POST
def approve_review(request, review_id):
    review = get_object_or_404(Review, id=review_id)
    review.status = "approved"
    review.save()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success', 'new_status': 'Approved', 'review_id': review_id})

    messages.success(request, "Review approved successfully.")
    return redirect("review_management")


@staff_member_required
@require_POST
def set_pending_review(request, review_id):
    review = get_object_or_404(Review, id=review_id)
    review.status = "pending"
    review.save()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success', 'new_status': 'Pending', 'review_id': review_id})

    messages.success(request, "Review set to pending.")
    return redirect("review_management")


@staff_member_required
@require_POST
def reject_review(request, review_id):
    review = get_object_or_404(Review, id=review_id)
    review.status = "rejected"
    review.save()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success', 'new_status': 'Rejected', 'review_id': review_id})

    messages.success(request, "Review rejected.")
    return redirect("review_management")


@staff_member_required
@require_POST
def delete_review(request, review_id):
    review = get_object_or_404(Review, id=review_id)
    review.delete()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success', 'action': 'deleted', 'review_id': review_id})

    messages.success(request, "Review deleted successfully.")
    return redirect("review_management")
