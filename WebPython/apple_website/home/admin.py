# my_app/admin.py
import json
from django.db.models import Sum, Count, F
from django.db.models.functions import TruncMonth, TruncDay, TruncYear, Coalesce, TruncQuarter
from django.db import models
from .models import Order, OrderItem, ProductReview
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from .models import Category, Product, ProductVariant, Specification, News, Payment_VNPay, ContactMessage, \
    DiscountCampaign, UserCoupon
from django.urls import path
from django.shortcuts import render, redirect


# Inline cho phép bạn thêm biến thể ngay trong trang Product


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1  # Số dòng trống cho biến thể mới
    fields = ('storage', 'color', 'price',
              'discount_percent', 'stock_quantity', 'image')


# 1. Định nghĩa Inline cho Specification


class SpecificationInline(admin.TabularInline):
    model = Specification
    extra = 1  # Số lượng form trống mặc định
    fields = ('order', 'key', 'value')


# Tùy chỉnh hiển thị trong trang Admin (optional nhưng được khuyến khích)


class NewsAdmin(admin.ModelAdmin):
    # Các trường hiển thị trong danh sách tin tức
    list_display = ('title', 'published_date', 'source', 'is_store_info')
    # Các trường có thể tìm kiếm
    search_fields = ('title', 'summary', 'source')
    # Thêm bộ lọc theo ngày
    list_filter = ('published_date', 'is_store_info')


# Đăng ký model với tùy chỉnh
admin.site.register(News, NewsAdmin)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}  # Tự động điền slug


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    inlines = [SpecificationInline, ProductVariantInline]
    list_display = ('name', 'category', 'is_new', 'is_bestseller')
    list_filter = ('category', 'is_new', 'is_bestseller')
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}
    fieldsets = (
        ('Thông tin cơ bản', {
            'fields': ('name', 'category', 'slug', 'chip_type')
        }),
        ('Mô tả & Thông số', {
            'fields': ('description',),
        }),
        ('Tình trạng & Bảo hành', {
            'fields': ('is_new', 'is_bestseller', 'warranty_months', 'shipping_info')
        }),
    )


admin.site.register(Payment_VNPay)


# Cách hiển thị các sản phẩm nằm trong đơn hàng ngay tại trang chi tiết đơn hàng

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0  # Không hiện sẵn các dòng trống
    # Chỉ cho xem, tránh sửa làm sai lệch lịch sử
    readonly_fields = ('product_name', 'variant', 'quantity', 'price')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'user', 'total_price',
                    'status', 'created_at', 'payment_method')
    list_filter = ('status', 'created_at', 'payment_method')
    date_hierarchy = 'created_at'  # Tạo thanh chọn thời gian: Năm -> Tháng -> Ngày
    search_fields = ('order_id', 'user__username')
    ordering = ('-created_at',)
    inlines = [OrderItemInline]

    # Chỉ định file template chúng ta vừa tạo ở Bước 1
    change_list_template = 'admin/order_summary_change_list.html'

    def changelist_view(self, request, extra_context=None):
        # 1. Tạo bản sao có thể chỉnh sửa của GET parameters
        query_params = request.GET.copy()

        # Lấy giá trị từ bản sao để dùng cho thống kê
        view_type = query_params.get('view_type', 'month')
        year_filter = query_params.get('year_filter', 2025)
        start_date = query_params.get('start_date')
        end_date = query_params.get('end_date')

        # 2. Xóa các tham số tùy chỉnh khỏi bản sao
        # giúp Django Admin không cố lọc theo các field không có trong database
        custom_params = ['view_type', 'year_filter', 'start_date', 'end_date']
        for param in custom_params:
            if param in query_params:
                del query_params[param]

        # 3. Gán bản sao ĐÃ LÀM SẠCH ngược lại vào request.GET
        # giúp hàm super().changelist_view hoạt động mà không bị lỗi
        request.GET = query_params

        # Gọi logic mặc định của Admin
        response = super().changelist_view(request, extra_context=extra_context)

        try:
            qs = response.context_data['cl'].queryset
        except (AttributeError, KeyError):
            return response

        # 4. LOGIC THỐNG KÊ DOANH THU (Chỉ tính đơn hàng 'completed')
        flex_qs = qs.filter(status='completed')

        if view_type == 'day' and start_date and end_date:
            flex_qs = flex_qs.filter(created_at__date__range=[start_date, end_date])
            time_unit = TruncDay('created_at')
        elif view_type == 'quarter':
            flex_qs = flex_qs.filter(created_at__year=year_filter)
            time_unit = TruncQuarter('created_at')
        elif view_type == 'year':
            time_unit = TruncYear('created_at')
        else:  # month
            flex_qs = flex_qs.filter(created_at__year=year_filter)
            time_unit = TruncMonth('created_at')

        flex_results = flex_qs.annotate(period=time_unit).values('period').annotate(
            total=Sum('total_price')
        ).order_by('period')

        # Chuẩn bị dữ liệu cho Chart.js
        flex_labels = []
        flex_values = []
        for entry in flex_results:
            p = entry['period']
            if not p: continue
            if view_type == 'quarter':
                q = (p.month - 1) // 3 + 1
                flex_labels.append(f"Quý {q}/{p.year}")
            elif view_type == 'day':
                flex_labels.append(p.strftime("%d/%m/%Y"))
            elif view_type == 'year':
                flex_labels.append(p.strftime("%Y"))
            else:
                flex_labels.append(p.strftime("%m/%Y"))
            flex_values.append(float(entry['total'] or 0))

        # 5. CẬP NHẬT CONTEXT
        # Tính tổng doanh thu của kỳ vừa lọc để hiển thị (tùy chọn thêm)
        total_period_revenue = sum(flex_values)

        extra_context = extra_context or {}
        extra_context.update({
            'flex_labels': json.dumps(flex_labels),
            'flex_values': json.dumps(flex_values),
            'current_view_type': view_type,
            'total_period_revenue': total_period_revenue,
        })

        response.context_data.update(extra_context)
        return response

    def format_chart_data(self, time_series):
        # 1. Lấy danh sách các mốc thời gian duy nhất và sắp xếp chúng theo đúng thứ tự thời gian
        # Chúng ta lọc bỏ các giá trị None và sắp xếp trực tiếp trên đối tượng datetime/date
        unique_periods = sorted(
            list(set(item['period'] for item in time_series if item['period'])))

        # 2. Tạo labels hiển thị (chuỗi dd/mm/yyyy)
        labels = [p.strftime("%d/%m/%Y") for p in unique_periods]

        # 3. Lấy tất cả danh mục hiện có để tạo đường trên biểu đồ
        categories = list(Category.objects.values_list('name', flat=True))
        # Thêm danh mục dự phòng nếu có sản phẩm chưa phân loại
        all_cats = categories + ["Chưa phân loại"]

        datasets = {}
        for cat in all_cats:
            datasets[cat] = [0] * len(labels)

        # 4. Tạo bản đồ ánh xạ từ mốc thời gian sang vị trí Index trong mảng
        period_to_index = {p: i for i, p in enumerate(unique_periods)}

        # 5. Đổ dữ liệu vào datasets
        for item in time_series:
            cat_name = item['variant__product__category__name'] or "Chưa phân loại"
            period = item['period']

            if cat_name in datasets and period in period_to_index:
                index = period_to_index[period]
                datasets[cat_name][index] = float(item['revenue'])

        # Lọc bỏ các danh mục không có đồng doanh thu nào trong khoảng thời gian này để biểu đồ đỡ rối
        final_datasets = {k: v for k, v in datasets.items() if sum(v) > 0}

        return {'labels': labels, 'datasets': final_datasets}


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'email', 'is_read', 'created_at')
    list_filter = ('is_read', 'created_at')
    search_fields = ('full_name', 'email', 'message')

    # Chỉ định các trường Admin có thể sửa (để phản hồi)
    fields = ('full_name', 'email', 'phone',
              'message', 'admin_reply', 'is_read')

    # Các trường thông tin của khách nên để readonly để tránh Admin sửa nhầm nội dung khách gửi
    readonly_fields = ('full_name', 'email', 'phone', 'message', 'created_at')


@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    # Hiển thị các cột thông tin quan trọng
    list_display = ('product', 'user', 'rating', 'created_at')
    # Cho phép lọc theo số sao và thời gian
    list_filter = ('rating', 'created_at')
    # Tìm kiếm theo tên sản phẩm hoặc nội dung bình luận
    search_fields = ('product__name', 'comment', 'user__username')
    # Sắp xếp mới nhất lên đầu
    ordering = ('-created_at',)


@admin.register(DiscountCampaign)
class DiscountCampaignAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'discount_percent',
                    'start_date', 'end_date', 'is_active')
    list_filter = ('is_active', 'category')


User = get_user_model()


@admin.register(UserCoupon)
class UserCouponAdmin(admin.ModelAdmin):
    list_display = ('user', 'code', 'discount_amount', 'is_used', 'created_at')

    # Tạo thêm một nút "Tặng mã cho tất cả User" trên trang quản trị
    change_list_template = "admin/user_coupon_changelist.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('grant-all/', self.admin_site.admin_view(self.grant_to_all_view),
                 name='grant-to-all'),
        ]
        return custom_urls + urls

    def grant_to_all_view(self, request):
        if request.method == "POST":
            custom_code = request.POST.get('custom_code')
            amount = request.POST.get('amount')
            desc = request.POST.get(
                'description', 'Mã giảm giá tặng toàn bộ thành viên')

            if custom_code and amount:
                all_users = User.objects.all()
                coupons_to_create = []

                for user in all_users:
                    # Tránh tặng trùng mã cho cùng 1 người
                    if not UserCoupon.objects.filter(user=user, code=custom_code).exists():
                        coupons_to_create.append(
                            UserCoupon(
                                user=user,
                                code=custom_code,
                                discount_amount=amount,
                                description=desc,
                                is_used=False
                            )
                        )

                UserCoupon.objects.bulk_create(coupons_to_create)
                self.message_user(
                    request, f"Đã tặng mã {custom_code} cho {len(coupons_to_create)} người dùng!")
                return redirect("..")

        return render(request, "admin/grant_coupon_form.html", {'opts': self.model._meta})
