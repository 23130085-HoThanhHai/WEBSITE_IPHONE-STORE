from django.urls import path
from . import views
from django.urls import path
from .views import sentiment_predict, product_detail
from .views import sentiment_view
from .views import submit_review
# from .views import ChatbotView

urlpatterns = [
    path('', views.index, name='index'),
    path('home/', views.index, name='index'),
    path('checkout/', views.checkout, name='checkout'),
    path('new/', views.new, name='new'),
    path('contact/', views.contact, name='contact'),
    path('iphone/', views.iphone, name='iphone'),
    path('ipad/', views.ipad, name='ipad'),
    path('macbook/', views.macbook, name='macbook'),
    path('phu-kien/', views.phukien, name='phukien'),
    path('response/', views.response, name='response'),
    path('payment/', views.payment, name='payment'),
    path('product_detail/<slug:product_slug>/',
         views.product_detail, name='product_detail'),
    # URL cho Đăng ký
    path('signup/', views.signup_view, name='signup'),

    # URL cho Đăng nhập
    path('login/', views.login_view, name='login'),

    # URL cho Đăng xuất
    path('logout/', views.logout_view, name='logout'),

    # URL cho thanh tìm kiếm
    path('search/', views.search_view, name='search'),
    path('search-suggestions/', views.search_suggestions,
         name='search_suggestions'),
    # chatbox
    # path('api/chatbot/', ChatbotView.as_view(), name='chatbot_api'),
    # URL cho Giỏ hàng
    # 1. Trang hiển thị danh sách giỏ hàng
    path('cart/', views.view_cart, name='cart'),

    # 2. Xử lý khi nhấn nút "Thêm vào giỏ" ở trang iPhone, iPad...
    path('cart/add/', views.add_to_cart, name='add_to_cart'),

    # 3. Xử lý khi nhấn nút + hoặc - trong trang giỏ hàng (AJAX)
    path('cart/update/', views.update_cart_item, name='update_cart_item'),

    # 4. (Tùy chọn) Xử lý khi nhấn nút "Xóa" sản phẩm
    path('cart/remove/<int:item_id>/',
         views.remove_cart_item, name='remove_cart_item'),
    path('cart/clear/', views.clear_cart, name='clear_cart'),
    path('cart/toggle-accessory/', views.toggle_accessory, name='toggle_accessory'),

    # vnpay path
    path('payment/payment-vnpay', views.payment_vnpay,
         name='payment_vnpay_process'),
    path('payment_ipn', views.payment_ipn, name='payment_ipn'),
    path('payment_return', views.payment_return, name='payment_return'),

    path('product/review/<slug:product_slug>/',
         views.submit_review, name='submit_review'),
    path('get_order_details/<str:order_id>/',
         views.get_order_details, name='get_order_details'),
    path('api/chat/', views.chat_api, name='chat_api'),

    # 5. Xử lý khuyến mãi
    path('apply-coupon/', views.apply_coupon, name='apply_coupon'),
    # sentiment
    path("sentiment/", sentiment_predict),

    path("sentiment/", sentiment_view, name="sentiment"),


    path("product/<int:product_id>/", product_detail, name="product_detail"),
]
