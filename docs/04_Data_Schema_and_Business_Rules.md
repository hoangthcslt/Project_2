# Tech Spec: 04_Data_Schema_and_Business_Rules

## 1. Project Overview
Dự án này là hệ thống "Ecosystem-Aware Recommender Chatbot". Mục tiêu không chỉ trả lời câu hỏi tìm kiếm sản phẩm đơn lẻ, mà còn tự động **Cross-sell / Upsell** (Bán chéo) các sản phẩm khác loại nhưng cùng hệ sinh thái (Ecosystem) dựa trên `os_type` hoặc `brand`. 

Ngôn ngữ giao tiếp của Bot: **Tiếng Việt** (Dù data review là tiếng Anh, LLM phải tự dịch và tổng hợp sang tiếng Việt khi trả lời User).

## 2. Data Schema (Cấu trúc dữ liệu)
Hệ thống sử dụng 3 file CSV đầu vào: `phones.csv`, `laptops.csv`, `headphones.csv`.
Agent BẮT BUỘC dùng Pydantic / Pandas để map chính xác các cột sau:

*   `brand` (String): Tên hãng (Apple, Samsung, Dell, Sony...).
*   `model_name` (String): Tên sản phẩm, dùng làm **ID Cầu Nối** giữa Neo4j và Qdrant.
*   `category` (String): Chỉ có 3 giá trị `phone`, `laptop`, `headphone`.
*   `price` (Float/Int): Giá sản phẩm.
*   `os_type` (String): Quan trọng cho Cross-sell. Các giá trị chuẩn: `ios`, `android`, `windows`, `macos`. (Lưu ý: tai nghe có thể tương thích đa nền tảng nhưng ưu tiên ghép cặp như Apple - iOS/MacOS).
*   `overall_rating` (Float): Điểm đánh giá (0.0 -> 5.0).
*   `popularity` (Int): Thang điểm 1, 2, 3 (3 là phổ biến nhất). Dùng để boost điểm khi Reranking.
*   `reviews` (String): Các bài đánh giá bằng tiếng Anh. **LƯU Ý: File `headphones.csv` KHÔNG CÓ cột này.** Code ingest phải dùng `try-except` hoặc `if 'reviews' in df.columns` để tránh lỗi `KeyError`.

## 3. Business Logic & Recommendation Rules

### Quy tắc 1: Luồng Cross-sell (Bán chéo hệ sinh thái)
Khi User hỏi mua 1 loại sản phẩm (Ví dụ: "Tìm điện thoại..."), Router LLM phải kích hoạt cờ `trigger_cross_sell = True`.
*   **Logic Truy vấn Neo4j:** Khi tìm thấy Phone phù hợp (VD: iPhone 15, os_type = ios, brand = Apple), Agent phải viết thêm lệnh Cypher để kéo thêm 1-2 Laptop hoặc Headphone có cùng `brand` (Apple) hoặc tương thích `os_type` (ios/macos).
*   **Prompt Generator:** Bắt buộc phải có câu dẫn dắt tự nhiên. Ví dụ: *"Vì bạn đang quan tâm tới iPhone 15, mình gợi ý thêm tai nghe AirPods Pro 2 cùng hệ sinh thái Apple để có trải nghiệm âm thanh tốt nhất."*

### Quy tắc 2: Logic Tính điểm (Scoring & Reranking)
Ở bước Retrieval, danh sách ứng viên (Candidate Contexts) sẽ được chấm điểm theo công thức:
`Final_Score = (Semantic_Score_từ_Qdrant) * 0.7 + (Popularity_Score) * 0.2 + (Overall_Rating_Score) * 0.1`
*   *Lưu ý cho Agent:* Headphone không có `Semantic_Score` (vì không có reviews), nên đối với Headphone, chỉ xếp hạng dựa trên giá, độ phổ biến và rating.

### Quy tắc 3: Xử lý Review đa ngôn ngữ
Nội dung cột `reviews` đang ở dạng tiếng Anh. Ở bước Prompt cho LLM Generator (bước cuối cùng), Agent BẮT BUỘC phải thêm chỉ thị:
*"Trích dẫn nhận xét của người dùng dựa trên Context (nguyên bản tiếng Anh) nhưng phải dịch mượt mà sang tiếng Việt. Nếu review nói 'Great battery life', hãy nói 'Nhiều người dùng đánh giá sản phẩm có thời lượng pin rất trâu'."*