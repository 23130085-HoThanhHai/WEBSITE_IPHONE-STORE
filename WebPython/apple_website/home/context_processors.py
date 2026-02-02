from .models import Order, ContactMessage, UserCoupon


def notifications(request):
    if request.user.is_authenticated:
        # 1. Lấy 5 đơn hàng thành công gần nhất
        order_notifications = Order.objects.filter(
            user=request.user, status='completed').order_by('-created_at')[:5]

        # 2. Lấy các tin nhắn có phản hồi từ Admin
        admin_replies = ContactMessage.objects.filter(
            user=request.user, admin_reply__isnull=False).order_by('-created_at')[:5]

        # 3. Lấy các Coupon chưa sử dụng của người dùng (MỚI)
        user_coupons = UserCoupon.objects.filter(
            user=request.user, is_used=False).order_by('-created_at')

        # 4. Tính tổng số thông báo (hiện số đỏ)
        total_notif = order_notifications.count() + admin_replies.count() + \
            user_coupons.count()

        return {
            'order_notif': order_notifications,
            'admin_notif': admin_replies,
            'coupons': user_coupons,  # Trả về list coupon để hiển thị trong navbar
            'total_notif': total_notif
        }

    # Nếu chưa đăng nhập, trả về các giá trị mặc định để tránh lỗi template
    return {
        'order_notif': [],
        'admin_notif': [],
        'coupons': [],
        'total_notif': 0
    }


def coupon_notifications(request):
    if request.user.is_authenticated:
        # Lấy các coupon chưa dùng của user
        unread_coupons = UserCoupon.objects.filter(
            user=request.user, is_used=False).order_by('-created_at')
        return {
            'notifications': unread_coupons,
            'noti_count': unread_coupons.count()
        }
    return {}
