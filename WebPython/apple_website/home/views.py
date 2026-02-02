from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import login as auth_login, logout as auth_logout, authenticate
from django.contrib.auth.decorators import login_required
from .forms import CustomUserCreationForm
from .models import OrderItem, Product, Category, News, Cart, CartItem, ProductReview, ProductVariant, Payment_VNPay, Order, ContactMessage, DiscountCampaign, UserCoupon
from django.utils import timezone
from .recommender import get_recommendations_for_variant, clear_model_cache
from django.db.models import Avg, Count, Prefetch
from django.contrib import messages
from django.http import JsonResponse
import hashlib
import hmac
import json
import urllib
import urllib.parse
import urllib.request
import random
import requests
from datetime import datetime
from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import render, redirect
# from urllib.parse import quote_plus

from home.models import PaymentForm
from home.vnpay import vnpay
import qrcode
import base64
from io import BytesIO
# Create your views here.
# vinh
# from rest_framework.views import APIView
# from rest_framework.response import Response
# from .rag_chatbox import get_chatbot_response
# ---
from django.http import JsonResponse
from .rag_chatbox import chat_service
import json
from django.views.decorators.csrf import csrf_exempt
#sentiment
from django.http import JsonResponse
from .ml_model import predict_sentiment
from django.shortcuts import render
from .ml_models.sentiment import predict_sentiment
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from .models import Product, ProductReview

@csrf_exempt  # Để tạm thời đơn giản hóa việc gửi data từ JS
def chat_api(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            user_message = data.get("message", "")

            # Gọi hàm chat_service đã test thành công
            bot_response = chat_service(user_message)

            return JsonResponse({"status": "success", "response": bot_response})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=500)
    return JsonResponse({"status": "error", "message": "Invalid request"}, status=400)


# --- Trang chính ---
def index(request):
    now = timezone.now()

    # 1. Lấy chiến dịch khuyến mãi đang hoạt động (Mới nhất)
    active_campaign = DiscountCampaign.objects.filter(
        is_active=True,
        start_date__lte=now,
        end_date__gte=now
    ).select_related('category').first()

    # 2. Lấy 8 sản phẩm mới nhất (Giữ nguyên logic cũ của bạn)
    latest_products = Product.objects.prefetch_related(
        Prefetch('variants', queryset=ProductVariant.objects.all(),
                 to_attr='cached_variants')
    ).order_by('-id')[:8]

    # 3. Xử lý logic hiển thị và tính toán giá khuyến mãi hàng loạt
    for p in latest_products:
        p.first_variant = p.cached_variants[0] if p.cached_variants else None

        # Nếu có chiến dịch và sản phẩm thuộc danh mục đó
        if active_campaign and p.first_variant and p.category == active_campaign.category:
            # Gán thêm thuộc tính để hiển thị trên Template
            p.first_variant.campaign_discount = active_campaign.discount_percent
            # Tính toán giá cuối cùng sau khi giảm (nếu chưa có logic trong Model)
            discount_amount = (p.first_variant.price *
                               active_campaign.discount_percent) / 100
            p.first_variant.campaign_price = p.first_variant.price - discount_amount

    context = {
        'products': latest_products,
        'active_campaign': active_campaign,
    }
    return render(request, 'index.html', context)

# --- Logic giỏ hàng ---


# 1. Xem giỏ hàng
@login_required
def view_cart(request):
    cart, created = Cart.objects.get_or_create(user=request.user)
    # Build recommendations only for main product categories (iPhone, iPad, Macbook)
    # and filter suggested variants to accessories.
    main_categories = ('iphone', 'ipad', 'macbook')
    recommendations = {}

    # determine accessory category detection function
    def is_accessory_category(cat_name: str):
        if not cat_name:
            return False
        s = cat_name.lower()
        # common names used in project: 'phu kien', 'phụ kiện', 'accessory'
        return ('phu' in s and 'kien' in s) or 'phu kien' in s or 'phụ kiện' in s or 'accessory' in s

    for item in cart.items.all():
        prod = item.product
        cat_name = prod.category.name if prod and prod.category else ''
        # only compute recommendations for main device categories
        if cat_name and any(mc in cat_name.lower() for mc in main_categories):
            recs = get_recommendations_for_variant(item.variant.id, top_n=6)
            # filter recs to only accessories
            filtered = [v for v in recs if v.product and is_accessory_category(
                getattr(v.product.category, 'name', ''))]
            # limit to 3 shown suggestions
            recommendations[item.id] = filtered[:3]
        else:
            recommendations[item.id] = []

    # collect variant ids already present in cart to mark checkboxes
    accessory_variant_ids = [
        ci.variant.id for ci in cart.items.all() if ci.variant]

    return render(request, 'cart.html', {
        'cart': cart,
        'recommendations': recommendations,
        'accessory_variant_ids': accessory_variant_ids,
    })

# 2. Thêm sản phẩm (Dùng cho nút "Thêm vào giỏ" ở trang iPhone, iPad...)


@login_required
def add_to_cart(request):
    if request.method == "POST":
        product_id = request.POST.get('product_id')
        variant_id = request.POST.get('variant_id')
        quantity = int(request.POST.get('quantity', 1))

        variant = get_object_or_404(ProductVariant, id=variant_id)
        
        # Nếu không có product_id, lấy từ variant
        if not product_id:
            product = variant.product
        else:
            product = get_object_or_404(Product, id=product_id)
        
        cart, _ = Cart.objects.get_or_create(user=request.user)

        item, created = CartItem.objects.get_or_create(
            cart=cart, product=product, variant=variant)
        if not created:
            item.quantity += quantity
        else:
            item.quantity = quantity
        item.save()

        total_items = sum(i.quantity for i in cart.items.all())
        return JsonResponse({'status': 'success', 'total_items': total_items})

# 3. Cập nhật số lượng (Dùng cho nút + - trong giỏ hàng)


@login_required
def update_cart_item(request):
    if request.method == "POST":
        item_id = request.POST.get('item_id')
        action = request.POST.get('action')
        cart_item = get_object_or_404(
            CartItem, id=item_id, cart__user=request.user)

        if action == 'plus':
            cart_item.quantity += 1
        elif action == 'minus' and cart_item.quantity > 1:
            cart_item.quantity -= 1

        cart_item.save()
        # Ép kiểu về float hoặc int trước khi định dạng để đảm bảo không lỗi Decimal
        item_cost = float(cart_item.get_cost)
        cart_total = float(cart_item.cart.get_total_price)
        return JsonResponse({
            'status': 'success',
            'new_quantity': cart_item.quantity,
            'item_total': "{:,.0f} VNĐ".format(item_cost),
            'cart_total': "{:,.0f} VNĐ".format(cart_total)
        })

# 4. Xóa sản phẩm khỏi giỏ


@login_required
def remove_cart_item(request, item_id):
    if request.method == "POST":
        cart_item = get_object_or_404(
            CartItem, id=item_id, cart__user=request.user)
        cart = cart_item.cart
        cart_item.delete()

        # Trả về tổng tiền mới sau khi xóa để AJAX cập nhật
        return JsonResponse({
            'status': 'success',
            'cart_total': f"{cart.get_total_price:,.0f} VNĐ"
        })
    # Nếu là request GET thông thường (dành cho fallback)
    cart_item = get_object_or_404(
        CartItem, id=item_id, cart__user=request.user)
    cart_item.delete()
    return redirect('cart')


@login_required
def clear_cart(request):
    """Remove all items from the current user's cart (AJAX POST or redirect)."""
    if request.method == 'POST':
        cart, _ = Cart.objects.get_or_create(user=request.user)
        cart.items.all().delete()
        return JsonResponse({'status': 'success', 'cart_total': "0 VNĐ"})

    # fallback for GET
    cart, _ = Cart.objects.get_or_create(user=request.user)
    cart.items.all().delete()
    return redirect('cart')


@login_required
def toggle_accessory(request):
    """AJAX endpoint to add/remove an accessory variant when user checks/unchecks suggestion."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)

    variant_id = request.POST.get('variant_id')
    checked = request.POST.get('checked') in ['1', 'true', 'True']
    try:
        variant = ProductVariant.objects.get(id=variant_id)
    except ProductVariant.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Variant not found'}, status=404)

    cart, _ = Cart.objects.get_or_create(user=request.user)

    if checked:
        # Add accessory to cart (one unit)
        item, created = CartItem.objects.get_or_create(
            cart=cart, product=variant.product, variant=variant)
        if not created:
            item.quantity += 1
            item.save()
    else:
        # Remove accessory item completely if exists
        try:
            acc_item = CartItem.objects.get(cart=cart, variant=variant)
            acc_item.delete()
        except CartItem.DoesNotExist:
            pass

    return JsonResponse({'status': 'success', 'cart_total': f"{cart.get_total_price:,.0f} VNĐ"})


@login_required
def checkout(request):
    # 1. Kiểm tra tham số từ URL (Logic cũ giữ nguyên)
    show_history_only = request.GET.get('show_history') == '1'

    # 2. Lấy dữ liệu giỏ hàng
    cart, created = Cart.objects.get_or_create(user=request.user)

    # --- PHẦN MỚI: TÍNH TOÁN TIỀN ---
    try:
        base_amount = int(cart.get_total_price)

        # Lấy giảm giá từ mã Coupon cá nhân đã áp dụng
        coupon_discount = float(request.session.get('discount_amount', 0))

        # Tính giảm giá tự động (gọi hàm bổ trợ đã viết ở bước trước)
        auto_discount, auto_msg = calculate_auto_discount(base_amount)

        # Tính tổng thanh toán cuối cùng
        total_amount = max(0, base_amount - coupon_discount - auto_discount)
    except Exception:
        base_amount = 0
        coupon_discount = 0
        auto_discount = 0
        auto_msg = ""
        total_amount = 0
    # -------------------------------

    # 3. Logic lấy đơn hàng (Logic cũ giữ nguyên)
    orders_query = Order.objects.filter(
        user=request.user, status='completed').order_by('-created_at')

    if show_history_only:
        previous_orders = orders_query
    else:
        previous_orders = orders_query[:5]

    context = {
        'cart': cart,
        'previous_orders': previous_orders,
        'show_history_only': show_history_only,
        'order_id': datetime.now().strftime('%Y%m%d%H%M%S'),

        # Truyền thêm các biến tính toán vào context
        'base_amount': base_amount,
        'coupon_discount': coupon_discount,
        'auto_discount': auto_discount,
        'auto_msg': auto_msg,
        'total_amount': total_amount,
    }
    return render(request, 'checkout.html', context)

def new(request):
    # Lấy tất cả tin tức, đã được sắp xếp theo ngày trong models.py (mới nhất trước)
    all_news = News.objects.all()

    # Truyền dữ liệu tin tức vào context để template có thể sử dụng
    context = {
        'news_items': all_news,
    }

    # Render template
    return render(request, 'new.html', context)


def contact(request):
    if request.method == "POST":
        full_name = request.POST.get('full_name')
        email = request.POST.get('email')
        phone = request.POST.get('phone')
        message_content = request.POST.get('message')

        # Tạo bản ghi mới
        ContactMessage.objects.create(
            user=request.user if request.user.is_authenticated else None,
            full_name=full_name,
            email=email,
            phone=phone,
            message=message_content
        )

        messages.success(
            request, "Cảm ơn bạn! Tin nhắn đã được gửi tới chúng tôi.")
        return redirect('contact')  # Hoặc trang bạn muốn

    return render(request, 'contact.html')


def iphone(request):
    # Use case-insensitive lookup for category name to avoid casing issues from Admin
    query = request.GET.get('q', '').strip()
    iphone_category = Category.objects.filter(name__iexact='iPhone').first()
    if not iphone_category:
        products = Product.objects.none()
    else:
        products = Product.objects.filter(
            category=iphone_category).prefetch_related('variants')
        if query:
            products = products.filter(name__icontains=query)

    # 3. Truyền danh sách sản phẩm qua context để hiển thị trong template
    context = {
        'products': products
    }

    return render(request, 'iphone.html', {'products': products, 'search_query': query})


def ipad(request):
    # Use case-insensitive lookup for category name
    query = request.GET.get('q', '').strip()
    ipad_category = Category.objects.filter(name__iexact='iPad').first()
    if not ipad_category:
        products = Product.objects.none()
    else:
        products = Product.objects.filter(
            category=ipad_category).prefetch_related('variants')
        if query:
            products = products.filter(name__icontains=query)

    # 3. Truyền danh sách sản phẩm qua context
    context = {
        'products': products
    }

    return render(request, 'ipad.html', {'products': products, 'search_query': query})


def macbook(request):
    try:
        # 1. Tìm đối tượng Category có tên là 'Macbook' (case-insensitive)
        query = request.GET.get('q', '').strip()
        macbook_category = Category.objects.filter(
            name__iexact='Macbook').first()
        if not macbook_category:
            # No matching category found — return empty queryset
            products = Product.objects.none()
        else:
            # 2. Lấy TẤT CẢ sản phẩm (Product) thuộc danh mục đó
            # Dùng .prefetch_related('variants') để tối ưu truy vấn
            products = Product.objects.filter(
                category=macbook_category).prefetch_related('variants')
            if query:
                products = products.filter(name__icontains=query)

    except Category.DoesNotExist:
        # Xử lý trường hợp không tìm thấy danh mục 'Macbook'
        products = []

    # 3. Truyền danh sách sản phẩm qua context
    context = {
        'products': products
    }

    return render(request, 'macbook.html', {'products': products, 'search_query': query})


def phukien(request):
    # 1. Lấy từ khóa 'q' từ URL (ví dụ: /phu-kien/?q=sac+du+phong)
    query = request.GET.get('q', '').strip()

    # 2. Tìm danh mục Phụ kiện
    accessory_category = Category.objects.filter(
        name__iexact='phu kien').first()

    if not accessory_category:
        products = Product.objects.none()
    else:
        # Lấy tất cả sản phẩm thuộc danh mục Phụ kiện
        products = Product.objects.filter(
            category=accessory_category).prefetch_related('variants')

        # 3. NẾU CÓ TỪ KHÓA, lọc tiếp danh sách sản phẩm này
        if query:
            products = products.filter(name__icontains=query)

    context = {
        'products': products,
        'search_query': query,  # Gửi lại từ khóa để hiển thị thông báo nếu cần
    }
    return render(request, 'phu-kien.html', context)


def response(request):
    return render(request, 'response.html')

def calculate_auto_discount(amount):
    """
    Chính sách bậc thang:
    - Đơn từ 30tr: Giảm 500k
    - Đơn từ 20tr: Giảm 200k
    - Đơn từ 10tr: Giảm 100k
    - Đơn từ 5tr: Giảm 50k
    """
    if amount >= 30000000:
        return 500000, "Ưu đãi đơn hàng giá trị khủng (Giảm 500k)"
    elif amount >= 20000000:
        return 200000, "Ưu đãi đơn hàng lớn (Giảm 200k)"
    elif amount >= 10000000:
        return 100000, "Ưu đãi đơn hàng lớn (Giảm 100k)"
    elif amount >= 5000000:
        return 50000, "Ưu đãi mua sắm (Giảm 50k)"
    return 0, ""
def payment(request):
    try:
        cart = Cart.objects.get(user=request.user)
        base_amount = int(cart.get_total_price)

        # 1. Lấy giảm giá từ Coupon cá nhân (nếu đã áp dụng ở bước trước)
        coupon_discount = float(request.session.get('discount_amount', 0))

        # 2. Tính giảm giá tự động theo bậc thang
        auto_discount, auto_msg = calculate_auto_discount(base_amount)

        # 3. Tổng tiền thanh toán cuối cùng
        total_discount = coupon_discount + auto_discount
        total_amount = max(0, base_amount - total_discount)

        # Lưu lại vào session để hàm payment_vnpay sử dụng
        request.session['final_payment_amount'] = total_amount
        # Lưu thêm để hiển thị thông báo ở template
        request.session['auto_discount_msg'] = auto_msg

    except Exception as e:
        total_amount = 0
        coupon_discount = 0
        auto_discount = 0

    if request.method == 'POST':
        payment_method = request.POST.get('payment')
        if payment_method == 'vnpay':
            return payment_vnpay(request)
        elif payment_method == 'cod':
            complete_coupon_usage(request)
            return render(request, 'response.html', {'result': 'Đặt hàng thành công'})

    context = {
        'base_amount': base_amount,
        'total_amount': total_amount,
        'coupon_discount': coupon_discount,
        'auto_discount': auto_discount,
        'auto_msg': auto_msg,
        'order_id': datetime.now().strftime('%Y%m%d%H%M%S'),
    }
    return render(request, 'payment.html', context)


def hmacsha512(key, data):
    byteKey = key.encode('utf-8')
    byteData = data.encode('utf-8')
    return hmac.new(byteKey, byteData, hashlib.sha512).hexdigest()


def payment_vnpay(request):
    if request.method == 'POST':
        # Lấy số tiền ĐÃ GIẢM từ session mà hàm payment đã lưu
        amount = request.session.get('final_payment_amount')

        # Nếu session mất, thử lấy từ POST, nếu không có nữa thì báo lỗi
        if not amount:
            amount = request.POST.get('amount')

        if amount:
            order_id = datetime.now().strftime('%Y%m%d%H%M%S')
            order_type = 'billpayment'
            order_desc = f"Thanh toan don hang {order_id}"
            ipaddr = get_client_ip(request)

            vnp = vnpay()
            vnp.requestData['vnp_Version'] = '2.1.0'
            vnp.requestData['vnp_Command'] = 'pay'
            vnp.requestData['vnp_TmnCode'] = settings.VNPAY_TMN_CODE
            vnp.requestData['vnp_Amount'] = int(amount) * 100  # Chuyển sang xu
            vnp.requestData['vnp_CurrCode'] = 'VND'
            vnp.requestData['vnp_TxnRef'] = order_id
            vnp.requestData['vnp_OrderInfo'] = order_desc
            vnp.requestData['vnp_OrderType'] = order_type
            vnp.requestData['vnp_Locale'] = 'vn'
            vnp.requestData['vnp_CreateDate'] = datetime.now().strftime(
                '%Y%m%d%H%M%S')
            vnp.requestData['vnp_IpAddr'] = ipaddr
            vnp.requestData['vnp_ReturnUrl'] = settings.VNPAY_RETURN_URL

            vnpay_payment_url = vnp.get_payment_url(
                settings.VNPAY_PAYMENT_URL, settings.VNPAY_HASH_SECRET_KEY)

            # Tạo QR Code (Giữ nguyên logic của bạn)
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(vnpay_payment_url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            qr_base64 = base64.b64encode(buffer.getvalue()).decode()

            return render(request, "vnpay/confirm_payment.html", {
                "qr_code": qr_base64,
                "payment_url": vnpay_payment_url,
                "amount": "{:,.0f}".format(float(amount)).replace(",", "."),
                "order_id": order_id
            })

    return render(request, "vnpay/payment.html", {"errors": "Không tìm thấy số tiền thanh toán"})


def payment_ipn(request):
    inputData = request.GET
    if inputData:
        vnp = vnpay()
        vnp.responseData = inputData.dict()
        order_id = inputData['vnp_TxnRef']
        amount = inputData['vnp_Amount']
        order_desc = inputData['vnp_OrderInfo']
        vnp_TransactionNo = inputData['vnp_TransactionNo']
        vnp_ResponseCode = inputData['vnp_ResponseCode']
        vnp_TmnCode = inputData['vnp_TmnCode']
        vnp_PayDate = inputData['vnp_PayDate']
        vnp_BankCode = inputData['vnp_BankCode']
        vnp_CardType = inputData['vnp_CardType']
        if vnp.validate_response(settings.VNPAY_HASH_SECRET_KEY):
            # Check & Update Order Status in your Database
            # Your code here
            firstTimeUpdate = True
            totalamount = True
            if totalamount:
                if firstTimeUpdate:
                    if vnp_ResponseCode == '00':
                        print('Payment Success. Your code implement here')
                        applied_coupon = request.session.get(
                            'applied_coupon_code')
                        if applied_coupon:
                            UserCoupon.objects.filter(
                                user=request.user,
                                code=applied_coupon
                            ).update(is_used=True)

                            del request.session['applied_coupon_code']
                            if 'discount_amount' in request.session:
                                del request.session['discount_amount']
                            complete_coupon_usage(request)
                    else:
                        print('Payment Error. Your code implement here')

                    # Return VNPAY: Merchant update success
                    result = JsonResponse(
                        {'RspCode': '00', 'Message': 'Confirm Success'})
                else:
                    # Already Update
                    result = JsonResponse(
                        {'RspCode': '02', 'Message': 'Order Already Update'})
            else:
                # invalid amount
                result = JsonResponse(
                    {'RspCode': '04', 'Message': 'invalid amount'})
        else:
            # Invalid Signature
            result = JsonResponse(
                {'RspCode': '97', 'Message': 'Invalid Signature'})
    else:
        result = JsonResponse({'RspCode': '99', 'Message': 'Invalid request'})

    return result


def payment_return(request):
    # 1. Kiểm tra nếu user chưa đăng nhập thì không thể xử lý giỏ hàng
    if not request.user.is_authenticated:
        # Bạn có thể redirect về trang login hoặc thông báo lỗi
        return render(request, "vnpay/payment_return.html", {
            "title": "Lỗi xác thực",
            "result": "Lỗi",
            "msg": "Phiên đăng nhập đã hết hạn. Vui lòng liên hệ hỗ trợ nếu đã trừ tiền."
        })

    inputData = request.GET
    if inputData:
        vnp = vnpay()
        vnp.responseData = inputData.dict()
        order_id = inputData['vnp_TxnRef']
        amount = int(inputData['vnp_Amount']) / 100
        order_desc = inputData['vnp_OrderInfo']
        vnp_TransactionNo = inputData['vnp_TransactionNo']
        vnp_ResponseCode = inputData['vnp_ResponseCode']
        vnp_TmnCode = inputData['vnp_TmnCode']
        vnp_PayDate = inputData['vnp_PayDate']
        vnp_BankCode = inputData['vnp_BankCode']
        vnp_CardType = inputData['vnp_CardType']

        payment = Payment_VNPay.objects.create(
            order_id=order_id,
            amount=amount,
            order_desc=order_desc,
            vnp_TransactionNo=vnp_TransactionNo,
            vnp_ResponseCode=vnp_ResponseCode
        )

        if vnp.validate_response(settings.VNPAY_HASH_SECRET_KEY):
            if vnp_ResponseCode == "00":
                try:
                    # 1. Lấy giỏ hàng của user
                    cart = Cart.objects.get(user=request.user)
                    cart_items = cart.items.all()

                    if cart_items.exists():
                        # 2. TẠO ĐƠN HÀNG (Order)
                        new_order = Order.objects.create(
                            user=request.user,
                            order_id=order_id,  # Mã từ VNPAY vnp_TxnRef
                            total_price=amount,
                            status='completed',  # Đã thanh toán thành công
                            payment_method='vnpay'
                        )

                        # 3. TẠO CHI TIẾT ĐƠN HÀNG (OrderItem)
                        for item in cart_items:
                            OrderItem.objects.create(
                                order=new_order,
                                product_name=item.product.name,  # Lưu tên để check review sau này
                                variant=item.variant,
                                quantity=item.quantity,
                                price=item.variant.price  # Lưu giá tại thời điểm mua
                            )

                        applied_coupon_code = request.session.get(
                            'applied_coupon_code')
                        if applied_coupon_code:
                            # Đánh dấu coupon đã dùng trong DB
                            UserCoupon.objects.filter(
                                user=request.user,
                                code=applied_coupon_code
                            ).update(is_used=True)

                            # Dọn dẹp session
                            del request.session['applied_coupon_code']
                            if 'discount_amount' in request.session:
                                del request.session['discount_amount']
                            print(
                                f"Coupon {applied_coupon_code} đã được xử lý.")

                            complete_coupon_usage(request)
                        # 4. Invalidate recommender cache so new order affects suggestions
                        try:
                            clear_model_cache()
                        except Exception:
                            pass

                        # 5. Xóa giỏ hàng sau khi đã tạo Order thành công
                        cart_items.delete()
                        print(
                            f"Thành công: Đã tạo đơn hàng {order_id} và xóa giỏ hàng.")

                except Cart.DoesNotExist:
                    print("Lỗi: Không tìm thấy giỏ hàng để tạo đơn hàng.")
                except Exception as e:
                    print(f"Lỗi khi lưu đơn hàng: {e}")

                # Trả về kết quả thành công (Nằm ngoài khối try/except nhưng trong block ResponseCode == "00")
                return render(request, "vnpay/payment_return.html", {
                    "title": "Kết quả thanh toán",
                    "result": "Thành công",
                    "order_id": order_id,
                    "amount": amount,
                    "order_desc": order_desc,
                    "vnp_TransactionNo": vnp_TransactionNo,
                    "vnp_ResponseCode": vnp_ResponseCode
                })
            else:
                # Trường hợp ResponseCode khác "00" (Thanh toán thất bại)
                return render(request, "vnpay/payment_return.html", {
                    "title": "Kết quả thanh toán",
                    "result": "Lỗi",
                    "order_id": order_id,
                    "amount": amount,
                    "order_desc": order_desc,
                    "vnp_TransactionNo": vnp_TransactionNo,
                    "vnp_ResponseCode": vnp_ResponseCode
                })
        else:
            # Sai Checksum
            return render(request, "vnpay/payment_return.html", {
                "title": "Kết quả thanh toán",
                "result": "Lỗi",
                "order_id": order_id,
                "amount": amount,
                "order_desc": order_desc,
                "vnp_TransactionNo": vnp_TransactionNo,
                "vnp_ResponseCode": vnp_ResponseCode,
                "msg": "Sai checksum"
            })
    else:
        # Không có inputData
        return render(request, "vnpay/payment_return.html", {"title": "Kết quả thanh toán", "result": ""})


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


n = random.randint(10**11, 10**12 - 1)
n_str = str(n)
while len(n_str) < 12:
    n_str = '0' + n_str


def query(request):
    if request.method == 'GET':
        return render(request, "vnpay/query.html", {"title": "Kiểm tra kết quả giao dịch"})

    url = settings.VNPAY_API_URL
    secret_key = settings.VNPAY_HASH_SECRET_KEY
    vnp_TmnCode = settings.VNPAY_TMN_CODE
    vnp_Version = '2.1.0'

    vnp_RequestId = n_str
    vnp_Command = 'querydr'
    vnp_TxnRef = request.POST['order_id']
    vnp_OrderInfo = 'kiem tra gd'
    vnp_TransactionDate = request.POST['trans_date']
    vnp_CreateDate = datetime.now().strftime('%Y%m%d%H%M%S')
    vnp_IpAddr = get_client_ip(request)

    hash_data = "|".join([
        vnp_RequestId, vnp_Version, vnp_Command, vnp_TmnCode,
        vnp_TxnRef, vnp_TransactionDate, vnp_CreateDate,
        vnp_IpAddr, vnp_OrderInfo
    ])

    secure_hash = hmac.new(secret_key.encode(),
                           hash_data.encode(), hashlib.sha512).hexdigest()

    data = {
        "vnp_RequestId": vnp_RequestId,
        "vnp_TmnCode": vnp_TmnCode,
        "vnp_Command": vnp_Command,
        "vnp_TxnRef": vnp_TxnRef,
        "vnp_OrderInfo": vnp_OrderInfo,
        "vnp_TransactionDate": vnp_TransactionDate,
        "vnp_CreateDate": vnp_CreateDate,
        "vnp_IpAddr": vnp_IpAddr,
        "vnp_Version": vnp_Version,
        "vnp_SecureHash": secure_hash
    }

    headers = {"Content-Type": "application/json"}

    response = requests.post(url, headers=headers, data=json.dumps(data))

    if response.status_code == 200:
        response_json = json.loads(response.text)
    else:
        response_json = {
            "error": f"Request failed with status code: {response.status_code}"}

    return render(request, "vnpay/query.html", {"title": "Kiểm tra kết quả giao dịch", "response_json": response_json})


def refund(request):
    if request.method == 'GET':
        return render(request, "vnpay/refund.html", {"title": "Hoàn tiền giao dịch"})

    url = settings.VNPAY_API_URL
    secret_key = settings.VNPAY_HASH_SECRET_KEY
    vnp_TmnCode = settings.VNPAY_TMN_CODE
    vnp_RequestId = n_str
    vnp_Version = '2.1.0'
    vnp_Command = 'refund'
    vnp_TransactionType = request.POST['TransactionType']
    vnp_TxnRef = request.POST['order_id']
    vnp_Amount = request.POST['amount']
    vnp_OrderInfo = request.POST['order_desc']
    vnp_TransactionNo = '0'
    vnp_TransactionDate = request.POST['trans_date']
    vnp_CreateDate = datetime.now().strftime('%Y%m%d%H%M%S')
    vnp_CreateBy = 'user01'
    vnp_IpAddr = get_client_ip(request)

    hash_data = "|".join([
        vnp_RequestId, vnp_Version, vnp_Command, vnp_TmnCode, vnp_TransactionType, vnp_TxnRef,
        vnp_Amount, vnp_TransactionNo, vnp_TransactionDate, vnp_CreateBy, vnp_CreateDate,
        vnp_IpAddr, vnp_OrderInfo
    ])

    secure_hash = hmac.new(secret_key.encode(),
                           hash_data.encode(), hashlib.sha512).hexdigest()

    data = {
        "vnp_RequestId": vnp_RequestId,
        "vnp_TmnCode": vnp_TmnCode,
        "vnp_Command": vnp_Command,
        "vnp_TxnRef": vnp_TxnRef,
        "vnp_Amount": vnp_Amount,
        "vnp_OrderInfo": vnp_OrderInfo,
        "vnp_TransactionDate": vnp_TransactionDate,
        "vnp_CreateDate": vnp_CreateDate,
        "vnp_IpAddr": vnp_IpAddr,
        "vnp_TransactionType": vnp_TransactionType,
        "vnp_TransactionNo": vnp_TransactionNo,
        "vnp_CreateBy": vnp_CreateBy,
        "vnp_Version": vnp_Version,
        "vnp_SecureHash": secure_hash
    }

    headers = {"Content-Type": "application/json"}

    response = requests.post(url, headers=headers, data=json.dumps(data))

    if response.status_code == 200:
        response_json = json.loads(response.text)
    else:
        response_json = {
            "error": f"Request failed with status code: {response.status_code}"}

    return render(request, "vnpay/refund.html", {"title": "Kết quả hoàn tiền giao dịch", "response_json": response_json})


def product_detail(request, product_slug):
    product = get_object_or_404(
        Product.objects.prefetch_related(
            'variants', 'specifications', 'reviews__user'),
        slug=product_slug
    )

    # Lấy thông số đánh giá từ DB
    stats = product.reviews.aggregate(avg=Avg('rating'), count=Count('id'))
    avg_rating = stats['avg'] or 0
    total_reviews = stats['count']

    can_review = False
    if request.user.is_authenticated:
        # KIỂM TRA MUA HÀNG: Sử dụng items__product_id để tránh ValueError
        has_purchased = Order.objects.filter(
            user=request.user,
            status='completed',
            items__product_name=product.name
        ).exists()

        already_reviewed = ProductReview.objects.filter(
            user=request.user, product=product).exists()

        if has_purchased and not already_reviewed:
            can_review = True

    # --- Logic Variants (giữ nguyên của bạn) ---
    variants = product.variants.all().order_by('storage', 'price')
    unique_colors_variants = variants.values('color').distinct()
    unique_colors_list = []
    for item in unique_colors_variants:
        v = variants.filter(color=item['color']).first()
        if v:
            unique_colors_list.append(v)

    default_variant = variants.first()
    specs = product.specifications.all()

    # Lấy sản phẩm gợi ý cho variant mặc định
    recommended_variants = []
    if default_variant:
        recommended_variants = get_recommendations_for_variant(default_variant.id, top_n=4)

    context = {
        'product': product,
        'variants': variants,
        'unique_colors': unique_colors_list,
        'default_variant': default_variant,
        'specs': specs,
        'reviews': product.reviews.all().order_by('-created_at'),
        'avg_rating': avg_rating,
        'total_reviews': total_reviews,
        'can_review': can_review,
        'recommended_variants': recommended_variants,
    }
    return render(request, 'product-detail.html', context)

# --- 1. Logic ĐĂNG KÝ ---


def signup_view(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Sử dụng auth_login (đã đổi tên khi import) để tránh trùng
            auth_login(request, user)
            return redirect('index')
    else:
        form = CustomUserCreationForm()
    return render(request, 'signup.html', {'form': form})

# --- 2. Logic ĐĂNG NHẬP ---


def login_view(request):
    if request.method == 'POST':
        # 1. Khởi tạo form với dữ liệu POST
        form = AuthenticationForm(request, data=request.POST)

        # 2. Kiểm tra tính hợp lệ (Django sẽ tự xác thực user ở bước này)
        if form.is_valid():
            # 3. Lấy đối tượng user đã xác thực thành công từ form
            user = form.get_user()

            # 4. Gọi hàm login của Django (đã được đổi tên thành auth_login)
            # Phải truyền ĐỦ 2 tham số: request và user
            auth_login(request, user)

            return redirect('index')
    else:
        form = AuthenticationForm()

    return render(request, 'login.html', {'form': form})

# --- 3. Logic ĐĂNG XUẤT ---


def logout_view(request):
    auth_logout(request)  # Sử dụng auth_logout để xóa session
    return redirect('login')  # Hoặc redirect về 'index' tùy bạn


# --- Thanh tìm kiếm ---
# Logic 1: Điều hướng khi nhấn Enter
def search_view(request):
    query = request.GET.get('q', '').strip().lower()

    if not query:
        return redirect('index')

    # Điều hướng thông minh dựa trên từ khóa
    if 'iphone' in query:
        return redirect(f'/iphone/?q={query}')
    elif 'ipad' in query:
        return redirect(f'/ipad/?q={query}')
    elif 'macbook' in query:
        return redirect(f'/macbook/?q={query}')
    else:
        # Mọi từ khóa khác (sạc, ốp, hoặc abc...) đều về trang phụ kiện
        return redirect(f'/phu-kien/?q={query}')

# Logic 2: Gợi ý nhanh (Autocomplete) khi đang gõ


def search_suggestions(request):
    query = request.GET.get('q', '')
    if len(query) > 1:
        # Tìm 5 sản phẩm khớp tên nhất
        products = Product.objects.filter(name__icontains=query)[:5]
        data = [{'name': p.name, 'slug': p.slug} for p in products]
        return JsonResponse(data, safe=False)
    return JsonResponse([], safe=False)
# chatbox
# class ChatbotView(APIView):
#     def post(self, request):
#         query = request.data.get('query')  # JS bên dưới sẽ gửi key là 'query'
#         if not query:
#             return Response({"error": "Thiếu câu hỏi"}, status=400)
#
#         # Gọi hàm xử lý từ rag_engine.py
#         reply = get_chatbot_response(query)
#
#         return Response({"reply": reply})


def get_order_details(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    items = []
    for item in order.items.all():
        items.append({
            'name': item.product_name,
            'qty': item.quantity,
            'price': "{:,.0f}".format(float(item.price))
        })
    return JsonResponse({
        'order_id': order.order_id,
        'total': "{:,.0f}".format(float(order.total_price)),
        'items': items
    })


@login_required
def submit_review(request, product_slug):
    if request.method == "POST":
        product = get_object_or_404(Product, slug=product_slug)

        rating = int(request.POST.get("rating"))
        comment = request.POST.get("comment")
        sentiment = predict_sentiment(comment)

        ProductReview.objects.create(
            product=product,
            user=request.user,
            rating=rating,
            comment=comment,
            sentiment=sentiment
        )

    return redirect("product_detail", product_slug=product.slug)


# --- KHUYẾN MÃI COUPON --- #
def apply_coupon(request):
    if request.method == "POST":
        code = request.POST.get('code')
        user = request.user

        # 1. Kiểm tra đăng nhập
        if not user.is_authenticated:
            return JsonResponse({'status': 'error', 'message': 'Vui lòng đăng nhập để dùng mã.'})

        try:
            # 2. Lấy giỏ hàng TRƯỚC khi tính toán (Sửa lỗi NameError)
            try:
                cart = Cart.objects.get(user=user)
            except Cart.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': 'Giỏ hàng của bạn đang trống.'})

            # 3. Kiểm tra mã giảm giá
            coupon = UserCoupon.objects.get(
                user=user, code=code, is_used=False)

            # 4. Tính toán tiền
            total_price = cart.get_total_price  # Bỏ () nếu là @property, giữ () nếu là def
            discount_amount = float(coupon.discount_amount)

            new_total = float(total_price) - discount_amount
            if new_total < 0:
                new_total = 0

            # 5. QUAN TRỌNG: Lưu vào session để hàm payment() có thể đọc được
            request.session['applied_coupon_code'] = code
            request.session['discount_amount'] = discount_amount

            return JsonResponse({
                'status': 'success',
                'discount': discount_amount,
                'new_total': new_total,
                'message': f'Áp dụng mã thành công! Bạn được giảm {discount_amount:,.0f} VNĐ'
            })

        except UserCoupon.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': 'Mã giảm giá không hợp lệ hoặc đã sử dụng.'
            })
    return JsonResponse({'status': 'error', 'message': 'Yêu cầu không hợp lệ.'})




#sentiment
LABEL_MAP = {
    0: "negative",
    1: "neutral",
    2: "positive"
}

def sentiment_predict(request):
    text = request.GET.get("text", "").strip()

    if not text:
        return JsonResponse({"error": "Chưa nhập nội dung"})

    label_id = predict_sentiment(text)

    return JsonResponse({
        "text": text,
        "sentiment": LABEL_MAP.get(label_id, "Unknown")
    })


def sentiment_view(request):
    result = None
    text = ""

    if request.method == "POST":
        text = request.POST.get("comment")
        if text:
            result = predict_sentiment(text)

    return render(request, "sentiment.html", {
        "text": text,
        "result": result
    })




    return redirect("product_detail", product.id)
# --- KHUYẾN MÃI COUPON --- #
def apply_coupon(request):
    if request.method == "POST":
        code = request.POST.get('code')
        user = request.user

        # 1. Kiểm tra đăng nhập
        if not user.is_authenticated:
            return JsonResponse({'status': 'error', 'message': 'Vui lòng đăng nhập để dùng mã.'})

        try:
            # 2. Lấy giỏ hàng TRƯỚC khi tính toán (Sửa lỗi NameError)
            try:
                cart = Cart.objects.get(user=user)
            except Cart.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': 'Giỏ hàng của bạn đang trống.'})

            # 3. Kiểm tra mã giảm giá
            coupon = UserCoupon.objects.get(
                user=user, code=code, is_used=False)

            # 4. Tính toán tiền
            total_price = cart.get_total_price  # Bỏ () nếu là @property, giữ () nếu là def
            discount_amount = float(coupon.discount_amount)

            new_total = float(total_price) - discount_amount
            if new_total < 0:
                new_total = 0

            # 5. QUAN TRỌNG: Lưu vào session để hàm payment() có thể đọc được
            request.session['applied_coupon_code'] = code
            request.session['discount_amount'] = discount_amount

            return JsonResponse({
                'status': 'success',
                'discount': discount_amount,
                'new_total': new_total,
                'message': f'Áp dụng mã thành công! Bạn được giảm {discount_amount:,.0f} VNĐ'
            })

        except UserCoupon.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': 'Mã giảm giá không hợp lệ hoặc đã sử dụng.'
            })
    return JsonResponse({'status': 'error', 'message': 'Yêu cầu không hợp lệ.'})


def complete_coupon_usage(request):
    code = request.session.get('applied_coupon_code')
    user = request.user

    if code and user.is_authenticated:
        # Cập nhật duy nhất mã của user này thành Đã sử dụng
        updated_count = UserCoupon.objects.filter(
            user=user,
            code=code,
            is_used=False
        ).update(is_used=True)

        if updated_count > 0:
            print(f"DEBUG: Mã {code} của {user.username} đã được vô hiệu hóa.")

        # Xóa session ngay lập tức
        request.session.pop('applied_coupon_code', None)
        request.session.pop('discount_amount', None)
        request.session.pop('final_payment_amount', None)


