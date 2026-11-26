"""Fetch known GGUF weights for the two local research runs."""
import argparse
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
import os
import requests
from finrag.store import ROOT

HASHES={"0.5":"74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db",
        "1.5":"6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e"}


def filehash(path):
    from hashlib import file_digest
    with path.open("rb") as f:
        return file_digest(f,"sha256").hexdigest()


def fetch(size):
    name=f"qwen2.5-{size}b-instruct-q4_k_m.gguf"
    target=ROOT/"data/models"/name
    target.parent.mkdir(exist_ok=True,parents=True)
    if target.exists() and filehash(target)==HASHES[size]:
        return target
    url=f"https://modelscope.cn/models/Qwen/Qwen2.5-{size}B-Instruct-GGUF/resolve/master/{name}"
    with requests.get(url,stream=True,timeout=(20,180)) as r:
        r.raise_for_status()
        with NamedTemporaryFile(dir=target.parent,delete=False) as out:
            path=Path(out.name)
            try:
                for chunk in r.iter_content(1024*1024):
                    out.write(chunk)
            except BaseException:
                out.close()
                path.unlink(missing_ok=True)
                raise
        if filehash(path)!=HASHES[size]:
            path.unlink()
            raise ValueError("GGUF 哈希不匹配")
        os.replace(path,target)
    return target


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("size",choices=HASHES)
    print(fetch(p.parse_args().size))

