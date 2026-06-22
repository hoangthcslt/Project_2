import os
import time
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

files = [
    "config.json",
    "config_sentence_transformers.json",
    "modules.json",
    "pytorch_model.bin",
    "sentence_bert_config.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
    "1_Pooling/config.json"
]

base_url = "https://hf-mirror.com/sentence-transformers/all-MiniLM-L6-v2/resolve/main/"
local_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "all-MiniLM-L6-v2"))

print(f"Starting download of all-MiniLM-L6-v2 model files to '{local_dir}'...")

for f in files:
    url = base_url + f
    local_path = os.path.join(local_dir, f.replace("/", os.sep))
    
    # Skip if file already exists and has a size > 0 (to avoid re-downloading large files like pytorch_model.bin)
    if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
        print(f"File {f} already exists. Skipping.")
        continue
        
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    
    success = False
    for attempt in range(1, 6):
        print(f"Downloading {f} (Attempt {attempt}/5)...")
        try:
            r = requests.get(url, verify=False, stream=True, timeout=15)
            r.raise_for_status()
            with open(local_path, "wb") as fd:
                for chunk in r.iter_content(chunk_size=8192):
                    fd.write(chunk)
            print(f"Successfully saved {f}")
            success = True
            break
        except Exception as e:
            print(f"Attempt {attempt} failed: {e}")
            time.sleep(2 * attempt)
            
    if not success:
        print(f"FATAL: FAILED to download {f} after 5 attempts.")

print("Download process completed.")
