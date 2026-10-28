from django.shortcuts import render, get_object_or_404,redirect
from admin_panel.product_management.models import Product, ProductVariant
from user.account.models import Category
from django.core.paginator import Paginator
import json
from django.http import JsonResponse

from django.db.models import Q, Min, Max


def product_api(request):
    products = Product.objects.filter(
        is_active=True,
        is_deleted=False
    )

    data = []

    for product in products:
        data.append({
            'id': product.id,
            'name': product.name,
            'brand': product.brand,
        })

    return JsonResponse({
        'success': True,
        'products': data
    })


def product_list(request):
    products = Product.objects.filter(
        is_active=True,
        is_deleted=False,
    ).filter(
        Q(category__isnull=True) | Q(category__is_active=True, category__is_deleted=False)
    ).prefetch_related('variants__images').distinct()

    
    search_param = request.GET.get('search', '').strip()
    if search_param:
        products = products.filter(
            Q(name__icontains=search_param) |
            Q(description__icontains=search_param) |
            Q(brand__icontains=search_param) |
            Q(category__name__icontains=search_param)
        )

    category_params = request.GET.getlist('category')
    category_params = [c.strip() for c in category_params if c.strip()]
    if category_params:
        cat_q = Q()
        for cat in category_params:
            if cat.isdigit():
                cat_q |= Q(category_id=int(cat))
            else:
                cat_q |= Q(category__name__iexact=cat)
        products = products.filter(cat_q)

    brand_params = request.GET.getlist('brand')
    brand_params = [b.strip() for b in brand_params if b.strip()]
    if brand_params:
        brand_q = Q()
        for b in brand_params:
            brand_q |= Q(brand__iexact=b)
        products = products.filter(brand_q)

    min_price_param = request.GET.get('min_price', '').strip()
    max_price_param = request.GET.get('max_price', '').strip()

    if min_price_param and min_price_param.isdigit():
        products = products.filter(
            variants__price__gte=int(min_price_param),
            variants__is_active=True,
            variants__is_deleted=False
        )

    if max_price_param and max_price_param.isdigit():
        products = products.filter(
            variants__price__lte=int(max_price_param),
            variants__is_active=True,
            variants__is_deleted=False
        )

    products = products.distinct()

    products = products.annotate(
        effective_price=Min('variants__price', filter=Q(variants__is_active=True, variants__is_deleted=False))
    )

    sort = request.GET.get('sort', 'featured')
    if sort == 'price-low':
        products = products.order_by('effective_price')
    elif sort == 'price-high':
        products = products.order_by('-effective_price')
    elif sort == 'name':
        products = products.order_by('name')
    elif sort == 'newest' or sort == 'featured':
        products = products.order_by('-created_at')
    else:
        products = products.order_by('-created_at')

    
    categories = Category.objects.filter(is_active=True, is_deleted=False)
    brands = sorted(list(set(
        Product.objects.filter(is_active=True, is_deleted=False)
        .exclude(brand='')
        .values_list('brand', flat=True)
    )))

    price_aggregate = ProductVariant.objects.filter(
        is_active=True,
        is_deleted=False,
        product__is_active=True,
        product__is_deleted=False
    ).aggregate(
        min_p=Min('price'),
        max_p=Max('price')
    )
    db_min_price = int(price_aggregate['min_p'] or 0)
    db_max_price = int(price_aggregate['max_p'] or 100000)
    if db_max_price % 5000 != 0:
        db_max_price = ((db_max_price // 5000) + 1) * 5000

    current_min_price = int(min_price_param) if (min_price_param and min_price_param.isdigit()) else db_min_price
    current_max_price = int(max_price_param) if (max_price_param and max_price_param.isdigit()) else db_max_price

    paginator = Paginator(products, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    params = request.GET.copy()
    if 'page' in params:
        del params['page']
    querystring = params.urlencode()

    price_filtered = bool(
        (min_price_param and min_price_param.isdigit() and int(min_price_param) > db_min_price) or
        (max_price_param and max_price_param.isdigit() and int(max_price_param) < db_max_price)
    )

    has_active_filters = bool(
        search_param or
        category_params or
        brand_params or
        price_filtered
    )

    context = {
        'products': page_obj,
        'page_obj': page_obj,
        'categories': categories,
        'brands': brands,
        'selected_categories': category_params,
        'selected_brands': brand_params,
        'current_category': category_params[0] if category_params else '',
        'search_query': search_param,
        'current_sort': sort,
        'min_price': min_price_param,
        'max_price': max_price_param,
        'db_min_price': db_min_price,
        'db_max_price': db_max_price,
        'current_min_price': current_min_price,
        'current_max_price': current_max_price,
        'price_filtered': price_filtered,
        'querystring': querystring,
        'has_active_filters': has_active_filters,
    }
    if request.user.is_authenticated:
        from user.user_profile.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        context['profile'] = profile

    return render(request, 'product_list.html', context)


def product_detail(request, product_id):
    
    product = get_object_or_404(
        Product.objects.filter(
            Q(category__isnull=True) | Q(category__is_active=True, category__is_deleted=False)
        ),
        id=product_id,
        is_active=True,
        is_deleted=False,
    )

    variants = list(product.variants.filter(is_active=True, is_deleted=False).prefetch_related('images'))

    default_variant = next((v for v in variants if v.is_default), None) or (variants[0] if variants else None)

    variant_images = []
    if default_variant:
        variant_images = list(default_variant.images.all()[:3])

    main_image = None
    if variant_images:
        primary = next((img for img in variant_images if img.is_primary), None)
        main_image = primary or variant_images[0]

    # ---- Offer lookup ----
    from admin_panel.offer.models import Offer as OfferModel
    from django.utils import timezone as tz_now
    _today = tz_now.now().date()

    _offer_qs = OfferModel.objects.filter(
        is_deleted=False,
        is_active=True,
    ).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=_today)
    ).filter(
        Q(start_date__isnull=True) | Q(start_date__lte=_today)
    ).select_related('category', 'product')

    # Keep only offers that apply to this product or its category
    applicable_offers = [
        off for off in _offer_qs
        if (off.offer_type == 'products' and off.product_id == product.id) or
           (off.offer_type == 'category' and product.category_id and off.category_id == product.category_id)
    ]

    def _best_offer(price):
        """Return (best_offer, discount_amount, final_price) or (None, 0, price)."""
        best, best_d = None, 0
        for off in applicable_offers:
            d_amt, final, ok = off.calculate_discount(price)
            if ok and d_amt > best_d:
                best, best_d = off, d_amt
        if best:
            _, fp, _ = best.calculate_discount(price)
            return best, best_d, fp
        return None, 0, price

    variants_payload = []
    for var in variants:
        imgs = [img.image.url for img in var.images.all()[:3] if img.image]
        b_off, d_amt, fp = _best_offer(var.price)
        offer_info = None
        if b_off:
            offer_info = {
                'name': b_off.name,
                'badge': b_off.get_discount_display(),
                'discount_amount_fmt': f"{float(d_amt):,.0f}",
                'final_price_fmt': f"{float(fp):,.0f}",
                'discount_amount': float(d_amt),
                'final_price': float(fp),
            }
        variants_payload.append({
            'id': var.id,
            'color': var.color or 'Default',
            'price': f"{var.price:,.0f}",
            'compare_at_price': f"{var.compare_at_price:,.0f}" if var.compare_at_price else None,
            'stock': var.stock,
            'case_size': var.case_size or '—',
            'strap_material': var.strap_material or '—',
            'sku': var.sku or '—',
            'images': imgs,
            'offer': offer_info,
        })

    related_products = list(Product.objects.filter(
        is_active=True,
        is_deleted=False,
        category=product.category,
    ).filter(
        Q(category__isnull=True) | Q(category__is_active=True, category__is_deleted=False)
    ).exclude(id=product.id).prefetch_related('variants__images')[:4])

    if len(related_products) < 4:
        needed = 4 - len(related_products)
        existing_ids = [p.id for p in related_products] + [product.id]
        more = Product.objects.filter(
            is_active=True,
            is_deleted=False,
        ).filter(
            Q(category__isnull=True) | Q(category__is_active=True, category__is_deleted=False)
        ).exclude(id__in=existing_ids).prefetch_related('variants__images')[:needed]
        related_products.extend(list(more))

    # ---- Reviews ----
    from admin_panel.review_management.models import Review
    reviews = Review.objects.filter(
        Q(product=product) | Q(product_name__iexact=product.name),
        status='approved'
    ).select_related('user').order_by('-created_at')

    avg_rating = 0
    can_review = False
    already_reviewed = False

    if reviews.exists():
        total = sum(r.rating for r in reviews)
        avg_rating = round(total / reviews.count(), 1)

    if request.user.is_authenticated:
        from user.checkout.models import Order, OrderItem
        # Check if user has a DELIVERED order with this product
        delivered_items = OrderItem.objects.filter(
            order__user=request.user,
            order__order_status='DELIVERED',
            product_id=product_id,
        )
        can_review = delivered_items.exists()
        # Check if they already reviewed this product
        already_reviewed = Review.objects.filter(
            user=request.user
        ).filter(
            Q(product=product) | Q(product_name__iexact=product.name)
        ).exists()

    # Default variant offer for initial template render
    default_offer = None
    if default_variant:
        b_off, d_amt, fp = _best_offer(default_variant.price)
        if b_off:
            default_offer = {
                'name': b_off.name,
                'badge': b_off.get_discount_display(),
                'discount_amount_fmt': f"{float(d_amt):,.0f}",
                'final_price_fmt': f"{float(fp):,.0f}",
                'discount_amount': float(d_amt),
                'final_price': float(fp),
            }

    context = {
        'product': product,
        'variants': variants,
        'variants_json': json.dumps(variants_payload),
        'default_variant': default_variant,
        'variant_images': variant_images,
        'main_image': main_image,
        'related_products': related_products,
        'reviews': reviews,
        'avg_rating': avg_rating,
        'review_count': reviews.count(),
        'can_review': can_review,
        'already_reviewed': already_reviewed,
        'applicable_offers': applicable_offers,
        'default_offer': default_offer,
    }
    if request.user.is_authenticated:
        from user.user_profile.models import UserProfile
        from user.cart.models import CartItem
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        context['profile'] = profile
        context['cart_count'] = CartItem.objects.filter(user=request.user).count()

    return render(request, 'product_detail.html', context)


def product_filter(request):
    categories = Category.objects.filter(is_active=True, is_deleted=False)
    brands = sorted(list(set(
        Product.objects.filter(is_active=True, is_deleted=False)
        .exclude(brand='')
        .values_list('brand', flat=True)
    )))

    price_aggregate = ProductVariant.objects.filter(
        is_active=True,
        is_deleted=False,
        product__is_active=True,
        product__is_deleted=False
    ).aggregate(
        min_p=Min('price'),
        max_p=Max('price')
    )
    db_min_price = int(price_aggregate['min_p'] or 0)
    db_max_price = int(price_aggregate['max_p'] or 100000)
    if db_max_price % 5000 != 0:
        db_max_price = ((db_max_price // 5000) + 1) * 5000

    category_params = [c.strip() for c in request.GET.getlist('category') if c.strip()]
    brand_params = [b.strip() for b in request.GET.getlist('brand') if b.strip()]
    min_price_param = request.GET.get('min_price', '').strip()
    max_price_param = request.GET.get('max_price', '').strip()
    search_param = request.GET.get('search', '').strip()
    sort_param = request.GET.get('sort', 'featured')

    current_min_price = int(min_price_param) if (min_price_param and min_price_param.isdigit()) else db_min_price
    current_max_price = int(max_price_param) if (max_price_param and max_price_param.isdigit()) else db_max_price

    context = {
        'categories': categories,
        'brands': brands,
        'selected_categories': category_params,
        'selected_brands': brand_params,
        'search_query': search_param,
        'current_sort': sort_param,
        'min_price': min_price_param,
        'max_price': max_price_param,
        'db_min_price': db_min_price,
        'db_max_price': db_max_price,
        'current_min_price': current_min_price,
        'current_max_price': current_max_price,
    }
    if request.user.is_authenticated:
        from user.user_profile.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        context['profile'] = profile

    return render(request, "product_filter.html", context)


def product_details(request, product_id=None):
    if product_id:
        return product_detail(request, product_id)
    first_p = Product.objects.filter(is_active=True, is_deleted=False).first()
    if first_p:
        return redirect('product_detail', product_id=first_p.id)
    return redirect('product_list')


def submit_review(request, product_id):
    """Allow only users with a DELIVERED order for this product to submit a review."""
    from admin_panel.review_management.models import Review
    from user.checkout.models import OrderItem
    from django.contrib import messages

    if not request.user.is_authenticated:
        return redirect(f"/login/?next=/product/{product_id}/review/")

    if request.method != 'POST':
        return redirect('product_detail', product_id=product_id)

    product = get_object_or_404(
        Product,
        id=product_id,
        is_active=True,
        is_deleted=False,
    )

    # Must have a delivered order containing this product
    has_delivered = OrderItem.objects.filter(
        order__user=request.user,
        order__order_status='DELIVERED',
        product_id=product_id,
    ).exists()

    if not has_delivered:
        messages.error(request, "You can only review products you have received.")
        return redirect('product_detail', product_id=product_id)

    # Prevent duplicate reviews
    already = Review.objects.filter(user=request.user).filter(
        Q(product=product) | Q(product_name__iexact=product.name)
    ).exists()
    if already:
        messages.info(request, "You have already submitted a review for this product.")
        return redirect('product_detail', product_id=product_id)

    rating = int(request.POST.get('rating', 5))
    rating = max(1, min(5, rating))
    comment = request.POST.get('comment', '').strip()

    if not comment:
        messages.error(request, "Please write a comment for your review.")
        return redirect('product_detail', product_id=product_id)

    Review.objects.create(
        user=request.user,
        product=product,
        product_name=product.name,
        rating=rating,
        comment=comment,
        status='approved',
    )

    messages.success(request, "Thank you! Your review has been published successfully.")
    return redirect('product_detail', product_id=product_id)