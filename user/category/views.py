from django.shortcuts import render, get_object_or_404
from user.account.models import Category
from admin_panel.product_management.models import Product


def category(request):
    """Show all active, non-deleted categories as cards."""
    categories = Category.objects.filter(is_active=True, is_deleted=False)

    context = {
        'categories': categories,
    }
    if request.user.is_authenticated:
        from user.user_profile.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        context['profile'] = profile

    return render(request, 'category.html', context)


def category_products(request, category_id):
    """Show products filtered by a specific category."""
    cat = get_object_or_404(Category, id=category_id, is_active=True, is_deleted=False)

    products = Product.objects.filter(
        category=cat,
        is_active=True,
        is_deleted=False,
    ).prefetch_related('variants__images')

    context = {
        'selected_category': cat,
        'products': products,
        'all_categories': Category.objects.filter(is_active=True, is_deleted=False),
    }
    if request.user.is_authenticated:
        from user.user_profile.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        context['profile'] = profile

    return render(request, 'category_products.html', context)