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

_model = None
_index = None
_product_ids = None

def _load_resources():
    """Tải model và index vào RAM (chỉ tải một lần)"""
    global _model, _index, _product_ids
    if _model is None:
        _model = SentenceTransformer(EMBED_MODEL_NAME)
    if _index is None:
        if os.path.exists(INDEX_PATH):
            _index = faiss.read_index(INDEX_PATH)
            with open(PKL_PATH, "rb") as f:
                _product_ids = pickle.load(f)
        else:
            print(" Cảnh báo: File Index không tồn tại. Hãy chạy ingest trước!")

def get_relevant_products(query, k=3):
    """Tìm k sản phẩm liên quan nhất từ Database"""
    _load_resources()
    if _index is None: return []

    query_vector = _model.encode([query])
    distances, indices = _index.search(np.array(query_vector).astype("float32"), k)

    result_ids = [
        _product_ids[i] for i in indices[0] 
        if i != -1 and i < len(_product_ids)
    ]

    products = Product.objects.filter(id__in=result_ids).prefetch_related('variants', 'specifications')
    
    product_map = {p.id: p for p in products}
    return [product_map[pid] for pid in result_ids if pid in product_map]