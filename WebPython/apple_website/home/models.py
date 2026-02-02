from django.db import models
from django.utils import timezone
from django.conf import settings
from django.utils.text import slugify
from django import forms
from django.db.models import Avg


class PaymentForm(forms.Form):

    order_id = forms.CharField(max_length=250)
    order_type = forms.CharField(max_length=20)
    amount = forms.IntegerField()
    order_desc = forms.CharField(max_length=100)
    bank_code = forms.CharField(max_length=20, required=False)
    language = forms.CharField(max_length=2)
# --- 1. MODEL PHÂN LOẠI (Category) ---
# Dùng để nhóm các loại sản phẩm (ví dụ: iPhone, iPad, MacBook, Phụ kiện)


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True,
                            verbose_name="Tên danh mục")
    slug = models.SlugField(max_length=100, unique=True, blank=True)

    class Meta:
        verbose_name_plural = "Danh mục"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

# --- 2. MODEL SẢN PHẨM CHÍNH (Product) ---
# Lưu trữ thông tin chung của một dòng sản phẩm (ví dụ: iPhone 15 Pro Max)


class Product(models.Model):
    # Thông tin cơ bản
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name='products', verbose_name="Danh mục")
    name = models.CharField(max_length=255, verbose_name="Tên sản phẩm")
    slug = models.SlugField(max_length=255, unique=True, blank=True)

    # THÊM TRƯỜNG MỚI CHO MACBOOK: Chip xử lý
    chip_type = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Chip xử lý (ví dụ: M1, M2 Pro)"
    )

    # Mô tả và chi tiết
    description = models.TextField(blank=True, verbose_name="Mô tả")

    # Tình trạng và Khuyến mãi
    is_new = models.BooleanField(default=False, verbose_name="Sản phẩm mới")
    is_bestseller = models.BooleanField(
        default=False, verbose_name="Bán chạy nhất")

    # Thông tin giao hàng/bảo hành
    warranty_months = models.IntegerField(
        default=12, verbose_name="Bảo hành (tháng)")
    shipping_info = models.CharField(
        max_length=255, default="Miễn phí toàn quốc", verbose_name="Thông tin vận chuyển")

    class Meta:
        verbose_name_plural = "Sản phẩm"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    @property
    def average_rating(self):
        # Tính trung bình rating từ tất cả các reviews liên kết
        result = self.reviews.aggregate(avg=Avg('rating'))
        return result['avg'] if result['avg'] else 0

    @property
    def review_count(self):
        return self.reviews.count()

# --- 3. MODEL BIẾN THỂ SẢN PHẨM (ProductVariant) ---
# Lưu trữ thông tin riêng biệt cho từng biến thể (Dung lượng + Màu sắc + Giá + Tồn kho)


class ProductVariant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE,
                                related_name='variants', verbose_name="Sản phẩm gốc")

    # Các thuộc tính tạo nên biến thể (Dựa trên HTML của bạn)
    storage = models.CharField(
        max_length=50, verbose_name="Dung lượng (GB/TB)")
    color = models.CharField(max_length=50, verbose_name="Màu sắc")

    # Thông tin kho và giá
    price = models.DecimalField(
        max_digits=10, decimal_places=0, verbose_name="Giá bán (VNĐ)")
    stock_quantity = models.IntegerField(
        default=0, verbose_name="Số lượng tồn kho")
    discount_percent = models.IntegerField(
        default=0, verbose_name="Phần trăm giảm giá (%)")

    # Hình ảnh riêng biệt cho biến thể
    image = models.ImageField(
        upload_to='iphone_images/', blank=True, null=True, verbose_name="Ảnh biến thể")

    class Meta:
        # Đảm bảo không có 2 biến thể trùng lặp (cùng sản phẩm, cùng dung lượng, cùng màu)
        unique_together = ('product', 'storage', 'color')
        verbose_name_plural = "Biến thể sản phẩm"
        ordering = ['price']

    @property
    def final_price(self):
        """
        Tự động tính giá cuối cùng:
        Ưu tiên 1: Giảm giá hàng loạt theo Campaign (nếu có)
        Ưu tiên 2: Giảm giá riêng lẻ của sản phẩm (discount_percent cũ)
        """
        now = timezone.now()
        # Tìm chiến dịch đang chạy cho danh mục của sản phẩm này
        # Lưu ý: Import DiscountCampaign bên trong hàm để tránh lỗi vòng lặp import
        from .models import DiscountCampaign

        campaign = DiscountCampaign.objects.filter(
            category=self.product.category,
            is_active=True,
            start_date__lte=now,
            end_date__gte=now
        ).first()

        if campaign:
            # Nếu có chiến dịch hàng loạt, áp dụng % của chiến dịch
            return self.price * (100 - campaign.discount_percent) / 100

        if self.discount_percent > 0:
            # Nếu không có chiến dịch hàng loạt, dùng discount_percent riêng lẻ
            return self.price * (100 - self.discount_percent) / 100

        return self.price

    def __str__(self):
        return f"{self.product.name} - {self.storage} - {self.color}"

# --- 4.MODEL THÔNG SỐ KỸ THUẬT (Specification) ---


class Specification(models.Model):
    # Khóa ngoại: Liên kết đến Model Product.
    # Một Product có thể có nhiều Specifications.
    product = models.ForeignKey(
        'Product',
        # Đặt tên để truy vấn ngược: product.specifications.all()
        related_name='specifications',
        on_delete=models.CASCADE,
        verbose_name="Sản phẩm"
    )

    key = models.CharField(
        max_length=100, verbose_name="Thuộc tính (ví dụ: Màn hình, Chip xử lý)")
    value = models.CharField(
        max_length=255, verbose_name="Giá trị (ví dụ: OLED 6.5 inches, Apple A13 Bionic)")
    order = models.IntegerField(default=0, verbose_name="Thứ tự hiển thị")

    class Meta:
        verbose_name = "Thông số kỹ thuật"
        verbose_name_plural = "Thông số kỹ thuật"
        ordering = ['product', 'order']  # Sắp xếp theo sản phẩm và thứ tự

    def __str__(self):
        return f"{self.product.name} - {self.key}: {self.value}"


# --- 5. MODEL TIN TỨC (News) ---


class News(models.Model):
    # Tiêu đề tin tức (tương ứng với <h3>)
    title = models.CharField(max_length=200, verbose_name="Tiêu đề")

    # Tóm tắt/Nội dung ngắn gọn (tương ứng với <p> nội dung)
    summary = models.TextField(verbose_name="Tóm tắt nội dung")

    # Ngày đăng tin (tương ứng với 'Ngày:')
    # auto_now_add=True sẽ tự động điền ngày khi tin tức được tạo lần đầu
    published_date = models.DateTimeField(
        default=timezone.now, verbose_name="Ngày đăng")

    # Nguồn tin (tương ứng với 'Nguồn:')
    source = models.CharField(
        max_length=100, blank=True, null=True, verbose_name="Nguồn tin")

    # Hình ảnh (tương ứng với <img src=...>)
    image = models.ImageField(
        upload_to='news_images/', verbose_name="Hình ảnh")

    # Đường dẫn liên kết (tương ứng với <a href=...>)
    external_link = models.URLField(
        max_length=500, blank=True, null=True, verbose_name="Đường dẫn Đọc thêm")

    # Trường tùy chọn để đánh dấu tin tức đặc biệt (ví dụ: 'store-info')
    is_store_info = models.BooleanField(
        default=False, verbose_name="Là thông tin cửa hàng")

    class Meta:
        verbose_name = "Tin tức"
        verbose_name_plural = "Tin tức & Cập nhật"
        # Sắp xếp tin tức mới nhất lên đầu
        ordering = ['-published_date']

    def __str__(self):
        return self.title


# --- 6. MODEL GIỎ HÀNG (Cart) ---
class Cart(models.Model):
    # Liên kết 1-1: Mỗi User chỉ có duy nhất 1 giỏ hàng
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='cart'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Giỏ hàng của {self.user.username}"

    # Hàm tính tổng tiền của cả giỏ hàng
    @property
    def get_total_price(self):
        return sum(item.get_cost for item in self.items.all())


class CartItem(models.Model):
    # Một giỏ hàng có nhiều sản phẩm
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name='items'
    )
    product = models.ForeignKey('Product', on_delete=models.CASCADE)
    variant = models.ForeignKey('ProductVariant', on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    @property
    def get_cost(self):
        # Đảm bảo variant.final_price là một con số (Decimal hoặc Int)
        return self.variant.final_price * self.quantity

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"


class Payment_VNPay(models.Model):

    order_id = models.CharField(
        max_length=100, default="0", null=True, blank=True)
    amount = models.FloatField(default=0.0, null=True, blank=True)
    order_desc = models.CharField(null=True, blank=True, max_length=200)
    vnp_TransactionNo = models.CharField(null=True, blank=True, max_length=200)
    vnp_ResponseCode = models.CharField(null=True, blank=True, max_length=200)


# --- 7. MODEL ĐƠN HÀNG (Order) và ĐƠN HÀNG CHI TIẾT (OrderItem) ---


class Order(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Chờ thanh toán'),
        ('completed', 'Đã thanh toán'),
        ('failed', 'Thất bại'),
        ('shipped', 'Đang giao hàng'),
    )
    # Khóa ngoại liên kết với User để phân biệt đơn hàng của ai
    user = models.ForeignKey(settings.AUTH_USER_MODEL,
                             on_delete=models.CASCADE, related_name='orders')
    # Mã đơn hàng từ VNPAY (vnp_TxnRef)
    order_id = models.CharField(max_length=100, unique=True)
    total_price = models.DecimalField(max_digits=12, decimal_places=0)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    payment_method = models.CharField(max_length=20, default='vnpay')

    def __str__(self):
        return f"Order {self.order_id} - {self.user.username}"


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order, related_name='items', on_delete=models.CASCADE)
    # Lưu tên cứng để tránh product bị xóa sau này
    product_name = models.CharField(max_length=255)
    variant = models.ForeignKey(
        ProductVariant, on_delete=models.SET_NULL, null=True)
    quantity = models.IntegerField(default=1)
    price = models.DecimalField(
        max_digits=12, decimal_places=0)  # Giá tại thời điểm mua

    def get_cost(self):
        return self.price * self.quantity


# --- 8. MODEL GỬI TIN NHẮN ---

class ContactMessage(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL,
                             on_delete=models.SET_NULL, null=True, blank=True)
    full_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True, null=True)
    subject = models.CharField(
        max_length=200, blank=True, null=True)  # Tiêu đề nếu cần
    message = models.TextField()

    # Phần dành cho Admin phản hồi
    admin_reply = models.TextField(
        blank=True, null=True, verbose_name="Phản hồi từ Admin")
    is_read = models.BooleanField(default=False)  # Đã đọc hay chưa
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Tin nhắn từ {self.full_name} - {self.email}"

# --- 9. MODEL ĐÁNH GIÁ SẢN PHẨM (ProductReview) ---


# class ProductReview(models.Model):
#     product = models.ForeignKey(
#         Product, on_delete=models.CASCADE, related_name='reviews')
#     user = models.ForeignKey(settings.AUTH_USER_MODEL,
#                              on_delete=models.CASCADE)
#     rating = models.IntegerField(default=5, choices=[(
#         i, i) for i in range(1, 6)])  # Lựa chọn từ 1-5 sao
#     comment = models.TextField(verbose_name="Nội dung bình luận")
#     created_at = models.DateTimeField(auto_now_add=True)
#
#     def __str__(self):
#         return f"{self.user.username} đánh giá {self.product.name} - {self.rating} sao"
class ProductReview(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='reviews'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE
    )
    rating = models.IntegerField(
        default=5,
        choices=[(i, i) for i in range(1, 6)]
    )
    comment = models.TextField(verbose_name="Nội dung bình luận")
    sentiment = models.CharField(
        max_length=10,
        choices=[
            ("positive", "Positive"),
            ("neutral", "Neutral"),
            ("negative", "Negative"),
        ],
        default="neutral"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} đánh giá {self.product.name} - {self.rating} sao"



# --- 10.MODEL CHƯƠNG TRÌNHKHUYẾN MÃI GIẢM GIÁ ---
class DiscountCampaign(models.Model):
    name = models.CharField(max_length=255, verbose_name="Tên chương trình")
    category = models.ForeignKey(
        'Category', on_delete=models.CASCADE, verbose_name="Danh mục giảm giá")
    discount_percent = models.PositiveIntegerField(
        verbose_name="Phần trăm giảm (%)")
    start_date = models.DateTimeField(verbose_name="Ngày bắt đầu")
    end_date = models.DateTimeField(verbose_name="Ngày kết thúc")
    is_active = models.BooleanField(default=True, verbose_name="Kích hoạt")
    banner_image = models.ImageField(
        upload_to='campaign_banners/', blank=True, null=True, verbose_name="Banner khuyến mãi")

    def is_running(self):
        now = timezone.now()
        return self.is_active and self.start_date <= now <= self.end_date

    def __str__(self):
        return f"{self.name} - Giảm {self.discount_percent}%"


# --- 11.MODEL MÃI GIẢM GIÁ COUPON---
class UserCoupon(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL,
                             on_delete=models.CASCADE, related_name='my_coupons')
    code = models.CharField(max_length=20)
    discount_amount = models.DecimalField(
        max_digits=12, decimal_places=0, verbose_name="Số tiền giảm (VNĐ)")
    description = models.CharField(
        max_length=255, help_text="Nội dung thông báo cho người dùng")
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.code}"
