from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .models import WishlistItem
from user.cart.models import CartItem
from admin_panel.product_management.models import Product


@login_required
def wishlist(request):
    wishlist_qs = WishlistItem.objects.filter(
        user=request.user
    ).select_related('product__category').prefetch_related(
        'product__variants__images'
    )

    enriched = []
    for wi in wishlist_qs:
        p = wi.product
        variant = p.variants.filter(is_active=True, is_deleted=False).first()
        image_url = None
        if p.thumbnail:
            image_url = p.thumbnail.url
        elif variant and variant.images.first():
            image_url = variant.images.first().image.url

        price = None
        if variant:
            price = variant.price

        enriched.append({
            'wishlist_item': wi,
            'product': p,
            'image_url': image_url,
            'price': price,
            'variant': variant,
        })

    context = {
        'wishlist_items': enriched,
        'wishlist_count': len(enriched),
    }
    if request.user.is_authenticated:
        from user.user_profile.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        context['profile'] = profile

    return render(request, 'wishlist.html', context)


@login_required
@require_POST
def toggle_wishlist(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_active=True, is_deleted=False)
    item, created = WishlistItem.objects.get_or_create(user=request.user, product=product)
    if not created:
        item.delete()
        in_wishlist = False
        msg = f'"{product.name}" removed from your wishlist.'
    else:
        in_wishlist = True
        msg = f'"{product.name}" added to your wishlist!'

    count = WishlistItem.objects.filter(user=request.user).count()
    return JsonResponse({'success': True, 'in_wishlist': in_wishlist, 'msg': msg, 'count': count})


@login_required
@require_POST
def remove_from_wishlist(request, product_id):
    WishlistItem.objects.filter(user=request.user, product_id=product_id).delete()
    return JsonResponse({
        'success': True,
        'count': WishlistItem.objects.filter(user=request.user).count(),
    })


@login_required
@require_POST
def move_to_cart(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_active=True, is_deleted=False)

    variant = product.variants.filter(is_active=True, is_deleted=False, stock__gt=0).first()

    if not variant:
        return JsonResponse({'success': False, 'msg': 'Product is out of stock.'})

    cart_item, created = CartItem.objects.get_or_create(
        user=request.user,
        product=product,
        variant=variant,
        defaults={'quantity': 1},
    )
    if not created:
        cart_item.quantity += 1
        cart_item.save()

    WishlistItem.objects.filter(user=request.user, product=product).delete()

    cart_count = CartItem.objects.filter(user=request.user).count()
    wishlist_count = WishlistItem.objects.filter(user=request.user).count()

    return JsonResponse({
        'success': True,
        'msg': f'"{product.name}" moved to cart!',
        'cart_count': cart_count,
        'wishlist_count': wishlist_count,
    })


def wishlist_status(request):
    if not request.user.is_authenticated:
        return JsonResponse({'product_ids': []})
    ids = list(WishlistItem.objects.filter(user=request.user).values_list('product_id', flat=True))
    count = len(ids)
    return JsonResponse({'product_ids': ids, 'count': count})
