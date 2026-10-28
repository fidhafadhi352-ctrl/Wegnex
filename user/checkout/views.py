from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.contrib import messages
from django.conf import settings
from django.urls import reverse
from decimal import Decimal
import json
import re
import razorpay

from .models import Order, OrderItem
from user.cart.models import CartItem
from user.address_page.models import Add_Address
from user.address_page.views import validate_address_data
from admin_panel.product_management.models import Product, ProductVariant
from admin_panel.wegnex_admin.models import Coupon
from django.utils import timezone
from user.wallet.models import Wallet, WalletTransaction


def _get_enriched_cart(user):
    raw_items = CartItem.objects.filter(
        user=user
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
        price = Decimal(str(v.price)) if v else Decimal('0.00')
        compare_price = Decimal(str(v.compare_at_price)) if (v and v.compare_at_price) else None

        image_url = None
        if v and v.images.first():
            image_url = v.images.first().image.url
        elif p.thumbnail:
            image_url = p.thumbnail.url

        variant_label = v.color if (v and v.color) else ''
        item_total = price * ci.quantity

        enriched.append({
            'id': ci.id,
            'product': p,
            'variant': v,
            'variant_label': variant_label,
            'image_url': image_url,
            'price': price,
            'compare_price': compare_price,
            'stock': stock,
            'quantity': ci.quantity,
            'item_total': item_total,
            'is_out_of_stock': stock <= 0,
            'is_insufficient_stock': ci.quantity > stock,
        })
    return enriched


@login_required
def checkout(request):
    cart_items = _get_enriched_cart(request.user)

    if not cart_items:
        messages.warning(request, "Your cart is empty. Please add items before checking out.")
        return redirect('cart')

    has_oos = any(item['is_out_of_stock'] or item['is_insufficient_stock'] for item in cart_items)

    subtotal = sum(item['item_total'] for item in cart_items if not item['is_out_of_stock'])
    shipping_fee = Decimal('0.00')  
    tax = Decimal('0.00')           
    discount = Decimal('0.00')
    applied_coupon = None

    coupon_code = request.session.get('coupon_code')
    if coupon_code:
        try:
            coupon_obj = Coupon.objects.get(code=coupon_code)
            valid, reason = coupon_obj.is_valid()
            if valid and subtotal >= coupon_obj.minimum_order_amount:
                discount = Decimal(str(coupon_obj.calculate_discount(float(subtotal))))
                applied_coupon = coupon_obj
            else:
                request.session.pop('coupon_code', None)
                request.session.pop('coupon_id', None)
                request.session.pop('coupon_discount', None)
                coupon_code = None
        except Exception:
            request.session.pop('coupon_code', None)
            request.session.pop('coupon_id', None)
            request.session.pop('coupon_discount', None)
            coupon_code = None

    final_price = max(Decimal('0.00'), subtotal - discount + shipping_fee + tax)

    now = timezone.now()
    available_coupons = Coupon.objects.filter(
        is_active=True
    ).exclude(
        valid_until__lt=now
    ).order_by('-discount_value')

    addresses = Add_Address.objects.filter(user=request.user).order_by('-is_default', '-created_at')
    selected_address = addresses.filter(is_default=True).first() or addresses.first()

    wallet_obj, _ = Wallet.objects.get_or_create(user=request.user)
    wallet_balance = wallet_obj.balance

    try:
        from user.user_profile.models import UserProfile
        profile = UserProfile.objects.get(user=request.user)
    except Exception:
        profile = None

    context = {
        'cart_items': cart_items,
        'item_count': sum(i['quantity'] for i in cart_items),
        'has_oos': has_oos,
        'subtotal': subtotal,
        'shipping_fee': shipping_fee,
        'tax': tax,
        'discount': discount,
        'final_price': final_price,
        'coupon_code': coupon_code,
        'applied_coupon': applied_coupon,
        'available_coupons': available_coupons,
        'addresses': addresses,
        'selected_address': selected_address,
        'razorpay_key_id': settings.RAZORPAY_KEY_ID,
        'wallet_balance': wallet_balance,
        'wallet_sufficient': wallet_balance >= final_price,
        'profile': profile,
    }
    return render(request, "checkout.html", context)


@login_required
@require_POST
def apply_coupon(request):
    
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json'

    code = (request.POST.get('coupon_code') or request.POST.get('code') or '').strip().upper()
    if not code and request.body:
        try:
            data = json.loads(request.body.decode('utf-8'))
            code = (data.get('coupon_code') or data.get('code') or '').strip().upper()
        except Exception:
            code = ''

    cart_items = _get_enriched_cart(request.user)
    if not cart_items:
        msg = "Your cart is empty. Please add items before applying a coupon."
        if is_ajax:
            return JsonResponse({'success': False, 'message': msg})
        messages.error(request, msg)
        return redirect('checkout')

    subtotal = sum(item['item_total'] for item in cart_items if not item['is_out_of_stock'])

    if not code:
        msg = "Please enter a coupon code."
        if is_ajax:
            return JsonResponse({'success': False, 'message': msg})
        messages.error(request, msg)
        return redirect('checkout')

    existing_coupon = request.session.get('coupon_code')
    if existing_coupon:
        if existing_coupon.upper() == code:
            msg = f"Coupon '{code}' is already applied to this order."
        else:
            msg = f"Coupon '{existing_coupon}' is already applied. Only one coupon can be used per order. Please remove the current coupon before applying '{code}'."
        if is_ajax:
            return JsonResponse({'success': False, 'message': msg, 'already_applied': True})
        messages.warning(request, msg)
        return redirect('checkout')

    try:
        coupon = Coupon.objects.get(code__iexact=code)
    except Coupon.DoesNotExist:
        msg = f"Coupon '{code}' does not exist or is invalid."
        if is_ajax:
            return JsonResponse({'success': False, 'message': msg})
        messages.error(request, msg)
        return redirect('checkout')
    
    is_valid, reason = coupon.is_valid()
    if not is_valid:
        if is_ajax:
            return JsonResponse({'success': False, 'message': reason})
        messages.error(request, reason)
        return redirect('checkout')

    if subtotal < coupon.minimum_order_amount:
        msg = f"Coupon '{coupon.code}' requires a minimum purchase of ₹{coupon.minimum_order_amount:,.0f}. (Your items subtotal: ₹{subtotal:,.0f})"
        if is_ajax:
            return JsonResponse({'success': False, 'message': msg})
        messages.error(request, msg)
        return redirect('checkout')

    discount = Decimal(str(coupon.calculate_discount(float(subtotal))))
    final_price = max(Decimal('0.00'), subtotal - discount)

    request.session['coupon_code'] = coupon.code
    request.session['coupon_id'] = coupon.id
    request.session['coupon_discount'] = float(discount)
    request.session.modified = True

    discount_desc = f"{coupon.discount_value:,.0f}% OFF" if coupon.discount_type == 'percentage' else f"₹{coupon.discount_value:,.0f} OFF"
    msg = f"Coupon '{coupon.code}' applied! You save ₹{discount:,.0f} on this order."

    if is_ajax:
        return JsonResponse({
            'success': True,
            'message': msg,
            'coupon_code': coupon.code,
            'discount': float(discount),
            'discount_formatted': f"₹{discount:,.0f}",
            'subtotal': float(subtotal),
            'final_price': float(final_price),
            'final_price_formatted': f"₹{final_price:,.0f}",
            'discount_type': coupon.discount_type,
            'discount_value': float(coupon.discount_value),
            'description': coupon.description or discount_desc,
        })

    messages.success(request, msg)
    return redirect('checkout')


@login_required
@require_POST
def remove_coupon(request):
    
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json'

    removed_code = request.session.pop('coupon_code', None)
    request.session.pop('coupon_id', None)
    request.session.pop('coupon_discount', None)
    request.session.modified = True

    cart_items = _get_enriched_cart(request.user)
    subtotal = sum(item['item_total'] for item in cart_items if not item['is_out_of_stock'])

    msg = f"Coupon '{removed_code}' removed." if removed_code else "No coupon was applied."

    if is_ajax:
        return JsonResponse({
            'success': True,
            'message': msg,
            'subtotal': float(subtotal),
            'final_price': float(subtotal),
            'final_price_formatted': f"₹{subtotal:,.0f}",
            'discount': 0.0,
        })

    messages.info(request, msg)
    return redirect('checkout')


@login_required
@require_POST
def place_order(request):
    cart_items = _get_enriched_cart(request.user)

    if not cart_items:
        messages.error(request, "Your cart is empty.")
        return redirect('cart')

    for item in cart_items:
        if item['is_out_of_stock']:
            messages.error(request, f"'{item['product'].name}' is out of stock. Please remove it from your cart.")
            return redirect('checkout')
        if item['is_insufficient_stock']:
            messages.error(request, f"'{item['product'].name}' only has {item['stock']} items available. Please update your cart.")
            return redirect('checkout')

    address_id = request.POST.get('address_id')
    if not address_id:
        messages.error(request, "Please select or add a shipping address.")
        return redirect('checkout')

    address = Add_Address.objects.filter(id=address_id, user=request.user).first()
    if not address:
        messages.error(request, "Invalid shipping address selected.")
        return redirect('checkout')

    payment_method = request.POST.get('payment_method', 'COD').upper()
    if payment_method not in ['COD', 'WALLET']:
        payment_method = 'COD'

    subtotal = sum(item['item_total'] for item in cart_items)
    shipping_fee = Decimal('0.00')
    tax = Decimal('0.00')
    discount = Decimal('0.00')

    coupon_code = request.session.get('coupon_code')
    if coupon_code:
        try:
            coupon_obj = Coupon.objects.get(code=coupon_code)
            valid, _ = coupon_obj.is_valid()
            if valid and subtotal >= coupon_obj.minimum_order_amount:
                discount = Decimal(str(coupon_obj.calculate_discount(float(subtotal))))
                coupon_obj.used_count += 1
                coupon_obj.save(update_fields=['used_count'])
            else:
                request.session.pop('coupon_code', None)
                request.session.pop('coupon_id', None)
                request.session.pop('coupon_discount', None)
                coupon_code = None
        except Exception:
            coupon_code = None

    final_price = max(Decimal('0.00'), subtotal - discount + shipping_fee + tax)

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json'

    if payment_method == 'WALLET':
        wallet_obj, _ = Wallet.objects.get_or_create(user=request.user)
        if wallet_obj.balance < final_price:
            msg = f"Insufficient wallet balance. Available: ₹{wallet_obj.balance:,.2f}, Required: ₹{final_price:,.2f}."
            if is_ajax:
                return JsonResponse({'success': False, 'msg': msg})
            messages.error(request, msg)
            return redirect('checkout')

    order_number = Order.generate_order_number()
    order = Order.objects.create(
        user=request.user,
        order_number=order_number,
        shipping_address=address,
        shipping_full_name=address.full_name,
        shipping_phone=address.phone_number,
        shipping_street_address=address.street_address,
        shipping_city=address.city,
        shipping_state=address.state,
        shipping_pincode=address.pincode,
        shipping_country=address.country,
        shipping_address_type=address.address_type,
        subtotal=subtotal,
        tax=tax,
        shipping_fee=shipping_fee,
        discount=discount,
        coupon_code=coupon_code,
        total_amount=final_price,
        payment_method=payment_method,
        payment_status='PENDING' if payment_method == 'COD' else 'PAID',
        order_status='CONFIRMED',
    )

    for item in cart_items:
        variant = item['variant']
        OrderItem.objects.create(
            order=order,
            product=item['product'],
            variant=variant,
            product_name=item['product'].name,
            variant_info=item['variant_label'],
            price=item['price'],
            quantity=item['quantity'],
            item_total=item['item_total'],
            status='CONFIRMED',
        )

        if variant:
            variant.stock = max(0, variant.stock - item['quantity'])
            variant.save()

    if payment_method == 'WALLET':
        wallet_obj.debit(
            amount=final_price,
            description=f'Payment for Order #{order.order_number}',
            source='ORDER_PAYMENT',
            order=order,
            reference=order.order_number
        )

    CartItem.objects.filter(user=request.user).delete()

    request.session.pop('coupon_code', None)
    request.session.pop('coupon_id', None)

    if is_ajax:
        return JsonResponse({
            'success': True,
            'msg': 'Order placed successfully using Wegnex Wallet!' if payment_method == 'WALLET' else 'Order placed successfully!',
            'order_number': order.order_number,
            'total_amount': float(order.total_amount),
            'payment_method': 'Wegnex Wallet (Paid)' if payment_method == 'WALLET' else order.get_payment_method_display(),
            'order_detail_url': reverse('order_detail', args=[order.order_number]),
            'redirect_url': reverse('order_success', args=[order.order_number]),
            'wallet_balance': float(wallet_obj.balance) if payment_method == 'WALLET' else None,
        })

    return redirect('order_success', order_number=order.order_number)


@login_required
@require_POST
def razorpay_create_order(request):

    try:
        address_id = request.POST.get('address_id')
        if not address_id and request.content_type == 'application/json':
            try:
                body = json.loads(request.body.decode('utf-8'))
                address_id = body.get('address_id')
            except Exception:
                pass

        cart_items = _get_enriched_cart(request.user)
        if not cart_items:
            return JsonResponse({'success': False, 'msg': 'Your cart is empty.'})

        for item in cart_items:
            if item['is_out_of_stock']:
                return JsonResponse({
                    'success': False,
                    'msg': f"'{item['product'].name}' is out of stock. Please remove it from your cart."
                })
            if item['is_insufficient_stock']:
                return JsonResponse({
                    'success': False,
                    'msg': f"'{item['product'].name}' only has {item['stock']} items available. Please update your cart."
                })

        if not address_id:
            return JsonResponse({'success': False, 'msg': 'Please select or add a shipping address.'})

        address = Add_Address.objects.filter(id=address_id, user=request.user).first()
        if not address:
            return JsonResponse({'success': False, 'msg': 'Invalid shipping address selected.'})

        subtotal = sum(item['item_total'] for item in cart_items)
        shipping_fee = Decimal('0.00')
        tax = Decimal('0.00')
        discount = Decimal('0.00')

        coupon_code = request.session.get('coupon_code')
        if coupon_code:
            try:
                from admin_panel.wegnex_admin.models import Coupon
                coupon_obj = Coupon.objects.get(code=coupon_code)
                valid, _ = coupon_obj.is_valid()
                if valid:
                    discount = Decimal(str(coupon_obj.calculate_discount(float(subtotal))))
                else:
                    request.session.pop('coupon_code', None)
                    request.session.pop('coupon_id', None)
                    coupon_code = None
            except Exception:
                coupon_code = None

        final_price = max(Decimal('1.00'), subtotal - discount + shipping_fee + tax)

        order_number = Order.generate_order_number()
        order = Order.objects.create(
            user=request.user,
            order_number=order_number,
            shipping_address=address,
            shipping_full_name=address.full_name,
            shipping_phone=address.phone_number,
            shipping_street_address=address.street_address,
            shipping_city=address.city,
            shipping_state=address.state,
            shipping_pincode=address.pincode,
            shipping_country=address.country,
            shipping_address_type=address.address_type,
            subtotal=subtotal,
            tax=tax,
            shipping_fee=shipping_fee,
            discount=discount,
            coupon_code=coupon_code,
            total_amount=final_price,
            payment_method='RAZORPAY',
            payment_status='PENDING',
            order_status='PENDING',
        )

        for item in cart_items:
            OrderItem.objects.create(
                order=order,
                product=item['product'],
                variant=item['variant'],
                product_name=item['product'].name,
                variant_info=item['variant_label'],
                price=item['price'],
                quantity=item['quantity'],
                item_total=item['item_total'],
                status='PENDING',
            )

        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        client.set_app_details({'title': 'Wegnex', 'version': '1.0'})
        amount_in_paise = int(final_price * 100)

        rzp_order = client.order.create({
            'amount': amount_in_paise,
            'currency': 'INR',
            'receipt': order.order_number,
            'payment_capture': 1,
        })

        order.razorpay_order_id = rzp_order['id']
        order.save(update_fields=['razorpay_order_id'])

        return JsonResponse({
            'success': True,
            'razorpay_order_id': rzp_order['id'],
            'razorpay_key_id': settings.RAZORPAY_KEY_ID,
            'amount': amount_in_paise,
            'currency': 'INR',
            'order_number': order.order_number,
            'user_name': address.full_name or request.user.username,
            'user_email': request.user.email or '',
            'user_phone': address.phone_number or '',
        })
    except Exception as e:
        return JsonResponse({'success': False, 'msg': f'Could not initiate Razorpay payment: {str(e)}'})


@login_required
@require_POST
def razorpay_verify_payment(request):
  
    try:
        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body.decode('utf-8'))
            except Exception:
                data = {}
        else:
            data = request.POST

        order_number = data.get('order_number')
        razorpay_payment_id = data.get('razorpay_payment_id')
        razorpay_order_id = data.get('razorpay_order_id')
        razorpay_signature = data.get('razorpay_signature')

        if not all([order_number, razorpay_payment_id, razorpay_order_id, razorpay_signature]):
            return JsonResponse({'success': False, 'msg': 'Missing payment verification details.'})

        order = Order.objects.filter(order_number=order_number, user=request.user).first()
        if not order:
            return JsonResponse({'success': False, 'msg': 'Order not found.'})

        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        params_dict = {
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature
        }

        try:
            client.utility.verify_payment_signature(params_dict)
        except razorpay.errors.SignatureVerificationError:
            order.payment_status = 'FAILED'
            order.save(update_fields=['payment_status'])
            return JsonResponse({
                'success': False,
                'msg': 'Payment signature verification failed.',
                'redirect_url': reverse('order_fail', args=[order.order_number])
            })

        order.payment_status = 'PAID'
        order.order_status = 'CONFIRMED'
        order.razorpay_payment_id = razorpay_payment_id
        order.razorpay_signature = razorpay_signature
        order.save(update_fields=['payment_status', 'order_status', 'razorpay_payment_id', 'razorpay_signature', 'updated_at'])

        for item in order.items.all():
            item.status = 'CONFIRMED'
            item.save(update_fields=['status'])
            if item.variant:
                item.variant.stock = max(0, item.variant.stock - item.quantity)
                item.variant.save(update_fields=['stock'])

        CartItem.objects.filter(user=request.user).delete()

        if order.coupon_code:
            try:
                coupon_obj = Coupon.objects.filter(code=order.coupon_code).first()
                if coupon_obj:
                    coupon_obj.used_count += 1
                    coupon_obj.save(update_fields=['used_count'])
            except Exception:
                pass

        request.session.pop('coupon_code', None)
        request.session.pop('coupon_id', None)
        request.session.pop('coupon_discount', None)

        return JsonResponse({
            'success': True,
            'msg': 'Payment verified successfully!',
            'order_number': order.order_number,
            'total_amount': float(order.total_amount),
            'payment_method': order.get_payment_method_display(),
            'order_detail_url': reverse('order_detail', args=[order.order_number]),
            'redirect_url': reverse('order_success', args=[order.order_number])
        })
    except Exception as e:
        return JsonResponse({'success': False, 'msg': f'Error verifying payment: {str(e)}'})


@login_required
@require_POST
def razorpay_payment_failed(request):
   
    try:
        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body.decode('utf-8'))
            except Exception:
                data = {}
        else:
            data = request.POST

        order_number = data.get('order_number')
        error_code = data.get('error_code', '')
        error_desc = data.get('error_description', '')

        if order_number:
            order = Order.objects.filter(order_number=order_number, user=request.user).first()
            if order:
                order.payment_status = 'FAILED'
                if error_code or error_desc:
                    order.notes = f"Payment Gateway Error: {error_code} - {error_desc}"[:500]
                order.save(update_fields=['payment_status', 'notes', 'updated_at'])
                return JsonResponse({
                    'success': True,
                    'redirect_url': reverse('order_fail', args=[order.order_number])
                })

        return JsonResponse({
            'success': True,
            'redirect_url': reverse('order_fail_general')
        })
    except Exception as e:
        return JsonResponse({'success': False, 'msg': str(e)})


@login_required
def order_fail(request, order_number=None):
    order = None
    if order_number:
        order = Order.objects.filter(order_number=order_number, user=request.user).first()
    return render(request, "order_fail.html", {'order': order})



@login_required
def order_success(request, order_number):
    order = get_object_or_404(Order, order_number=order_number, user=request.user)
    items = order.items.select_related('product', 'variant').prefetch_related('variant__images')

    enriched_items = []
    for oi in items:
        image_url = None
        if oi.variant and oi.variant.images.first():
            image_url = oi.variant.images.first().image.url
        elif oi.product and oi.product.thumbnail:
            image_url = oi.product.thumbnail.url

        enriched_items.append({
            'item': oi,
            'image_url': image_url,
        })

    context = {
        'order': order,
        'order_items': enriched_items,
    }
    return render(request, "order_success.html", context)


@login_required
def order_detail(request, order_number):
    return redirect('order_view_detail', order_number=order_number)


@login_required
@require_POST
def add_checkout_address(request):
    errors, cleaned = validate_address_data(request.POST)
    if errors:
        return JsonResponse({'success': False, 'errors': errors, 'msg': errors[0]})

    full_name = cleaned['full_name']
    street_address = cleaned['street_address']
    city = cleaned['city']
    state = cleaned['state']
    pincode = cleaned['pincode']
    country = cleaned['country']
    phone_number = cleaned['phone_number']
    address_type = cleaned['address_type']
    is_default = request.POST.get('is_default') == 'true' or request.POST.get('is_default') == '1'

    if not Add_Address.objects.filter(user=request.user).exists() or is_default:
        Add_Address.objects.filter(user=request.user).update(is_default=False)
        is_default = True

    new_addr = Add_Address.objects.create(
        user=request.user,
        full_name=full_name,
        street_address=street_address,
        city=city,
        state=state,
        pincode=pincode,
        country=country,
        phone_number=phone_number,
        address_type=address_type,
        is_default=is_default,
    )

    return JsonResponse({
        'success': True,
        'msg': 'Address added successfully.',
        'address': {
            'id': new_addr.id,
            'full_name': new_addr.full_name,
            'street_address': new_addr.street_address,
            'city': new_addr.city,
            'state': new_addr.state,
            'pincode': new_addr.pincode,
            'country': new_addr.country,
            'phone_number': new_addr.phone_number,
            'address_type': new_addr.address_type,
            'is_default': new_addr.is_default,
        }
    })


@login_required
@require_POST
def edit_checkout_address(request, address_id):
    addr = Add_Address.objects.filter(id=address_id, user=request.user).first()
    if not addr:
        return JsonResponse({'success': False, 'msg': 'Address not found.'})

    errors, cleaned = validate_address_data(request.POST)
    if errors:
        return JsonResponse({'success': False, 'errors': errors, 'msg': errors[0]})

    addr.full_name = cleaned['full_name']
    addr.street_address = cleaned['street_address']
    addr.city = cleaned['city']
    addr.state = cleaned['state']
    addr.pincode = cleaned['pincode']
    addr.country = cleaned['country']
    addr.phone_number = cleaned['phone_number']
    addr.address_type = cleaned['address_type']

    is_default = request.POST.get('is_default') == 'true' or request.POST.get('is_default') == '1'
    if is_default:
        Add_Address.objects.filter(user=request.user).exclude(id=addr.id).update(is_default=False)
        addr.is_default = True

    addr.save()

    return JsonResponse({
        'success': True,
        'msg': 'Address updated successfully.',
        'address': {
            'id': addr.id,
            'full_name': addr.full_name,
            'street_address': addr.street_address,
            'city': addr.city,
            'state': addr.state,
            'pincode': addr.pincode,
            'country': addr.country,
            'phone_number': addr.phone_number,
            'address_type': addr.address_type,
            'is_default': addr.is_default,
        }
    })


@login_required
@require_POST
def set_default_checkout_address(request, address_id):
    addr = Add_Address.objects.filter(id=address_id, user=request.user).first()
    if not addr:
        return JsonResponse({'success': False, 'msg': 'Address not found.'})

    Add_Address.objects.filter(user=request.user).update(is_default=False)
    addr.is_default = True
    addr.save()

    return JsonResponse({'success': True, 'msg': 'Default address updated.'})


@login_required
@require_POST
def delete_checkout_address(request, address_id):
    addr = Add_Address.objects.filter(id=address_id, user=request.user).first()
    if not addr:
        return JsonResponse({'success': False, 'msg': 'Address not found.'})

    was_default = addr.is_default
    name = addr.full_name
    addr.delete()

    remaining_addresses = list(Add_Address.objects.filter(user=request.user).order_by('-is_default', '-created_at'))
    new_default_id = None
    if remaining_addresses:
        if was_default:
            first_addr = remaining_addresses[0]
            first_addr.is_default = True
            first_addr.save()
            new_default_id = first_addr.id
        else:
            default_addr = next((a for a in remaining_addresses if a.is_default), remaining_addresses[0])
            new_default_id = default_addr.id

    return JsonResponse({
        'success': True,
        'msg': f"Address for '{name}' was deleted.",
        'remaining_count': len(remaining_addresses),
        'new_default_id': new_default_id,
    })