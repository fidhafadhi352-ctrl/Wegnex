from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from django.db.models import Q, Sum
from django.core.paginator import Paginator
from decimal import Decimal
import json
import datetime

from user.checkout.models import Order, OrderItem
from user.wallet.models import Wallet, WalletTransaction


def is_admin_authorized(request):
    return request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser)


@never_cache
def order_management(request):
    if not is_admin_authorized(request):
        messages.error(request, "Please log in with administrator privileges to manage orders.")
        return redirect("admin_login")

    orders_qs = Order.objects.select_related('user', 'shipping_address').prefetch_related('items__product', 'items__variant').all()

    search_query = request.GET.get('search', '').strip()
    if search_query:
        orders_qs = orders_qs.filter(
            Q(order_number__icontains=search_query) |
            Q(shipping_full_name__icontains=search_query) |
            Q(shipping_phone__icontains=search_query) |
            Q(shipping_city__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query) |
            Q(items__product_name__icontains=search_query)
        ).distinct()

    status_filter = request.GET.get('status', '').strip()
    if status_filter and status_filter.lower() != 'all':
        status_key = status_filter.lower()
        if status_key == 'pending':
            orders_qs = orders_qs.filter(order_status__in=['PENDING', 'CONFIRMED', 'PROCESSING'])
        elif status_key == 'shipped':
            orders_qs = orders_qs.filter(order_status='SHIPPED')
        elif status_key in ['out for delivery', 'out_for_delivery']:
            orders_qs = orders_qs.filter(order_status='OUT_FOR_DELIVERY')
        elif status_key == 'delivered':
            orders_qs = orders_qs.filter(order_status='DELIVERED')
        elif status_key == 'cancelled':
            orders_qs = orders_qs.filter(order_status='CANCELLED')
        elif status_key in ['return_requested', 'return-requested', 'return requested']:
            orders_qs = orders_qs.filter(Q(order_status='RETURN_REQUESTED') | Q(items__status='RETURN_REQUESTED')).distinct()
        elif status_key == 'returned':
            orders_qs = orders_qs.filter(Q(order_status='RETURNED') | Q(items__status='RETURNED')).distinct()
        elif status_key == 'paid':
            orders_qs = orders_qs.filter(payment_status='PAID')
        else:
            orders_qs = orders_qs.filter(order_status__iexact=status_filter)


    sort_by = request.GET.get('sort', 'date_desc').strip()
    if sort_by == 'date_asc':
        orders_qs = orders_qs.order_by('created_at')
    elif sort_by == 'total_desc':
        orders_qs = orders_qs.order_by('-total_amount')
    elif sort_by == 'total_asc':
        orders_qs = orders_qs.order_by('total_amount')
    elif sort_by == 'order_id_desc':
        orders_qs = orders_qs.order_by('-order_number')
    elif sort_by == 'order_id_asc':
        orders_qs = orders_qs.order_by('order_number')
    else: 
        sort_by = 'date_desc'
        orders_qs = orders_qs.order_by('-created_at')
 
    all_orders = Order.objects.all()
    total_revenue = all_orders.exclude(order_status='CANCELLED').aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00')
    total_orders_count = all_orders.count()
    pending_fulfillment_count = all_orders.filter(order_status__in=['PENDING', 'CONFIRMED', 'PROCESSING']).count()
    cancelled_orders_count = all_orders.filter(order_status='CANCELLED').count()
    return_requests_count = OrderItem.objects.filter(status='RETURN_REQUESTED').count()
    return_rate = round((cancelled_orders_count / total_orders_count * 100), 1) if total_orders_count > 0 else 0.0

  
    paginator = Paginator(orders_qs, 8)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    total_filtered = paginator.count
    if total_filtered == 0:
        showing_start = 0
        showing_end = 0
    else:
        showing_start = page_obj.start_index()
        showing_end = page_obj.end_index()

    has_active_filters = bool(
        search_query or
        (status_filter and status_filter.lower() != 'all') or
        (sort_by and sort_by != 'date_desc')
    )

    context = {
        'page_obj': page_obj,
        'orders': page_obj.object_list,
        'search_query': search_query,
        'status_filter': status_filter,
        'sort_by': sort_by,
        'has_active_filters': has_active_filters,
        'total_revenue': total_revenue,
        'total_orders_count': total_orders_count,
        'pending_fulfillment_count': pending_fulfillment_count,
        'cancelled_orders_count': cancelled_orders_count,
        'return_requests_count': return_requests_count,
        'return_rate': return_rate,
        'showing_start': showing_start,
        'showing_end': showing_end,
        'total_filtered': total_filtered,
    }
    return render(request, "order_management.html", context)


@never_cache
def order_details(request, order_number=None):
   
    if not is_admin_authorized(request):
        messages.error(request, "Please log in with administrator privileges to view order details.")
        return redirect("admin_login")

    order = None
    if order_number:
        order = get_object_or_404(
            Order.objects.select_related('user', 'shipping_address').prefetch_related('items__product', 'items__variant'),
            order_number=order_number
        )
    else:

        order = Order.objects.select_related('user', 'shipping_address').prefetch_related('items__product', 'items__variant').order_by('-created_at').first()

    items = []
    has_return_requests = False
    if order:
        for itm in order.items.all():
            img_url = None
            if itm.product and hasattr(itm.product, 'images') and itm.product.images.exists():
                first_img = itm.product.images.first()
                if first_img and first_img.image:
                    img_url = first_img.image.url

            is_return_requested = (itm.status == 'RETURN_REQUESTED')
            if is_return_requested:
                has_return_requests = True

            items.append({
                'item_obj': itm,
                'id': itm.id,
                'product_name': itm.product_name,
                'variant_info': itm.variant_info or 'Standard',
                'sku': getattr(itm.variant, 'sku', f"WGX-{itm.id:04d}"),
                'price': itm.price,
                'quantity': itm.quantity,
                'item_total': itm.item_total,
                'status': itm.status,
                'is_return_requested': is_return_requested,
                'is_returned': itm.status == 'RETURNED',
                'is_cancelled': itm.status == 'CANCELLED',
                'is_delivered': itm.status == 'DELIVERED',
                'image_url': img_url or "https://images.unsplash.com/photo-1523170335258-f5ed11844a49?auto=format&fit=crop&w=300&q=80",
                'cancellation_reason': itm.cancellation_reason,
            })

    if order and order.order_status == 'RETURN_REQUESTED':
        has_return_requests = True

    total_return_requested_amount = sum(itm['item_total'] for itm in items if itm['is_return_requested'])

    status_choices = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('SHIPPED', 'Shipped'),
        ('OUT_FOR_DELIVERY', 'Out for Delivery'),
        ('DELIVERED', 'Delivered'),
        ('CANCELLED', 'Cancelled'),
        ('RETURN_REQUESTED', 'Return Requested'),
        ('RETURNED', 'Returned'),
    ]

    context = {
        'order': order,
        'items': items,
        'has_return_requests': has_return_requests,
        'total_return_requested_amount': total_return_requested_amount,
        'status_choices': status_choices,
        'current_status': order.order_status if order else 'PENDING',
    }
    return render(request, "order_details.html", context)


@never_cache
@require_POST
def update_order_status(request, order_number=None):
    if not is_admin_authorized(request):
        return JsonResponse({'success': False, 'message': 'Unauthorized access.'}, status=403)

    if not order_number:
        order_number = request.POST.get('order_number')

    if not order_number and request.body:
        try:
            body_data = json.loads(request.body)
            order_number = body_data.get('order_number')
            raw_status = body_data.get('status') or body_data.get('new_status')
        except Exception:
            raw_status = None
    else:
        raw_status = request.POST.get('status') or request.POST.get('new_status')

    if not order_number:
        return JsonResponse({'success': False, 'message': 'Order number is required.'}, status=400)

    try:
        order = Order.objects.prefetch_related('items__variant').get(order_number=order_number)
    except Order.DoesNotExist:
        return JsonResponse({'success': False, 'message': f"Order #{order_number} not found."}, status=404)

    if not raw_status:
        return JsonResponse({'success': False, 'message': 'New status is required.'}, status=400)

    status_clean = raw_status.strip().upper()
    status_mapping = {
        'PENDING': 'PENDING',
        'CONFIRMED': 'CONFIRMED',
        'PROCESSING': 'PROCESSING',
        'SHIPPED': 'SHIPPED',
        'OUT FOR DELIVERY': 'OUT_FOR_DELIVERY',
        'OUT_FOR_DELIVERY': 'OUT_FOR_DELIVERY',
        'DELIVERED': 'DELIVERED',
        'CANCELLED': 'CANCELLED',
        'RETURN_REQUESTED': 'RETURN_REQUESTED',
        'RETURN REQUESTED': 'RETURN_REQUESTED',
        'RETURNED': 'RETURNED',
    }

    new_status = status_mapping.get(status_clean)
    if not new_status:
        return JsonResponse({
            'success': False,
            'message': f"Invalid status: '{raw_status}'. Allowed statuses: Pending, Processing, Shipped, Out for Delivery, Delivered, Cancelled, Returned."
        }, status=400)

    old_status = order.order_status
    if old_status == new_status:
        return JsonResponse({
            'success': True,
            'message': f"Order status is already {order.get_order_status_display()}.",
            'order_number': order.order_number,
            'new_status': order.order_status,
            'new_status_display': order.get_order_status_display(),
            'payment_status': order.payment_status,
        })

    # Sequential transition rules:
    # Pending/Confirmed -> Shipped or Cancelled
    # Shipped/Processing -> Out for Delivery or Cancelled
    # Out for Delivery -> Delivered or Cancelled
    # Delivered, Cancelled, Returned cannot transition further
    valid_transitions = {
        'PENDING': ['SHIPPED', 'CANCELLED'],
        'CONFIRMED': ['SHIPPED', 'CANCELLED'],
        'PROCESSING': ['SHIPPED', 'OUT_FOR_DELIVERY', 'CANCELLED'],
        'SHIPPED': ['OUT_FOR_DELIVERY', 'CANCELLED'],
        'OUT_FOR_DELIVERY': ['DELIVERED', 'CANCELLED'],
        'DELIVERED': [],
        'CANCELLED': [],
        'RETURNED': [],
        'RETURN_REQUESTED': ['RETURNED'],
    }

    allowed_transitions = valid_transitions.get(old_status, [])
    if new_status not in allowed_transitions:
        old_display = order.get_order_status_display()
        new_display = dict(Order.ORDER_STATUS_CHOICES).get(new_status, new_status)
        return JsonResponse({
            'success': False,
            'message': f"Cannot change order status from '{old_display}' to '{new_display}'. Orders must follow sequential progression: Pending → Shipped → Out for Delivery → Delivered."
        }, status=400)

    if new_status == 'CANCELLED':
        for itm in order.items.exclude(status='CANCELLED'):
            itm.status = 'CANCELLED'
            itm.cancellation_reason = f"Cancelled by Administrator on {datetime.datetime.now().strftime('%b %d, %Y %I:%M %p')}"
            itm.save()
            if itm.variant:
                itm.variant.stock += itm.quantity
                itm.variant.save()

        order.order_status = 'CANCELLED'

        refund_msg = ""
        if order.payment_status == 'PAID':
            already_refunded = WalletTransaction.objects.filter(
                order=order,
                transaction_type='CREDIT',
                source__in=['ORDER_CANCELLATION_REFUND', 'ORDER_RETURN_REFUND']
            ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')

            refundable_amount = max(Decimal('0.00'), order.total_amount - already_refunded)
            if refundable_amount > Decimal('0.00'):
                wallet_obj, _ = Wallet.objects.get_or_create(user=order.user)
                wallet_obj.credit(
                    amount=refundable_amount,
                    description=f'Refund for cancellation of Order #{order.order_number} by Administrator',
                    source='ORDER_CANCELLATION_REFUND',
                    order=order,
                    reference=order.order_number
                )
                now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
                order.notes = (order.notes or '') + f"\n[Refund] ₹{refundable_amount:,.2f} refunded directly to wallet on admin cancellation ({now_str})."
                refund_msg = f" ₹{refundable_amount:,.2f} refunded directly to {order.user.username}'s wallet."

        order.notes = (order.notes or '') + f"\nOrder cancelled by admin on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        order.save()

        return JsonResponse({
            'success': True,
            'order_number': order.order_number,
            'new_status': 'CANCELLED',
            'new_status_display': 'Cancelled',
            'payment_status': order.payment_status,
            'message': f"Order #{order.order_number} has been CANCELLED.{refund_msg} Inventory restored."
        })

    if old_status == 'CANCELLED' and new_status != 'CANCELLED':
        for itm in order.items.all():
            if itm.variant:
                if itm.variant.stock >= itm.quantity:
                    itm.variant.stock -= itm.quantity
                    itm.variant.save()
            itm.status = new_status
            itm.cancellation_reason = None
            itm.save()

    if new_status == 'RETURNED' and old_status == 'RETURN_REQUESTED':
        for itm in order.items.filter(status='RETURN_REQUESTED'):
            already_refunded = WalletTransaction.objects.filter(
                order=order,
                transaction_type='CREDIT',
                source='ORDER_RETURN_REFUND',
                description__icontains=f"#{itm.id}"
            ).exists()
            if not already_refunded and not (itm.status == 'RETURNED' and 'credited to wallet' in (itm.cancellation_reason or '')):
                wallet_obj, _ = Wallet.objects.get_or_create(user=order.user)
                wallet_obj.credit(
                    amount=itm.item_total,
                    description=f'Return refund for {itm.product_name} x{itm.quantity} (Order #{order.order_number} Item #{itm.id}) - Approved by Admin',
                    source='ORDER_RETURN_REFUND',
                    order=order,
                    reference=order.order_number
                )
                if itm.variant:
                    itm.variant.stock += itm.quantity
                    itm.variant.save(update_fields=['stock'])
            itm.status = 'RETURNED'
            now_str = datetime.datetime.now().strftime("%b %d, %Y %I:%M %p")
            itm.cancellation_reason = (itm.cancellation_reason or '') + f' | Return approved & refunded to wallet on {now_str}.'
            itm.save(update_fields=['status', 'cancellation_reason'])

    order.order_status = new_status

    if new_status == 'DELIVERED' and order.payment_method == 'COD':
        order.payment_status = 'PAID'

    order.save()

    for itm in order.items.exclude(status__in=['CANCELLED', 'RETURNED', 'RETURN_REQUESTED']):
        itm.status = new_status
        itm.save()

    return JsonResponse({
        'success': True,
        'order_number': order.order_number,
        'new_status': order.order_status,
        'new_status_display': order.get_order_status_display(),
        'payment_status': order.payment_status,
        'message': f"Order #{order.order_number} status updated to {order.get_order_status_display()} successfully."
    })


@never_cache
@require_POST
def approve_return_refund(request, item_id):
   
    if not is_admin_authorized(request):
        return JsonResponse({'success': False, 'message': 'Unauthorized access.'}, status=403)

    try:
        item = OrderItem.objects.select_related('order__user', 'variant').get(id=item_id)
    except OrderItem.DoesNotExist:
        return JsonResponse({'success': False, 'message': f'Order item #{item_id} not found.'}, status=404)

    if item.status not in ['RETURN_REQUESTED', 'RETURNED']:
        return JsonResponse({
            'success': False,
            'message': f"Item is in '{item.status}' status. Only items with a return request can be approved."
        }, status=400)

    order = item.order
    user = order.user

    already_refunded = WalletTransaction.objects.filter(
        order=order,
        transaction_type='CREDIT',
        source='ORDER_RETURN_REFUND',
        description__icontains=f"#{item.id}"
    ).exists()

    if already_refunded or (item.status == 'RETURNED' and 'credited to wallet' in (item.cancellation_reason or '')):
        return JsonResponse({
            'success': False,
            'message': f"Return refund for '{item.product_name}' has already been processed to {user.username}'s wallet."
        }, status=400)

    refund_amount = item.item_total

    if item.variant:
        item.variant.stock += item.quantity
        item.variant.save(update_fields=['stock'])

    wallet_obj, _ = Wallet.objects.get_or_create(user=user)
    wallet_obj.credit(
        amount=refund_amount,
        description=f'Return refund for {item.product_name} x{item.quantity} (Order #{order.order_number} Item #{item.id}) - Approved by Admin',
        source='ORDER_RETURN_REFUND',
        order=order,
        reference=order.order_number
    )

    now_str = datetime.datetime.now().strftime("%b %d, %Y %I:%M %p")
    item.status = 'RETURNED'
    item.cancellation_reason = (item.cancellation_reason or '') + f' | Return approved & refund of ₹{refund_amount:,.2f} credited to wallet on {now_str}.'
    item.save(update_fields=['status', 'cancellation_reason'])

    if not order.items.exclude(status__in=['RETURNED', 'CANCELLED']).exists():
        order.order_status = 'RETURNED'
        order.save(update_fields=['order_status'])

    return JsonResponse({
        'success': True,
        'message': f"Return approved! Refund of ₹{refund_amount:,.2f} credited to {user.username}'s wallet.",
        'item_id': item_id,
        'refund_amount': float(refund_amount),
        'user': user.username,
        'new_wallet_balance': float(wallet_obj.balance),
        'order_status': order.order_status,
    })


@never_cache
@require_POST
def reject_return_request(request, item_id):

    if not is_admin_authorized(request):
        return JsonResponse({'success': False, 'message': 'Unauthorized access.'}, status=403)

    try:
        item = OrderItem.objects.select_related('order__user').get(id=item_id)
    except OrderItem.DoesNotExist:
        return JsonResponse({'success': False, 'message': f'Order item #{item_id} not found.'}, status=404)

    if item.status != 'RETURN_REQUESTED':
        return JsonResponse({
            'success': False,
            'message': f"Item is in '{item.status}' status. Only items with pending return requests can be rejected."
        }, status=400)

    admin_note = request.POST.get('reason', 'Return rejected by Administrator')
    item.status = 'DELIVERED'
    now_str = datetime.datetime.now().strftime("%b %d, %Y %I:%M %p")
    item.cancellation_reason = (item.cancellation_reason or '') + f' | Return rejected on {now_str}. Note: {admin_note}'
    item.save(update_fields=['status', 'cancellation_reason'])

    order = item.order
    if order.order_status == 'RETURN_REQUESTED':
        order.order_status = 'DELIVERED'
        order.save(update_fields=['order_status'])

    return JsonResponse({
        'success': True,
        'message': f"Return request for '{item.product_name}' was rejected.",
        'item_id': item_id,
    })


@never_cache
@require_POST
def approve_all_returns_for_order(request, order_number):
    if not is_admin_authorized(request):
        return JsonResponse({'success': False, 'message': 'Unauthorized access.'}, status=403)

    try:
        order = Order.objects.prefetch_related('items__variant', 'items__product').get(order_number=order_number)
    except Order.DoesNotExist:
        return JsonResponse({'success': False, 'message': f'Order #{order_number} not found.'}, status=404)

    return_items = order.items.filter(status='RETURN_REQUESTED')
    if not return_items.exists():
        if order.order_status == 'RETURN_REQUESTED':
            return_items = order.items.filter(status__in=['RETURN_REQUESTED', 'DELIVERED'])

    if not return_items.exists():
        return JsonResponse({'success': False, 'message': 'No pending return requests found for this order.'}, status=400)

    user = order.user
    wallet_obj, _ = Wallet.objects.get_or_create(user=user)
    total_refund = Decimal('0.00')
    now_str = datetime.datetime.now().strftime("%b %d, %Y %I:%M %p")

    for item in return_items:
        already_refunded = WalletTransaction.objects.filter(
            order=order,
            transaction_type='CREDIT',
            source='ORDER_RETURN_REFUND',
            description__icontains=f"#{item.id}"
        ).exists()

        if not already_refunded and not (item.status == 'RETURNED' and 'credited to wallet' in (item.cancellation_reason or '')):
            refund_amount = item.item_total
            if item.variant:
                item.variant.stock += item.quantity
                item.variant.save(update_fields=['stock'])

            wallet_obj.credit(
                amount=refund_amount,
                description=f'Return refund for {item.product_name} x{item.quantity} (Order #{order.order_number} Item #{item.id}) - Approved by Admin',
                source='ORDER_RETURN_REFUND',
                order=order,
                reference=order.order_number
            )
            total_refund += refund_amount

        item.status = 'RETURNED'
        item.cancellation_reason = (item.cancellation_reason or '') + f' | Return approved & refund of ₹{item.item_total:,.2f} credited to wallet on {now_str}.'
        item.save(update_fields=['status', 'cancellation_reason'])

    order.order_status = 'RETURNED'
    order.save(update_fields=['order_status'])

    return JsonResponse({
        'success': True,
        'message': f"Return approved! Refund of ₹{total_refund:,.2f} credited to {user.username}'s wallet.",
        'order_number': order.order_number,
        'refund_amount': float(total_refund),
        'user': user.username,
        'new_wallet_balance': float(wallet_obj.balance),
        'order_status': 'RETURNED'
    })


@never_cache
@require_POST
def reject_all_returns_for_order(request, order_number):
    if not is_admin_authorized(request):
        return JsonResponse({'success': False, 'message': 'Unauthorized access.'}, status=403)

    try:
        order = Order.objects.prefetch_related('items').get(order_number=order_number)
    except Order.DoesNotExist:
        return JsonResponse({'success': False, 'message': f'Order #{order_number} not found.'}, status=404)

    admin_note = request.POST.get('reason', 'Return rejected by Administrator')
    now_str = datetime.datetime.now().strftime("%b %d, %Y %I:%M %p")

    return_items = order.items.filter(status='RETURN_REQUESTED')
    for item in return_items:
        item.status = 'DELIVERED'
        item.cancellation_reason = (item.cancellation_reason or '') + f' | Return rejected on {now_str}. Note: {admin_note}'
        item.save(update_fields=['status', 'cancellation_reason'])

    order.order_status = 'DELIVERED'
    order.save(update_fields=['order_status'])

    return JsonResponse({
        'success': True,
        'message': f"Return request for Order #{order.order_number} was rejected.",
        'order_number': order.order_number,
        'order_status': 'DELIVERED'
    })


