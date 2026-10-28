from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import models
from .models import CartItem
from admin_panel.product_management.models import Product, ProductVariant
from admin_panel.wegnex_admin.models import Coupon
from decimal import Decimal
from django.utils import timezone


@login_required
def cart(request):
    raw_items = CartItem.objects.filter(
        user=request.user
    ).select_related('product__category', 'variant').prefetch_related(
        'product__variants__images', 'variant__images'
    )

    enriched = []
    for ci in raw_items:
        p = ci.product
        v = ci.variant

        if not p.is_active or p.is_deleted:
            continue
        if v and (not v.is_active or v.is_deleted):
            continue

        stock = v.stock if v else 0
        price = v.price if v else 0
        compare_price = v.compare_at_price if v else None

        image_url = None
        if v and v.images.first():
            image_url = v.images.first().image.url
        elif p.thumbnail:
            image_url = p.thumbnail.url

        variant_label = ''
        if v and v.color:
            variant_label = v.color

        item_total = float(price) * ci.quantity

        enriched.append({
            'id': ci.id,
            'product': p,
            'variant': v,
            'variant_label': variant_label,
            'image_url': image_url,
            'price': float(price),
            'compare_price': float(compare_price) if compare_price else None,
            'stock': stock,
            'quantity': ci.quantity,
            'item_total': item_total,
            'is_out_of_stock': stock <= 0,
            'max_qty': min(stock, 10),  
        })

    subtotal = sum(i['item_total'] for i in enriched)
    item_count = sum(i['quantity'] for i in enriched)
    has_valid_items = any(not i['is_out_of_stock'] for i in enriched)

    context = {
        'cart_items': enriched,
        'subtotal': subtotal,
        'item_count': item_count,
        'has_valid_items': has_valid_items,
        'cart_count': len(enriched),
        'final_total': subtotal,
    }

    if request.user.is_authenticated:
        from user.user_profile.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        context['profile'] = profile

    return render(request, 'cart.html', context)


@login_required
@require_POST
def add_to_cart(request, product_id):
    product = Product.objects.filter(
        id=product_id, is_active=True, is_deleted=False
    ).first()
    if not product:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
            return JsonResponse({'success': False, 'msg': 'Product is not available.'})
        from django.shortcuts import redirect
        return redirect('product_list')

    variant_id = request.POST.get('variant_id')
    variant = None
    if variant_id:
        variant = ProductVariant.objects.filter(
            id=variant_id, product=product, is_active=True, is_deleted=False
        ).first()
    if not variant:
        variant = product.variants.filter(
            is_active=True, is_deleted=False, stock__gt=0
        ).first()

    if not variant:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
            return JsonResponse({'success': False, 'msg': 'Product is currently out of stock.'})
        from django.shortcuts import redirect
        from django.contrib import messages
        messages.warning(request, 'Product is currently out of stock.')
        return redirect(request.META.get('HTTP_REFERER') or 'product_detail', product_id=product.id)

    if variant.stock <= 0:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
            return JsonResponse({'success': False, 'msg': 'This variant is out of stock.'})
        from django.shortcuts import redirect
        from django.contrib import messages
        messages.warning(request, 'This variant is out of stock.')
        return redirect(request.META.get('HTTP_REFERER') or 'product_detail', product_id=product.id)

    qty = max(1, int(request.POST.get('quantity', 1)))

    cart_item, created = CartItem.objects.get_or_create(
        user=request.user, product=product, variant=variant,
        defaults={'quantity': qty}
    )
    if not created:
        new_qty = cart_item.quantity + qty
        max_qty = min(variant.stock, 10)
        if new_qty > max_qty:
            new_qty = max_qty
        cart_item.quantity = new_qty
        cart_item.save()

    from user.wishlist.models import WishlistItem
    deleted_count, _ = WishlistItem.objects.filter(user=request.user, product=product).delete()
    was_in_wishlist = deleted_count > 0
    wishlist_count = WishlistItem.objects.filter(user=request.user).count()

    cart_count = CartItem.objects.filter(user=request.user).count()
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
        return JsonResponse({
            'success': True,
            'msg': f'"{product.name}" added to cart!',
            'cart_count': cart_count,
            'in_wishlist': False,
            'removed_from_wishlist': was_in_wishlist,
            'wishlist_count': wishlist_count,
        })
    from django.shortcuts import redirect
    from django.contrib import messages
    messages.success(request, f'"{product.name}" added to your cart!')
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect('product_detail', product_id=product.id)


@login_required
@require_POST
def remove_from_cart(request, item_id):
    CartItem.objects.filter(id=item_id, user=request.user).delete()
    remaining = CartItem.objects.filter(user=request.user).select_related('variant')
    subtotal = sum(
        float(ci.variant.price if ci.variant else 0) * ci.quantity
        for ci in remaining
        if ci.product.is_active and not ci.product.is_deleted
    )
    return JsonResponse({
        'success': True,
        'cart_count': remaining.count(),
        'subtotal': subtotal,
    })


@login_required
@require_POST
def update_cart_qty(request, item_id):
    qty = int(request.POST.get('quantity', 1))
    item = CartItem.objects.select_related('product', 'variant').filter(
        id=item_id, user=request.user
    ).first()

    if not item:
        return JsonResponse({'success': False, 'msg': 'Item not found.'})


    if not item.product.is_active or item.product.is_deleted:
        item.delete()
        return JsonResponse({'success': False, 'msg': 'Product is no longer available.', 'removed': True})

    stock = item.variant.stock if item.variant else 0
    max_qty = min(stock, 10)

    if qty < 1:
        item.delete()
        removed = True
        item_total = 0
    else:
        if qty > max_qty:
            qty = max_qty
        item.quantity = qty
        item.save()
        removed = False
        price = float(item.variant.price if item.variant else 0)
        item_total = price * qty

    remaining = CartItem.objects.filter(user=request.user).select_related('variant')
    subtotal = sum(
        float(ci.variant.price if ci.variant else 0) * ci.quantity
        for ci in remaining
        if ci.product.is_active and not ci.product.is_deleted
    )

    return JsonResponse({
        'success': True,
        'removed': removed,
        'qty': qty,
        'item_total': item_total,
        'cart_count': remaining.count(),
        'subtotal': subtotal,
    })


@login_required
@require_POST
def apply_coupon(request):
    code = request.POST.get('code', '').strip().upper()
    if not code:
        return JsonResponse({'success': False, 'msg': 'Please enter a coupon code.'})

    try:
        coupon = Coupon.objects.get(code__iexact=code)
    except Coupon.DoesNotExist:
        return JsonResponse({'success': False, 'msg': 'Invalid coupon code.'})

    valid, reason = coupon.is_valid()
    if not valid:
        return JsonResponse({'success': False, 'msg': reason})

    cart_items = CartItem.objects.filter(user=request.user).select_related('product', 'variant')
    subtotal = Decimal('0.00')
    for ci in cart_items:
        p = ci.product
        v = ci.variant
        if not p.is_active or p.is_deleted:
            continue
        if v and (not v.is_active or v.is_deleted):
            continue
        if v and v.stock > 0:
            subtotal += Decimal(str(v.price)) * ci.quantity

    if subtotal < coupon.minimum_order_amount:
        return JsonResponse({
            'success': False,
            'msg': f'Minimum order amount of ₹{int(coupon.minimum_order_amount):,} required for this coupon.'
        })

    discount = coupon.calculate_discount(subtotal)
    final_total = subtotal - discount

    request.session['coupon_code'] = coupon.code
    request.session['coupon_id'] = coupon.id
    request.session.modified = True

    return JsonResponse({
        'success': True,
        'msg': f'Coupon "{coupon.code}" applied successfully!',
        'discount': float(discount),
        'subtotal': float(subtotal),
        'final_total': float(final_total),
        'coupon_code': coupon.code,
        'coupon_description': coupon.description or '',
        'discount_label': f'{int(coupon.discount_value)}% OFF' if coupon.discount_type == 'percentage' else f'₹{int(coupon.discount_value)} OFF',
    })


@login_required
@require_POST
def remove_coupon(request):
    request.session.pop('coupon_code', None)
    request.session.pop('coupon_id', None)
    request.session.modified = True

    cart_items = CartItem.objects.filter(user=request.user).select_related('product', 'variant')
    subtotal = Decimal('0.00')
    for ci in cart_items:
        p = ci.product
        v = ci.variant
        if not p.is_active or p.is_deleted:
            continue
        if v and (not v.is_active or v.is_deleted):
            continue
        if v and v.stock > 0:
            subtotal += Decimal(str(v.price)) * ci.quantity

    return JsonResponse({
        'success': True,
        'msg': 'Coupon removed.',
        'subtotal': float(subtotal),
    })


@login_required
def list_coupons(request):
    now = timezone.now()
    coupons = Coupon.objects.filter(
        is_active=True,
        valid_from__lte=now,
    ).filter(
        models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=now)
    ).filter(
        models.Q(usage_limit__isnull=True) | models.Q(used_count__lt=models.F('usage_limit'))
    )

    result = []
    for c in coupons:
        discount_label = (
            f'{int(c.discount_value)}% OFF'
            if c.discount_type == 'percentage'
            else f'₹{int(c.discount_value)} OFF'
        )
        result.append({
            'code': c.code,
            'description': c.description or '',
            'discount_label': discount_label,
            'min_order': float(c.minimum_order_amount),
            'valid_until': c.valid_until.strftime('%d %b %Y') if c.valid_until else None,
        })

    return JsonResponse({'coupons': result})