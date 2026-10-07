from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views.decorators.cache import never_cache
from .models import Add_Address
from user.user_profile.models import UserProfile
import re


def validate_address_data(data):
    """Validate address input fields and return errors list and cleaned dictionary."""
    errors = []
    full_name = data.get("full_name", "").strip()
    street_address = data.get("street_address", "").strip()
    city = data.get("city", "").strip()
    state = data.get("state", "").strip()
    pincode = data.get("pincode", "").strip()
    country = data.get("country", "").strip()
    phone_number = data.get("phone_number", "").strip()
    address_type = data.get("address_type", "Home").strip()

    # Full name
    if not full_name:
        errors.append("Full name is required.")
    elif len(full_name) < 3:
        errors.append("Full name must contain at least 3 characters.")
    elif not re.match(r'^[A-Za-z\s\.]+$', full_name):
        errors.append("Full name can contain only letters, spaces, and periods.")

    # Street address
    if not street_address:
        errors.append("Street address is required.")
    elif len(street_address) < 5:
        errors.append("Street address must be at least 5 characters.")

    # City
    if not city:
        errors.append("City is required.")
    elif not re.match(r'^[A-Za-z\s]+$', city):
        errors.append("City can contain only letters and spaces.")

    # State
    if not state:
        errors.append("State is required.")
    elif not re.match(r'^[A-Za-z\s]+$', state):
        errors.append("State can contain only letters and spaces.")

    # Pincode
    if not pincode:
        errors.append("Pincode is required.")
    elif not re.match(r'^\d{6}$', pincode):
        errors.append("Pincode must contain exactly 6 digits.")

    # Country
    if not country:
        errors.append("Country is required.")
    elif not re.match(r'^[A-Za-z\s]+$', country):
        errors.append("Country can contain only letters and spaces.")

    # Phone number
    if not phone_number:
        errors.append("Phone number is required.")
    else:
        cleaned_phone = re.sub(r'[\s\-\(\)\+]', '', phone_number)
        if cleaned_phone.startswith('91') and len(cleaned_phone) == 12:
            cleaned_phone = cleaned_phone[2:]
        if not re.match(r'^[6-9]\d{9}$', cleaned_phone):
            errors.append("Please enter a valid 10-digit mobile number starting with 6, 7, 8, or 9.")
        else:
            phone_number = cleaned_phone

    # Address type
    if address_type not in ['Home', 'Work', 'Other']:
        address_type = 'Home'

    return errors, {
        'full_name': full_name,
        'street_address': street_address,
        'city': city,
        'state': state,
        'pincode': pincode,
        'country': country,
        'phone_number': phone_number,
        'address_type': address_type,
    }


@never_cache
def address(request):
    if not request.user.is_authenticated:
        messages.error(request, "Please sign in to view your addresses.")
        return redirect("login")

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    addresses = Add_Address.objects.filter(user=request.user).order_by('-is_default', '-created_at')

    return render(request, "address.html", {
        "addresses": addresses,
        "profile": profile,
        "user": request.user,
    })


@never_cache
def add_address(request):
    if not request.user.is_authenticated:
        messages.error(request, "Please sign in to add an address.")
        return redirect("login")

    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        errors, cleaned = validate_address_data(request.POST)
        is_default = request.POST.get("is_default") in ["on", "1", "true", "True"]

        if errors:
            for err in errors:
                messages.error(request, err)
            return render(request, "add_address.html", {
                "profile": profile,
                "user": request.user,
                "form_data": request.POST,
            })

        # If user has no existing address, set this one as default
        has_existing = Add_Address.objects.filter(user=request.user).exists()
        if not has_existing:
            is_default = True

        if is_default:
            Add_Address.objects.filter(user=request.user, is_default=True).update(is_default=False)

        Add_Address.objects.create(
            user=request.user,
            full_name=cleaned["full_name"],
            street_address=cleaned["street_address"],
            city=cleaned["city"],
            state=cleaned["state"],
            pincode=cleaned["pincode"],
            country=cleaned["country"],
            phone_number=cleaned["phone_number"],
            address_type=cleaned["address_type"],
            is_default=is_default,
        )

        messages.success(request, "Address saved successfully.")
        return redirect("address")

    return render(request, "add_address.html", {
        "profile": profile,
        "user": request.user,
        "form_data": {
            "country": "India",
            "address_type": "Home",
        },
    })


@never_cache
def edit_address(request, address_id):
    if not request.user.is_authenticated:
        messages.error(request, "Please sign in to edit your address.")
        return redirect("login")

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    addr = get_object_or_404(Add_Address, id=address_id, user=request.user)

    if request.method == "POST":
        errors, cleaned = validate_address_data(request.POST)
        is_default = request.POST.get("is_default") in ["on", "1", "true", "True"]

        if errors:
            for err in errors:
                messages.error(request, err)
            return render(request, "edit_address.html", {
                "address": addr,
                "profile": profile,
                "user": request.user,
                "form_data": request.POST,
            })

        total_addresses = Add_Address.objects.filter(user=request.user).count()
        if total_addresses == 1:
            is_default = True

        if is_default:
            Add_Address.objects.filter(user=request.user, is_default=True).exclude(id=addr.id).update(is_default=False)
            addr.is_default = True
        else:
            if addr.is_default and total_addresses > 1:
                next_addr = Add_Address.objects.filter(user=request.user).exclude(id=addr.id).first()
                if next_addr:
                    next_addr.is_default = True
                    next_addr.save()
            addr.is_default = False

        addr.full_name = cleaned["full_name"]
        addr.street_address = cleaned["street_address"]
        addr.city = cleaned["city"]
        addr.state = cleaned["state"]
        addr.pincode = cleaned["pincode"]
        addr.country = cleaned["country"]
        addr.phone_number = cleaned["phone_number"]
        addr.address_type = cleaned["address_type"]
        addr.save()

        messages.success(request, "Address updated successfully.")
        return redirect("address")

    return render(request, "edit_address.html", {
        "address": addr,
        "profile": profile,
        "user": request.user,
        "form_data": {
            "full_name": addr.full_name,
            "street_address": addr.street_address,
            "city": addr.city,
            "state": addr.state,
            "pincode": addr.pincode,
            "country": addr.country,
            "phone_number": addr.phone_number,
            "address_type": addr.address_type,
            "is_default": addr.is_default,
        },
    })


@never_cache
def delete_address(request, address_id):
    if not request.user.is_authenticated:
        messages.error(request, "Please sign in to delete an address.")
        return redirect("login")

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    addr = get_object_or_404(Add_Address, id=address_id, user=request.user)

    if request.method == "POST" or request.GET.get("confirm") == "1":
        was_default = addr.is_default
        name = addr.full_name
        addr.delete()

        if was_default:
            next_addr = Add_Address.objects.filter(user=request.user).first()
            if next_addr:
                next_addr.is_default = True
                next_addr.save()

        messages.success(request, f"Address for '{name}' was deleted successfully.")
        return redirect("address")

    return render(request, "delete_address.html", {
        "address": addr,
        "profile": profile,
        "user": request.user,
    })


@never_cache
def set_default_address(request, address_id):
    if not request.user.is_authenticated:
        messages.error(request, "Please sign in.")
        return redirect("login")

    addr = get_object_or_404(Add_Address, id=address_id, user=request.user)
    Add_Address.objects.filter(user=request.user, is_default=True).update(is_default=False)
    addr.is_default = True
    addr.save()

    messages.success(request, f"'{addr.full_name}' ({addr.address_type}) is now your default address.")
    return redirect("address")
