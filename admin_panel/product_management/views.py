import json
import base64
import uuid
from io import BytesIO

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_http_methods
from django.core.files.base import ContentFile
from PIL import Image as PILImage

from user.account.models import Category
from .models import Product, ProductVariant, VariantImage

def is_admin(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser) and user.is_active


def _save_cropped_image(b64_data, folder, filename_prefix='img'):
    if ',' in b64_data:
        b64_data = b64_data.split(',', 1)[1]

    raw = base64.b64decode(b64_data)
    img = PILImage.open(BytesIO(raw)).convert('RGB')

    max_size = 1200
    w, h = img.size
    if max(w, h) > max_size:
        ratio = max_size / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), PILImage.LANCZOS)

    out = BytesIO()
    img.save(out, format='JPEG', quality=90, optimize=True)
    out.seek(0)

    filename = f"{filename_prefix}_{uuid.uuid4().hex[:8]}.jpg"
    return ContentFile(out.read(), name=filename)

@never_cache
def product_list(request):
    if not is_admin(request.user):
        messages.error(request, "Please log in with administrator privileges.")
        return redirect("admin_login")

    base_qs = Product.objects.filter(is_deleted=False).select_related('category')

    total_products = base_qs.count()
    active_products = base_qs.filter(is_active=True).count()
    inactive_products = base_qs.filter(is_active=False).count()

    search_query = request.GET.get('search', '').strip()
    if search_query:
        qs = base_qs.filter(
            Q(name__icontains=search_query) |
            Q(brand__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    else:
        qs = base_qs

    qs = qs.order_by('-created_at', '-id')

    paginator = Paginator(qs, 8)
    try:
        page_obj = paginator.get_page(request.GET.get('page', 1))
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.get_page(1)

    categories = Category.objects.filter(is_deleted=False, is_active=True).order_by('name')

    return render(request, 'product_management/product_list_admin.html', {
        'admin_user': request.user,
        'products': page_obj,
        'page_obj': page_obj,
        'paginator': paginator,
        'search_query': search_query,
        'total_products': total_products,
        'active_products': active_products,
        'inactive_products': inactive_products,
        'categories': categories,
    })

@never_cache
@require_http_methods(["POST"])
def add_product(request):
    if not is_admin(request.user):
        return redirect("admin_login")

    name = request.POST.get('name', '').strip()
    description = request.POST.get('description', '').strip()
    brand = request.POST.get('brand', '').strip()
    category_id = request.POST.get('category', '').strip()
    is_active = request.POST.get('is_active') in ['on', '1', 'true', 'True']
    is_featured = request.POST.get('is_featured') in ['on', '1', 'true', 'True']

    if not name:
        messages.error(request, "Product name is required.")
        return redirect('admin_product_list')

    if len(name) < 2 or len(name) > 200:
        messages.error(request, "Product name must be 2–200 characters.")
        return redirect('admin_product_list')

    if Product.objects.filter(name__iexact=name, is_deleted=False).exists():
        messages.error(request, f"A product named '{name}' already exists.")
        return redirect('admin_product_list')

    category = None
    if category_id:
        try:
            category = Category.objects.get(id=category_id, is_deleted=False)
        except Category.DoesNotExist:
            pass

    product = Product.objects.create(
        name=name,
        description=description,
        brand=brand,
        category=category,
        is_active=is_active,
        is_featured=is_featured,
    )
    messages.success(request, f"Product '{product.name}' created. Now add its variants.")
    return redirect('variant_management', product_id=product.id)


@never_cache
@require_http_methods(["POST"])
def edit_product(request, product_id):
    if not is_admin(request.user):
        return redirect("admin_login")

    product = get_object_or_404(Product, id=product_id)

    name = request.POST.get('name', '').strip()
    description = request.POST.get('description', '').strip()
    brand = request.POST.get('brand', '').strip()
    category_id = request.POST.get('category', '').strip()
    is_active = request.POST.get('is_active') in ['on', '1', 'true', 'True']
    is_featured = request.POST.get('is_featured') in ['on', '1', 'true', 'True']

    if not name:
        messages.error(request, "Product name is required.")
        return redirect('admin_product_list')

    if Product.objects.filter(name__iexact=name, is_deleted=False).exclude(id=product.id).exists():
        messages.error(request, f"Another product named '{name}' already exists.")
        return redirect('admin_product_list')

    category = None
    if category_id:
        try:
            category = Category.objects.get(id=category_id, is_deleted=False)
        except Category.DoesNotExist:
            pass

    product.name = name
    product.description = description
    product.brand = brand
    product.category = category
    product.is_active = is_active
    product.is_featured = is_featured
    product.save()

    messages.success(request, f"Product '{product.name}' updated successfully.")
    return redirect('admin_product_list')


@never_cache
@require_POST
def delete_product(request, product_id):
    if not is_admin(request.user):
        return redirect("admin_login")
    product = get_object_or_404(Product, id=product_id)
    product.soft_delete()
    messages.success(request, f"Product '{product.name}' has been deleted.")
    return redirect('admin_product_list')


@never_cache
@require_POST
def toggle_product_status(request, product_id):
    if not is_admin(request.user):
        return redirect("admin_login")
    product = get_object_or_404(Product, id=product_id)
    product.is_active = not product.is_active
    product.save()
    label = "Active" if product.is_active else "Inactive"
    messages.success(request, f"Product '{product.name}' is now {label}.")
    return redirect('admin_product_list')

@never_cache
def variant_management(request, product_id):
    if not is_admin(request.user):
        messages.error(request, "Please log in with administrator privileges.")
        return redirect("admin_login")

    product = get_object_or_404(Product, id=product_id, is_deleted=False)
    variants = product.variants.filter(is_deleted=False).prefetch_related('images').order_by('created_at')

    return render(request, 'product_management/variant_management.html', {
        'admin_user': request.user,
        'product': product,
        'variants': variants,
    })


@never_cache
@require_http_methods(["POST"])
def add_variant(request, product_id):
    if not is_admin(request.user):
        return redirect("admin_login")

    product = get_object_or_404(Product, id=product_id, is_deleted=False)

    color = request.POST.get('color', '').strip()
    strap_material = request.POST.get('strap_material', '').strip()
    case_size = request.POST.get('case_size', '').strip()
    price = request.POST.get('price', '').strip()
    compare_at_price = request.POST.get('compare_at_price', '').strip()
    stock = request.POST.get('stock', '0').strip()
    sku = request.POST.get('sku', '').strip()
    is_active = request.POST.get('is_active') in ['on', '1', 'true', 'True']

    cropped_images = request.POST.getlist('cropped_images[]')

    if not price:
        messages.error(request, "Price is required for each variant.")
        return redirect('variant_management', product_id=product_id)

    try:
        price = float(price)
    except ValueError:
        messages.error(request, "Price must be a valid number.")
        return redirect('variant_management', product_id=product_id)

    if price <= 0:
        messages.error(request, "Price must be greater than 0.")
        return redirect('variant_management', product_id=product_id)

    compare_price_val = None
    if compare_at_price:
        try:
            compare_price_val = float(compare_at_price)
        except ValueError:
            pass

    try:
        stock_val = int(stock)
    except ValueError:
        stock_val = 0

    valid_images = [img for img in cropped_images if img and img.startswith('data:image')]
    if len(valid_images) < 3:
        messages.error(request, "Please upload at least 3 images for each variant.")
        return redirect('variant_management', product_id=product_id)

    variant = ProductVariant.objects.create(
        product=product,
        color=color,
        strap_material=strap_material,
        case_size=case_size,
        price=price,
        compare_at_price=compare_price_val,
        stock=stock_val,
        sku=sku,
        is_active=is_active,
    )

    for i, b64 in enumerate(valid_images):
        try:
            content_file = _save_cropped_image(b64, 'products/variants', filename_prefix=f'v{variant.id}')
            vi = VariantImage(variant=variant, order=i, is_primary=(i == 0))
            vi.image.save(content_file.name, content_file, save=True)
        except Exception as e:
            pass

    messages.success(request, f"Variant added successfully to '{product.name}'.")

    if not product.variants.filter(is_deleted=False, is_default=True).exclude(id=variant.id).exists():
        variant.is_default = True
        variant.save()

    return redirect('variant_management', product_id=product_id)


@never_cache
@require_http_methods(["POST"])
def edit_variant(request, product_id, variant_id):
    if not is_admin(request.user):
        return redirect("admin_login")

    product = get_object_or_404(Product, id=product_id, is_deleted=False)
    variant = get_object_or_404(ProductVariant, id=variant_id, product=product)

    color = request.POST.get('color', '').strip()
    strap_material = request.POST.get('strap_material', '').strip()
    case_size = request.POST.get('case_size', '').strip()
    price = request.POST.get('price', '').strip()
    compare_at_price = request.POST.get('compare_at_price', '').strip()
    stock = request.POST.get('stock', '0').strip()
    sku = request.POST.get('sku', '').strip()
    is_active = request.POST.get('is_active') in ['on', '1', 'true', 'True']
    new_cropped_images = request.POST.getlist('cropped_images[]')
    delete_image_ids = request.POST.getlist('delete_images[]')

    if not price:
        messages.error(request, "Price is required.")
        return redirect('variant_management', product_id=product_id)

    try:
        price = float(price)
    except ValueError:
        messages.error(request, "Price must be a valid number.")
        return redirect('variant_management', product_id=product_id)

    compare_price_val = None
    if compare_at_price:
        try:
            compare_price_val = float(compare_at_price)
        except ValueError:
            pass

    try:
        stock_val = int(stock)
    except ValueError:
        stock_val = 0

    if delete_image_ids:
        VariantImage.objects.filter(id__in=delete_image_ids, variant=variant).delete()

    remaining_count = variant.images.count()
    new_valid = [img for img in new_cropped_images if img and img.startswith('data:image')]

    if remaining_count + len(new_valid) < 3:
        messages.error(request, "At least 3 images are required per variant.")
        return redirect('variant_management', product_id=product_id)

    next_order = variant.images.count()
    for i, b64 in enumerate(new_valid):
        try:
            content_file = _save_cropped_image(b64, 'products/variants', filename_prefix=f'v{variant.id}e')
            vi = VariantImage(variant=variant, order=next_order + i, is_primary=False)
            vi.image.save(content_file.name, content_file, save=True)
        except Exception:
            pass

    if not variant.images.filter(is_primary=True).exists():
        first = variant.images.first()
        if first:
            first.is_primary = True
            first.save()

    variant.color = color
    variant.strap_material = strap_material
    variant.case_size = case_size
    variant.price = price
    variant.compare_at_price = compare_price_val
    variant.stock = stock_val
    variant.sku = sku
    variant.is_active = is_active
    variant.save()

    messages.success(request, "Variant updated successfully.")
    return redirect('variant_management', product_id=product_id)


@never_cache
@require_POST
def delete_variant(request, product_id, variant_id):
    if not is_admin(request.user):
        return redirect("admin_login")
    product = get_object_or_404(Product, id=product_id, is_deleted=False)
    variant = get_object_or_404(ProductVariant, id=variant_id, product=product)
    was_default = variant.is_default
    variant.soft_delete()

    if was_default:
        next_v = product.variants.filter(is_deleted=False).order_by('created_at').first()
        if next_v:
            next_v.is_default = True
            next_v.save()
    messages.success(request, "Variant deleted successfully.")
    return redirect('variant_management', product_id=product_id)


@never_cache
@require_POST
def toggle_variant_status(request, product_id, variant_id):
    if not is_admin(request.user):
        return redirect("admin_login")
    product = get_object_or_404(Product, id=product_id, is_deleted=False)
    variant = get_object_or_404(ProductVariant, id=variant_id, product=product)
    variant.is_active = not variant.is_active
    variant.save()
    label = "Active" if variant.is_active else "Inactive"
    messages.success(request, f"Variant is now {label}.")
    return redirect('variant_management', product_id=product_id)


@never_cache
def get_product_json(request, product_id):
    if not is_admin(request.user):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    product = get_object_or_404(Product, id=product_id)
    return JsonResponse({
        'id': product.id,
        'name': product.name,
        'description': product.description,
        'brand': product.brand,
        'category_id': product.category_id,
        'is_active': product.is_active,
        'is_featured': product.is_featured,
    })


@never_cache
@require_POST
def set_default_variant(request, product_id, variant_id):
    if not is_admin(request.user):
        return redirect("admin_login")

    product = get_object_or_404(Product, id=product_id, is_deleted=False)
    variant = get_object_or_404(ProductVariant, id=variant_id, product=product, is_deleted=False)

    product.variants.filter(is_deleted=False).update(is_default=False)

    variant.is_default = True
    variant.save()

    messages.success(request, f"Default variant set to: {variant or 'Variant #' + str(variant.id)}.")
    return redirect('variant_management', product_id=product_id)

