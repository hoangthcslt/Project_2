import os
import sys
from dotenv import load_dotenv
import urllib3

# 1. Tự động cấu hình mã hóa UTF-8 cho stdout/stderr để tránh lỗi UnicodeEncodeError trên Windows
if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 2. Tự động nạp các biến môi trường từ file .env vào os.environ
load_dotenv()

# 3. Bỏ qua xác thực SSL cho huggingface_hub globally (cả requests và httpx backend)
# giúp khắc phục triệt để lỗi "Distant resource does not seem to be on huggingface.co"
os.environ["HF_HUB_DISABLE_SSL_VERIFICATION"] = "1"

# Tắt các cảnh báo bảo mật về việc verify=False để tránh làm loãng console log
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
