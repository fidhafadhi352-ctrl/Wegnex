import time
import json
import razorpay
from decimal import Decimal
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.conf import settings
from .models import Wallet, WalletTransaction
from user.user_profile.models import UserProfile


@login_required
def wallet(request):
    wallet_obj, _ = Wallet.objects.get_or_create(user=request.user)
    transactions = wallet_obj.transactions.all().order_by('-created_at')
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    context = {
        'wallet': wallet_obj,
        'wallet_balance': wallet_obj.balance,
        'transactions': transactions,
        'profile': profile,
        'razorpay_key_id': getattr(settings, 'RAZORPAY_KEY_ID', ''),
    }
    return render(request, "wallet.html", context)


@login_required
@require_POST
def wallet_create_order(request):
    """Creates a Razorpay order for wallet recharge."""
    try:
        amount_raw = request.POST.get('amount')
        if not amount_raw and request.body:
            try:
                data = json.loads(request.body.decode('utf-8'))
                amount_raw = data.get('amount')
            except Exception:
                pass

        if not amount_raw:
            return JsonResponse({'success': False, 'msg': 'Please enter a valid amount.'})

        amount = Decimal(str(amount_raw)).quantize(Decimal('0.01'))
        if amount <= 0:
            return JsonResponse({'success': False, 'msg': 'Amount must be greater than zero.'})

        if amount > Decimal('100000'):
            return JsonResponse({'success': False, 'msg': 'Maximum recharge amount is ₹1,00,000 per transaction.'})

        amount_in_paise = int(amount * 100)

        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        client.set_app_details({'title': 'Wegnex', 'version': '1.0'})
        receipt_id = f"wrcg_{request.user.id}_{int(time.time())}"

        rzp_order = client.order.create({
            'amount': amount_in_paise,
            'currency': 'INR',
            'receipt': receipt_id,
            'payment_capture': 1,
            'notes': {
                'user_id': request.user.id,
                'username': request.user.username,
                'email': request.user.email,
                'type': 'WALLET_RECHARGE',
            }
        })

        profile = UserProfile.objects.filter(user=request.user).first()
        user_phone = (getattr(profile, 'phone_number', '') or '') if profile else ''

        return JsonResponse({
            'success': True,
            'razorpay_order_id': rzp_order['id'],
            'razorpay_key_id': settings.RAZORPAY_KEY_ID,
            'amount': amount_in_paise,
            'amount_inr': float(amount),
            'currency': 'INR',
            'user_name': request.user.get_full_name() or request.user.username,
            'user_email': request.user.email or '',
            'user_phone': user_phone,
        })

    except Exception as e:
        return JsonResponse({'success': False, 'msg': f'Could not initiate payment: {str(e)}'})


@login_required
@require_POST
def wallet_verify_payment(request):
    """Verifies Razorpay payment signature and credits the user's wallet."""
    try:
        data = request.POST
        if not data and request.body:
            try:
                data = json.loads(request.body.decode('utf-8'))
            except Exception:
                data = {}

        razorpay_payment_id = data.get('razorpay_payment_id')
        razorpay_order_id = data.get('razorpay_order_id')
        razorpay_signature = data.get('razorpay_signature')
        amount_raw = data.get('amount')

        if not all([razorpay_payment_id, razorpay_order_id, razorpay_signature]):
            return JsonResponse({'success': False, 'msg': 'Incomplete payment verification parameters.'})

        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        client.utility.verify_payment_signature({
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature
        })

        
        if WalletTransaction.objects.filter(reference=razorpay_payment_id).exists():
            wallet_obj, _ = Wallet.objects.get_or_create(user=request.user)
            return JsonResponse({
                'success': True,
                'msg': 'Payment already verified and credited.',
                'new_balance': float(wallet_obj.balance),
                'formatted_balance': f'₹{wallet_obj.balance:,.2f}',
            })

        amount = Decimal(str(amount_raw)).quantize(Decimal('0.01')) if amount_raw else Decimal('0.00')
        if amount <= 0:
            rzp_order_info = client.order.fetch(razorpay_order_id)
            amount = Decimal(str(rzp_order_info.get('amount', 0))) / Decimal('100.00')

        
        wallet_obj, _ = Wallet.objects.get_or_create(user=request.user)
        wallet_obj.balance += amount
        wallet_obj.save()

        txn = WalletTransaction.objects.create(
            wallet=wallet_obj,
            transaction_type='CREDIT',
            amount=amount,
            balance_after=wallet_obj.balance,
            description=f'Wallet Recharge via Razorpay ({razorpay_payment_id})',
            source='WALLET_RECHARGE',
            reference=razorpay_payment_id,
            status='SUCCESS',
        )

        return JsonResponse({
            'success': True,
            'msg': f'₹{amount:,.2f} added to your wallet successfully!',
            'amount': float(amount),
            'formatted_amount': f'₹{amount:,.2f}',
            'new_balance': float(wallet_obj.balance),
            'formatted_balance': f'₹{wallet_obj.balance:,.2f}',
            'payment_method': 'Razorpay',
            'reference': txn.reference,
            'date': txn.created_at.strftime('%d %B %Y • %I:%M %p'),
            'transaction': {
                'id': txn.id,
                'description': txn.description,
                'reference': txn.reference,
                'amount': float(txn.amount),
                'formatted_amount': f'+₹{txn.amount:,.2f}',
                'date': txn.created_at.strftime('%d %B %Y • %I:%M %p'),
                'type': 'credit',
            }
        })

    except razorpay.errors.SignatureVerificationError:
        return JsonResponse({'success': False, 'msg': 'Payment verification failed (invalid signature).'})
    except Exception as e:
        return JsonResponse({'success': False, 'msg': f'Verification error: {str(e)}'})
