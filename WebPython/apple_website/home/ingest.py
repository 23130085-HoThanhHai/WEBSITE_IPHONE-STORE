import os
import pickle
import faiss
import numpy as np
from django.conf import settings
from sentence_transformers import SentenceTransformer
from .models import Product

EMBED_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
INDEX_PATH = os.path.join(settings.BASE_DIR, "rag_products.index")
PKL_PATH = os.path.join(settings.BASE_DIR, "rag_products.pkl")

def run_ingest():
    """Chuyển đổi toàn bộ Database sản phẩm thành Vector để tìm kiếm"""
    print("Đang bắt đầu quá trình hoc dữ liệu...")
    
    products = Product.objects.prefetch_related("variants", "specifications", "category").all()
    
    texts = []
    product_ids = []

    for p in products:
        variant_details = []
        for v in p.variants.all():
            variant_details.append(f"{v.storage} {v.color} giá {v.final_price:,.0f} VNĐ")
        variant_text = " | ".join(variant_details)
        specs = [f"{s.key}: {s.value}" for s in p.specifications.all()]
        spec_text = ". ".join(specs)
        content = (
            f"Tên: {p.name}. Danh mục: {p.category.name}. "
            f"Chip: {p.chip_type or 'Chưa cập nhật'}. "
            f"Phiên bản & Giá: {variant_text}. "
            f"Thông số kỹ thuật: {spec_text}. "
            f"Mô tả: {p.description}"
        )
        
        texts.append(content)
        product_ids.append(p.id)

    model = SentenceTransformer(EMBED_MODEL_NAME)
    embeddings = model.encode(texts)

    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(np.array(embeddings).astype("float32"))

    faiss.write_index(index, INDEX_PATH)
    with open(PKL_PATH, "wb") as f:
        pickle.dump(product_ids, f)
    
    print(f" Thành công: Đã nạp {len(product_ids)} sản phẩm vào bộ nhớ AI.")