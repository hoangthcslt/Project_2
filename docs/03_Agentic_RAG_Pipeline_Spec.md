# Tech Spec: 03_Agentic_RAG_Pipeline_Spec (Ecosystem Recommender)

## 1. Module Overview
Quy trình cốt lõi bóc tách ý định người dùng thành thông số cứng (Specs/OS) và nhu cầu mềm (Reviews), sau đó định tuyến thông minh.

---

## 2. Core Components Detail

### 2.1. Query Extraction & Intent Classification
Dùng LLM (Structured Outputs / Function Calling) để parse câu hỏi của người dùng thành JSON gồm:
1. `structured_filters`: Giá, RAM, Hãng, Danh mục (Phone/Laptop/Headphone).
2. `semantic_intent`: Nhu cầu mềm (chụp ảnh, pin trâu).
3. `ecosystem_context`: Hệ điều hành hoặc thiết bị user đang dùng (để phục vụ gợi ý tương thích).

### 2.2. Intelligent Router & Dual-Execution
**Luồng thực thi logic (BẮT BUỘC):**
1. **Bước 1 (Base Retrieval):** Dùng `structured_filters` tạo Cypher query vào Neo4j lấy danh sách `candidate_products`. Bắt buộc phải ưu tiên các sản phẩm khớp với `ecosystem_context`.
2. **Bước 2 (Optional Semantic Filtering):**
   - Lặp qua danh sách `candidate_products`.
   - NẾU sản phẩm là Headphone (hoặc không có reviews) -> Giữ nguyên danh sách, KHÔNG query Qdrant.
   - NẾU sản phẩm là Phone/Laptop VÀ User có `semantic_intent` -> Dùng list `product_id` từ Neo4j làm Pre-filter để tìm kiếm ngữ nghĩa trong Qdrant.

### 2.3. Reranker (Cross-Encoder)
Chấm điểm `(User Query, Product Context)` để xếp hạng Top 5 sản phẩm phù hợp nhất.

### 2.4. Generator (LLM Context Synthesis)
**Quy tắc Prompt Generator trong `src/prompts/generator_prompt.py` (CRITICAL):**
- **Persona:** Tư vấn viên E-commerce chuyên nghiệp.
- **Constraint 1 (Độ chính xác):** CHỈ được báo giá và thông số kỹ thuật có trong Context. Không tự làm tròn giá, không bịa khuyến mãi.
- **Constraint 2 (Ecosystem Upsell):** BẮT BUỘC phải giải thích lý do gợi ý dựa trên hệ sinh thái (VD: "Sản phẩm này cùng hệ sinh thái Android/iOS với thiết bị bạn đang tìm, giúp đồng bộ hóa tốt hơn").
- **Constraint 3:** KHÔNG BAO GIỜ khuyên người dùng sang mua của đối thủ. Nếu không có sản phẩm thỏa mãn cấu hình và giá, hãy lịch sự yêu cầu User nới lỏng ngân sách.

---

## 3. Data Flow Contracts (JSON Formats)

### Sau Query Extraction
```json
{
  "original_query": "Tìm iPhone nào chụp ảnh đẹp, tiện thể gợi ý luôn tai nghe hợp với nó",
  "extracted_data": {
    "structured_filters": { "brand": "Apple", "category": ["Phone", "Headphone"] },
    "semantic_intent": "chụp ảnh đẹp",
    "ecosystem_context": "iOS"
  }
}
```
**Cấu trúc Context đưa vào Generator**
{
  "final_answer_context": [
    {
      "category": "Phone",
      "model": "iPhone 15",
      "price": 20000000,
      "os_type": "iOS",
      "review_highlights": "Camera vượt trội trong tầm giá."
    },
    {
      "category": "Headphone",
      "model": "AirPods Pro 2",
      "price": 5000000,
      "os_type": "iOS",
      "review_highlights": null 
    }
  ]
}