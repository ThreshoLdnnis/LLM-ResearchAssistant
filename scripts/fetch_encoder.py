"""Download the exact ONNX export used by the experiment, then verify both hashes."""
from hashlib import sha256
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
import requests
from finrag.search import MODEL, REV

FILES = {"onnx/model_quantized.onnx": "15b717c382bcb518ba457b93ea6850ede7f4f1cd8937454aa06972366cd19bcc",
         "tokenizer.json": "48cea5d44424912a6fd1ea647bf4fe50b55ab8b1e5879c3275f80e339e8fae26"}


def main():
    MODEL.mkdir(parents=True, exist_ok=True)
    host = os.getenv("HF_ENDPOINT","https://huggingface.co").rstrip("/")
    for name, digest in FILES.items():
        path = MODEL / Path(name).name
        if path.exists() and sha256(path.read_bytes()).hexdigest() == digest:
            continue
        r = requests.get(f"{host}/Xenova/bge-small-zh-v1.5/resolve/{REV}/{name}", timeout=(15,120))
        r.raise_for_status()
        if sha256(r.content).hexdigest() != digest:
            raise ValueError(f"模型文件哈希不匹配 {name}")
        with NamedTemporaryFile(dir=MODEL, delete=False) as f:
            f.write(r.content)
        os.replace(f.name,path)
    print("BGE encoder verified")


if __name__ == "__main__":
    main()

