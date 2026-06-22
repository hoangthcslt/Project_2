# Sử dụng image Python nhẹ bản slim
FROM python:3.10-slim

# Thiết lập thư mục làm việc trong container
WORKDIR /app

# Cài đặt các công cụ hệ thống cần thiết (nếu có)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements và cài đặt thư viện
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir langchain-google-genai

# Copy toàn bộ mã nguồn, dữ liệu và mô hình cục bộ vào container
COPY src/ ./src
COPY data/ ./data
COPY all-MiniLM-L6-v2/ ./all-MiniLM-L6-v2
COPY .env .

# Khai báo biến môi trường cho Python chạy UTF-8 chuẩn
ENV PYTHONUTF8=1

# Mở cổng 8000
EXPOSE 8000

# Lệnh chạy FastAPI server
CMD ["uvicorn", "src.api.server:app", "--host", "0.0.0.0", "--port", "8000"]