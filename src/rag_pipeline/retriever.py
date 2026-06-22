"""
src/rag_pipeline/retriever.py
HybridRetriever: Neo4j (Specs + Cross-sell) + Qdrant (Semantic Reviews Pre-filtered).
RULE 00:
  - LIMIT 20 bắt buộc trong mọi Cypher — chống treo DB.
  - Logging đầy đủ tại mỗi bước (input, cypher, output, latency).
  - Try-catch bao quanh mọi I/O.
  - Type hinting đầy đủ.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional, Any
from loguru import logger

from neo4j import GraphDatabase, Driver
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchAny
from sentence_transformers import SentenceTransformer, CrossEncoder

from src.config.settings import get_settings
from src.rag_pipeline.extractor import UserIntent


# =============================================================================
# OS Mapping Table — Canonical os_type (từ LLM) → Giá trị thực tế trong Neo4j DB
# =============================================================================
# DB hiện tại chỉ có 3 giá trị: 'ios', 'android/window', 'unknown'
# Không cần reset DB — xử lý mapping ở tầng Retriever.
_OS_TO_DB_VALUES: dict[str, list[str]] = {
    "ios":     ["ios"],
    "macos":   ["ios"],           # MacBook/Apple cũng được lưu dưới 'ios' trong DB
    "android": ["android/window"],
    "windows": ["android/window"],
    "linux":   ["android/window", "unknown"],
}


# =============================================================================
# 1. Data Contract — RetrievedProduct
# =============================================================================

@dataclass
class RetrievedProduct:
    """Cấu trúc dữ liệu chuẩn (Data Contract) cho mỗi sản phẩm được retrieve."""
    product_id: str
    category: str
    brand: str
    os_type: str
    specs: dict[str, Any] = field(default_factory=dict)
    review_highlights: Optional[str] = None
    semantic_score: float = 0.0
    popularity: int = 1
    overall_rating: float = 0.0
    final_score: float = 0.0
    is_cross_sell: bool = False


@dataclass
class RetrievalResult:
    """Object chứa kết quả retrieval và metadata phục vụ Thinking Process UI."""
    products: list[RetrievedProduct]
    metadata: dict[str, Any] = field(default_factory=dict)


# =============================================================================
# 2. HybridRetriever Class
# =============================================================================

class HybridRetriever:
    """Thực hiện Hybrid Retrieval: Neo4j (cứng) + Qdrant (mềm/semantic).

    Luồng:
        1. _query_neo4j() → lấy candidates theo structured_filters + cross-sell.
        2. _query_qdrant() → semantic search trong Qdrant, pre-filter bằng IDs từ Neo4j.
        3. retrieve() → kết hợp, tính final_score, trả về list[RetrievedProduct].
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._neo4j_driver: Driver = self._init_neo4j()
        self._qdrant: QdrantClient = self._init_qdrant()
        self._embed_model: SentenceTransformer = self._init_embed()
        self._reranker_model: CrossEncoder = self._init_reranker()

    # ------------------------------------------------------------------
    # Init helpers
    # ------------------------------------------------------------------

    def _init_neo4j(self) -> Driver:
        s = self._settings
        logger.info("Kết nối Neo4j: {}", s.neo4j_uri)
        try:
            driver = GraphDatabase.driver(
                s.neo4j_uri, auth=(s.neo4j_username, s.neo4j_password)
            )
            driver.verify_connectivity()
            logger.success("Neo4j kết nối thành công.")
            return driver
        except Exception as e:
            logger.error("Không thể kết nối Neo4j: {}", e)
            raise

    def _init_qdrant(self) -> QdrantClient:
        s = self._settings
        logger.info("Kết nối Qdrant: {}:{}", s.qdrant_host, s.qdrant_port)
        try:
            # check_compatibility=False: bỏ qua cảnh báo version mismatch
            # (client 1.17.x vs server 1.9.x — API vẫn tương thích)
            client = QdrantClient(
                host=s.qdrant_host,
                port=s.qdrant_port,
                check_compatibility=False,
            )
            logger.success("Qdrant kết nối thành công.")
            return client
        except Exception as e:
            logger.error("Không thể kết nối Qdrant: {}", e)
            raise

    def _init_embed(self) -> SentenceTransformer:
        model_name = self._settings.resolved_embedding_model
        logger.info("Tải Embedding model: {}", model_name)
        return SentenceTransformer(model_name)

    def _init_reranker(self) -> Optional[CrossEncoder]:
        logger.info("Tải Reranker model: BAAI/bge-reranker-base")
        try:
            return CrossEncoder("BAAI/bge-reranker-base")
        except Exception as e:
            logger.warning("Không thể tải Reranker model BAAI/bge-reranker-base (bỏ qua Reranking): {}", e)
            return None


    # ------------------------------------------------------------------
    # 2.1 — Neo4j Query (Specs + Cross-sell)
    # ------------------------------------------------------------------

    def _query_neo4j(self, intent: UserIntent) -> tuple[list[RetrievedProduct], dict[str, Any]]:
        """Truy vấn Neo4j tìm sản phẩm khớp cứng (Specs). Trả về (products, metadata)."""
        results: list[RetrievedProduct] = []
        metadata: dict[str, Any] = {"queries": []}
        limit = self._settings.neo4j_query_limit

        # --- Build điều kiện WHERE động ---
        conditions: list[str] = []
        params: dict[str, Any] = {"limit": limit}

        if intent.brand:
            conditions.append("toLower(b.name) = $brand")
            params["brand"] = intent.brand.lower()

        if intent.os_type:
            db_values = self._resolve_os_values(intent.os_type)
            conditions.append("os.name IN $os_values")
            params["os_values"] = db_values
            logger.debug("OS mapping: '{}' → DB values {}", intent.os_type, db_values)

        if intent.max_price:
            conditions.append("toFloat(p.price) <= $max_price")
            params["max_price"] = float(intent.max_price)

        if intent.min_price:
            conditions.append("toFloat(p.price) >= $min_price")
            params["min_price"] = float(intent.min_price)

        if intent.category:
            conditions.append("c.name IN $categories")
            params["categories"] = self._resolve_categories(intent.category)

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        # --- Query chính ---
        main_cypher = f"""
MATCH (p:Product)-[:BELONGS_TO]->(b:Brand),
      (p)-[:IS_CATEGORY]->(c:Category)
OPTIONAL MATCH (p)-[:RUNS_ON]->(os:OS)
WITH p, b, c, os
{where_clause}
RETURN
    p.id                     AS product_id,
    c.name                   AS category,
    b.name                   AS brand,
    coalesce(os.name, 'N/A') AS os_type,
    properties(p)            AS specs
LIMIT $limit
"""
        metadata["queries"].append({
            "type": "main_neo4j",
            "cypher": main_cypher.strip(),
            "params": params
        })
        logger.debug("=== Cypher chính ===\n{}", main_cypher.strip())
        logger.debug("Params: {}", params)

        try:
            start = time.perf_counter()
            with self._neo4j_driver.session() as session:
                records = session.run(main_cypher, **params).data()

            latency_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "Neo4j main query: {} kết quả | {:.1f}ms",
                len(records),
                latency_ms,
            )

            metadata["main_count"] = len(records)
            for r in records:
                specs = r.get("specs", {})
                results.append(
                    RetrievedProduct(
                        product_id=r["product_id"],
                        category=r["category"],
                        brand=r["brand"],
                        os_type=r["os_type"],
                        specs=specs,
                        popularity=self._safe_int(specs.get("popularity"), 1),
                        overall_rating=self._safe_float(specs.get("overall_rating"), 0.0),
                        is_cross_sell=False,
                    )
                )
        except Exception as e:
            logger.error("Lỗi Neo4j main query: {}", e)

        # Step 1.2: Cross-sell
        if intent.trigger_cross_sell and results:
            cross_results, cross_meta = self._query_neo4j_crosssell(results[0], intent)
            results.extend(cross_results)
            metadata["queries"].extend(cross_meta.get("queries", []))
            metadata["cross_sell_count"] = len(cross_results)

        return results, metadata

    def _query_neo4j_crosssell(
        self, main_product: RetrievedProduct, intent: UserIntent
    ) -> tuple[list[RetrievedProduct], dict[str, Any]]:
        """Tìm sản phẩm gợi ý dựa trên hệ sinh thái (Ecosystem)."""
        cross_results: list[RetrievedProduct] = []
        metadata: dict[str, Any] = {"queries": []}
        
        target_brand = main_product.brand
        target_os = main_product.os_type
        
        # Xác định category cần gợi ý
        current_cat = main_product.category.lower().strip()
        if "headphone" in current_cat:
            normalized_current = "headphone"
        elif "phone" in current_cat:
            normalized_current = "phone"
        elif "laptop" in current_cat:
            normalized_current = "laptop"
        else:
            normalized_current = current_cat

        cross_categories = ["phone", "laptop", "headphone"]
        if normalized_current in cross_categories:
            cross_categories.remove(normalized_current)

        db_cross_categories = self._resolve_categories(cross_categories)

        cross_params: dict[str, Any] = {
            "limit": 5, # Gợi ý ít hơn main
            "cross_categories": db_cross_categories,
        }
        
        cross_conditions = []
        if target_brand:
            cross_conditions.append("toLower(b.name) = $target_brand")
            cross_params["target_brand"] = target_brand.lower()

        if target_os:
            db_values = self._resolve_os_values(target_os)
            cross_conditions.append("os.name IN $target_os_values")
            cross_params["target_os_values"] = db_values

        brand_os_clause = "(" + " OR ".join(cross_conditions) + ")" if cross_conditions else ""
        where_clause = f"WHERE c.name IN $cross_categories AND {brand_os_clause}" if brand_os_clause else "WHERE c.name IN $cross_categories"

        cross_cypher = f"""
MATCH (p:Product)-[:BELONGS_TO]->(b:Brand),
      (p)-[:IS_CATEGORY]->(c:Category)
OPTIONAL MATCH (p)-[:RUNS_ON]->(os:OS)
WITH p, b, c, os
{where_clause}
RETURN
    p.id                     AS product_id,
    c.name                   AS category,
    b.name                   AS brand,
    coalesce(os.name, 'N/A') AS os_type,
    properties(p)            AS specs
LIMIT $limit
"""
        metadata["queries"].append({
            "type": "cross_sell_neo4j",
            "cypher": cross_cypher.strip(),
            "params": cross_params
        })
        logger.debug("=== Cypher Cross-sell (categories={}) ===\n{}", cross_categories, cross_cypher.strip())

        try:
            start = time.perf_counter()
            with self._neo4j_driver.session() as session:
                records = session.run(cross_cypher, **cross_params).data()

            latency_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "Neo4j cross-sell query: {} kết quả | {:.1f}ms",
                len(records),
                latency_ms,
            )

            for r in records:
                specs = r.get("specs", {})
                cross_results.append(
                    RetrievedProduct(
                        product_id=r["product_id"],
                        category=r["category"],
                        brand=r["brand"],
                        os_type=r["os_type"],
                        specs=specs,
                        popularity=self._safe_int(specs.get("popularity"), 1),
                        overall_rating=self._safe_float(specs.get("overall_rating"), 0.0),
                        is_cross_sell=True,
                    )
                )
        except Exception as e:
            logger.error("Lỗi Neo4j cross-sell query: {}", e)

        return cross_results, metadata

    # ------------------------------------------------------------------
    # 2.2 — Qdrant Query (Semantic Search + Pre-filter)
    # ------------------------------------------------------------------

    def _query_qdrant(
        self, intent: UserIntent, candidate_products: list[RetrievedProduct]
    ) -> tuple[dict[str, str], dict[str, Any]]:
        """Truy vấn ngữ nghĩa từ Qdrant cho các sản phẩm đã tìm thấy bởi Neo4j."""
        review_map: dict[str, str] = {}
        metadata: dict[str, Any] = {"hit_count": 0} # Khởi tạo metadata trống ở đây

        if not intent.semantic_intent:
            logger.info("Không có semantic_intent → Bỏ qua Qdrant.")
            return review_map, metadata # SỬA: Trả về đúng tuple 2 phần tử

        # Chỉ lấy Phone/Laptop (Headphone không có reviews)
        eligible_ids = [
            p.product_id
            for p in candidate_products
            if p.category.lower() != "headphone"
        ]

        if not eligible_ids:
            logger.info("Không có sản phẩm eligible (Phone/Laptop) → Bỏ qua Qdrant.")
            return review_map,  metadata

        logger.info(
            "Qdrant semantic search: query='{}' | pre-filter {} sản phẩm",
            intent.semantic_intent,
            len(eligible_ids),
        )

        try:
            start = time.perf_counter()
            query_vector = self._embed_model.encode(intent.semantic_intent).tolist()

            # Pre-filter: chỉ search trong reviews của candidate product_ids
            qdrant_filter = Filter(
                must=[
                    FieldCondition(
                        key="product_id",
                        match=MatchAny(any=eligible_ids),
                    )
                ]
            )

            # qdrant-client 1.17+ xóa search() khỏi public API, và query_points() không tương thích với Qdrant server 1.9.4.
            # Dùng REST wrapper search_points trực tiếp thông qua http client tương thích server 1.9+.
            from qdrant_client.http.models import SearchRequest
            req = SearchRequest(
                vector=query_vector,
                filter=qdrant_filter,
                limit=self._settings.top_k_retrieval,
                with_payload=True
            )
            response = self._qdrant.http.search_api.search_points(
                collection_name=self._settings.qdrant_collection,
                search_request=req
            )
            hits = response.result

            metadata["hit_count"] = len(hits)
            latency_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "Qdrant trả về {} hits | {:.1f}ms", len(hits), latency_ms
            )

            # Gom kết quả: mỗi product_id giữ review có score cao nhất
            for hit in hits:
                pid = hit.payload.get("product_id", "")
                review_text = hit.payload.get("review_text", "")
                score = hit.score

                if pid and review_text:
                    # Cập nhật score vào candidate + lưu review highlight
                    for product in candidate_products:
                        if product.product_id == pid and score > product.semantic_score:
                            product.semantic_score = score

                    if pid not in review_map:
                        review_map[pid] = review_text

                    logger.debug("  Hit: pid={} | score={:.4f}", pid, score)

        except Exception as e:
            logger.error("Lỗi Qdrant query_points: {}", e)

        return review_map, metadata

    # ------------------------------------------------------------------
    # 2.3 — retrieve() — Public API
    # ------------------------------------------------------------------

    def retrieve(self, intent: UserIntent) -> RetrievalResult:
        """Entry point công khai. Kết hợp Neo4j + Qdrant và trả về RetrievalResult.

        Args:
            intent: UserIntent đã được bóc tách bởi IntentExtractor.

        Returns:
            RetrievalResult containing products and metadata.
        """
        logger.info("=== HybridRetriever.retrieve() ===")
        overall_start = time.perf_counter()
        
        # Step 1: Neo4j
        candidates, neo4j_metadata = self._query_neo4j(intent)
        if not candidates:
            logger.warning("Neo4j không trả về kết quả nào.")
            return RetrievalResult(products=[], metadata=neo4j_metadata)

        # Step 2: Qdrant
        review_map, qdrant_metadata = self._query_qdrant(intent, candidates)

        # Step 2.5: AI Reranker (nếu có semantic_intent)
        if intent.semantic_intent and candidates and self._reranker_model is not None:
            logger.info("Thực hiện Reranking bằng CrossEncoder BAAI/bge-reranker-base...")
            pairs = []
            for product in candidates:
                specs_str = ", ".join(f"{k}: {v}" for k, v in product.specs.items() if k not in ["price", "id"])
                doc_text = f"Thương hiệu: {product.brand}. Danh mục: {product.category}. Thông số: {specs_str}"
                pairs.append((intent.semantic_intent, doc_text))
            
            try:
                start_rerank = time.perf_counter()
                scores = self._reranker_model.predict(pairs)
                rerank_latency = (time.perf_counter() - start_rerank) * 1000
                logger.info("Reranker hoàn tất sau {:.1f}ms", rerank_latency)
                
                for idx, product in enumerate(candidates):
                    product.semantic_score = float(scores[idx])
                    logger.debug("  Reranked {}: score={:.4f}", product.product_id, product.semantic_score)
            except Exception as e:
                logger.error("Lỗi Reranker: {}", e)

        # Step 3: Gắn review và tính final_score
        for product in candidates:
            if product.product_id in review_map:
                product.review_highlights = review_map[product.product_id]

            popularity_norm = (product.popularity - 1) / 2.0
            rating_norm = product.overall_rating / 5.0
            product.final_score = (
                product.semantic_score * 0.7
                + popularity_norm * 0.2
                + rating_norm * 0.1
            )

        ranked = sorted(
            candidates,
            key=lambda p: (p.is_cross_sell, -p.final_score),
        )

        total_ms = (time.perf_counter() - overall_start) * 1000
        
        # Compile final metadata
        final_metadata = {
            **neo4j_metadata,
            "qdrant": qdrant_metadata,
            "total_latency_ms": total_ms
        }
        
        logger.success(
            "Retrieve hoàn tất: {} sản phẩm | {:.1f}ms",
            len(ranked), total_ms
        )

        return RetrievalResult(products=ranked, metadata=final_metadata)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_os_values(os_type: str) -> list[str]:
        """Chuyển canonical os_type (từ LLM) → list giá trị thực tế trong Neo4j.

        DB hiện tại gộp non-Apple vào 'android/window', Apple vào 'ios'.
        Hàm này giúp Retriever tự động xử lý mà không cần reset DB.
        """
        return _OS_TO_DB_VALUES.get(os_type.lower(), [os_type.lower()])

    @staticmethod
    def _resolve_categories(categories: list[str]) -> list[str]:
        """Chuyển canonical category (từ LLM) → list giá trị thực tế trong Neo4j (bao gồm cả Headphones/headphone)."""
        resolved = []
        for cat in categories:
            cat_lower = cat.lower().strip()
            if "headphone" in cat_lower:
                resolved.extend(["headphone", "headphones", "Headphones"])
            elif "phone" in cat_lower:
                resolved.extend(["phone", "phones", "Phones"])
            elif "laptop" in cat_lower:
                resolved.extend(["laptop", "laptops", "Laptops"])
            else:
                resolved.append(cat)
        return list(set(resolved))

    @staticmethod
    def _safe_int(val: Any, default: int = 0) -> int:
        try:
            return int(float(str(val)))
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _safe_float(val: Any, default: float = 0.0) -> float:
        try:
            return float(str(val))
        except (ValueError, TypeError):
            return default

    def close(self) -> None:
        """Đóng kết nối Neo4j khi không cần dùng nữa."""
        if self._neo4j_driver:
            self._neo4j_driver.close()
            logger.info("Đã đóng kết nối Neo4j.")


# =============================================================================
# Quick Test — chạy: python -m src.rag_pipeline.retriever
# =============================================================================

if __name__ == "__main__":
    import sys
    import json

    # Fix Windows terminal encoding (cp1252 → utf-8)
    sys.stdout.reconfigure(encoding="utf-8")

    logger.remove()
    logger.add(sys.stderr, level="DEBUG", colorize=True)

    retriever = HybridRetriever()

    # --- Test case 1: Phone Apple + cross-sell + semantic ---
    test_intent_1 = UserIntent(
        brand="Apple",
        category=["phone"],
        os_type="ios",
        max_price=30_000_000,
        semantic_intent="chụp ảnh đẹp",
        trigger_cross_sell=True,
        ecosystem_context=None,
    )

    # --- Test case 2: Laptop Windows, không có semantic ---
    # max_price tăng lên 100M để loại trừ khả năng bị filter giá
    # (os_type dùng 'windows' → STARTS WITH sẽ match 'windows 11', 'windows 10')
    test_intent_2 = UserIntent(
        brand=None,
        category=["laptop"],
        os_type="windows",
        max_price=100_000_000,
        semantic_intent=None,
        trigger_cross_sell=False,
    )

    for idx, intent in enumerate([test_intent_1, test_intent_2], start=1):
        print(f"\n{'='*70}")
        print(f"TEST CASE {idx}: {intent.category} | brand={intent.brand} | semantic='{intent.semantic_intent}'")
        print("="*70)

        results = retriever.retrieve(intent)

        if not results:
            print("  ⚠️  Không có kết quả.")
        else:
            for rank, product in enumerate(results, start=1):
                tag = "[CROSS-SELL]" if product.is_cross_sell else "[MAIN]"
                print(
                    f"  #{rank} {tag} {product.product_id} | {product.category} | "
                    f"brand={product.brand} | score={product.final_score:.4f}"
                )
                if product.review_highlights:
                    preview = product.review_highlights[:80].replace("\n", " ")
                    print(f"      Review: \"{preview}...\"")

    retriever.close()
