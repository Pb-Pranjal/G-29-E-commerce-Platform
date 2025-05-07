# Create your models here.
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


# models.py in UserApp
class CustomUserManager(BaseUserManager):
    def create_user(self, email, name,username, password=None, role=None):
        if not email:
            raise ValueError("Users must have an email address")
        if not username:
            raise ValueError("Users must have a username")
        email = self.normalize_email(email)
        user = self.model(email=email, name=name,username=username, role=role)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, name,username, password):
        user = self.create_user(email, name,username, password, role='admin')
        user.is_staff = True
        user.is_superuser = True
        user.save(using=self._db)
        return user

class CustomUser(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = (
        ('buyer', 'Buyer'),
        ('seller', 'Seller'),

    )

    email = models.EmailField(unique=True)
    name = models.CharField(max_length=255)
    username=models.CharField(max_length=255,unique=True)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name','username']

    def __str__(self):
        return self.email

class Product(models.Model):
    CATEGORY_CHOICES = [
        ('desks', 'Desks'),
        ('office-chairs', 'Office Chairs'),
        ('paintings', 'Paintings'),
        ('coffee-tables', 'Coffee Tables'),
        ('sofa-couches', 'Sofa and Couches'),
        ('bookshelves', 'Bookshelves'),
        ('side tables', 'Side Tables'),
        ('dining tables', 'Dining Tables'),
        ('dining chairs', 'Dining Chairs'),
        ('buffets and sideboards', 'Buffets and Sideboards'),
        ('bar carts', 'Bar Carts'),
        ('file cabinets', 'File Cabinets'),
        ('wall clocks', 'Wall Clocks'),
         ('doormats', 'Doormats'),
          ('fairy lights', 'Fairy Lights'),
          ('others', 'Others'),
          

        # Add more as needed
    ]

    seller = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=100)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField()
    image_url = models.URLField(blank=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    on_sale = models.BooleanField(default=False)
    sale_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    def discount_percentage(self):
        if self.on_sale and self.sale_price:
            discount=100*(self.price-self.sale_price)/self.price
            return int(discount)
        return 0

    def __str__(self):
        return self.name
    
    
class Order(models.Model):
    buyer = models.ForeignKey( CustomUser, on_delete=models.CASCADE, related_name='orders')
    created_at = models.DateTimeField(auto_now_add=True)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=50)
    address = models.TextField()
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    tracking_number = models.CharField(max_length=50, null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('processing', 'Processing'),
            ('shipped', 'Shipped'),
            ('out_for_delivery', 'Out for Delivery'),
            ('delivered', 'Delivered'),
            ('cancelled', 'Cancelled')
        ],
        default='pending'
    )
    estimated_delivery = models.DateField(null=True, blank=True)


    def __str__(self):
        return f"{self.buyer.username}'s order on {self.created_at}"

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()

    def __str__(self):
       return self.product.name

class Wishlist(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='wishlists')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'product')  # Prevent duplicate items in wishlist

    def __str__(self):
        return f"{self.user.name}'s wishlist - {self.product.name}"

class Cart(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='carts')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'product')  # Each user can only have one cart item per product

    def __str__(self):
        return f"{self.user.name}'s cart - {self.product.name}"

