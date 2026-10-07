from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_http_methods
from user.account.models import Category


def is_admin_authorized(user):
    """Ensure the user is authenticated, active, and has staff/superuser privileges."""
    return user.is_authenticated and (user.is_staff or user.is_superuser) and user.is_active


@never_cache
def category_management(request):
    if not is_admin_authorized(request.user):
        messages.error(request, "Please log in with administrator privileges.")
        return redirect("admin_login")

    # Base Queryset — only non-deleted categories
    base_qs = Category.objects.filter(is_deleted=False)

    # Statistics (3 stat cards — no soft-delete card)
    total_categories = base_qs.count()
    active_categories = base_qs.filter(is_active=True).count()
    inactive_categories = base_qs.filter(is_active=False).count()

    # Backend Search with Cancel/Clear button support
    search_query = request.GET.get('search', '').strip()
    if search_query:
        categories_qs = base_qs.filter(
            Q(name__icontains=search_query) | Q(description__icontains=search_query)
        )
    else:
        categories_qs = base_qs

    # Sorting: fixed descending (newest first) — no dropdown
    categories_qs = categories_qs.order_by('-created_at', '-id')

    # Backend Pagination — 6 per page
    paginator = Paginator(categories_qs, 6)
    page_number = request.GET.get('page', 1)
    try:
        page_obj = paginator.get_page(page_number)
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.get_page(1)

    context = {
        'admin_user': request.user,
        'categories': page_obj,
        'page_obj': page_obj,
        'paginator': paginator,
        'search_query': search_query,
        'total_categories': total_categories,
        'active_categories': active_categories,
        'inactive_categories': inactive_categories,
    }
    return render(request, "category_management.html", context)


@never_cache
@require_http_methods(["GET", "POST"])
def add_category(request):
    if not is_admin_authorized(request.user):
        messages.error(request, "Please log in with administrator privileges.")
        return redirect("admin_login")

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        is_active = request.POST.get("is_active") in ["true", "True", "1", "on"]
        is_featured = request.POST.get("is_featured") in ["true", "True", "1", "on"]
        image = request.FILES.get("image")

        # Name validations
        if not name:
            messages.error(request, "Category name is required.")
            return redirect("category_management")

        if len(name) < 2 or len(name) > 100:
            messages.error(request, "Category name must be between 2 and 100 characters.")
            return redirect("category_management")

        # Check unique name (case-insensitive for non-deleted categories)
        if Category.objects.filter(name__iexact=name, is_deleted=False).exists():
            messages.error(request, f"A category with the name '{name}' already exists.")
            return redirect("category_management")

        # Validate image if provided
        if image:
            valid_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.avif', '.gif']
            ext = '.' + image.name.split('.')[-1].lower() if '.' in image.name else ''
            if ext not in valid_extensions:
                messages.error(request, "Please upload a valid image file (JPG, PNG, WEBP, AVIF).")
                return redirect("category_management")
            if image.size > 5 * 1024 * 1024:
                messages.error(request, "Image size should not exceed 5MB.")
                return redirect("category_management")

        Category.objects.create(
            name=name,
            description=description,
            image=image,
            is_active=is_active,
            is_featured=is_featured,
        )
        messages.success(request, f"Category '{name}' created successfully.")
        return redirect("category_management")

    return redirect("category_management")


@never_cache
@require_http_methods(["GET", "POST"])
def edit_category(request, category_id):
    if not is_admin_authorized(request.user):
        messages.error(request, "Please log in with administrator privileges.")
        return redirect("admin_login")

    category = get_object_or_404(Category, id=category_id)

    # Support fetching category details via JSON for modal population
    if request.method == "GET":
        if request.headers.get("x-requested-with") == "XMLHttpRequest" or request.GET.get("format") == "json":
            return JsonResponse({
                "status": "success",
                "category": {
                    "id": category.id,
                    "name": category.name,
                    "description": category.description,
                    "image_url": category.image.url if category.image else "",
                    "is_active": category.is_active,
                    "is_featured": category.is_featured,
                }
            })
        return redirect("category_management")

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        is_active = request.POST.get("is_active") in ["true", "True", "1", "on"]
        is_featured = request.POST.get("is_featured") in ["true", "True", "1", "on"]
        image = request.FILES.get("image")
        remove_image = request.POST.get("remove_image") in ["1", "true", "on"]

        if not name:
            messages.error(request, "Category name cannot be empty.")
            return redirect("category_management")

        if len(name) < 2 or len(name) > 100:
            messages.error(request, "Category name must be between 2 and 100 characters.")
            return redirect("category_management")

        # Duplicate check excluding current category
        if Category.objects.filter(name__iexact=name, is_deleted=False).exclude(id=category.id).exists():
            messages.error(request, f"Another category with the name '{name}' already exists.")
            return redirect("category_management")

        if image:
            valid_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.avif', '.gif']
            ext = '.' + image.name.split('.')[-1].lower() if '.' in image.name else ''
            if ext not in valid_extensions:
                messages.error(request, "Please upload a valid image file (JPG, PNG, WEBP, AVIF).")
                return redirect("category_management")
            if image.size > 5 * 1024 * 1024:
                messages.error(request, "Image size should not exceed 5MB.")
                return redirect("category_management")
            category.image = image
        elif remove_image and category.image:
            category.image.delete(save=False)
            category.image = None

        category.name = name
        category.description = description
        category.is_active = is_active
        category.is_featured = is_featured
        category.save()

        messages.success(request, f"Category '{category.name}' updated successfully.")
        return redirect("category_management")


@never_cache
@require_POST
def delete_category(request, category_id):
    """Soft-delete category and all its products."""
    if not is_admin_authorized(request.user):
        messages.error(request, "Please log in with administrator privileges.")
        return redirect("admin_login")

    category = get_object_or_404(Category, id=category_id)
    affected_count = category.products.filter(is_deleted=False).count()
    category.soft_delete()
    if affected_count > 0:
        messages.success(request, f"Category '{category.name}' and its {affected_count} associated product(s) have been removed.")
    else:
        messages.success(request, f"Category '{category.name}' has been deleted.")
    return redirect("category_management")


@never_cache
@require_POST
def restore_category(request, category_id):
    """Restore soft-deleted category and its products."""
    if not is_admin_authorized(request.user):
        messages.error(request, "Please log in with administrator privileges.")
        return redirect("admin_login")

    category = get_object_or_404(Category, id=category_id)
    category.restore()
    messages.success(request, f"Category '{category.name}' and its associated products have been restored.")
    return redirect(f"{request.META.get('HTTP_REFERER', '/admin_panel/category_management/?filter=deleted')}")


@never_cache
@require_POST
def toggle_category_status(request, category_id):
    """Toggle Active / Inactive status of category and its products."""
    if not is_admin_authorized(request.user):
        messages.error(request, "Please log in with administrator privileges.")
        return redirect("admin_login")

    category = get_object_or_404(Category, id=category_id)
    category.is_active = not category.is_active
    category.save()

    if not category.is_active:
        category.products.filter(is_deleted=False).update(is_active=False)
    else:
        category.products.filter(is_deleted=False).update(is_active=True)

    status_label = "Active" if category.is_active else "Inactive"
    messages.success(request, f"Category '{category.name}' and its products are now {status_label}.")
    return redirect(f"{request.META.get('HTTP_REFERER', '/admin_panel/category_management/')}")