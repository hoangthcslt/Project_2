"""
src/main.py
Entrypoint duy nhất cho Agentic RAG Shopping Assistant.
Kết nối Extractor -> Retriever -> Generator thành một luồng hoàn chỉnh.
"""

import sys
import os
from loguru import logger

# Bổ sung root vào sys.path để tránh lỗi ModuleNotFoundError
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.rag_pipeline.extractor import IntentExtractor
from src.rag_pipeline.retriever import HybridRetriever
from src.rag_pipeline.generator import AnswerGenerator

def main():
    # 0. Cấu hình logger
    sys.stdout.reconfigure(encoding="utf-8")
    logger.remove()
    logger.add(sys.stderr, level="INFO", colorize=True)

    print("\n" + "="*60)
    print("🤖 CHÀO MỪNG BẠN ĐẾN VỚI AGENTIC RAG SHOPPING ASSISTANT")
    print("      (Tư vấn Điện thoại, Laptop, Tai nghe chuyên nghiệp)")
    print("="*60)
    print("Nhập 'exit' hoặc 'quit' để thoát.\n")

    try:
        # 1. Khởi tạo các module
        logger.info("Đang khởi tạo hệ thống...")
        extractor = IntentExtractor()
        retriever = HybridRetriever()
        generator = AnswerGenerator()
        logger.success("Hệ thống đã sẵn sàng!\n")

        # 2. Vòng lặp Chat
        history = []
        while True:
            try:
                user_query = input("💬 Bạn: ").strip()
                
                if not user_query:
                    continue
                if user_query.lower() in ["exit", "quit", "thoát"]:
                    print("\nCảm ơn bạn đã sử dụng dịch vụ. Hẹn gặp lại!")
                    break

                print("\n" + "-"*30)
                print("⏳ Đang xử lý câu hỏi của bạn...")

                # Bước 1: Bóc tách Intent (Có ngữ cảnh)
                intent = extractor.extract(user_query, history)

                # Bước 2: Truy xuất sản phẩm (Bỏ qua nếu là Small Talk)
                products = []
                if intent.is_small_talk:
                    logger.info("Main: Small Talk detected.")
                else:
                    retrieval_result = retriever.retrieve(intent)
                    products = retrieval_result.products

                # Bước 3: Tổng hợp câu trả lời
                answer = generator.generate(user_query, intent, products)

                # Lưu vào history
                history.append({"role": "user", "content": user_query})
                history.append({"role": "assistant", "content": answer})

                # Bước 4: In kết quả
                print("\n🤖 Assistant:\n")
                print(answer)
                print("\n" + "="*60 + "\n")

            except KeyboardInterrupt:
                print("\nNgắt từ bàn phím. Đang thoát...")
                break
            except Exception as e:
                logger.error("Lỗi trong vòng lặp chat: {}", e)
                print("⚠️  Có lỗi xảy ra. Hãy thử hỏi lại bằng cách khác nhé.")

    except Exception as e:
        logger.critical("Không thể khởi động hệ thống: {}", e)
    finally:
        if 'retriever' in locals():
            retriever.close()

if __name__ == "__main__":
    main()
