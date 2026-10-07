from django.shortcuts import render, get_object_or_404,redirect
from admin_panel.product_management.models import Product, ProductVariant
from user.account.models import Category
from django.core.paginator import Paginator


from django.db.models import Q

def product_list(request):
    """User-facing product listing — show only active, non-deleted products added by admin."""
    products = Product.objects.filter(
        is_active=True,
        is_deleted=False,
    ).filter(
        Q(category__isnull=True) | Q(category__is_active=True, category__is_deleted=False)
    ).prefetch_related('variants__images').distinct()

    # Category filter
    category_param = request.GET.get('category')
    if category_param:
        if category_param.isdigit():
            products = products.filter(category_id=int(category_param))
        else:
            products = products.filter(category__name__iexact=category_param)

    # Search filter
    search_param = request.GET.get('search')
    if search_param:
        products = products.filter(
            Q(name__icontains=search_param) |
            Q(description__icontains=search_param) |
            Q(brand__icontains=search_param) |
            Q(category__name__icontains=search_param)
        )

    # Sorting
    sort = request.GET.get('sort')
    if sort == 'price-low':
        products = products.order_by('variants__price')
    elif sort == 'price-high':
        products = products.order_by('-variants__price')
    elif sort == 'name':
        products = products.order_by('name')
    else:
        products = products.order_by('-created_at')

    paginator = Paginator(products, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    categories = Category.objects.filter(is_active=True, is_deleted=False)

    context = {
        'products': page_obj,
        'page_obj': page_obj,
        'categories': categories,
        'current_category': category_param or '',
        'search_query': search_param or '',
        'current_sort': sort or 'featured',
    }
    if request.user.is_authenticated:
        from user.user_profile.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        context['profile'] = profile

    return render(request, 'product_list.html', context)


import json

def product_detail(request, product_id):
    """User-facing product detail page matching luxury design mockup."""
    product = get_object_or_404(
        Product.objects.filter(
            Q(category__isnull=True) | Q(category__is_active=True, category__is_deleted=False)
        ),
        id=product_id,
        is_active=True,
        is_deleted=False,
    )

    # Get all active variants
    variants = list(product.variants.filter(is_active=True, is_deleted=False).prefetch_related('images'))

    # Default variant
    default_variant = next((v for v in variants if v.is_default), None) or (variants[0] if variants else None)

    # Gather images for gallery — ONLY up to 3 images from this specific variant!
    variant_images = []
    if default_variant:
        variant_images = list(default_variant.images.all()[:3])

    # Main image
    main_image = None
    if variant_images:
        primary = next((img for img in variant_images if img.is_primary), None)
        main_image = primary or variant_images[0]

    # Prepare variants payload so switching variants updates the 3 images dynamically
    variants_payload = []
    for var in variants:
        imgs = [img.image.url for img in var.images.all()[:3] if img.image]
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
        })

    # Related products from same category or other active products
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

    context = {
        'product': product,
        'variants': variants,
        'variants_json': json.dumps(variants_payload),
        'default_variant': default_variant,
        'variant_images': variant_images,
        'main_image': main_image,
        'related_products': related_products,
    }
    if request.user.is_authenticated:
        from user.user_profile.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        context['profile'] = profile

    return render(request, 'product_detail.html', context)


def product_filter(request):
    return render(request, "product_filter.html")


def product_details(request, product_id=None):
    if product_id:
        return product_detail(request, product_id)
    first_p = Product.objects.filter(is_active=True, is_deleted=False).first()
    if first_p:
        return redirect('product_detail', product_id=first_p.id)
    return redirect('product_list')