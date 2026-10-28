"""Download pinned, free CPU ONNX CLIP models, without torch or paid APIs.

Source: https://huggingface.co/Xenova/clip-vit-base-patch32
English model; application documents its Chinese topic-dictionary mapping.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from storybook.retrieval import MODEL_FILES, MODEL_REPO, MODEL_REVISION


def main() -> int:
    parser = argparse.ArgumentParser(description="下载约156 MB免费ONNX CLIP并验证CPU编码器。")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--base-url", default="https://huggingface.co", help="默认官方Hugging Face；可显式指定可用的下载镜像。")
    parser.add_argument("--skip-verify", action="store_true", help="只下载；API的clip_ready仍由实际加载判断。")
    args = parser.parse_args()
    destination = args.root.resolve() / "data" / "models" / "clip"
    destination.mkdir(parents=True, exist_ok=True)
    # Existing verified downloads remain usable; new files replace atomically.
    records = []
    for filename in MODEL_FILES:
        path = destination / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        url = f"{args.base_url.rstrip('/')}/{MODEL_REPO}/resolve/{MODEL_REVISION}/{filename}"
        minimum = 10_000_000 if filename.endswith(".onnx") else 100
        if not path.exists() or path.stat().st_size < minimum:
            print(f"下载 {filename} …", flush=True)
            temporary = path.with_suffix(path.suffix + ".part")
            request = urllib.request.Request(url, headers={"User-Agent": "storybook-lab-clip-setup/1.0"})
            try:
                with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as target:
                    total = int(response.headers.get("Content-Length", "0"))
                    received = 0
                    while chunk := response.read(1024 * 1024):
                        target.write(chunk)
                        received += len(chunk)
                        if received // (10 * 1024 * 1024) != (received - len(chunk)) // (10 * 1024 * 1024):
                            print(f"  {received / 1_000_000:.1f} MB" + (f" / {total / 1_000_000:.1f} MB" if total else ""), flush=True)
                if temporary.stat().st_size < minimum:
                    raise RuntimeError(f"下载内容过短，可能收到错误页：{filename}")
                if not filename.endswith(".onnx"):
                    json.loads(temporary.read_text(encoding="utf-8"))
                os.replace(temporary, path)
            except Exception as exc:
                print(f"下载失败 {filename}：{exc}\n应用仍会明确使用标签降级；可稍后重新运行此脚本。", file=sys.stderr)
                return 1
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        records.append({"file": filename, "bytes": path.stat().st_size, "sha256": digest, "source": url})
        print(f"已就绪 {filename}: {path.stat().st_size / 1_000_000:.2f} MB", flush=True)
    verified = False
    if not args.skip_verify:
        from PIL import Image
        from storybook.retrieval import AssetSearch
        search = AssetSearch(args.root)
        if not search.clip_ready:
            print(search.clip_error, file=sys.stderr)
            return 2
        import tempfile
        with tempfile.TemporaryDirectory(prefix="clip-verify-", dir=destination) as temp:
            image_path = Path(temp) / "sample.png"
            Image.new("RGB", (256, 256), color=(60, 140, 220)).save(image_path)
            text_vector = search._clip_text("a blue square")
            image_vector = search._clip_image(image_path)
            if text_vector.shape != image_vector.shape or text_vector.shape != (512,):
                raise RuntimeError("模型投影维度不匹配。")
            print(f"实际ONNX CPU图文编码验证通过：512维，余弦相似度 {float(text_vector @ image_vector):.4f}", flush=True)
            verified = True
    (destination / "download_manifest.json").write_text(json.dumps({"repo": MODEL_REPO, "revision": MODEL_REVISION, "verified_cpu_embeddings": verified, "files": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("CLIP安装完成。中文查询将显式映射有限的英文主题词典。", flush=True)
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
