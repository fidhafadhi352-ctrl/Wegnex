from django.db import models
from django.contrib.auth.models import User

# Create your models here.

class Add_Address(models.Model):

    ADDRESS_TYPES = (('Home', 'Home'), ('Work', 'Work'), ('Other', 'Other'))

    user = models.ForeignKey(User, on_delete=models.CASCADE)

    full_name = models.CharField(max_length=100)
    street_address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=50)
    pincode  = models.CharField(max_length=6)
    country = models.CharField(max_length=50)
    phone_number = models.CharField(max_length=10)
    address_type = models.CharField(max_length=50,choices=ADDRESS_TYPES)

    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name


    