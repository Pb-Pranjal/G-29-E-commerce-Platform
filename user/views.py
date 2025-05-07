from django.shortcuts import render,redirect,get_object_or_404
from .models import Product
from django.contrib.auth import authenticate, login,logout
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from .models import CustomUser,Product, Order, OrderItem, Wishlist, Cart
from django.contrib.auth.decorators import login_required
from decimal import Decimal
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.urls import reverse
from datetime import datetime, timedelta
from django.db.models import Count, Sum, Avg, F, Q
from django.utils import timezone
from rent.models import Rent
from django.conf import settings
from django.db import IntegrityError
import requests
import random
import time
import json


# Create your views here.
def signup_view(request):
    if request.method == 'POST':
        name = request.POST['name']
        email = request.POST['email']
        username = request.POST['username'] 
        password = request.POST['password']
        role = request.POST['role']

        if CustomUser.objects.filter(email=email).exists():
            messages.error(request, "Email already registered")
            return redirect('signup')
        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, "Username already taken")
            return redirect('signup')

        user = CustomUser.objects.create_user(name=name, email=email,username=username, password=password, role=role)
        messages.success(request, "Account created successfully! Please log in.")
        return redirect('login')
    return render(request, 'signup.html')



def login_view(request):
    if request.method == 'POST':
        email = request.POST['email']
        password = request.POST['password']
        user = authenticate(request, email=email, password=password)
        if user is not None:
            login(request, user)
            return redirect('main')  # Use the correct name for the main page route
        else:
            messages.error(request, "Invalid email or password")
            return redirect('login')  # Redirect back to the login page
    return render(request, 'login.html')


def homepageFunction(request):
        return render(request,"homepage.html")
def mainpageFunction(request):
    context = {}
    
    # Only fetch sales data if user is authenticated and is a seller
    if request.user.is_authenticated and request.user.role == "seller":
        # Get the period from query parameters (default to 'week')
        period = request.GET.get('period', 'week')
        
        # Calculate date range based on period
        today = timezone.now().date()
        if period == 'week':
            start_date = today - timedelta(days=7)
            period_display = "Week"
        elif period == 'month':
            start_date = today - timedelta(days=30)
            period_display = "Month"
        else:  # year
            start_date = today - timedelta(days=365)
            period_display = "Year"
        
        # Get all orders for the seller within the date range
        seller_orders = OrderItem.objects.filter(
            product__seller=request.user,
            order__created_at__date__gte=start_date,
            order__created_at__date__lte=today
        )
        
        # Calculate daily sales
        daily_sales = {}
        total_sales = 0
        best_day = None
        best_day_sales = 0
        
        # Initialize all days in the period with zero sales
        current_date = start_date
        while current_date <= today:
            day_name = current_date.strftime('%a')  # Abbreviated day name (Mon, Tue, etc.)
            daily_sales[day_name] = {'value': 0, 'percentage': 10}  # Default 10% height for zero sales
            current_date += timedelta(days=1)
        
        # Count sales for each day
        for order in seller_orders:
            order_date = order.order.created_at.date()
            day_name = order_date.strftime('%a')
            
            # Update the count for this day
            daily_sales[day_name]['value'] += order.quantity
            total_sales += order.quantity
            
            # Check if this is the best day so far
            if daily_sales[day_name]['value'] > best_day_sales:
                best_day = day_name
                best_day_sales = daily_sales[day_name]['value']
        
        # Calculate percentage heights for the chart (max 100%)
        max_daily_sales = max([data['value'] for data in daily_sales.values()]) if daily_sales else 1
        for day, data in daily_sales.items():
            if max_daily_sales > 0:
                data['percentage'] = min(100, int((data['value'] / max_daily_sales) * 100))
        
        # Calculate average daily sales
        days_in_period = (today - start_date).days + 1
        avg_daily_sales = round(total_sales / days_in_period, 1) if days_in_period > 0 else 0
        
        # Get top selling products
        top_products = OrderItem.objects.filter(
            product__seller=request.user,
            order__created_at__date__gte=start_date,
            order__created_at__date__lte=today
        ).values('product__name').annotate(
            sold_count=Sum('quantity')
        ).order_by('-sold_count')[:5]
        
        # Calculate demand percentage for each product
        max_sold = top_products[0]['sold_count'] if top_products else 1
        for product in top_products:
            product['demand_percentage'] = min(100, int((product['sold_count'] / max_sold) * 100))
        
        # Since there's no Review model, create some sample reviews
        customer_reviews = [
            {
                'name': 'John Doe',
                'product': 'Modern Dining Table',
                'rating': 5,
                'comment': 'The dining table is exactly as described. The quality is excellent and it was delivered on time. Very satisfied with the purchase!'
            },
            {
                'name': 'Jane Smith',
                'product': 'Leather Sofa Set',
                'rating': 4,
                'comment': 'The sofa set is comfortable and looks great in my living room. The delivery was a bit delayed, but the product quality makes up for it.'
            },
            {
                'name': 'Sarah Lee',
                'product': 'Wooden Bookshelf',
                'rating': 5,
                'comment': 'The bookshelf is sturdy and well-made. It was easy to assemble and looks perfect in my home office. Highly recommend!'
            }
        ]
        
        # Add all data to context
        context = {
            'daily_sales': daily_sales,
            'total_sales': total_sales,
            'avg_daily_sales': avg_daily_sales,
            'best_day': best_day,
            'best_day_sales': best_day_sales,
            'period': period_display,
            'top_products': top_products,
            'customer_reviews': customer_reviews
        }
    
    return render(request, "mainpage.html", context)

@login_required
def productFunction(request):
    search_query = request.GET.get('q', '')
    category = request.GET.get('category', '')
    sort_by = request.GET.get('sort', '')
    
    all_products = []

    # 1. Fetch from Flask API
    try:
        response = requests.get('https://snehag.pythonanywhere.com/api/products')
        response.raise_for_status()
        flask_products = response.json()

        # 2. Store the Flask API products in the Django database
        for flask_product in flask_products:
            # Get or create the seller user
            seller_username = flask_product.get('seller_username')
            if seller_username:
                seller, created = CustomUser.objects.get_or_create(
                    username=seller_username,
                    defaults={
                        'email': f'{seller_username}@example.com',  # You might want to handle this differently
                        'role': 'seller'
                    }
                )
            else:
                seller = request.user  # Fallback to current user if no seller info

            # Check if the product already exists in the Django DB based on some unique field (e.g., product id)
            django_product, created = Product.objects.update_or_create(
                id=flask_product['id'],  # Assuming 'id' is unique for each product
                defaults={
                    'name': flask_product['name'],
                    'description': flask_product['description'],
                    'price': flask_product['price'],
                    'stock': flask_product['stock'],
                    'image_url': flask_product['image_url'],
                    'category': flask_product['category'],
                    'on_sale': flask_product['on_sale'],
                    'sale_price': flask_product['sale_price'] if flask_product['on_sale'] else None,
                    'seller': seller  # Set the seller
                }
            )
            # After update_or_create, you will have the product updated or created in Django DB
           
    except requests.exceptions.RequestException:
        flask_products = []

    # 3. Fetch from Django DB if Flask API doesn't return any products
    django_products = Product.objects.all()
    for p in django_products:
        all_products.append({
            'id': p.id,
            'name': p.name,
            'description': p.description,
            'price': float(p.price),
            'stock': p.stock,
            'image_url': p.image_url,
            'category': p.category,
            'on_sale': p.on_sale,
            'sale_price': float(p.sale_price) if p.sale_price else None,
            'seller_id': p.seller.id
        })

    # 4. If seller, show only their products
    if request.user.role == 'seller':
        all_products = [p for p in all_products if p['seller_id'] == request.user.id]
    
    # 5. Apply search filter
    if search_query:
        all_products = [p for p in all_products if
                        search_query.lower() in p['name'].lower() or
                        search_query.lower() in p['description'].lower() or
                        search_query.lower() in p['category'].lower()]

    # 6. Apply category filter
    if category:
        all_products = [p for p in all_products if p['category'] == category]

    # 7. Apply sorting
    if sort_by == 'price_low':
        all_products.sort(key=lambda x: x['price'])
    elif sort_by == 'price_high':
        all_products.sort(key=lambda x: -x['price'])
    elif sort_by == 'name':
        all_products.sort(key=lambda x: x['name'])
    elif sort_by == 'newest':
        all_products.sort(key=lambda x: -x['id'])

    # 8. Get unique categories
    categories = list(set(p['category'] for p in all_products))

    context = {
        'products': all_products,
        'categories': categories,
        'search_query': search_query,
        'selected_category': category,
        'selected_sort': sort_by
    }

    return render(request, 'Product.html', context)

@login_required
def aboutFunction(request):
        return render(request,"Aboutus.html")
@login_required
def contactFunction(request):
        return render(request,"Contact.html")



def sellerFunction(request):
     if request.method == 'POST':
        try:
            # Get form data
            name = request.POST.get('name')
            description = request.POST.get('description')
            price = float(request.POST.get('price', 0))  # Convert to float
            stock = int(request.POST.get('stock', 0))    # Convert to int
            image_url = request.POST.get('image_url')
            category = request.POST.get('category')
            on_sale = request.POST.get('on_sale') == 'on'
            sale_price = float(request.POST.get('sale_price', 0)) if request.POST.get('sale_price') else None

            # Save product with current user as seller
            product = Product.objects.create(
                seller=request.user,
                name=name,
                description=description,
                price=price,
                stock=stock,
                image_url=image_url,
                category=category,
                on_sale=on_sale,
                sale_price=sale_price
            )

            # Prepare data for Flask API - ensure all fields match Flask API expectations
            flask_data = {
                'name': name,
                'description': description,
                'price': str(price),  # Convert to string as Flask might expect string
                'stock': str(stock),  # Convert to string as Flask might expect string
                'image_url': image_url,
                'category': category,
                'on_sale': str(on_sale).lower(),  # Convert to lowercase string
                'sale_price': str(sale_price) if sale_price is not None else None,
                'seller_username': request.user.username
            }

            # Debug print Flask data
            print("\nData being sent to Flask API:")
            print(json.dumps(flask_data, indent=2))

            # Send to Flask API
            try:
                # Send the POST request with proper headers and data format
                flask_response = requests.post(
                    'https://snehag.pythonanywhere.com/api/products',
                    json=flask_data,
                    headers={
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    },
                    timeout=10  # Add timeout to prevent hanging
                )
                
                # Log the response for debugging
                print(f"\nFlask API Response Status: {flask_response.status_code}")
                print(f"Flask API Response Headers: {dict(flask_response.headers)}")
                print(f"Flask API Response Body: {flask_response.text}")
                
                if flask_response.status_code in [200, 201]:
                    messages.success(request, "Product submitted and sent to Flask API!")
                else:
                    error_msg = f"Product saved, but Flask API error: {flask_response.status_code} - {flask_response.text}"
                    messages.warning(request, error_msg)
                    print(f"\nError: {error_msg}")
            except requests.exceptions.RequestException as e:
                error_msg = f"Product saved, but failed to contact Flask API: {str(e)}"
                messages.warning(request, error_msg)
                print(f"\nError: {error_msg}")
                print(f"Full error details: {e.__class__.__name__}: {str(e)}")
            
            return redirect('all_products')
            
        except Exception as e:
            error_msg = f"Error creating product: {str(e)}"
            messages.error(request, error_msg)
            print(f"\nError in sellerFunction: {error_msg}")
            print(f"Full error details: {e.__class__.__name__}: {str(e)}")
            return redirect('seller')
    
     return render(request,"seller.html")



def place_order_view(request):
    if request.method == 'POST':
        product_id = request.POST.getlist('product_id')
        quantities = request.POST.getlist('quantities')
        
        if not product_id:
            return render(request, 'place_order.html', {
                'products': Product.objects.all(),
                'error': 'Please select at least one product.'
            })

        total = 0
        items = []

        for product_id, quantity in zip(product_id, quantities):
            product = Product.objects.get(id=product_id)
            quantity = int(quantity)
            total += product.price * quantity
            items.append((product, quantity))
            payment_method = request.POST.get('payment_method')
        address = request.POST.get('address')

        if not payment_method or not address:
            return render(request, 'place_order.html', {
                'products': Product.objects.all(),
                'error': 'Payment method and address are required.'
            })



        # Create the order
        order = Order.objects.create(buyer=request.user, total=Decimal(total))

        # Create order items
        for product, quantity in items:
            OrderItem.objects.create(order=order, product=product, quantity=quantity)

        return redirect('user_dashboard')  # After order, go to dashboard

    # GET request — show product list to select from
    products = Product.objects.all()
    return render(request, 'product.html', {'products': products})

@login_required
def category_view(request, category_slug):
    # Check if the user is a seller
    if request.user.role == 'seller':
        # If the user is a seller, show only their products for the selected category
        products = Product.objects.filter(category=category_slug, seller=request.user)
    else:
        # If the user is a buyer, show all products for the selected category
        products = Product.objects.filter(category=category_slug)

    # Render the filtered products to the template
    return render(request, 'Product.html', {
        'products': products,
        'category': category_slug.replace('-', ' ').title()
    })
def buy_now_view(request):
    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        product = get_object_or_404(Product, id=product_id)

        return render(request, 'buynow.html', {'product': product})
    else:
        return render(request, 'buynow.html', {'error': 'Invalid request'})
@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        try:
            product = get_object_or_404(Product, pk=product_id)
            cart = request.session.get('cart', {})
            product_id_str = str(product_id)

            if product_id_str in cart:
                cart[product_id_str]['quantity'] += 1
                message = f"Quantity updated for {product.name}"
            else:
                cart[product_id_str] = {
                    'name': product.name,
                    'price': float(product.price),
                    'image_url': product.image_url if product.image_url else '',
                    'quantity': 1
                }
                message = f"{product.name} added to your cart"

            request.session['cart'] = cart
            return JsonResponse({
                'success': True,
                'message': message,
                'redirect': reverse('cart')
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            })
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'})
def view_cart(request):
    cart = request.session.get('cart', {})
    cart_items = {}
    total=0

    for product_id, item in cart.items():
        subtotal = item['price'] * item['quantity']
        total += subtotal
        cart_items[product_id] = {
            'name': item['name'],
            'price': item['price'],
            'quantity': item['quantity'],
            'image_url': item.get('image_url'),
            'subtotal': f"{subtotal:.2f}"
        }

    return render(request, 'cart.html', {'cart_items': cart_items,'total':f"{total:.2f}"})

def remove_from_cart(request, product_id):
    if request.method == 'POST':
        cart = request.session.get('cart', {})
        product_id_str = str(product_id)

        if product_id_str in cart:
            del cart[product_id_str]
            request.session['cart'] = cart
            messages.success(request, 'Item removed from cart.')
        else:
            messages.warning(request, 'Item not found in cart.')

    return redirect('cart')

@require_POST
def update_quantity(request, product_id):
    if request.method == 'POST':
        action = request.POST.get('action')
        cart = request.session.get('cart', {})
        product_id_str = str(product_id)

        if product_id_str in cart:
            if action == 'increase':
                cart[product_id_str]['quantity'] += 1
            elif action == 'decrease':
                cart[product_id_str]['quantity'] -= 1
                if cart[product_id_str]['quantity'] <= 0:
                    del cart[product_id_str]

        request.session['cart'] = cart

    return redirect('cart')  # 🔁 

from decimal import Decimal
from django.shortcuts import render, redirect
from django.contrib import messages
from .models import Product, Order, OrderItem

def checkout_view(request):
    cart = request.session.get('cart', {})
    total = sum(item['price'] * item['quantity'] for item in cart.values())

    if request.method == 'POST':
        address = request.POST.get('address')
        payment_method = request.POST.get('payment_method')
# Generate a tracking number (using timestamp and random number)
        tracking_number = f"TR{int(time.time())}{random.randint(1000, 9999)}"

        # Create the order with basic details
        order = Order.objects.create(
            buyer=request.user,
            total=Decimal(total),
            payment_method=payment_method,
            address=address,
            latitude=None,
            longitude=None,
            tracking_number=tracking_number,
            status='pending'  # Set initial status
        )


        # Create associated order items
        for product_id_str, item in cart.items():
            try:
                product = Product.objects.get(id=int(product_id_str))
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=item['quantity']
                )
            except Product.DoesNotExist:
                continue

        # Clear cart after order placement
        request.session['cart'] = {}

        messages.success(request, 'Order placed successfully!')
        return redirect('order_place')  # Adjust as needed

    return render(request, 'checkout.html', {'total': total})

   
def order_place(request):
     return render(request,'orderplace.html')
def profile(request):
    if not request.user.is_authenticated:
        return redirect('login')
    
    name = request.user.name
    email = request.user.email
    role = request.user.role
    
    context = {
        'name': name,
        'email': email,
        'role': role,
    }
    
    if role == 'buyer':
        # Get purchase history
        orders = Order.objects.filter(buyer=request.user).order_by('-created_at')
        purchase_details = []
        total_spent = 0
        
        for order in orders:
            for item in order.items.all():
                purchase_details.append({
                    'name': item.product.name,
                    'price': item.product.price,
                    'quantity': item.quantity,
                    'total': item.product.price * item.quantity,
                    'order': order  # Include the order object
                })
                total_spent += item.product.price * item.quantity
        
        context.update({
            'purchase_details': purchase_details,
            'total_spent': total_spent
        })
        
        # Get rental history
        from rent.models import Rental
        from datetime import date
        
        rentals = Rental.objects.filter(user=request.user).order_by('-start_date')
        today = date.today()
        
        context.update({
            'rentals': rentals,
            'today': today
        })
        
    elif role == 'seller':
        # Get seller's products
        seller_products = list(Product.objects.filter(seller=request.user))
        context['seller_products'] = seller_products
        try:
            response = requests.get('https://snehag.pythonanywhere.com/api/products')
            if response.status_code == 200:
                flask_products = response.json()
                
                class FlaskProduct:
                    def __init__(self, data):
                        self.id = data.get('id')
                        self.name = data.get('name')
                        self.description = data.get('description')
                        self.category = data.get('category')
                        self.price = data.get('price')
                        self.on_sale = data.get('on_sale', False)
                        self.sale_price = data.get('sale_price', None)
                        self.discount_percentage = data.get('discount_percentage', 0)
                        self.image_url = data.get('image_url', '/static/images/default.jpg')
                        self.is_flask = True

                flask_seller_products = [
                    FlaskProduct(p) for p in flask_products
                    if p.get('seller_username') == request.user.username
                ]
                
                seller_products.extend(flask_seller_products)
        except Exception as e:
            print("Error fetching from Flask:", e)
    
    return render(request, 'profile.html', context)


    # Ensure the logged-in user has a profile and filter their orders


def logout_view(request):
    logout(request)
    return redirect('main')

@login_required
def add_to_wishlist(request, product_id):
    if request.method == 'POST':
        try:
            product = get_object_or_404(Product, id=product_id)
            
            # Check if item already in wishlist
            if Wishlist.objects.filter(user=request.user, product=product).exists():
                return JsonResponse({
                    'success': False,
                    'message': f"{product.name} is already in your wishlist."
                })
            
            # Create new wishlist item
            Wishlist.objects.create(user=request.user, product=product)
            return JsonResponse({
                'success': True,
                'message': f"{product.name} added to your wishlist."
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            })
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'})

@login_required
def remove_from_wishlist(request, product_id):
    if request.method == 'POST':
        try:
            product = get_object_or_404(Product, id=product_id)
            wishlist_item = get_object_or_404(Wishlist, user=request.user, product=product)
            product_name = product.name
            wishlist_item.delete()
            return JsonResponse({
                'success': True,
                'message': f"{product_name} removed from your wishlist."
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            })
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'})

@login_required
def view_wishlist(request):
    if not request.user.is_authenticated:
        return redirect('login')
    
    if request.user.role == "seller":
        # For sellers, show wishlist items only for their own products
        wishlist_items = Wishlist.objects.filter(
            user=request.user,
            product__seller=request.user
        ).select_related('product')
    else:
        # For buyers, show all their wishlist items
        wishlist_items = Wishlist.objects.filter(
            user=request.user
        ).select_related('product')
    
    context = {
        'wishlist_items': wishlist_items
    }
    return render(request, 'wishlist.html', context)

@login_required
def product_detail(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    in_wishlist = False
    if request.user.is_authenticated:
        in_wishlist = Wishlist.objects.filter(user=request.user, product=product).exists()
    
    return render(request, 'product_detail.html', {
        'product': product,
        'in_wishlist': in_wishlist
    })
@login_required
def product_list(request):
    if request.user.role != 'seller':
        return redirect('homepage')
    
    # Get seller's products from Django database
    django_products = Product.objects.filter(seller=request.user)
    
    # Get products from Flask API
    try:
        response = requests.get('https://snehag.pythonanywhere.com/api/products')
        if response.status_code == 200:
            flask_products = response.json()
            # Filter products to only show those added by the current seller
            flask_seller_products = [
                product for product in flask_products 
                if product.get('seller_username') == request.user.username
            ]
        else:
            flask_seller_products = []
    except requests.exceptions.RequestException:
        flask_seller_products = []
    
    # Create a Product-like class for Flask products
    class FlaskProduct:
        def __init__(self, data):
            self.id = data.get('id')
            self.name = data.get('name')
            self.description = data.get('description')
            self.price = data.get('price')
            self.stock = data.get('stock')
            self.image_url = data.get('image_url')
            self.category = data.get('category')
            self.on_sale = data.get('on_sale', False)
            self.sale_price = data.get('sale_price')
            self.is_flask = True
    
    # Convert Flask products to FlaskProduct objects
    flask_products_objects = [FlaskProduct(p) for p in flask_seller_products]
    
    # Combine Django and Flask products
    all_products = list(django_products) + flask_products_objects
    
    # Get product statistics
    products_with_stats = []
    for product in all_products:
        # Get total orders for this product
        total_orders = OrderItem.objects.filter(
            product__name=product.name,
            product__seller=request.user
        ).count()
        
        # Get total quantity sold
        total_quantity = OrderItem.objects.filter(
            product__name=product.name,
            product__seller=request.user
        ).aggregate(
            total=Sum('quantity')
        )['total'] or 0
        
        # Get total revenue
        total_revenue = OrderItem.objects.filter(
            product__name=product.name,
            product__seller=request.user
        ).aggregate(
            total=Sum(F('quantity') * F('product__price'))
        )['total'] or 0
        
        # Get wishlist count
        wishlist_count = Wishlist.objects.filter(
            product__name=product.name,
            product__seller=request.user
        ).count()
        
        products_with_stats.append({
            'product': product,
            'total_orders': total_orders,
            'total_quantity': total_quantity,
            'total_revenue': total_revenue,
            'wishlist_count': wishlist_count
        })
    
    context = {
        'products_with_stats': products_with_stats,
        'name': request.user.name,
        'email': request.user.email,
        'role': request.user.role
    }
    return render(request, 'product_list.html', context)
def list_view(request):
    return redirect('seller_product_list')

@login_required
def update_product(request, id):
    # First try to get the product from Django database
    try:
        product = Product.objects.get(id=id, seller=request.user)
        is_flask = False
    except Product.DoesNotExist:
        # If not in Django, try to get from Flask API
        try:
            response = requests.get(f'https://snehag.pythonanywhere.com/api/products/{id}')
            if response.status_code == 200:
                flask_product = response.json()
                if flask_product.get('seller_username') != request.user.username:
                    messages.error(request, "You don't have permission to edit this product")
                    return redirect('seller_product_list')
                is_flask = True
            else:
                messages.error(request, "Product not found")
                return redirect('seller_product_list')
        except requests.exceptions.RequestException:
            messages.error(request, "Error connecting to Flask API")
            return redirect('seller_product_list')

    if request.method == 'POST':
        try:
            # Prepare the update data
            update_data = {
                'name': request.POST.get('name'),
                'description': request.POST.get('description'),
                'price': float(request.POST.get('price')),
                'stock': int(request.POST.get('stock')),
                'image_url': request.POST.get('image_url'),
                'category': request.POST.get('category'),
                'on_sale': request.POST.get('on_sale') == 'on',
                'sale_price': float(request.POST.get('sale_price')) if request.POST.get('sale_price') else None,
                'seller_username': request.user.username
            }

            if is_flask:
                # Update in Flask API
                response = requests.put(
                    f'https://snehag.pythonanywhere.com/api/products/{id}',
                    json=update_data,
                    headers={'Content-Type': 'application/json'}
                )
                
                if response.status_code == 200:
                    messages.success(request, "Product updated successfully in Flask API")
                    return redirect('seller_product_list')
                else:
                    messages.error(request, f"Failed to update product in Flask API: {response.text}")
                    return redirect('seller_product_list')
            else:
                # Update in Django database
                product.name = update_data['name']
                product.description = update_data['description']
                product.price = update_data['price']
                product.stock = update_data['stock']
                product.image_url = update_data['image_url']
                product.category = update_data['category']
                product.on_sale = update_data['on_sale']
                product.sale_price = update_data['sale_price']
                product.save()

                # Also update in Flask API
                try:
                    response = requests.put(
                        f'https://snehag.pythonanywhere.com/api/products/{id}',
                        json=update_data,
                        headers={'Content-Type': 'application/json'}
                    )
                    if response.status_code == 200:
                        messages.success(request, "Product updated successfully in both systems")
                    else:
                        messages.warning(request, "Product updated in Django but failed to update in Flask API")
                except requests.exceptions.RequestException:
                    messages.warning(request, "Product updated in Django but failed to update in Flask API")

                return redirect('seller_product_list')
        except Exception as e:
            messages.error(request, f"Error updating product: {str(e)}")
            return redirect('seller_product_list')
    
    # For GET request, prepare the context
    if is_flask:
        context = {
            'product': {
                'id': id,
                'name': flask_product.get('name'),
                'description': flask_product.get('description'),
                'price': flask_product.get('price'),
                'stock': flask_product.get('stock'),
                'image_url': flask_product.get('image_url'),
                'category': flask_product.get('category'),
                'on_sale': flask_product.get('on_sale', False),
                'sale_price': flask_product.get('sale_price'),
                'is_flask': True
            }
        }
    else:
        context = {'product': product}
    
    return render(request, 'update.html', context)

@login_required
def delete_product(request, id):
    try:
        print(f"Starting delete process for product {id}")  # Debug print
        
        # First try to delete from Flask API
        try:
            # Check if product exists in Flask
            response = requests.get(f'https://snehag.pythonanywhere.com/api/products/{id}')
            if response.status_code == 200:
                product_data = response.json()
                print(f"Found product in Flask: {product_data}")  # Debug print
                
                # Check if the user is the seller
                if product_data['seller_username'] != request.user.username:
                    messages.error(request, "You are not authorized to delete this product.")
                    return redirect('seller_product_list')
                
                # Delete from Flask API
                delete_response = requests.delete(
                    f'https://snehag.pythonanywhere.com/api/products/{id}',
                    json={'seller_username': request.user.username},
                    headers={'Content-Type': 'application/json'}
                )
                
                print(f"Flask API delete response: {delete_response.status_code} - {delete_response.text}")  # Debug print
                
                if delete_response.status_code != 200:
                    messages.error(request, f"Failed to delete product from Flask API: {delete_response.text}")
                    return redirect('seller_product_list')
                
        except Exception as e:
            print(f"Flask API error: {str(e)}")  # Debug print
            # Continue to try Django deletion even if Flask fails
        
        # Then try to delete from Django database
        try:
            product = Product.objects.get(id=id)
            print(f"Found product in Django: {product}")  # Debug print
            
            if product.seller != request.user:
                messages.error(request, "You are not authorized to delete this product.")
                return redirect('seller_product_list')
            
            product.delete()
            print(f"Successfully deleted product {id} from Django database")  # Debug print
            
        except Product.DoesNotExist:
            print(f"Product {id} not found in Django database")  # Debug print
            # Product not in Django, which is fine if it was in Flask
        
        messages.success(request, "Product deleted successfully!")
        return redirect('seller_product_list')
        
    except Exception as e:
        messages.error(request, f"Error: {str(e)}")
        print(f"General error: {str(e)}")  # Debug print
        return redirect('seller_product_list')

from django.utils.text import slugify
from django.http import JsonResponse

def search_ajax(request):
    query = request.GET.get('q', '').strip().lower()
    
    CATEGORY_SLUGS = {
        'desks': 'Desks',
        'office-chairs': 'Office Chairs',
        'paintings': 'Paintings',
        'coffee-tables': 'Coffee Tables',
        'sofa-couches': 'Sofa and Couches',
        'bookshelves': 'Bookshelves',
        'side-tables': 'Side Tables',
        'dining-tables': 'Dining Tables',
        'dining-chairs': 'Dining Chairs',
        'buffets-and-sideboards': 'Buffets and Sideboards',
        'bar-carts': 'Bar Carts',
        'file-cabinets': 'File Cabinets',
        'wall clocks': 'Wall Clocks',
        'doormats': 'Doormats',
        'fairy lights': 'Fairy Lights',
        'others': 'Others',
        # Add more categories as needed
    }

    # Normalize keys to remove spaces for matching
    normalized_category_slugs = {
        category_slug.replace(' ', '-').lower(): category_name
        for category_slug, category_name in CATEGORY_SLUGS.items()
    }

    # Check for a match
    if query in normalized_category_slugs:
        return JsonResponse({'url': f'/category/{query}/'})

    # Return default if no match
    return JsonResponse({'url': '/'})


@login_required
def wishlist_statistics(request):
    # Check if the user is a seller
    if request.user.role != 'seller':
        return redirect('main')
    
    # Get all products added to wishlists that belong to the current seller
    wishlist_items = Wishlist.objects.filter(product__seller=request.user)
    
    # Create a dictionary to count how many times each product is in wishlists
    product_wishlist_count = {}
    for item in wishlist_items:
        product_id = item.product.id
        if product_id in product_wishlist_count:
            product_wishlist_count[product_id] += 1
        else:
            product_wishlist_count[product_id] = 1
    
    # Get all products with their wishlist counts (only for the current seller)
    products_with_counts = []
    for product in Product.objects.filter(seller=request.user):
        wishlist_count = product_wishlist_count.get(product.id, 0)
        products_with_counts.append({
            'product': product,
            'wishlist_count': wishlist_count
        })
    
    # Sort products by wishlist count (highest first)
    products_with_counts.sort(key=lambda x: x['wishlist_count'], reverse=True)
    
    context = {
        'products_with_counts': products_with_counts
    }
    
    return render(request, 'wishlist_statistics.html', context)

@login_required
def sales_overview(request):
    if request.user.role != 'seller':
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    # Get time period from query params, default to week
    period = request.GET.get('period', 'week')
    
    # Calculate start date based on period
    today = datetime.now().date()
    if period == 'week':
        start_date = today - timedelta(days=7)
    elif period == 'month':
        start_date = today - timedelta(days=30)
    else:  # year
        start_date = today - timedelta(days=365)
    
    # Get all orders for the seller's products within the date range
    seller_orders = Order.objects.filter(
        items__product__seller=request.user,
        created_at__date__gte=start_date,
        created_at__date__lte=today
    ).distinct()
    
    # Calculate daily sales
    daily_sales = []
    for i in range((today - start_date).days + 1):
        current_date = start_date + timedelta(days=i)
        day_total = seller_orders.filter(
            created_at__date=current_date
        ).aggregate(
            total=Sum('total')
        )['total'] or 0
        
        daily_sales.append({
            'day': current_date.strftime('%a'),
            'amount': float(day_total)
        })
    
    # Calculate total sales
    total_sales = seller_orders.aggregate(
        total=Sum('total')
    )['total'] or 0
    
    # Calculate average daily sales
    avg_daily_sales = total_sales / len(daily_sales) if daily_sales else 0
    
    # Find best sales day
    best_day = max(daily_sales, key=lambda x: x['amount'])
    
    # Get top products
    top_products = OrderItem.objects.filter(
        order__in=seller_orders,
        product__seller=request.user
    ).values(
        'product__name',
        'product__price'
    ).annotate(
        total_quantity=Sum('quantity'),
        total_revenue=Sum(F('quantity') * F('product__price'))
    ).order_by('-total_quantity')[:5]
    
    # Format top products data
    top_products_data = [{
        'name': item['product__name'],
        'quantity': item['total_quantity'],
        'revenue': float(item['total_revenue'])
    } for item in top_products]
    
    # Get customer reviews (if you have a review model, add it here)
    # For now, we'll use a placeholder
    customer_reviews = []
    
    context = {
        'daily_sales': daily_sales,
        'total_sales': float(total_sales),
        'avg_daily_sales': float(avg_daily_sales),
        'best_day': best_day,
        'top_products': top_products_data,
        'customer_reviews': customer_reviews,
        'period': period
    }
    
    return render(request, 'sales_overview.html', context)

@login_required
def seller_dashboard(request):
    if request.user.role != 'seller':
        return redirect('homepage')
    
    # Get products from Flask API
    try:
        response = requests.get('https://snehag.pythonanywhere.com/api/products')
        if response.status_code == 200:
            flask_products = response.json()
            # Filter products to only show those added by the current seller
            seller_products = [
                product for product in flask_products 
                if product.get('seller_username') == request.user.username
            ]
        else:
            seller_products = []
    except requests.exceptions.RequestException:
        seller_products = []
    
    # Get recent orders for seller's products
    recent_orders = []
    for order_item in OrderItem.objects.filter(
        product__seller=request.user
    ).select_related('order', 'product').order_by('-order__created_at')[:5]:
        total = float(order_item.product.price) * order_item.quantity
        recent_orders.append({
            'product': order_item.product,
            'quantity': order_item.quantity,
            'total': total,
            'order': order_item.order
        })
    
    # Calculate total sales for seller's products
    total_sales = OrderItem.objects.filter(
        product__seller=request.user
    ).aggregate(
        total=Sum(F('product__price') * F('quantity'))
    )['total'] or 0
    
    # Get top selling products for this seller
    top_products = OrderItem.objects.filter(
        product__seller=request.user
    ).values(
        'product__name'
    ).annotate(
        total=Sum('quantity')
    ).order_by('-total')[:5]
    
    # Get product statistics
    products_with_stats = []
    for product in seller_products:
        # Create a Product-like object for Flask products
        class FlaskProduct:
            def __init__(self, data):
                self.id = data.get('id')
                self.name = data.get('name')
                self.description = data.get('description')
                self.price = data.get('price')
                self.stock = data.get('stock')
                self.image_url = data.get('image_url')
                self.category = data.get('category')
                self.on_sale = data.get('on_sale', False)
                self.sale_price = data.get('sale_price')
                self.is_flask = True
        
        flask_product = FlaskProduct(product)
        
        # Get total orders for this product
        total_orders = OrderItem.objects.filter(
            product__name=flask_product.name,
            product__seller=request.user
        ).count()
        
        # Get total quantity sold
        total_quantity = OrderItem.objects.filter(
            product__name=flask_product.name,
            product__seller=request.user
        ).aggregate(
            total=Sum('quantity')
        )['total'] or 0
        
        # Get total revenue
        total_revenue = OrderItem.objects.filter(
            product__name=flask_product.name,
            product__seller=request.user
        ).aggregate(
            total=Sum(F('quantity') * F('product__price'))
        )['total'] or 0
        
        # Get wishlist count
        wishlist_count = Wishlist.objects.filter(
            product__name=flask_product.name,
            product__seller=request.user
        ).count()
        
        products_with_stats.append({
            'product': flask_product,
            'total_orders': total_orders,
            'total_quantity': total_quantity,
            'total_revenue': total_revenue,
            'wishlist_count': wishlist_count
        })
    
    context = {
        'products': seller_products,
        'products_with_stats': products_with_stats,
        'recent_orders': recent_orders,
        'total_sales': total_sales,
        'top_products': top_products,
    }
    
    return render(request, 'seller_dashboard.html', context)

def search_products(request):
    query = request.GET.get('q', '').strip()
    
    if not query:
        return JsonResponse({'url': '/'})
    
    # Search in product names and descriptions
    products = Product.objects.filter(
        Q(name__icontains=query) |
        Q(description__icontains=query)
    )
    
    if products.exists():
        # If products found, redirect to products page with search query
        return JsonResponse({'url': f'/product/?search={query}'})
    
    # Check if query matches any category
    CATEGORY_SLUGS = {
        'desks': 'Desks',
        'office-chairs': 'Office Chairs',
        'paintings': 'Paintings',
        'coffee-tables': 'Coffee Tables',
        'sofa-couches': 'Sofa and Couches',
        'bookshelves': 'Bookshelves',
        'side-tables': 'Side Tables',
        'dining-tables': 'Dining Tables',
        'dining-chairs': 'Dining Chairs',
        'buffets-and-sideboards': 'Buffets and Sideboards',
        'bar-carts': 'Bar Carts',
        'file-cabinets': 'File Cabinets',
        'wall-clocks': 'Wall Clocks',
        'doormats': 'Doormats',
        'fairy-lights': 'Fairy Lights',
        'others': 'Others',
    }
    
    # Normalize query and category slugs for comparison
    normalized_query = query.lower().replace(' ', '-')
    normalized_categories = {
        slug.replace(' ', '-').lower(): name
        for slug, name in CATEGORY_SLUGS.items()
    }
    
    if normalized_query in normalized_categories:
        return JsonResponse({'url': f'/category/{normalized_query}/'})
    
    # If no matches found, redirect to products page with search query
    return JsonResponse({'url': f'/product/?search={query}'})

@login_required
def seller_product_list(request):
    if request.user.role != 'seller':
        return redirect('homepage')
    
    # Get seller's products from Django database
    django_products = Product.objects.filter(seller=request.user)
    
    # Get products from Flask API
    try:
        response = requests.get('https://snehag.pythonanywhere.com/api/products')
        if response.status_code == 200:
            flask_products = response.json()
            # Filter products to only show those added by the current seller
            flask_seller_products = [
                product for product in flask_products 
                if product.get('seller_username') == request.user.username
            ]
        else:
            flask_seller_products = []
    except requests.exceptions.RequestException:
        flask_seller_products = []
    
    # Create a Product-like class for Flask products
    class FlaskProduct:
        def __init__(self, data):
            self.id = data.get('id')
            self.name = data.get('name')
            self.description = data.get('description')
            self.price = data.get('price')
            self.stock = data.get('stock')
            self.image_url = data.get('image_url')
            self.category = data.get('category')
            self.on_sale = data.get('on_sale', False)
            self.sale_price = data.get('sale_price')
            self.is_flask = True
    
    # Convert Flask products to FlaskProduct objects
    flask_products_objects = [FlaskProduct(p) for p in flask_seller_products]
    
    # Combine Django and Flask products
    all_products = list(django_products) + flask_products_objects
    
    # Get product statistics
    products_with_stats = []
    for product in all_products:
        # Get total orders for this product
        total_orders = OrderItem.objects.filter(
            product__name=product.name,
            product__seller=request.user
        ).count()
        
        # Get total quantity sold
        total_quantity = OrderItem.objects.filter(
            product__name=product.name,
            product__seller=request.user
        ).aggregate(
            total=Sum('quantity')
        )['total'] or 0
        
        # Get total revenue
        total_revenue = OrderItem.objects.filter(
            product__name=product.name,
            product__seller=request.user
        ).aggregate(
            total=Sum(F('quantity') * F('product__price'))
        )['total'] or 0
        
        # Get wishlist count
        wishlist_count = Wishlist.objects.filter(
            product__name=product.name,
            product__seller=request.user
        ).count()
        
        products_with_stats.append({
            'product': product,
            'total_orders': total_orders,
            'total_quantity': total_quantity,
            'total_revenue': total_revenue,
            'wishlist_count': wishlist_count
        })
    
    context = {
        'products_with_stats': products_with_stats,
        'name': request.user.name,
        'email': request.user.email,
        'role': request.user.role
    }
    return render(request, 'product_list.html', context)

@login_required
def track_order(request, tracking_number):
    try:
        order = get_object_or_404(Order, tracking_number=tracking_number)
        # Verify that the current user is the buyer of this order
        if order.buyer != request.user:
            raise PermissionDenied("You don't have permission to view this order.")
        
        context = {
            'order': order,
        }
        return render(request, 'user/track_order.html', context)
    except Order.DoesNotExist:
        messages.error(request, "Order not found.")
        return redirect('profile')
    except PermissionDenied:
        messages.error(request, "You don't have permission to view this order.")
        return redirect('profile')


@login_required
def chatbot(request):
    if request.user.role != 'buyer':
        return JsonResponse({'error': 'Only buyers can use the chatbot'}, status=403)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            message = data.get('message', '').strip().lower()
            
            # Basic responses based on keywords
            if any(word in message for word in ['hello', 'hi', 'hey']):
                response = "Hello! I'm your furniture store assistant. How can I help you today?"
            elif 'order' in message or 'track' in message:
                # Get user's recent orders
                recent_orders = Order.objects.filter(buyer=request.user).order_by('-created_at')[:3]
                if recent_orders:
                    response = "Here are your recent orders:\n"
                    for order in recent_orders:
                        response += f"- Order #{order.id}: {order.status}, Total: ${order.total}\n"
                else:
                    response = "You don't have any recent orders. Would you like to browse our products?"
            elif 'product' in message or 'item' in message:
                # Search for products
                search_terms = message.replace('product', '').replace('item', '').strip()
                if search_terms:
                    products = Product.objects.filter(
                        Q(name__icontains=search_terms) |
                        Q(description__icontains=search_terms)
                    )[:3]
                    if products:
                        response = "I found these products:\n"
                        for product in products:
                            response += f"- {product.name}: ${product.price}\n"
                    else:
                        response = "I couldn't find any products matching your search. Try different keywords."
                else:
                    response = "What type of furniture are you looking for?"
            elif 'delivery' in message or 'shipping' in message:
                response = """Our standard delivery times are:
- Within city: 2-3 business days
- Outside city: 3-5 business days
- Remote areas: 5-7 business days"""
            elif 'return' in message or 'refund' in message:
                response = """Our return policy:
- 30-day return window
- Items must be in original condition
- Free returns for damaged items
- Refunds processed within 5-7 business days"""
            elif 'help' in message:
                response = """I can help you with:
1. Order tracking
2. Product information
3. Delivery times
4. Returns and refunds
What would you like to know?"""
            else:
                response = "I'm not sure I understand. Could you please rephrase your question? I can help with order tracking, product information, delivery times, and more."
            
            return JsonResponse({'response': response})
            
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    
    return render(request, 'chatbot.html')

@login_required
def order_detail(request, order_id):
    try:
        order = get_object_or_404(Order, id=order_id)
        
        # Check if user has permission to view this order
        if request.user.role == 'buyer' and order.buyer != request.user:
            messages.error(request, "You don't have permission to view this order.")
            return redirect('profile')
        
        # For sellers, check if any items in the order belong to them
        if request.user.role == 'seller':
            seller_items = order.items.filter(product__seller=request.user)
            if not seller_items.exists():
                messages.error(request, "You don't have permission to view this order.")
                return redirect('profile')
        
        context = {
            'order': order,
            'items': order.items.all(),
            'can_update_status': request.user.role == 'seller' and order.status in ['pending', 'processing']
        }
        return render(request, 'order_detail.html', context)
    except Order.DoesNotExist:
        messages.error(request, "Order not found.")
        return redirect('profile')

@login_required
def seller_orders(request):
    if request.user.role != 'seller':
        messages.error(request, "You don't have permission to access this page.")
        return redirect('home')
    
    # Get all orders for products belonging to the seller
    orders = Order.objects.filter(
        items__product__seller=request.user
    ).distinct().order_by('-created_at')
    
    context = {
        'orders': orders
    }
    return render(request, 'seller_orders.html', context)

@login_required
def update_order_status(request, order_id):
    if request.user.role != 'seller':
        messages.error(request, "You don't have permission to update order status.")
        return redirect('home')
    
    try:
        order = Order.objects.get(id=order_id)
        
        # Verify that the order contains items from this seller
        if not order.items.filter(product__seller=request.user).exists():
            messages.error(request, "You don't have permission to update this order.")
            return redirect('seller_orders')
        
        if request.method == 'POST':
            new_status = request.POST.get('status')
            
            # Validate status transition
            if new_status == 'processing' and order.status == 'pending':
                order.status = 'processing'
                order.save()
                messages.success(request, "Order status updated to Processing.")
            elif new_status == 'shipped' and order.status == 'processing':
                order.status = 'shipped'
                order.save()
                messages.success(request, "Order status updated to Shipped.")
            else:
                messages.error(request, "Invalid status transition.")
            
            return redirect('seller_orders')
        
        return redirect('order_detail', order_id=order_id)
    
    except Order.DoesNotExist:
        messages.error(request, "Order not found.")
        return redirect('seller_orders')
    
