import pandas as pd
from neo4j import GraphDatabase

# 1. CẤU HÌNH KẾT NỐI (Thay bằng thông tin từ AuraDB của bạn)
NEO4J_URI = "neo4j+s://e75033fe.databases.neo4j.io"
NEO4J_USER = "e75033fe"
NEO4J_PASSWORD = "aOoe9cd3wsilc-VXAOq3kDIvMByjA3yJvcXZNNSmhOc"

class TechGraphIngestor:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def ingest_data(self, df, category):
        with self.driver.session() as session:
            for _, row in df.iterrows():
                session.execute_write(self._create_nodes_and_relationships, row, category)

    @staticmethod
    def _create_nodes_and_relationships(tx, row, category):
        # 1. Tạo/Cập nhật Node Brand (kèm Popularity)
        tx.run("""
            MERGE (b:Brand {name: $brand_name})
            SET b.popularity = $brand_pop
        """, brand_name=str(row['brand']).lower().strip(), 
             brand_pop=row.get('popularity', 1))

        # 2. Tạo Node Product
        # Chúng ta dùng MERGE dựa trên tên model để tránh trùng lặp
        tx.run("""
            MATCH (b:Brand {name: $brand_name})
            MERGE (p:Product {model_name: $model_name, category: $category})
            SET p.price = $price, 
                p.rating = $rating, 
                p.popularity = $product_pop,
                p.specs = $specs
            MERGE (p)-[:MADE_BY]->(b)
        """, 
        brand_name=str(row['brand']).lower().strip(),
        model_name=row['model_name'],
        category=category,
        price=float(row['price']),
        rating=float(row['rating']) if pd.notnull(row['rating']) else 0,
        product_pop=row.get('popularity', 1),
        specs=row.get('specs_summary', "")
        )

        # 3. Tạo Node Processor (nếu có - dành cho Laptop/Phone)
        if 'processor' in row and pd.notnull(row['processor']) and str(row['processor']) != "N/A":
            tx.run("""
                MATCH (p:Product {model_name: $model_name})
                MERGE (proc:Processor {name: $proc_name})
                MERGE (p)-[:USES_PROCESSOR]->(proc)
            """, model_name=row['model_name'], proc_name=str(row['processor']).strip())

# --- THỰC THI ---

# Đọc dữ liệu (Bạn hãy thay đường dẫn file thực tế của mình nhé)
df_phone = pd.read_csv(r"c:\Users\User\Desktop\PROJECT 2\Project_2\phone.csv")
df_headphone = pd.read_csv(r"c:\Users\User\Desktop\PROJECT 2\Project_2\headphone.csv")
df_laptop = pd.read_csv(r"c:\Users\User\Desktop\PROJECT 2\Project_2\laptop.csv")

# Khởi tạo Ingestor
ingestor = TechGraphIngestor(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

# Nạp từng loại
print("Đang nạp dữ liệu Laptop...")
ingestor.ingest_data(df_laptop, "laptop")

print("Đang nạp dữ liệu Điện thoại...")
ingestor.ingest_data(df_phone, "phone")

print("Đang nạp dữ liệu Tai nghe...")
# Lưu ý: Với headphone, cần đảm bảo cột tên model là 'model'
df_headphone = df_headphone.rename(columns={'model': 'model'})
ingestor.ingest_data(df_headphone, "headphone")

ingestor.close()
print("Hoàn tất nạp dữ liệu vào Knowledge Graph!")