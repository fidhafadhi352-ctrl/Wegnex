from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
import datetime

from admin_panel.wegnex_admin.models import Coupon


def coupon(request):
    coupons = Coupon.objects.all().order_by("-created_at")
    active_count = coupons.filter(is_active=True).count()
    total_usage = sum(c.used_count for c in coupons)
    return render(request, "coupon.html", {
        "coupons": coupons,
        "active_count": active_count,
        "total_usage": total_usage,
    })


@require_POST
def create_coupon(request):
    errors = {}

    code = request.POST.get("code", "").strip().upper()
    discount_type = request.POST.get("discount_type", "percentage")
    discount_value_str = request.POST.get("discount_value", "")
    minimum_order_str = request.POST.get("minimum_order_amount", "0")
    maximum_discount_str = request.POST.get("maximum_discount_amount", "")
    usage_limit_str = request.POST.get("usage_limit", "")
    valid_from_str = request.POST.get("valid_from", "")
    valid_until_str = request.POST.get("valid_until", "")
    is_active = request.POST.get("is_active", "true") == "true"

    if not code:
        errors["code"] = "Coupon code is required."
    elif len(code) > 30:
        errors["code"] = "Code must be 30 characters or fewer."
    elif Coupon.objects.filter(code=code).exists():
        errors["code"] = "Coupon code already exists."

    if discount_type not in ("percentage", "fixed"):
        errors["discount_type"] = "Invalid discount type."

    discount_value = None
    try:
        discount_value = float(discount_value_str)
        if discount_value <= 0:
            errors["discount_value"] = "Discount value must be greater than 0."
        elif discount_type == "percentage" and discount_value > 100:
            errors["discount_value"] = "Percentage discount cannot exceed 100%."
    except (ValueError, TypeError):
        errors["discount_value"] = "Enter a valid discount value."

    minimum_order = 0
    try:
        minimum_order = float(minimum_order_str) if minimum_order_str else 0
        if minimum_order < 0:
            errors["minimum_order_amount"] = "Minimum order amount cannot be negative."
    except (ValueError, TypeError):
        errors["minimum_order_amount"] = "Enter a valid minimum order amount."

    max_disc = None
    if maximum_discount_str:
        try:
            max_disc = float(maximum_discount_str)
            if max_disc <= 0:
                errors["maximum_discount_amount"] = "Maximum discount must be greater than 0."
        except (ValueError, TypeError):
            errors["maximum_discount_amount"] = "Enter a valid maximum discount amount."

    usage_lim = None
    if usage_limit_str:
        try:
            usage_lim = int(usage_limit_str)
            if usage_lim < 1:
                errors["usage_limit"] = "Usage limit must be at least 1."
        except (ValueError, TypeError):
            errors["usage_limit"] = "Enter a valid usage limit."

    valid_from = timezone.now()
    if valid_from_str:
        try:
            valid_from = timezone.make_aware(datetime.datetime.strptime(valid_from_str, "%Y-%m-%d"))
        except ValueError:
            errors["valid_from"] = "Invalid start date format."

    valid_until = None
    if valid_until_str:
        try:
            valid_until = timezone.make_aware(datetime.datetime.strptime(valid_until_str, "%Y-%m-%d"))
            if valid_until <= valid_from:
                errors["valid_until"] = "Expiry date must be after the start date."
        except ValueError:
            errors["valid_until"] = "Invalid expiry date format."

    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    coupon_obj = Coupon.objects.create(
        code=code,
        discount_type=discount_type,
        discount_value=discount_value,
        minimum_order_amount=minimum_order,
        maximum_discount_amount=max_disc,
        usage_limit=usage_lim,
        valid_from=valid_from,
        valid_until=valid_until,
        is_active=is_active,
    )

    return JsonResponse({
        "success": True,
        "message": "Coupon created successfully.",
        "coupon": _coupon_to_dict(coupon_obj),
    })


@require_POST
def delete_coupon(request, coupon_id):
    coupon_obj = get_object_or_404(Coupon, id=coupon_id)
    code = coupon_obj.code
    coupon_obj.delete()
    return JsonResponse({"success": True, "message": "Coupon deleted successfully."})


def _coupon_to_dict(c):
    return {
        "id": c.id,
        "code": c.code,
        "discount_type": c.discount_type,
        "discount_value": str(c.discount_value),
        "minimum_order_amount": str(c.minimum_order_amount),
        "maximum_discount_amount": str(c.maximum_discount_amount) if c.maximum_discount_amount else "",
        "usage_limit": c.usage_limit,
        "used_count": c.used_count,
        "valid_from": c.valid_from.strftime("%Y-%m-%d") if c.valid_from else "",
        "valid_until": c.valid_until.strftime("%Y-%m-%d") if c.valid_until else "",
        "is_active": c.is_active,
    }
