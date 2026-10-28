from django.shortcuts import render

# Create your views here.


def user_management(request):
    return render(request,"user_management.html")

def admin_user(request):
    return render(request,"admin_user.html")