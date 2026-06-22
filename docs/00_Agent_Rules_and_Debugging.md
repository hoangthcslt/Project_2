# Tech Spec: 00_Agent_Rules_and_Debugging
**THÔNG ĐIỆP TỪ SOLUTION ARCHITECT GỬI AI AGENT (CURSOR/ANTIGRAVITY):**
File này chứa các nguyên tắc tối cao. Khi tham gia vào dự án này, mi (Agent) PHẢI đọc và TUÂN THỦ TUYỆT ĐỐI các quy tắc dưới đây. Mọi sự vi phạm sẽ dẫn đến việc rollback code ngay lập tức. Không tranh cãi, không tự ý sáng tạo sai lệch chuẩn mực.

---

## 1. KỶ LUẬT THÉP TRONG LẬP TRÌNH BACKEND (STRICT CODING RULES)

### 🔴 Lệnh Cấm (DON'Ts)
1. **CẤM "Ảo giác" (No Hallucination) API:** KHÔNG ĐƯỢC tự bịa ra các hàm của thư viện `neo4j`, `qdrant-client`, `langchain` hay `llama-index`. Nếu không chắc chắn về syntax mới nhất, PHẢI dùng công cụ duyệt web để đọc tài liệu chính thức trước khi viết code.
2. **CẤM Hardcode credentials:** MỌI API Keys, DB URLs, Passwords PHẢI được nạp từ `.env` qua thư viện `pydantic-settings` hoặc `os.getenv()`.
3. **CẤM viết code Monolith lộn xộn:** Mỗi file chỉ làm một nhiệm vụ (Single Responsibility Principle). Hàm nào dài quá 50 dòng thì PHẢI tách ra.
4. **CẤM truyền dữ liệu tự do (No loose State):** CẤM truyền dữ liệu lung tung bằng Dict/Tuples vô danh giữa các hàm. Mọi luồng dữ liệu trong Agentic RAG PHẢI được định nghĩa chặt chẽ qua `StateGraph` (nếu dùng LangGraph) và `TypedDict` / `Pydantic`

### 🟢 Lệnh Bắt Buộc (DOs)
1. **BẮT BUỘC dùng Type Hinting (Python 3.10+):** Mọi hàm, biến, class đều phải khai báo kiểu dữ liệu. Sử dụng `pydantic` models để validate data.
2. **BẮT BUỘC gắn Logging ở mọi Node:** Bắt buộc cấu hình module `logging` của Python thay vì dùng `print()`. Ghi rõ Input/Output và Latency tại mỗi bước (Router, Reranker, Generator...).
3. **BẮT BUỘC bắt lỗi Try-Catch (Exception Handling):** Bất kỳ thao tác I/O nào (gọi LLM, query DB) đều phải được bọc trong `try-except` và ghi log lỗi cụ thể.
4. **BẮT BUỘC chặn Graph/Cypher Injection:** Khi Agent dùng LLM sinh câu lệnh Cypher (Neo4j) từ Text, BẮT BUỘC phải giới hạn số lượng node trả về (Thêm `LIMIT 20` vào cuối mọi query) để chống treo Database.
---

## 2. HƯỚNG DẪN SETUP PHẦN UI (REACT) VÀ ĐÁNH GIÁ (RAGAS)

### 2.1. UI Implementation (React / SPA)
Phần Frontend tách biệt hoàn toàn với Backend. Agent BẮT BUỘC tuân thủ luồng phát triển sau để tránh crash do Backend chưa sẵn sàng:

* **Quy tắc 1: Bắt buộc Mock API trước.**
  TRƯỚC KHI gọi API bằng `axios` hay `fetch` tới Backend FastAPI, Agent PHẢI tạo một file `src/services/mockApi.js` (hoặc `.ts`). File này chứa hàm trả về một `Promise` giả lập thời gian chờ (delay 2-3s) và trả về JSON đúng chuẩn của RAG Pipeline (chứa `final_answer` và `used_sources`).
* **Quy tắc 2: Quản lý UI States nghiêm ngặt.**
  Component chat RAG PHẢI xử lý đủ 3 trạng thái:
  - `Idle` (Chờ nhập câu hỏi)
  - `Loading` (Đang gọi RAG - BẮT BUỘC có UI Spinner/Skeleton hoặc dòng chữ "Agent is thinking/searching Neo4j...")
  - `Success/Error` (Hiển thị Markdown của câu trả lời hoặc thông báo lỗi).
* **Quy tắc 3: Tích hợp Backend.**
  CHỈ KHI luồng giao diện với mock data chạy hoàn hảo, Agent mới được phép đổi sang gọi endpoint thật (VD: `POST /api/v1/query`). BẮT BUỘC phải cấu hình CORS trên FastAPI backend thì React mới gọi được.

### 2.2. Evaluation Implementation (RAGAS)
Hệ thống RAG không có đánh giá là một hệ thống mù.
* **Pipeline Đánh giá:** Phải thiết lập script tính 2 metrics cốt lõi:
    1.  `Faithfulness`: Câu trả lời có trung thành với Context lấy từ Qdrant/Neo4j không, hay LLM tự bịa?
    2.  `Answer Relevance`: Câu trả lời có đúng trọng tâm câu hỏi của User không?
* **Cách chạy Eval:** Tạo tập dữ liệu test nhỏ (10-20 câu), viết script đẩy qua Agentic Pipeline và đo bằng RAGAS để xuất ra file CSV.

---

## 3. TROUBLESHOOTING KHI HỆ THỐNG CRASH

### Sự cố 1: Lỗi CORS khi React gọi FastAPI
* **Triệu chứng:** Console trình duyệt báo lỗi `CORS policy: No 'Access-Control-Allow-Origin' header is present`.
* **Cách Debug:** Agent không được tìm cách sửa ở frontend. PHẢI mở file server FastAPI, import `CORSMiddleware` từ `fastapi.middleware.cors` và allow origin của ứng dụng React (thường là `http://localhost:3000` hoặc `5173`).

### Sự cố 2: Intelligent Router chọn sai đường hoặc bị lỗi JSON
* **Triệu chứng:** Pipeline báo lỗi định dạng khi đọc Output của Router.
* **Cách Debug:** Mở file log Backend, in nguyên văn raw text LLM trả về TRƯỚC KHI parse bằng `json.loads()`. Sửa lại System Prompt, yêu cầu format JSON block nghiêm ngặt.

### Sự cố 3: Không kết nối được Neo4j / Qdrant
* **Triệu chứng:** Backend báo `ServiceUnavailable` hoặc timeout.
* **Cách Debug:**
    1. Chạy `docker ps` để kiểm tra container Neo4j/Qdrant có đang `Up` không.
    2. Đảm bảo port (7687 cho Neo4j, 6333 cho Qdrant) đang được map đúng.

---
**KẾT LUẬN:** Agent đã rõ lệnh chưa? Nếu đã đọc xong file này, BẮT BUỘC ghi nhớ toàn bộ bối cảnh và áp dụng ngay lập tức vào các tác vụ code tiếp theo. Không có ngoại lệ!