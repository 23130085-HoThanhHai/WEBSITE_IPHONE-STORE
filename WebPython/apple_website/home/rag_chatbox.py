import os
from google import genai
from .services import get_relevant_products


def chat_service(query: str) -> str:
    """Hàm chính xử lý tin nhắn của khách hàng bằng cách kết hợp RAG và Gemini"""
    try:
        relevant_products = get_relevant_products(query, k=3)

        if not relevant_products:
            return "Dạ hiện tại em chưa tìm thấy thông tin sản phẩm này tại Store IP Vinh. Anh/Chị có muốn em tư vấn dòng máy khác không ạ?"
        context_blocks = []
        for p in relevant_products:
            variants = p.variants.all()
            if variants:
                price_min = min(v.final_price for v in variants)
                price_str = f"Giá chỉ từ: {price_min:,.0f} VNĐ"
                list_versions = " | ".join(
                    [f"{v.storage}-{v.color}: {v.final_price:,.0f}đ" for v in variants])
            else:
                price_str = "Giá: Liên hệ"
                list_versions = "Đang cập nhật"
            specs = ", ".join(
                [f"{s.key}: {s.value}" for s in p.specifications.all()[:4]])

            block = (
                f"SẢN PHẨM: {p.name}\n"
                f"{price_str}\n"
                f"PHIÊN BẢN: {list_versions}\n"
                f"CẤU HÌNH: {specs}\n"
                f"MÔ TẢ: {p.description[:200]}"
            )
            context_blocks.append(block)

        context = "\n\n---\n\n".join(context_blocks)

        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

        system_instruction = (
            "Bạn là nhân viên tư vấn của 'STORE IP VINH'. "
            "Sử dụng dữ liệu sản phẩm cung cấp để trả lời. Không bịa đặt thông tin cấu hình hoặc giá. "
            "Phong cách: Lịch sự, chuyên nghiệp, hỗ trợ nhiệt tình. "
            "Cuối câu mời khách ghé cửa hàng tại TP Vinh."
        )

        full_prompt = f"{system_instruction}\n\nDANH SÁCH SẢN PHẨM:\n{context}\n\nCÂU HỎI: {query}"

        # response = client.models.generate_content(
        #     model="gemini-1.5-flash",
        #     contents=full_prompt,
        # )
        # response = client.models.generate_content(
        #     model="gemini-2.0-flash",
        #     contents=full_prompt,
        # )
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=full_prompt,
        )

        return response.text.strip()

    except Exception as e:
        print(f" Lỗi tại rag_chatbox: {e}")
        return "Dạ, hệ thống đang bận một chút, Anh/Chị vui lòng thử lại sau giây lát nhé!"
