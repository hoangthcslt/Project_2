---

### Nội dung mới cho `02_Data_Ingestion_Spec.md`

```markdown
# Tech Spec: 02_Data_Ingestion_Spec

## 1. Module Overview
Module `Data Ingestion` sử dụng luồng xử lý kép (Dual-Pipeline) để tiêu hóa các file CSV.
- **Luồng 1 (Semantic):** Trích xuất cột `reviews` (nếu có) -> Chunking -> Embedding -> Qdrant.
- **Luồng 2 (Relational/Graph):** Trích xuất các cột Specs (brand, model, chip, ram, price, os_type) -> Neo4j.

---

## 2. Document Processing Pipeline (Vector Store Flow)
### 2.1. Lọc và Xử lý CSV
- Đọc file CSV bằng `Pandas`.
- **LUẬT XỬ LÝ DỮ LIỆU KHUYẾT (CRITICAL):** Lọc riêng các sản phẩm thuộc danh mục Headphone (không có cột `reviews`). Sản phẩm nào KHÔNG có review thì BỎ QUA luồng Qdrant, chỉ đẩy vào Neo4j.

### 2.2. Text Chunking (Reviews)
- Phân tách nội dung review thành các đoạn nhỏ để lấy intent.
- Sử dụng `chunk_size = 256` hoặc `512` tokens, `chunk_overlap = 50`. Tuyệt đối không dùng chunk quá lớn làm loãng cảm xúc/ý định của review.

### 2.3. Load to Qdrant
- Upsert vào Qdrant với metadata bắt buộc phải chứa `product_id` (hoặc `model_name` chuẩn hóa) làm CẦU NỐI với Neo4j.

---

## 3. Knowledge Graph Pipeline (Graph Store Flow)
### 3.1. Thiết kế Schema (Bắt buộc tuân thủ)
Agent phải sử dụng Cypher để tạo cấu trúc Graph sau:
- **Nodes:** `(Product)`, `(Brand)`, `(OS)`.
- **Relationships:**
  - `(Product)-[:BELONGS_TO]->(Brand)`
  - `(Product)-[:RUNS_ON]->(OS)`
- **Properties của Product Node:** `price`, `ram`, `rom`, `chip`, `camera`...

### 3.2. Load to Neo4j
- Sử dụng lệnh `MERGE` để tránh duplicate nodes. Ví dụ: `MERGE (b:Brand {name: row.brand}) MERGE (p:Product {id: row.id}) MERGE (p)-[:BELONGS_TO]->(b)`.

---

## 4. Agent Coding Guidelines (DOs & DON'Ts)

### 🔴 MỤC BẮT BUỘC (DOs)
1. **CẦU NỐI VECTOR VÀ GRAPH (THE BRIDGE):** Bắt buộc Agent phải gán chung một `product_id` (hoặc Model_Name làm ID) duy nhất trong CẢ HAI DB. Trong Qdrant nó nằm ở Metadata, trong Neo4j nó là Node Property.
2. **Tạo Index:** Phải viết script `init_db.py` để tạo Constraint/Index cho `product_id`, `Brand`, `OS_Type` trong Neo4j trước khi ingest.
3. **Batching:** Dùng `upsert_batch` cho Qdrant và `UNWIND` parameters cho Neo4j. KHÔNG insert từng dòng trong vòng lặp `for`.