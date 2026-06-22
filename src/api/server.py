"""
src/api/server.py
Backend API Server sử dụng FastAPI.
RULE 00:
  - Cung cấp logs chi tiết cho "Thinking Process" ở Frontend.
  - Sử dụng CORS để cho phép Frontend (Vite) truy cập.
  - Logging đầy đủ cho mỗi request.
"""

import time
from typing import List, Any, Dict
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from loguru import logger

from src.rag_pipeline.extractor import IntentExtractor, UserIntent
from src.rag_pipeline.retriever import HybridRetriever, RetrievalResult, RetrievedProduct
from src.rag_pipeline.generator import AnswerGenerator

# --- Models ---

class ChatRequest(BaseModel):
    query: str
    history: List[Dict[str, Any]] = []

class ChatResponse(BaseModel):
    answer: str
    extraction_log: Dict[str, Any]
    retrieval_log: Dict[str, Any]
    products: List[Dict[str, Any]]
    latency_ms: float

# --- App Initialization ---

app = FastAPI(title="Agentic RAG Shopping Assistant API")

# Setup CORS cho phép Frontend truy cập
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Trong production nên giới hạn origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Khởi tạo Pipeline (Singleton-like for API)
extractor = IntentExtractor()
retriever = HybridRetriever()
generator = AnswerGenerator()

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """Endpoint chính xử lý câu hỏi của người dùng và trả về kèm Thinking Process logs."""
    logger.info("--- API Request: {} ---", request.query)
    start_time = time.perf_counter()
    
    try:
        # Bước 1: Intent Extraction (Truyền thêm history)
        intent: UserIntent = extractor.extract(request.query, request.history)
        
        # Guardrail: Check if query is out of scope
        if intent.is_out_of_scope == True:
            logger.warning("Phát hiện câu hỏi ngoài chuyên môn/nhạy cảm (is_out_of_scope = True).")
            latency_ms = (time.perf_counter() - start_time) * 1000
            return ChatResponse(
                answer=(
                    "Xin lỗi bạn, tôi là trợ lý tư vấn mua sắm đồ điện tử (điện thoại, laptop, tai nghe). "
                    "Tôi không thể trả lời hoặc thực hiện các câu hỏi liên quan đến chủ đề này. "
                    "Bạn vui lòng đặt câu hỏi khác liên quan đến việc tư vấn mua sắm đồ công nghệ nhé!"
                ),
                extraction_log=intent.model_dump(),
                retrieval_log={
                    "status": "Bị từ chối bởi hệ thống Guardrails - Câu hỏi ngoài chuyên môn",
                    "queries": [],
                    "total_latency_ms": 0
                },
                products=[],
                latency_ms=latency_ms
            )
        
        # Bước 2: Retrieval (Bỏ qua nếu là Small Talk)
        products = []
        retrieval_log = {}

        if intent.is_small_talk == True:
            logger.info("Phát hiện Small Talk -> Bỏ qua Retrieval.")
            retrieval_log = {
                "status": "Phát hiện câu hỏi giao tiếp - Tối ưu hóa bằng cách bỏ qua truy vấn Database",
                "queries": [],
                "qdrant": {"hit_count": 0},
                "total_latency_ms": 0
            }
        else:
            retrieval_result: RetrievalResult = retriever.retrieve(intent)
            products = retrieval_result.products
            retrieval_log = retrieval_result.metadata
        
        # Bước 3: Answer Generation
        answer: str = generator.generate(request.query, intent, products)
        
        # Bước 4: Chuẩn bị Response
        latency_ms = (time.perf_counter() - start_time) * 1000
        
        # Chuyển đổi list RetrievedProduct sang list các dict để JSON hóa
        product_list = [p.__dict__ for p in products]
        
        # Xử lý nested objects trong dict nếu có (pydantic model to dict)
        extraction_log = intent.model_dump()
        
        return ChatResponse(
            answer=answer,
            extraction_log=extraction_log,
            retrieval_log=retrieval_log,
            products=product_list,
            latency_ms=latency_ms
        )

    except Exception as e:
        logger.error("API Error: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
