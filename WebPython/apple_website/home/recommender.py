from collections import defaultdict
from functools import lru_cache
from home.models import Order, OrderItem, ProductVariant


def _gather_transactions():
    """Return list of sets of variant ids from completed orders."""
    transactions = []
    orders = Order.objects.filter(status='completed').prefetch_related('items')
    for o in orders:
        variant_ids = set()
        for it in o.items.all():
            if it.variant_id:
                variant_ids.add(int(it.variant_id))
        if variant_ids:
            transactions.append(variant_ids)
    return transactions


def _build_counts(transactions):
    single_count = defaultdict(int)
    pair_count = defaultdict(int)
    for txn in transactions:
        for i in txn:
            single_count[i] += 1
        # count unordered pairs
        items = list(txn)
        for a in range(len(items)):
            for b in range(a + 1, len(items)):
                pair = tuple(sorted((items[a], items[b])))
                pair_count[pair] += 1
    return single_count, pair_count


@lru_cache(maxsize=1)
def _build_model():
    transactions = _gather_transactions()
    singles, pairs = _build_counts(transactions)
    return singles, pairs


def clear_model_cache():
    """Clear the cached model so it's rebuilt on next call."""
    try:
        _build_model.cache_clear()
    except Exception:
        pass


def get_recommendations_for_variant(
    variant_id,
    top_n=3,
    min_support=3,
    min_confidence=0.3
):
    """
    Trả về danh sách tối đa top_n ProductVariant được gợi ý cho variant_id,
    dựa trên confidence P(j|i) = support(i, j) / support(i).

    - min_support: số đơn hàng tối thiểu chứa sản phẩm i
    - min_confidence: ngưỡng xác suất mua kèm tối thiểu
    - Chỉ gợi ý sản phẩm thuộc category 'phu kien'
    """

    # 1. Lấy dữ liệu thống kê đã được cache
    singles, pairs = _build_model()

    variant_id = int(variant_id)

    # 2. Lấy support của sản phẩm đang xem
    support_i = singles.get(variant_id, 0)

    # Nếu sản phẩm quá ít người mua → không đủ tin cậy để gợi ý
    if support_i < min_support:
        return []

    scores = []

    # 3. Tính confidence cho các sản phẩm mua kèm
    for (a, b), pair_count in pairs.items():
        if a == variant_id:
            confidence = pair_count / support_i
            if confidence >= min_confidence:
                scores.append((b, confidence, pair_count))

        elif b == variant_id:
            confidence = pair_count / support_i
            if confidence >= min_confidence:
                scores.append((a, confidence, pair_count))

    # 4. Sắp xếp theo confidence giảm dần, sau đó theo số lần mua chung
    scores.sort(key=lambda x: (x[1], x[2]), reverse=True)

    # 5. Lấy danh sách id sản phẩm theo thứ tự đã xếp hạng
    candidate_ids = [item[0] for item in scores]

    if not candidate_ids:
        return []

    # 6. Truy vấn DB và chỉ giữ lại sản phẩm thuộc category "phu kien"
    variants = list(
        ProductVariant.objects.filter(id__in=candidate_ids)
        .select_related('product__category')
        .filter(product__category__name__iexact='phu kien')
    )

    # 7. Giữ đúng thứ tự xếp hạng ban đầu
    id_to_variant = {v.id: v for v in variants}
    ordered_variants = [
        id_to_variant[vid] for vid in candidate_ids if vid in id_to_variant
    ]

    return ordered_variants[:top_n]

    """
    For a given variant id, return top_n recommended ProductVariant objects
    ordered by confidence P(j|i) = support(i,j) / support(i).
    Only returns products from category "phu kien" (accessories).
    """
    singles, pairs = _build_model()
    variant_id = int(variant_id)
    support_i = singles.get(variant_id, 0)
    if support_i < min_support:
        return []

    scores = []
    for (a, b), cnt in pairs.items():
        if a == variant_id:
            confidence = cnt / support_i
            scores.append((b, confidence, cnt))
        elif b == variant_id:
            confidence = cnt / support_i
            scores.append((a, confidence, cnt))

    # sort by confidence then by raw count
    scores.sort(key=lambda x: (x[1], x[2]), reverse=True)
    
    # Get all candidate variant IDs sorted by score
    candidate_ids = [s[0] for s in scores]

    # Fetch ProductVariant objects and filter only "phu kien" category
    variants = list(
        ProductVariant.objects.filter(id__in=candidate_ids)
        .select_related('product__category')
        .filter(product__category__name__iexact='phu kien')
    )
    
    # reorder according to original scores and limit to top_n
    id_to_var = {v.id: v for v in variants}
    ordered = [id_to_var[i] for i in candidate_ids if i in id_to_var]
    return ordered[:top_n]
