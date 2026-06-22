"""
src/rag_pipeline/generator.py
AnswerGenerator: Tổng hợp câu trả lời cuối cùng dựa trên Context của Retriever.
RULE 00:
  - Sử dụng ChatGoogleGenerativeAI (Gemini).
  - Không bịa đặt thông tin (Anti-hallucination).
  - Định dạng Markdown.
"""

from loguru import logger
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from src.config.settings import get_settings
from src.rag_pipeline.extractor import UserIntent
from src.rag_pipeline.retriever import RetrievedProduct
from src.prompts.generator_prompt import GENERATOR_SYSTEM_PROMPT


class AnswerGenerator:
    """Class chịu trách nhiệm tổng hợp câu trả lời cuối cùng cho User."""

    def __init__(self) -> None:
        settings = get_settings()
        logger.info("Khởi tạo AnswerGenerator với model: {}", settings.smart_model)

        self._llm = ChatGoogleGenerativeAI(
            model=settings.smart_model,
            google_api_key=settings.google_api_key,
            temperature=settings.llm_temperature,
        )

    def generate(
        self, query: str, intent: UserIntent, products: list[RetrievedProduct]
    ) -> str:
        """Tạo câu trả lời dựa trên query, intent và list sản phẩm đã tìm được.

        Args:
            query: Câu hỏi gốc của khách hàng.
            intent: Intent đã bóc tách.
            products: Danh sách sản phẩm từ HybridRetriever.

        Returns:
            str: Câu trả lời định dạng Markdown bằng Tiếng Việt.
        """
        logger.info("=== AnswerGenerator.generate() ===")
        
        if not products and not intent.is_small_talk:
            return (
                "Xin lỗi bạn, mình hiện chưa tìm thấy sản phẩm nào đúng chính xác với yêu cầu của bạn. "
                "Bạn có thể thử điều chỉnh mức giá hoặc chọn một thương hiệu khác để mình tìm kiếm lại nhé!"
            )

        # 1. Format context từ danh sách sản phẩm
        context_str = self._format_products_context(products)

        # 2. Chuẩn bị prompt
        system_text = GENERATOR_SYSTEM_PROMPT.replace("{{context}}", context_str).replace(
            "{{query}}", query
        )

        try:
            settings = get_settings()
            keys = settings.all_google_api_keys
            
            last_error = None
            for i, key in enumerate(keys):
                try:
                    messages = [
                        SystemMessage(content=system_text),
                        HumanMessage(content=f"Dựa trên context, hãy trả lời câu hỏi: {query}"),
                    ]

                    # Khởi tạo LLM động với key hiện tại
                    llm = ChatGoogleGenerativeAI(
                        model=settings.smart_model,
                        google_api_key=key,
                        temperature=settings.llm_temperature,
                    )
                    
                    response = llm.invoke(messages)
                    self._llm = llm  # Cache lại LLM thành công
                    
                    logger.success("Phát sinh câu trả lời thành công sử dụng Key #{}.", i + 1)
                    return response.content
                except Exception as e:
                    err_msg = str(e)
                    if "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg or "quota" in err_msg.lower():
                        logger.warning("API Key #{} bị rate-limit (429), đang thử xoay sang key tiếp theo...", i + 1)
                        last_error = e
                        continue
                    else:
                        logger.error("Lỗi không phải rate-limit trong AnswerGenerator: {}", e)
                        raise e
            
            if last_error:
                raise last_error
            raise RuntimeError("Không có API key hợp lệ để tạo câu trả lời.")

        except Exception as e:
            logger.error("Lỗi khi gọi LLM Generator: {}", e)
            return "Rất tiếc, đã có lỗi xảy ra trong quá trình xử lý câu trả lời hoặc hết quota API. Vui lòng thử lại sau."

    def _format_products_context(self, products: list[RetrievedProduct]) -> str:
        """Chuyển list sản phẩm thành chuỗi text chi tiết để feed cho LLM."""
        formatted = []
        for i, p in enumerate(products, 1):
            type_label = "[MAIN]" if not p.is_cross_sell else "[CROSS-SELL SUGGESTION]"
            
            p_info = (
                f"{i}. {type_label} {p.product_id}\n"
                f"   - Hãng: {p.brand} | Loại: {p.category} | OS: {p.os_type}\n"
                f"   - Thông số: {p.specs}\n"
                f"   - Điểm đánh giá: {p.overall_rating}/5 | Độ phổ biến: {p.popularity}/3\n"
            )
            
            if p.review_highlights:
                p_info += f"   - Nhận xét từ khách hàng (English): {p.review_highlights}\n"
            
            formatted.append(p_info)
            
        return "\n".join(formatted)
