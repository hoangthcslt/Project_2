# Tech Spec: 01_System_Architecture

## 1. System & Business Overview
**Business Context:** Hệ thống là một Chatbot tư vấn mua sắm đồ điện tử chuyên dụng (Phone, Laptop, Headphone). Nguồn dữ liệu đầu vào là các file CSV chứa thông số kỹ thuật (Specs) và Đánh giá người dùng (Reviews). 

**Điểm nhấn cốt lõi của hệ thống:**
1. **Độ chính xác tuyệt đối:** Dữ liệu Specs (Price, RAM, Chip, Brand) đòi hỏi độ chính xác 100%, không được phép "ảo giác" (hallucinate).
2. **Tìm kiếm ngữ nghĩa linh hoạt:** Dữ liệu Reviews đòi hỏi khả năng hiểu ngôn ngữ tự nhiên để khớp với nhu cầu mềm của khách hàng (VD: "chụp ảnh đẹp", "pin trâu").
3. **Ecosystem-aware Recommender:** Hệ thống có khả năng nhận diện hệ sinh thái thông qua thuộc tính `os_type`. Khả năng này cho phép tự động gợi ý các sản phẩm mang tính tương thích cao (Ví dụ: Gợi ý tai nghe có cùng hệ sinh thái với điện thoại đang dùng).

Luồng thực thi trải qua 4 giai đoạn chính: Data Ingestion -> Knowledge Base -> Agentic RAG Pipeline -> UI & Evaluation.

## 2. Recommended Tech Stack
* **RAG Orchestration:** `LlamaIndex` hoặc `LangChain` + `LangGraph`.
* **API Framework:** `FastAPI` + `Uvicorn`.
* **Data Processing:** `Pandas` (Tối ưu cho file CSV có cấu trúc).
* **Knowledge Base:** `Neo4j` (Lưu trữ Specs, Brand, OS_Type) và `Qdrant` (Lưu trữ Reviews).
* **AI Models:** Model LLM (GPT-4o / Gemini / Claude), Embedding (BAAI/bge-m3), Reranker (BAAI/bge-reranker-v2-m3).
* **Frontend:** `React.js` + `TailwindCSS`.

## 3. Directory Structure
```text
agentic-rag-system/
├── data/                       # Chứa các file CSV (Phone, Laptop, Headphone)
├── src/                        
│   ├── config/                 
│   ├── prompts/                # BẮT BUỘC: Chứa các System Prompts (.py). KHÔNG hardcode.
│   │   ├── router_prompt.py
│   │   ├── generator_prompt.py
│   │   └── extraction_prompt.py
│   ├── ingestion/              # Xử lý CSV và đẩy vào Neo4j/Qdrant
│   ├── knowledge_base/         
│   ├── rag_pipeline/           # Core logic: Extraction -> Route -> Retrieve -> Rerank -> Generate
│   ├── api/                    
│   └── evaluation/             
├── ui/                         # React Frontend
├── docker-compose.yml          
├── requirements.txt            
├── .env.example                
└── README.md