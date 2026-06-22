import os
from neo4j import GraphDatabase
from qdrant_client import QdrantClient
from dotenv import load_dotenv

load_dotenv()

# --- KHỞI TẠO KẾT NỐI ---
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")

neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
qdrant = QdrantClient(QDRANT_URL)

def reset_databases():
    print("⚠️ BẮT ĐẦU QUÁ TRÌNH RESET DATABASE...")

    # 1. XÓA SẠCH NEO4J
    print("1. Đang dọn dẹp Neo4j Aura Cloud...")
    try:
        with neo4j_driver.session() as session:
            # Lệnh DETACH DELETE n sẽ xóa sạch mọi Nodes và Relationships
            session.run("MATCH (n) DETACH DELETE n")
        print("   ✅ Đã xóa sạch Graph DB!")
    except Exception as e:
        print(f"   ❌ Lỗi khi xóa Neo4j: {e}")

    # 2. XÓA SẠCH QDRANT
    print("\n2. Đang dọn dẹp Qdrant Vector DB...")
    try:
        collection_name = "product_reviews"
        if qdrant.collection_exists(collection_name):
            qdrant.delete_collection(collection_name)
            print(f"   ✅ Đã xóa Collection '{collection_name}'!")
        else:
            print(f"   ⏭️ Collection '{collection_name}' không tồn tại, bỏ qua.")
    except Exception as e:
        print(f"   ❌ Lỗi khi xóa Qdrant: {e}")

    print("\n🎉 RESET THÀNH CÔNG! BẠN CÓ THỂ CHẠY LẠI FILE load_data.py BÂY GIỜ.")

if __name__ == "__main__":
    # Yêu cầu xác nhận để chống chạy nhầm
    confirm = input("Bạn có chắc chắn muốn XÓA SẠCH toàn bộ Database không? (y/n): ")
    if confirm.lower() == 'y':
        reset_databases()
    else:
        print("Đã hủy thao tác.")