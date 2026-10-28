from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Q, Avg
from decimal import Decimal
from datetime import timedelta

from user.account.models import Category
from admin_panel.product_management.models import Product
from .models import Offer


@never_cache
def offer(request):
    search_query = request.GET.get('search', '').strip()
    type_filter = request.GET.get('type', 'all').strip().lower()
    status_filter = request.GET.get('status', 'all').strip().lower()

    offers_qs = Offer.objects.filter(is_deleted=False).select_related('category', 'product')

    if search_query:
        offers_qs = offers_qs.filter(
            Q(name__icontains=search_query) |
            Q(code__icontains=search_query) |
            Q(category__name__icontains=search_query) |
            Q(product__name__icontains=search_query)
        )

    if type_filter in ['percentage', 'fixed']:
        offers_qs = offers_qs.filter(discount_type=type_filter)

    if status_filter == 'active':
        offers_qs = offers_qs.filter(is_active=True)
    elif status_filter == 'inactive':
        offers_qs = offers_qs.filter(is_active=False)

    offers_qs = offers_qs.order_by('-created_at')

    # Calculate stats
    total_offers = Offer.objects.filter(is_deleted=False).count()
    active_offers = Offer.objects.filter(is_deleted=False, is_active=True).count()
    avg_discount = Offer.objects.filter(
        is_deleted=False, discount_type='percentage'
    ).aggregate(avg=Avg('discount_value'))['avg'] or 0

    today = timezone.now().date()
    expiring_soon = Offer.objects.filter(
        is_deleted=False,
        is_active=True,
        end_date__isnull=False,
        end_date__gte=today,
        end_date__lte=today + timedelta(days=7)
    ).count()

    paginator = Paginator(offers_qs, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    categories = Category.objects.filter(is_deleted=False).order_by('name')
    products = Product.objects.filter(is_deleted=False, is_active=True).order_by('name')

    return render(request, "offer.html", {
        "offers": page_obj,
        "page_obj": page_obj,
        "categories": categories,
        "products": products,
        "total_offers": total_offers,
        "active_offers": active_offers,
        "avg_discount": round(avg_discount, 1),
        "expiring_soon": expiring_soon,
        "search_query": search_query,
        "type_filter": type_filter,
        "status_filter": status_filter,
    })


@require_POST
def add_offer(request):
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    try:
        name = request.POST.get('name', '').strip()
        discount_type = request.POST.get('discount_type', 'percentage').strip().lower()
        discount_value_str = request.POST.get('discount_value', '').strip().replace('%', '').replace('₹', '').replace(',', '').strip()
        apply_to = request.POST.get('apply_to', 'category').strip().lower()
        category_id = request.POST.get('category_id') or request.POST.get('category')
        product_id = request.POST.get('product_id') or request.POST.get('product')

        min_purchase_str = request.POST.get('minimum_purchase', '').strip().replace('₹', '').replace(',', '').strip()
        max_discount_str = request.POST.get('maximum_discount', '').strip().replace('₹', '').replace(',', '').strip()
        start_date = request.POST.get('start_date') or None
        end_date = request.POST.get('end_date') or None
        is_active = request.POST.get('is_active') in ['true', 'on', '1', True]

        if not name:
            err = "Offer name is required."
            return JsonResponse({'success': False, 'message': err}, status=400) if is_ajax else redirect_with_error(request, err)

        if not discount_value_str:
            err = "Discount value is required."
            return JsonResponse({'success': False, 'message': err}, status=400) if is_ajax else redirect_with_error(request, err)

        try:
            discount_value = Decimal(discount_value_str)
            if discount_value <= 0:
                raise ValueError()
            if discount_type == 'percentage' and discount_value > 100:
                err = "Percentage discount cannot exceed 100%."
                return JsonResponse({'success': False, 'message': err}, status=400) if is_ajax else redirect_with_error(request, err)
        except Exception:
            err = "Please enter a valid discount amount greater than 0."
            return JsonResponse({'success': False, 'message': err}, status=400) if is_ajax else redirect_with_error(request, err)

        min_purchase = Decimal(min_purchase_str) if min_purchase_str else Decimal('0.00')
        max_discount = Decimal(max_discount_str) if max_discount_str else None

        if start_date and end_date and end_date < start_date:
            err = "End date cannot be earlier than start date."
            return JsonResponse({'success': False, 'message': err}, status=400) if is_ajax else redirect_with_error(request, err)

        category = None
        product = None

        if apply_to == 'category':
            if not category_id:
                err = "Please select a target category."
                return JsonResponse({'success': False, 'message': err}, status=400) if is_ajax else redirect_with_error(request, err)
            category = get_object_or_404(Category, id=category_id)
        else:
            if not product_id:
                err = "Please select a target product."
                return JsonResponse({'success': False, 'message': err}, status=400) if is_ajax else redirect_with_error(request, err)
            product = get_object_or_404(Product, id=product_id)

        code = request.POST.get('code', '').strip().upper()
        if not code:
            import random
            code = f"OFFER{random.randint(1000, 9999)}"

        offer_obj = Offer.objects.create(
            name=name,
            code=code,
            discount_type=discount_type,
            discount_value=discount_value,
            offer_type='category' if apply_to == 'category' else 'products',
            category=category,
            product=product,
            minimum_purchase=min_purchase,
            maximum_discount=max_discount,
            start_date=start_date,
            end_date=end_date,
            is_active=is_active
        )

        msg = f"Offer '{offer_obj.name}' created successfully!"
        if is_ajax:
            return JsonResponse({'success': True, 'message': msg, 'offer_id': offer_obj.id})
        messages.success(request, msg)
        return redirect('offer.html')

    except Exception as e:
        err = f"Failed to create offer: {str(e)}"
        if is_ajax:
            return JsonResponse({'success': False, 'message': err}, status=500)
        messages.error(request, err)
        return redirect('offer.html')


@require_POST
def edit_offer(request, offer_id):
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    offer_obj = get_object_or_404(Offer, id=offer_id, is_deleted=False)

    try:
        name = request.POST.get('name', '').strip()
        discount_type = request.POST.get('discount_type', 'percentage').strip().lower()
        discount_value_str = request.POST.get('discount_value', '').strip().replace('%', '').replace('₹', '').replace(',', '').strip()
        apply_to = request.POST.get('apply_to', 'category').strip().lower()
        category_id = request.POST.get('category_id') or request.POST.get('category')
        product_id = request.POST.get('product_id') or request.POST.get('product')

        min_purchase_str = request.POST.get('minimum_purchase', '').strip().replace('₹', '').replace(',', '').strip()
        max_discount_str = request.POST.get('maximum_discount', '').strip().replace('₹', '').replace(',', '').strip()
        start_date = request.POST.get('start_date') or None
        end_date = request.POST.get('end_date') or None
        is_active = request.POST.get('is_active') in ['true', 'on', '1', True]

        if not name:
            err = "Offer name is required."
            return JsonResponse({'success': False, 'message': err}, status=400) if is_ajax else redirect_with_error(request, err)

        try:
            discount_value = Decimal(discount_value_str)
            if discount_value <= 0:
                raise ValueError()
            if discount_type == 'percentage' and discount_value > 100:
                err = "Percentage discount cannot exceed 100%."
                return JsonResponse({'success': False, 'message': err}, status=400) if is_ajax else redirect_with_error(request, err)
        except Exception:
            err = "Please enter a valid discount amount."
            return JsonResponse({'success': False, 'message': err}, status=400) if is_ajax else redirect_with_error(request, err)

        min_purchase = Decimal(min_purchase_str) if min_purchase_str else Decimal('0.00')
        max_discount = Decimal(max_discount_str) if max_discount_str else None

        if start_date and end_date and end_date < start_date:
            err = "End date cannot be earlier than start date."
            return JsonResponse({'success': False, 'message': err}, status=400) if is_ajax else redirect_with_error(request, err)

        if apply_to == 'category':
            if not category_id:
                err = "Please select a target category."
                return JsonResponse({'success': False, 'message': err}, status=400) if is_ajax else redirect_with_error(request, err)
            offer_obj.category = get_object_or_404(Category, id=category_id)
            offer_obj.product = None
            offer_obj.offer_type = 'category'
        else:
            if not product_id:
                err = "Please select a target product."
                return JsonResponse({'success': False, 'message': err}, status=400) if is_ajax else redirect_with_error(request, err)
            offer_obj.product = get_object_or_404(Product, id=product_id)
            offer_obj.category = None
            offer_obj.offer_type = 'products'

        offer_obj.name = name
        offer_obj.discount_type = discount_type
        offer_obj.discount_value = discount_value
        offer_obj.minimum_purchase = min_purchase
        offer_obj.maximum_discount = max_discount
        offer_obj.start_date = start_date
        offer_obj.end_date = end_date
        offer_obj.is_active = is_active
        offer_obj.save()

        msg = f"Offer '{offer_obj.name}' updated successfully!"
        if is_ajax:
            return JsonResponse({'success': True, 'message': msg})
        messages.success(request, msg)
        return redirect('offer.html')

    except Exception as e:
        err = f"Failed to update offer: {str(e)}"
        if is_ajax:
            return JsonResponse({'success': False, 'message': err}, status=500)
        messages.error(request, err)
        return redirect('offer.html')


@require_POST
def toggle_offer_status(request, offer_id):
    offer_obj = get_object_or_404(Offer, id=offer_id, is_deleted=False)
    offer_obj.is_active = not offer_obj.is_active
    offer_obj.save()

    status_str = "activated" if offer_obj.is_active else "deactivated"
    msg = f"Offer '{offer_obj.name}' has been {status_str}."

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'is_active': offer_obj.is_active,
            'message': msg
        })

    messages.success(request, msg)
    return redirect('offer.html')


@require_POST
def delete_offer(request, offer_id):
    offer_obj = get_object_or_404(Offer, id=offer_id)
    offer_obj.is_deleted = True
    offer_obj.is_active = False
    offer_obj.save()

    msg = f"Offer '{offer_obj.name}' has been deleted."
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': msg})

    messages.success(request, msg)
    return redirect('offer.html')


def redirect_with_error(request, msg):
    messages.error(request, msg)
    return redirect('offer.html')