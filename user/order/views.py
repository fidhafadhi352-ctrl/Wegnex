import os
import io
import datetime
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, Http404
from django.views.decorators.http import require_POST
from django.db.models import Sum
from user.checkout.models import Order, OrderItem
from user.wallet.models import Wallet, WalletTransaction

# ReportLab imports for luxury PDF invoice generation
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


def order(request):
    user_orders = []
    if request.user.is_authenticated:
        orders_qs = Order.objects.filter(user=request.user).prefetch_related(
            'items__product', 'items__variant__images'
        ).order_by('-created_at')

        for ord_obj in orders_qs:
            items = list(ord_obj.items.all())
            first_item = items[0] if items else None
            img_url = None
            if first_item:
                if first_item.variant and first_item.variant.images.first():
                    img_url = first_item.variant.images.first().image.url
                elif first_item.product and first_item.product.thumbnail:
                    img_url = first_item.product.thumbnail.url

            user_orders.append({
                'id': ord_obj.order_number,
                'order_number': ord_obj.order_number,
                'date': ord_obj.created_at.strftime('%b %d, %Y'),
                'product_name': first_item.product_name if first_item else 'Wegnex Luxury Timepiece',
                'item_count': len(items),
                'price': ord_obj.total_amount,
                'payment': ord_obj.get_payment_method_display(),
                'status': ord_obj.order_status.title(),
                'status_raw': ord_obj.order_status,
                'image_url': img_url or "https://images.unsplash.com/photo-1523170335258-f5ed11844a49?auto=format&fit=crop&w=400&q=80",
            })

    return render(request, "order.html", {'user_orders': user_orders})


def order_view(request, order_number=None):
    target_num = order_number or request.GET.get('order_id') or request.GET.get('id')

    order_obj = None
    if target_num:
        if request.user.is_authenticated:
            order_obj = Order.objects.filter(order_number=target_num, user=request.user).first()
        if not order_obj:
            order_obj = Order.objects.filter(order_number=target_num).first()

    if order_obj:
        items_qs = order_obj.items.select_related('product', 'variant').prefetch_related('variant__images')
        enriched_items = []
        for oi in items_qs:
            img_url = None
            if oi.variant and oi.variant.images.first():
                img_url = oi.variant.images.first().image.url
            elif oi.product and oi.product.thumbnail:
                img_url = oi.product.thumbnail.url

            effective_status = oi.status or order_obj.order_status
            
            item_color = 'Midnight Black'
            item_size = '42 mm'
            if oi.variant:
                if oi.variant.color:
                    item_color = oi.variant.color
                if oi.variant.case_size:
                    item_size = oi.variant.case_size
            elif oi.variant_info:
                parts = [p.strip() for p in oi.variant_info.split('|')]
                if len(parts) >= 1 and parts[0]:
                    item_color = parts[0]
                if len(parts) >= 2 and parts[1]:
                    item_size = parts[1]

            enriched_items.append({
                'id': oi.id,
                'product_name': oi.product_name,
                'variant_info': oi.variant_info,
                'color': item_color,
                'case_size': item_size,
                'movement': 'Automatic Mechanical',
                'price': oi.price,
                'quantity': oi.quantity,
                'item_total': oi.item_total,
                'image_url': img_url or "https://images.unsplash.com/photo-1523170335258-f5ed11844a49?auto=format&fit=crop&w=400&q=80",
                'status': effective_status.title(),
                'status_raw': effective_status,
                'is_delivered': effective_status == 'DELIVERED',
                'is_cancelled': effective_status == 'CANCELLED',
                'is_return_requested': effective_status == 'RETURN_REQUESTED',
                'is_returned': effective_status == 'RETURNED',
                'cancellation_reason': oi.cancellation_reason,
            })

        status_map = {
            'PENDING': 'Pending',
            'CONFIRMED': 'Order Placed',
            'PROCESSING': 'Processing',
            'SHIPPED': 'Shipped',
            'OUT_FOR_DELIVERY': 'Out for Delivery',
            'DELIVERED': 'Delivered',
            'CANCELLED': 'Cancelled',
            'RETURN_REQUESTED': 'Return Requested',
            'RETURNED': 'Returned',
        }
        current_status_name = status_map.get(order_obj.order_status, 'Order Placed')

        context = {
            'order': order_obj,
            'order_items': enriched_items,
            'current_status_name': current_status_name,
            'is_real_order': True,
        }
        return render(request, "order_view.html", context)

    demo_orders = {
        'WGX-982381': {
            'order_number': 'WGX-982381',
            'product_name': 'Wegnex Heritage Automatic',
            'price': '48,999',
            'date': 'Jun 24, 2026',
            'status': 'Shipped',
            'payment': 'Razorpay',
            'img': 'https://images.unsplash.com/photo-1523170335258-f5ed11844a49?auto=format&fit=crop&w=400&q=80',
        },
        'WGX-921145': {
            'order_number': 'WGX-921145',
            'product_name': 'Wegnex Royal Chronograph',
            'price': '54,999',
            'date': 'Jun 18, 2026',
            'status': 'Delivered',
            'payment': 'Razorpay',
            'img': 'https://images.unsplash.com/photo-1524805444758-089113d48a6d?auto=format&fit=crop&w=400&q=80',
        },
        'WGX-991845': {
            'order_number': 'WGX-991845',
            'product_name': 'Wegnex Prestige Gold',
            'price': '62,999',
            'date': 'Jun 12, 2026',
            'status': 'Processing',
            'payment': 'Wallet',
            'img': 'https://images.unsplash.com/photo-1547996160-81dfa63595aa?auto=format&fit=crop&w=400&q=80',
        },
        'WGX-990721': {
            'order_number': 'WGX-990721',
            'product_name': 'Wegnex Skeleton Automatic',
            'price': '72,999',
            'date': 'Jun 05, 2026',
            'status': 'Returned',
            'payment': 'Razorpay',
            'img': 'https://images.unsplash.com/photo-1524592094714-0f0654e20314?auto=format&fit=crop&w=400&q=80',
        },
    }

    selected_demo = demo_orders.get(target_num)
    context = {
        'demo_order': selected_demo,
        'is_real_order': False,
    }
    return render(request, "order_view.html", context)


@require_POST
def cancel_order_item(request, item_id):
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'msg': 'Please login first.'}, status=401)

    reason = request.POST.get('reason', '')
    note = request.POST.get('note', '')
    action = request.POST.get('action', 'cancel')
    cancel_scope = request.POST.get('cancel_scope', 'item')  # 'item' or 'order'

    try:
        cancel_quantity = int(request.POST.get('cancel_quantity', 1))
    except (ValueError, TypeError):
        cancel_quantity = 1

    item = OrderItem.objects.filter(id=item_id, order__user=request.user).first()
    if not item:
        return JsonResponse({'success': False, 'msg': 'Item not found.'})

    order_obj = item.order

    if action == 'cancel':
        if order_obj.order_status in ['DELIVERED', 'CANCELLED']:
            return JsonResponse({'success': False, 'msg': 'This order cannot be cancelled in its current status.'})
        if item.status == 'CANCELLED':
            return JsonResponse({'success': False, 'msg': 'This item has already been cancelled.'})

        if cancel_scope == 'item':
            if cancel_quantity < 1:
                cancel_quantity = 1
            if cancel_quantity > item.quantity:
                cancel_quantity = item.quantity

            unit_price = item.price

            if cancel_quantity == item.quantity:
                item.status = 'CANCELLED'
                item.cancellation_reason = f"Individual cancellation ({cancel_quantity} units). Reason: {reason}. Note: {note}"
                item.save()
            else:
                remaining_qty = item.quantity - cancel_quantity
                item.quantity = remaining_qty
                item.item_total = unit_price * remaining_qty
                item.save()
                OrderItem.objects.create(
                    order=order_obj,
                    product=item.product,
                    variant=item.variant,
                    product_name=item.product_name,
                    variant_info=item.variant_info,
                    price=unit_price,
                    quantity=cancel_quantity,
                    item_total=unit_price * cancel_quantity,
                    status='CANCELLED',
                    cancellation_reason=f"Partially cancelled ({cancel_quantity} units). Reason: {reason}. Note: {note}"
                )

            if item.variant:
                item.variant.stock += cancel_quantity
                item.variant.save()

            cancelled_amount = unit_price * cancel_quantity
            all_cancelled = not order_obj.items.exclude(status='CANCELLED').exists()
            if all_cancelled:
                order_obj.order_status = 'CANCELLED'
                order_obj.notes = f"All items cancelled. Last: {cancel_quantity}x {item.product_name}. Reason: {reason}"
            else:
                order_obj.notes = f"Cancelled {cancel_quantity}x {item.product_name}. Reason: {reason}"
            order_obj.save()

            refund_amount = Decimal('0.00')
            wallet_msg = ''
            if order_obj.payment_status == 'PAID':
                already_refunded = WalletTransaction.objects.filter(
                    order=order_obj,
                    transaction_type='CREDIT',
                    source__in=['ORDER_CANCELLATION_REFUND', 'ORDER_RETURN_REFUND']
                ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')

                remaining_refundable = max(Decimal('0.00'), order_obj.total_amount - already_refunded)
                refund_amount = min(cancelled_amount, remaining_refundable)
                if refund_amount > Decimal('0.00'):
                    wallet_obj, _ = Wallet.objects.get_or_create(user=request.user)
                    wallet_obj.credit(
                        amount=refund_amount,
                        description=f'Refund for cancellation of {cancel_quantity}x {item.product_name} (Order #{order_obj.order_number})',
                        source='ORDER_CANCELLATION_REFUND',
                        order=order_obj,
                        reference=order_obj.order_number
                    )
                    wallet_msg = f' ₹{refund_amount:,.2f} refunded directly to your Wegnex Wallet.'

            return JsonResponse({
                'success': True,
                'msg': f"Successfully cancelled {cancel_quantity} unit(s) of '{item.product_name}'.{wallet_msg}",
                'scope': 'item',
                'cancelled_qty': cancel_quantity,
                'all_cancelled': all_cancelled,
                'refund_amount': float(refund_amount),
                'wallet_refunded': bool(refund_amount),
            })

        else:
            for itm in order_obj.items.exclude(status='CANCELLED'):
                itm.status = 'CANCELLED'
                itm.cancellation_reason = f"Full order cancellation. Reason: {reason}. Note: {note}"
                itm.save()
                if itm.variant:
                    itm.variant.stock += itm.quantity
                    itm.variant.save()

            order_obj.order_status = 'CANCELLED'
            order_obj.notes = f"Entire order cancelled. Reason: {reason}. Note: {note}"
            order_obj.save()

            refund_amount = Decimal('0.00')
            wallet_msg = ''
            if order_obj.payment_status == 'PAID':
                already_refunded = WalletTransaction.objects.filter(
                    order=order_obj,
                    transaction_type='CREDIT',
                    source__in=['ORDER_CANCELLATION_REFUND', 'ORDER_RETURN_REFUND']
                ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')

                refundable = max(Decimal('0.00'), order_obj.total_amount - already_refunded)
                if refundable > Decimal('0.00'):
                    wallet_obj, _ = Wallet.objects.get_or_create(user=request.user)
                    wallet_obj.credit(
                        amount=refundable,
                        description=f'Refund for full cancellation of Order #{order_obj.order_number}',
                        source='ORDER_CANCELLATION_REFUND',
                        order=order_obj,
                        reference=order_obj.order_number
                    )
                    refund_amount = refundable
                    wallet_msg = f' ₹{refund_amount:,.2f} refunded directly to your Wegnex Wallet.'

            return JsonResponse({
                'success': True,
                'msg': f"Entire Order #{order_obj.order_number} has been cancelled.{wallet_msg}",
                'scope': 'order',
                'all_cancelled': True,
                'refund_amount': float(refund_amount),
                'wallet_refunded': bool(wallet_msg),
            })

    elif action == 'return':
        effective_item_status = item.status or order_obj.order_status
        if effective_item_status == 'RETURN_REQUESTED':
            return JsonResponse({'success': False, 'msg': 'A return request for this item has already been submitted and is pending admin review.'})
        if effective_item_status != 'DELIVERED':
            return JsonResponse({'success': False, 'msg': 'Only delivered items can be submitted for return.'})

        refund_method = request.POST.get('refund_method', 'wallet')
        refund_amount = item.item_total

        # Set status to RETURN_REQUESTED (Wait for admin approval; do not credit wallet or restore stock yet)
        item.status = 'RETURN_REQUESTED'
        now_str = datetime.datetime.now().strftime("%b %d, %Y %I:%M %p")
        item.cancellation_reason = f"Return requested by customer on {now_str}. Reason: {reason}. Note: {note} | Refund Method: {refund_method.title()}"
        item.save(update_fields=['status', 'cancellation_reason'])

        # Update order status to RETURN_REQUESTED
        order_obj.order_status = 'RETURN_REQUESTED'
        order_obj.save(update_fields=['order_status'])

        return JsonResponse({
            'success': True,
            'msg': f"Return request for '{item.product_name}' submitted successfully. Refund of ₹{refund_amount:,.2f} will be credited to your wallet once approved by admin.",
            'refund_amount': float(refund_amount),
            'status': 'RETURN_REQUESTED',
            'wallet_credited': False
        })

    return JsonResponse({'success': False, 'msg': 'Invalid action.'})


# ─────────────────────────────────────────────────────────
#  PDF INVOICE DOWNLOAD
# ─────────────────────────────────────────────────────────

# Register TTF font once at module level so every request reuses it
try:
    if os.path.exists('C:/Windows/Fonts/arial.ttf'):
        pdfmetrics.registerFont(TTFont('WGX-Regular', 'C:/Windows/Fonts/arial.ttf'))
        pdfmetrics.registerFont(TTFont('WGX-Bold', 'C:/Windows/Fonts/arialbd.ttf'))
        _FONT = 'WGX-Regular'
        _FONT_BOLD = 'WGX-Bold'
    else:
        _FONT = 'Helvetica'
        _FONT_BOLD = 'Helvetica-Bold'
except Exception:
    _FONT = 'Helvetica'
    _FONT_BOLD = 'Helvetica-Bold'


def _make_style(name, **kwargs):
    """Helper to create a ParagraphStyle cleanly."""
    return ParagraphStyle(name, **kwargs)


@login_required
def download_invoice_pdf(request, order_number):
    """
    Generates and streams a luxury branded PDF invoice for the given order.
    Only the order's owner can download it.
    """
    order_obj = Order.objects.filter(
        order_number=order_number, user=request.user
    ).prefetch_related('items__variant__images', 'items__product').first()

    if not order_obj:
        raise Http404("Order not found or you are not authorized to download this invoice.")

    # ── Build PDF in memory ──────────────────────────────
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=32,
        bottomMargin=32,
    )

    # ── Colour palette ───────────────────────────────────
    C_DARK   = colors.HexColor('#111111')
    C_GOLD   = colors.HexColor('#B38E5D')
    C_GREY   = colors.HexColor('#555555')
    C_LGREY  = colors.HexColor('#888888')
    C_BORDER = colors.HexColor('#E0E0E0')
    C_BG     = colors.HexColor('#F8F8F8')
    C_WHITE  = colors.white
    C_GREEN  = colors.HexColor('#16A34A')
    C_RED    = colors.HexColor('#DC2626')

    # ── Styles ───────────────────────────────────────────
    brand_st = _make_style('Brand',   fontName=_FONT_BOLD, fontSize=20, leading=24,
                            textColor=C_DARK)
    subbrand = _make_style('SubBrand', fontName=_FONT,     fontSize=7.5, leading=11,
                            textColor=C_LGREY)
    invtitle = _make_style('InvTitle', fontName=_FONT_BOLD, fontSize=18, leading=22,
                            textColor=C_GOLD, alignment=TA_RIGHT)
    invmeta  = _make_style('InvMeta',  fontName=_FONT,     fontSize=8, leading=12,
                            textColor=C_GREY, alignment=TA_RIGHT)
    sec_hd   = _make_style('SecHD',    fontName=_FONT_BOLD, fontSize=8, leading=11,
                            textColor=C_DARK)
    body_sm  = _make_style('BodySm',   fontName=_FONT,     fontSize=8, leading=12,
                            textColor=C_GREY)
    th_l     = _make_style('THL',      fontName=_FONT_BOLD, fontSize=8, leading=11,
                            textColor=C_WHITE)
    th_r     = _make_style('THR',      fontName=_FONT_BOLD, fontSize=8, leading=11,
                            textColor=C_WHITE, alignment=TA_RIGHT)
    td_l     = _make_style('TDL',      fontName=_FONT,     fontSize=8, leading=12,
                            textColor=C_DARK)
    td_r     = _make_style('TDR',      fontName=_FONT,     fontSize=8, leading=12,
                            textColor=C_DARK, alignment=TA_RIGHT)
    footer_s = _make_style('Footer',   fontName=_FONT,     fontSize=7, leading=10,
                            textColor=C_LGREY, alignment=TA_CENTER)
    total_l  = _make_style('TotL',     fontName=_FONT_BOLD, fontSize=9, leading=12,
                            textColor=C_WHITE)
    total_r  = _make_style('TotR',     fontName=_FONT_BOLD, fontSize=9, leading=12,
                            textColor=C_GOLD, alignment=TA_RIGHT)

    story = []

    # ── HEADER ROW ───────────────────────────────────────
    inv_date  = order_obj.created_at.strftime('%d %b %Y')
    inv_num   = f"INV-{order_obj.order_number}"

    hdr_data = [
        [
            Paragraph("<b>W E G N E X</b>", brand_st),
            Paragraph("<b>TAX INVOICE</b>", invtitle),
        ],
        [
            Paragraph(
                "Luxury Horology &amp; Timepieces<br/>"
                "Wegnex Retail Pvt Ltd | GSTIN: 32AABCR1234F1Z8<br/>"
                "care@wegnex.com | www.wegnex.com<br/>"
                "Kochi, Kerala, India – 682 001",
                subbrand,
            ),
            Paragraph(
                f"<b>Invoice&nbsp;#:</b>&nbsp;{inv_num}<br/>"
                f"<b>Order&nbsp;#:</b>&nbsp;{order_obj.order_number}<br/>"
                f"<b>Order&nbsp;Date:</b>&nbsp;{inv_date}<br/>"
                f"<b>Invoice&nbsp;Date:</b>&nbsp;{datetime.date.today().strftime('%d %b %Y')}",
                invmeta,
            ),
        ],
    ]
    hdr_tbl = Table(hdr_data, colWidths=[300, 220])
    hdr_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING',    (0, 0), (-1, -1), 2),
    ]))
    story.append(hdr_tbl)
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1.5, color=C_GOLD, spaceAfter=10))

    # ── BILLING / ORDER INFO ROW ─────────────────────────
    addr_parts = [
        order_obj.shipping_full_name,
        order_obj.shipping_street_address,
        f"{order_obj.shipping_city}, {order_obj.shipping_state} – {order_obj.shipping_pincode}",
        order_obj.shipping_country,
        f"Phone: {order_obj.shipping_phone}",
    ]
    addr_html = "<br/>".join(addr_parts)

    pay_status_color = '#16A34A' if order_obj.payment_status == 'PAID' else '#DC2626'
    info_data = [
        [Paragraph("CUSTOMER &amp; SHIPPING DETAILS", sec_hd),
         Paragraph("ORDER INFORMATION", sec_hd)],
        [
            Paragraph(addr_html, body_sm),
            Paragraph(
                f"<b>Payment Method:</b> {order_obj.get_payment_method_display()}<br/>"
                f"<b>Payment Status:</b> <font color='{pay_status_color}'>"
                f"<b>{order_obj.payment_status}</b></font><br/>"
                f"<b>Order Status:</b> {order_obj.get_order_status_display()}<br/>"
                f"<b>Address Type:</b> {order_obj.shipping_address_type.title()}",
                body_sm,
            ),
        ],
    ]
    info_tbl = Table(info_data, colWidths=[290, 230])
    info_tbl.setStyle(TableStyle([
        ('VALIGN',       (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND',   (0, 0), (-1, -1), C_BG),
        ('BOX',          (0, 0), (-1, -1), 0.5, C_BORDER),
        ('INNERGRID',    (0, 0), (-1, -1), 0.5, C_BORDER),
        ('TOPPADDING',   (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 8),
        ('LEFTPADDING',  (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('FONTNAME',     (0, 0), (-1, 0), _FONT_BOLD),
    ]))
    story.append(info_tbl)
    story.append(Spacer(1, 14))

    # ── ITEMS TABLE ──────────────────────────────────────
    items_qs = order_obj.items.all()
    rows = [[
        Paragraph("#",           th_l),
        Paragraph("Item Description", th_l),
        Paragraph("Variant",     th_l),
        Paragraph("Qty",         th_r),
        Paragraph("Unit Price",  th_r),
        Paragraph("Total",       th_r),
    ]]
    for idx, oi in enumerate(items_qs, 1):
        variant_str = oi.variant_info or "Standard"
        rows.append([
            Paragraph(str(idx), td_l),
            Paragraph(oi.product_name, td_l),
            Paragraph(variant_str, td_l),
            Paragraph(str(oi.quantity), td_r),
            Paragraph(f"Rs.{oi.price:,.2f}", td_r),
            Paragraph(f"Rs.{oi.item_total:,.2f}", td_r),
        ])

    items_tbl = Table(rows, colWidths=[22, 210, 85, 32, 80, 80])
    items_tbl.setStyle(TableStyle([
        ('BACKGROUND',   (0, 0), (-1, 0), C_DARK),
        ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',   (0, 0), (-1, 0), 7),
        ('BOTTOMPADDING',(0, 0), (-1, 0), 7),
        ('TOPPADDING',   (0, 1), (-1, -1), 7),
        ('BOTTOMPADDING',(0, 1), (-1, -1), 7),
        ('LEFTPADDING',  (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7),
        ('LINEBELOW',    (0, 1), (-1, -1), 0.4, C_BORDER),
        ('BOX',          (0, 0), (-1, -1), 0.5, C_BORDER),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [C_WHITE, C_BG]),
    ]))
    story.append(items_tbl)
    story.append(Spacer(1, 10))

    # ── TOTALS ───────────────────────────────────────────
    discount_label = f"Discount ({order_obj.coupon_code})" if order_obj.coupon_code else "Discount"
    shipping_val   = f"Rs.{order_obj.shipping_fee:,.2f}" if order_obj.shipping_fee > 0 else "FREE"

    tot_rows = [
        [Paragraph("Subtotal",       body_sm), Paragraph(f"Rs.{order_obj.subtotal:,.2f}", td_r)],
        [Paragraph(discount_label,   body_sm), Paragraph(f"-Rs.{order_obj.discount:,.2f}", td_r)],
        [Paragraph("Shipping",       body_sm), Paragraph(shipping_val, td_r)],
        [Paragraph("Tax",            body_sm), Paragraph(f"Rs.{order_obj.tax:,.2f}", td_r)],
        [Paragraph("<b>Grand Total</b>", total_l), Paragraph(f"<b>Rs.{order_obj.total_amount:,.2f}</b>", total_r)],
    ]
    tot_tbl = Table(tot_rows, colWidths=[130, 100])
    tot_tbl.setStyle(TableStyle([
        ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',   (0, 0), (-1, -2), 3),
        ('BOTTOMPADDING',(0, 0), (-1, -2), 3),
        ('LEFTPADDING',  (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('LINEABOVE',    (0, -1), (-1, -1), 0.5, C_BORDER),
        ('BACKGROUND',   (0, -1), (-1, -1), C_DARK),
        ('TOPPADDING',   (0, -1), (-1, -1), 7),
        ('BOTTOMPADDING',(0, -1), (-1, -1), 7),
    ]))
    # Right-align the totals block
    wrap_tbl = Table([['', tot_tbl]], colWidths=[290, 230])
    wrap_tbl.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    story.append(wrap_tbl)
    story.append(Spacer(1, 18))

    # ── FOOTER ───────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER, spaceAfter=7))
    story.append(Paragraph(
        "<b>Terms &amp; Conditions:</b> All Wegnex luxury timepieces carry a 2-Year International "
        "Warranty against manufacturing defects. Returns &amp; cancellations are governed by the "
        "Wegnex Return Policy. For support contact care@wegnex.com.",
        footer_s,
    ))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "This is a computer-generated invoice and does not require a physical signature.  "
        "Wegnex Retail Pvt. Ltd. — All rights reserved.",
        footer_s,
    ))

    # ── Render PDF ───────────────────────────────────────
    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    filename = f"Wegnex-Invoice-{order_obj.order_number}.pdf"
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
