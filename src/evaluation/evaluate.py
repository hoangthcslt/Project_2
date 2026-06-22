import os
import sys
import pandas as pd
from loguru import logger

# Reconfigure stdout/stderr for UTF-8 to prevent encoding issues on Windows
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# Add project root to PYTHONPATH
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv

# Ensure dotenv is loaded from project root
env_path = os.path.join(project_root, ".env")
load_dotenv(env_path)

from src.config.settings import get_settings
from src.rag_pipeline.extractor import IntentExtractor
from src.rag_pipeline.retriever import HybridRetriever
from src.rag_pipeline.generator import AnswerGenerator

# Initialize pipeline
logger.info("Initializing RAG Pipeline components...")
try:
    extractor = IntentExtractor()
    retriever = HybridRetriever()
    generator = AnswerGenerator()
except Exception as e:
    logger.error(f"Failed to initialize RAG Pipeline: {e}")
    sys.exit(1)

settings = get_settings()

test_cases = [
    {
        "query": "Tôi muốn tìm laptop Dell dưới 15 triệu.",
        "ground_truth": "Có một số laptop Dell dưới 15 triệu phù hợp như Dell 15 DC15250 (giá khoảng 9.6 triệu VND) hoặc Dell DC15255 (giá khoảng 11.7 triệu VND). Cả hai máy đều chạy Windows 11 và có bộ nhớ lưu trữ 512GB SSD."
    },
    {
        "query": "Tìm điện thoại Apple iPhone dưới 20 triệu.",
        "ground_truth": "Các mẫu iPhone dưới 20 triệu VND có sẵn là iPhone XR (giá khoảng 14.4 - 15.4 triệu VND) and iPhone 11 (giá khoảng 14.4 - 15.4 triệu VND). Cả hai đều chạy hệ điều hành iOS và dung lượng lưu trữ 64GB hoặc 128GB."
    },
    {
        "query": "Tôi muốn mua tai nghe chụp tai AKG âm thanh chất lượng tốt.",
        "ground_truth": "Có một số tai nghe chụp tai AKG âm thanh tốt như AKG K72 (giá khoảng 950.000 VND) và AKG K702 (giá khoảng 2.1 triệu VND). Chúng hỗ trợ kết nối không dây và là dòng tai nghe chụp tai."
    },
    {
        "query": "Tìm điện thoại Apple iPhone màu đen dung lượng 128GB.",
        "ground_truth": "Có mẫu iPhone XR màu đen dung lượng 128GB với giá khoảng 15.4 triệu VND và iPhone 11 màu đen 128GB giá khoảng 15.4 triệu VND."
    },
    {
        "query": "Tôi muốn mua tai nghe chụp tai Anker có chống ồn tốt.",
        "ground_truth": "Có mẫu tai nghe chụp tai Anker H700 có chống ồn tốt (noise cancelling) với giá khoảng 750.000 VND hoặc mẫu Anker Space One Pro giá cao cấp hơn."
    }
]

# Run RAG Pipeline
dataset_data = {
    "question": [],
    "contexts": [],
    "answer": [],
    "ground_truth": []
}

logger.info("Running RAG Pipeline for test cases...")
for idx, tc in enumerate(test_cases):
    query = tc["query"]
    gt = tc["ground_truth"]
    logger.info(f"[{idx+1}/{len(test_cases)}] Processing query: {query}")
    
    try:
        # Extract intent
        intent = extractor.extract(query)
        
        # Retrieve products
        retrieval_result = retriever.retrieve(intent)
        products = retrieval_result.products
        
        # Generate answer
        answer = generator.generate(query, intent, products)
        
        # Format contexts as list of strings
        contexts = []
        for p in products:
            specs_str = ", ".join(f"{k}: {v}" for k, v in p.specs.items() if k not in ["id"])
            context_str = f"Sản phẩm: {p.product_id}. Thương hiệu: {p.brand}. Danh mục: {p.category}. Thông số: {specs_str}. Đánh giá: {p.review_highlights or ''}"
            contexts.append(context_str)
            
        dataset_data["question"].append(query)
        dataset_data["contexts"].append(contexts)
        dataset_data["answer"].append(answer)
        dataset_data["ground_truth"].append(gt)
        logger.success(f"[{idx+1}/{len(test_cases)}] Done.")
    except Exception as e:
        logger.error(f"[{idx+1}/{len(test_cases)}] Error during execution: {e}")
        # Append fallback data so we don't lose the row and still write the CSV
        dataset_data["question"].append(query)
        dataset_data["contexts"].append([])
        dataset_data["answer"].append(f"[Lỗi API: {str(e)[:100]}]")
        dataset_data["ground_truth"].append(gt)

# Check if we got any data
if not dataset_data["question"]:
    logger.error("No test cases were successfully executed. Exiting.")
    sys.exit(1)

# Ragas Evaluation
logger.info("Initializing Ragas evaluator...")
eval_success = False
results = None

try:
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import Faithfulness, AnswerRelevancy
    from ragas.run_config import RunConfig
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_community.embeddings import HuggingFaceEmbeddings
    
    # Initialize models for evaluation
    llm = ChatGoogleGenerativeAI(
        model=settings.smart_model,
        google_api_key=settings.google_api_key,
        temperature=0.0
    )
    
    embeddings = HuggingFaceEmbeddings(
        model_name=settings.resolved_embedding_model
    )
    
    # Instantiate metrics
    faithfulness_metric = Faithfulness(llm=llm)
    answer_relevancy_metric = AnswerRelevancy(llm=llm, embeddings=embeddings)
    
    dataset = Dataset.from_dict(dataset_data)
    
    # Use RunConfig with low concurrency to avoid rate limits
    run_config = RunConfig(
        max_workers=1,
        timeout=120,
        max_retries=5
    )
    
    logger.info("Starting Ragas evaluation (metrics: faithfulness, answer_relevancy)...")
    results = evaluate(
        dataset=dataset,
        metrics=[faithfulness_metric, answer_relevancy_metric],
        llm=llm,
        embeddings=embeddings,
        run_config=run_config
    )
    eval_success = True
    logger.success("Ragas evaluation completed successfully!")
except Exception as e:
    logger.error(f"Failed to run Ragas evaluation (likely due to API rate limits): {e}")

# Compile results and export to CSV
output_dir = os.path.join(project_root, "data")
os.makedirs(output_dir, exist_ok=True)
csv_path = os.path.join(output_dir, "evaluation_results.csv")

if eval_success and results is not None:
    df = results.to_pandas()
    
    # Calculate average scores
    avg_scores = {}
    print("\n" + "="*50)
    print(" KẾT QUẢ ĐÁNH GIÁ RAGAS TRUNG BÌNH")
    print("="*50)
    for metric, score in results.items():
        avg_scores[metric] = score
        print(f"- {metric.capitalize()}: {score:.4f}")
    print("="*50 + "\n")
    
    # Print detailed table
    print("CHI TIẾT ĐÁNH GIÁ TỪNG CÂU HỎI:")
    print(df[["question", "faithfulness", "answer_relevancy"]].to_string(index=False))
else:
    # Fallback to saving raw data with empty scores
    df = pd.DataFrame(dataset_data)
    df["faithfulness"] = None
    df["answer_relevancy"] = None
    
    print("\n" + "="*50)
    print(" CẢNH BÁO: CHẤM ĐIỂM RAGAS THẤT BẠI (LỖI RATE LIMIT)")
    print("="*50)
    print("Đã lưu kết quả RAG Pipeline thô. Khi có quota API, bạn có thể chạy lại để chấm điểm.")
    print("="*50 + "\n")
    
    print("CHI TIẾT CÂU TRẢ LỜI ĐÃ THU THẬP:")
    print(df[["question", "answer"]].to_string(index=False))

df.to_csv(csv_path, index=False, encoding="utf-8-sig")
logger.success(f"Saved evaluation results to {csv_path}")
