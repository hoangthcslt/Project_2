"""
src/rag_pipeline/extractor.py
Bóc tách UserIntent từ câu hỏi tự nhiên bằng LLM structured output.
RULE 00:
  - Dùng with_structured_output để tránh parse JSON thủ công, giảm thiểu lỗi.
  - Mọi credential lấy từ Settings, KHÔNG hardcode.
  - Type hinting đầy đủ (Python 3.10+).
  - Logging tại mọi bước.
"""
from __future__ import annotations

import time
from typing import Optional
from loguru import logger
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from src.config.settings import get_settings
from src.prompts.extraction_prompt import EXTRACTION_SYSTEM_PROMPT


# =============================================================================
# 1. Pydantic Model — UserIntent
# =============================================================================

class UserIntent(BaseModel):
    """Schema bóc tách ý định người dùng, hỗ trợ nhận diện Small Talk."""

    is_small_talk: bool = Field(
        default=False,
        description="True nếu là câu hỏi chào hỏi, cảm ơn hoặc tán gẫu.",
    )
    is_out_of_scope: bool = Field(
        default=False,
        description="True nếu là câu hỏi nhạy cảm, chính trị, code hack hoặc ngoài chuyên môn mua sắm công nghệ.",
    )
    brand: Optional[str] = Field(
        default=None,
        description="Tên hãng sản xuất (Apple, Samsung, Dell...). None nếu không đề cập.",
    )
    category: list[str] = Field(
        default_factory=list,
        description="Danh sách loại sản phẩm: 'phone', 'laptop', 'headphone'.",
    )
    os_type: Optional[str] = Field(
        default=None,
        description="Hệ điều hành/hệ sinh thái: 'ios', 'android', 'windows', 'macos'.",
    )
    max_price: Optional[int] = Field(
        default=None,
        description="Giá tối đa tính bằng VNĐ.",
    )
    min_price: Optional[int] = Field(
        default=None,
        description="Giá tối thiểu tính bằng VNĐ.",
    )
    semantic_intent: Optional[str] = Field(
        default=None,
        description="Nhu cầu mềm/cảm xúc: 'chụp ảnh đẹp', 'pin trâu', 'âm thanh tốt'.",
    )
    trigger_cross_sell: bool = Field(
        default=True,
        description="True nếu cần gợi ý thêm sản phẩm khác cùng hệ sinh thái.",
    )
    ecosystem_context: Optional[str] = Field(
        default=None,
        description="Hệ sinh thái hiện tại của User (thiết bị đang dùng).",
    )


# =============================================================================
# 2. IntentExtractor Class
# =============================================================================

class IntentExtractor:
    """Bóc tách câu hỏi tự nhiên thành UserIntent sử dụng LangChain structured output.

    Sử dụng with_structured_output để LLM trả về JSON đã được validate bởi
    Pydantic, tránh lỗi parse thủ công (RULE 00 - No loose state).
    """

    def __init__(self) -> None:
        settings = get_settings()

        logger.info("Khởi tạo IntentExtractor với model: {}", settings.smart_model)

        # Dùng ChatGoogleGenerativeAI với google_api_key từ .env
        _base_llm = ChatGoogleGenerativeAI(
            model=settings.smart_model,
            google_api_key=settings.google_api_key,
            temperature=settings.llm_temperature,
        )

        # with_structured_output: LLM tự động trả về object UserIntent đã validate
        self._chain = _base_llm.with_structured_output(UserIntent)

    def extract(
        self, user_query: str, chat_history: list[dict] = []
    ) -> UserIntent:
        """Parse câu hỏi của user thành UserIntent, có tính đến ngữ cảnh hội thoại.

        Args:
            user_query: Câu hỏi hiện tại của người dùng.
            chat_history: Danh sách các tin nhắn trước đó [{"role": "user/assistant", "content": "..."}]

        Returns:
            UserIntent: Object chứa thông tin đã bóc tách và phân loại.
        """
        logger.info("=== IntentExtractor.extract() ===")
        
        # Chỉ lấy tối đa 5 lượt hội thoại gần nhất để tránh làm loãng prompt (User request)
        history_window = chat_history[-10:]  # 5 rounds = 10 messages
        
        history_context = ""
        if history_window:
            history_context = "CONVERSATION HISTORY:\n"
            for msg in history_window:
                role = "User" if msg["role"] == "user" else "AI"
                history_context += f"{role}: {msg['content']}\n"
            history_context += "\n"

        logger.info("Query: '{}' | History size: {}", user_query, len(history_window))
        start_time = time.perf_counter()

        try:
            settings = get_settings()
            keys = settings.all_google_api_keys
            
            last_error = None
            for i, key in enumerate(keys):
                try:
                    full_content = f"{history_context}CURRENT USER INPUT: {user_query}"
                    messages = [
                        SystemMessage(content=EXTRACTION_SYSTEM_PROMPT),
                        HumanMessage(content=full_content),
                    ]
                    
                    # Khởi tạo chain động với key hiện tại
                    llm = ChatGoogleGenerativeAI(
                        model=settings.smart_model,
                        google_api_key=key,
                        temperature=settings.llm_temperature,
                    )
                    chain = llm.with_structured_output(UserIntent)
                    
                    intent: UserIntent = chain.invoke(messages)
                    self._chain = chain  # Cache lại chain thành công
                    
                    latency_ms = (time.perf_counter() - start_time) * 1000
                    logger.success(
                        "Extraction thành công sử dụng Key #{} sau {:.1f}ms | intent={}",
                        i + 1,
                        latency_ms,
                        intent.model_dump(),
                    )
                    return intent
                except Exception as e:
                    err_msg = str(e)
                    if "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg or "quota" in err_msg.lower():
                        logger.warning("API Key #{} bị rate-limit (429), đang thử xoay sang key tiếp theo...", i + 1)
                        last_error = e
                        continue
                    else:
                        logger.error("Lỗi không phải rate-limit trong IntentExtractor: {}", e)
                        raise e
            
            if last_error:
                raise last_error
            raise RuntimeError("Không có API key hợp lệ để thực hiện Extraction.")

        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "Extraction thất bại sau {:.1f}ms | error={}", latency_ms, str(e)
            )
            raise


# =============================================================================
# Quick Test
# =============================================================================

if __name__ == "__main__":
    import sys

    # Fix Windows terminal encoding (cp1252 → utf-8)
    sys.stdout.reconfigure(encoding="utf-8")

    logger.remove()
    logger.add(sys.stderr, level="DEBUG")

    extractor = IntentExtractor()

    test_queries = [
        "Tôi muốn tìm iPhone chụp ảnh đẹp dưới 25 triệu, gợi ý thêm tai nghe phù hợp",
        "Laptop Dell cho sinh viên, giá từ 10 đến 15 triệu, cần pin trâu",
        "Samsung Galaxy S series, hệ sinh thái Android",
    ]

    for q in test_queries:
        print(f"\n{'='*60}")
        print(f"QUERY: {q}")
        result = extractor.extract(q)
        print(f"RESULT:\n{result.model_dump_json(indent=2)}")
