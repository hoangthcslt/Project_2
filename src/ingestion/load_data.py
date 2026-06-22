import os
from dotenv import load_dotenv
# Load các biến môi trường từ file .env trước khi import các thư viện khác
load_dotenv()

import uuid
from pathlib import Path
import pandas as pd
from neo4j import GraphDatabase
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
from sentence_transformers import SentenceTransformer

# 1. KHỞI TẠO KẾT NỐI (ĐỌC TỪ .ENV CHUẨN RULE 00)
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")

from src.config.settings import get_settings

print("Đang kết nối tới Neo4j Aura Cloud...")
neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))

print("Đang kết nối tới Qdrant Local...")
qdrant = QdrantClient(QDRANT_URL)

print("Đang tải Embedding Model (Offline hoặc Online)...")
embed_model = SentenceTransformer(get_settings().resolved_embedding_model)

def clean_val(val, default="Unknown"):
    # Nếu giá trị là NaN (Pandas), None, hoặc chuỗi rỗng / chuỗi "nan" -> Ép về Mặc định
    if pd.isna(val) or val is None or str(val).strip() == "" or str(val).strip().lower() == "nan":
        return default
    return str(val).strip()

def process_data():
    csv_files =["laptop.csv", "phone.csv", "headphone.csv"]
    
    if not qdrant.collection_exists("product_reviews"):
        print("Tạo Collection 'product_reviews' trên Qdrant...")
        qdrant.create_collection(
            collection_name="product_reviews",
            vectors_config=VectorParams(size=384, distance=Distance.COSINE)
        )

    for file_name in csv_files:
        file_path = Path(__file__).parent.parent.parent / "data" / file_name
        print(f"\n{'='*50}")
        print(f"🚀 ĐANG XỬ LÝ FILE: {file_name}")
        print(f"{'='*50}")
        
        try:
            # Đọc file với low_memory=False để tránh warning mixed types
            df = pd.read_csv(file_path, low_memory=False)
            
            # SỬA LỖI: Lọc bỏ toàn bộ dòng trống/rác của Excel (laptop.csv bị phình lên 1 triệu dòng trống ở cuối)
            if 'model_name' in df.columns:
                df = df.dropna(subset=['model_name'])
                df = df[df['model_name'].astype(str).str.strip() != '']
                df = df[df['model_name'].astype(str).str.lower() != 'nan']
                
            # QUY ĐỔI GIÁ TIỀN SANG VND CHO TỪNG DANH MỤC
            if 'price' in df.columns:
                # Ép kiểu cột price sang số (float), giá trị lỗi chuyển thành NaN
                df['price'] = pd.to_numeric(df['price'], errors='coerce')
                
                # Thực hiện nhân tỉ giá quy đổi tương ứng sang VND
                if file_name == "phone.csv":
                    df['price'] = df['price'] * 300.0
                    print(f"[{file_name}] 🔄 Đã quy đổi giá tiền từ INR sang VND (nhân 300) thành công.")
                elif file_name in ["laptop.csv", "headphone.csv"]:
                    df['price'] = df['price'] * 25000.0
                    print(f"[{file_name}] 🔄 Đã quy đổi giá tiền từ USD sang VND (nhân 25000) thành công.")
            
            df = df.fillna("Unknown")
            
            # -------------------------------------------------------------
            # BƯỚC 1: XỬ LÝ DỮ LIỆU ĐỘNG (DYNAMIC SPECS) CHO NEO4J
            # -------------------------------------------------------------
            print(f"[{file_name}] Đang chuẩn bị dữ liệu động cho Neo4j...")
            
            # Cột dùng cho Graph nodes, không cho specs
            core_cols = ['brand', 'os_type', 'category', 'model_name', 'review']
            
            records_for_neo4j = []
            for _, row in df.iterrows():
                row_dict = row.to_dict()
                
                model_name_clean = clean_val(row_dict.get("model_name"), "")
                if not model_name_clean:
                    continue 
                
                brand_clean = clean_val(row_dict.get("brand"), "Unknown")
                os_clean = clean_val(row_dict.get("os_type"), "Unknown").lower()
                category_clean = clean_val(row_dict.get("category"), "Unknown").lower().strip()
                if category_clean == "headphones":
                    category_clean = "headphone"
                elif category_clean == "phones":
                    category_clean = "phone"
                elif category_clean == "laptops":
                    category_clean = "laptop"
                
                # Quét làm sạch specs, đảm bảo price là float thực tế biểu diễn cho VND
                specs_dict = {}
                for k, v in row_dict.items():
                    if k in core_cols:
                        continue
                    if k == 'price':
                        try:
                            if v == "Unknown" or pd.isna(v) or v is None:
                                continue
                            specs_dict[k] = float(v)
                        except (ValueError, TypeError):
                            continue
                    else:
                        specs_dict[k] = clean_val(v, "N/A")
                
                records_for_neo4j.append({
                    "model_name": model_name_clean,
                    "brand": brand_clean,
                    "os_type": os_clean,
                    "category": category_clean,
                    "specs": specs_dict  
                })

            print(f"[{file_name}] Đang đẩy {len(records_for_neo4j)} bản ghi vào Neo4j...")
            # LƯU Ý KỸ: Dưới đây ta dùng ĐỒNG NHẤT row.os_type (VIẾT THƯỜNG), KHÔNG viết hoa OS_type
            cypher_query = """
            UNWIND $rows AS row
            MERGE (b:Brand {name: row.brand})
            MERGE (os:OS {name: row.os_type})
            MERGE (c:Category {name: row.category})
            MERGE (p:Product {id: row.model_name})
            
            SET p += row.specs  
            
            MERGE (p)-[:BELONGS_TO]->(b)
            MERGE (p)-[:RUNS_ON]->(os)
            MERGE (p)-[:IS_CATEGORY]->(c)
            """
            
            # Batch đẩy vào Neo4j (Tách mỗi lô 1000 dòng để không quá tải Cloud)
            batch_size_neo4j = 1000
            with neo4j_driver.session() as session:
                for i in range(0, len(records_for_neo4j), batch_size_neo4j):
                    batch = records_for_neo4j[i:i + batch_size_neo4j]
                    session.run(cypher_query, rows=batch)
            print(f"[{file_name}] ✅ Đã nạp thành công Node và Cấu hình vào Neo4j!")

            # --- CHUẨN BỊ VECTOR CHO QDRANT ---
            if 'review' in df.columns:
                print(f"[{file_name}] Đang chuẩn bị và lọc tập Reviews...")
                valid_reviews = []
                for _, row in df.iterrows():
                    review_text = clean_val(row.get('review'), "")
                    model_name_clean = clean_val(row.get('model_name'), "")
                    
                    if not review_text or review_text == "Unknown" or len(review_text) < 10 or not model_name_clean:
                        continue
                        
                    valid_reviews.append({
                        "review_text": review_text,
                        "model_name": model_name_clean,
                        "brand": clean_val(row.get('brand'), "Unknown")
                    })
                
                if valid_reviews:
                    print(f"[{file_name}] Đang Vector hóa {len(valid_reviews)} reviews bằng Batch Encoding (rất nhanh)...")
                    texts_to_embed = [item["review_text"] for item in valid_reviews]
                    # Batch encoding: dùng show_progress_bar=True để hiển thị tiến trình
                    vectors = embed_model.encode(texts_to_embed, batch_size=128, show_progress_bar=True)
                    
                    print(f"[{file_name}] Đang chuẩn bị các PointStruct để đẩy vào Qdrant...")
                    points = []
                    for idx, item in enumerate(valid_reviews):
                        review_id = str(uuid.uuid4())
                        points.append(PointStruct(
                            id=review_id,
                            vector=vectors[idx].tolist(),
                            payload={
                                "product_id": item["model_name"],
                                "brand": item["brand"],
                                "review_text": item["review_text"]
                            }
                        ))
                        
                    batch_size_qdrant = 500
                    for i in range(0, len(points), batch_size_qdrant):
                        batch = points[i:i + batch_size_qdrant]
                        qdrant.upsert(collection_name="product_reviews", points=batch)
                    print(f"[{file_name}] ✅ Đã đẩy {len(points)} vector reviews vào Qdrant!")
            else:
                print(f"[{file_name}] ⏭️ BỎ QUA Qdrant vì không có cột reviews.")
                
        except Exception as e:
            print(f"❌ LỖI khi xử lý file {file_name}: {str(e)}")

    print("\n🎉 HOÀN TẤT TOÀN BỘ QUÁ TRÌNH INGESTION!")

if __name__ == "__main__":
    process_data()