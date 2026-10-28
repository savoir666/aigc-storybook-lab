"""Local, inspectable retrieval: TF–IDF text vectors and optional ONNX CLIP.

CLIP is the English OpenAI model exported by Xenova. Chinese queries use an
explicit, limited topic dictionary; this is not a Chinese CLIP model or an LLM
translation service. Missing/broken models are reported as a labelled fallback.
"""
from __future__ import annotations

import importlib.util
import json
import re
import threading
from pathlib import Path
from typing import Any

import numpy as np


MODEL_REPO = "Xenova/clip-vit-base-patch32"
MODEL_REVISION = "4c1807b705b1d015fb032789cc4d221b23025a6f"
MODEL_FILES = ("onnx/text_model_quantized.onnx", "onnx/vision_model_quantized.onnx", "tokenizer.json", "preprocessor_config.json")

# Deliberately published dictionary, rather than pretending to translate all Chinese.
ZH_EN = {
    "森林探险": "forest adventure", "太空旅行": "space travel", "海洋奇遇": "ocean adventure",
    "太空": "outer space", "宇宙": "universe", "森林": "forest", "海洋": "ocean",
    "海底": "underwater", "沙滩": "beach", "海滩": "beach", "草地": "meadow",
    "城堡": "castle", "星球": "planet", "星空": "starry sky", "星星": "stars",
    "月亮": "moon", "月球": "moon", "太阳": "sun", "火箭": "rocket",
    "飞船": "spaceship", "宇航员": "astronaut", "机器人": "robot", "外星人": "alien",
    "珊瑚": "coral reef", "鲸鱼": "whale", "海豚": "dolphin", "海龟": "sea turtle",
    "小鱼": "fish", "鱼儿": "fish", "章鱼": "octopus", "水母": "jellyfish",
    "狐狸": "fox", "兔子": "rabbit", "小兔": "rabbit", "熊猫": "panda",
    "小熊": "bear", "松鼠": "squirrel", "猫头鹰": "owl", "蝴蝶": "butterfly",
    "小鸟": "bird", "树木": "trees", "大树": "tree", "树屋": "tree house",
    "花朵": "flowers", "蘑菇": "mushrooms", "河流": "river", "小河": "river",
    "瀑布": "waterfall", "山": "mountain", "彩虹": "rainbow", "雨": "rain",
    "雪": "snow", "夜晚": "night", "白天": "daytime", "日落": "sunset",
    "女孩": "girl", "男孩": "boy", "孩子": "child", "儿童": "children",
    "朋友": "friends", "友谊": "friendship", "勇气": "courage", "分享": "sharing",
    "冒险": "adventure", "探险": "adventure", "温暖": "warm", "快乐": "happy",
    "悲伤": "sad", "绘本": "storybook illustration", "水彩": "watercolor",
}


def translate_clip_query(query: str) -> dict[str, str]:
    remainder = query
    terms: list[str] = []
    for zh in sorted(ZH_EN, key=len, reverse=True):
        if zh in remainder:
            terms.append(ZH_EN[zh])
            remainder = remainder.replace(zh, " ")
    english = " ".join(re.findall(r"[A-Za-z][A-Za-z0-9 '-]*", remainder)).strip()
    if english:
        terms.append(english)
    terms = list(dict.fromkeys(terms))
    return {
        "text": "a children's storybook illustration of " + (", ".join(terms) or "a scene"),
        "method": "explicit Chinese topic dictionary + original English",
        "unmapped_chinese": "".join(re.findall(r"[\u4e00-\u9fff]+", remainder)),
    }


class AssetSearch:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.library = self.root / "data" / "library"
        self.model_dir = self.root / "data" / "models" / "clip"
        self._manifest_stamp = None
        self._assets: list[dict] = []
        self._vectorizer = self._matrix = None
        self._text_session = self._vision_session = self._tokenizer = None
        self._image_vectors: dict[str, tuple[tuple, np.ndarray]] = {}
        self._lock = threading.RLock()
        self.clip_error = "尚未安装CLIP模型；图片使用标签文本向量降级检索。"

    def _load_manifest(self) -> None:
        path = self.library / "manifest.json"
        stamp = (path.stat().st_mtime_ns, path.stat().st_size) if path.exists() else None
        if stamp == self._manifest_stamp and self._vectorizer is not None:
            return
        raw: Any = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else []
        if isinstance(raw, list):
            assets = raw
        elif isinstance(raw.get("assets"), list):
            assets = raw["assets"]
        else:
            assets = [dict(a, type=a.get("type", kind)) for key, kind in (("templates", "template"), ("images", "image"), ("sounds", "sound")) for a in raw.get(key, [])]
        self._assets = []
        aliases = {"text": "template", "templates": "template", "images": "image", "audio": "sound", "sounds": "sound"}
        for index, asset in enumerate(assets):
            if not isinstance(asset, dict):
                continue
            item = dict(asset)
            item["type"] = aliases.get(item.get("type", item.get("kind", "template")), item.get("type", item.get("kind", "template")))
            item.setdefault("id", f"asset-{index}")
            item.setdefault("title", item.get("name", item["id"]))
            item.setdefault("description", item.get("text", ""))
            item.setdefault("tags", [])
            if not item.get("url") and item.get("path"):
                local = self._asset_path(item)
                if local is not None:
                    item["url"] = "/files/library/" + local.relative_to(self.library).as_posix()
            self._assets.append(item)
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
        except ImportError as exc:
            raise RuntimeError("文本向量检索需要 scikit-learn；请安装 requirements.txt。") from exc
        self._vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(1, 3), sublinear_tf=True, norm="l2")
        documents = [self._document(a) or "空素材" for a in self._assets]
        self._matrix = self._vectorizer.fit_transform(documents or ["空素材库"])
        self._manifest_stamp = stamp

    @staticmethod
    def _document(asset: dict) -> str:
        tags = asset.get("tags", [])
        if isinstance(tags, list):
            tags = " ".join(map(str, tags))
        return " ".join(json.dumps(asset.get(key, ""), ensure_ascii=False) if isinstance(asset.get(key), (dict, list)) else str(asset.get(key, "")) for key in ("title", "description", "text", "theme", "en_description", "premise", "characters", "outline", "age_range")) + " " + str(tags)

    def _asset_path(self, asset: dict) -> Path | None:
        value = str(asset.get("path", asset.get("file", "")))
        if not value and str(asset.get("url", "")).startswith("/files/library/"):
            value = str(asset["url"])[len("/files/library/"):]
        if not value:
            return None
        for candidate in (self.library / value, self.root / value):
            resolved = candidate.resolve()
            if resolved.is_relative_to(self.library) and resolved.is_file():
                return resolved
        return None

    def _ensure_clip(self) -> bool:
        if self._text_session is not None:
            return True
        missing = [filename for filename in MODEL_FILES if not (self.model_dir / filename).is_file()]
        if missing:
            self.clip_error = "CLIP模型未就绪；运行 python scripts/setup_clip.py。图片当前使用标签文本向量降级。"
            return False
        if not all(importlib.util.find_spec(m) for m in ("onnxruntime", "tokenizers")):
            self.clip_error = "缺少 onnxruntime/tokenizers；图片当前使用标签文本向量降级。"
            return False
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 4
            opts.inter_op_num_threads = 1
            text_session = ort.InferenceSession(str(self.model_dir / MODEL_FILES[0]), sess_options=opts, providers=["CPUExecutionProvider"])
            vision_session = ort.InferenceSession(str(self.model_dir / MODEL_FILES[1]), sess_options=opts, providers=["CPUExecutionProvider"])
            tokenizer = Tokenizer.from_file(str(self.model_dir / "tokenizer.json"))
            tokenizer.enable_truncation(max_length=77)
            tokenizer.enable_padding(length=77, pad_id=49407, pad_token="<|endoftext|>")
            self._text_session, self._vision_session, self._tokenizer = text_session, vision_session, tokenizer
            self.clip_error = ""
            return True
        except Exception as exc:
            self.clip_error = f"CLIP初始化失败（{type(exc).__name__}）；图片使用标签文本向量降级。"
            return False

    def release_clip(self):
        """Release inference sessions before long local encoding; results stay saved."""
        import gc
        with self._lock:
            self._text_session=self._vision_session=self._tokenizer=None
            self._image_vectors.clear()
            gc.collect()

    @property
    def clip_ready(self) -> bool:
        with self._lock:
            return self._ensure_clip()

    @property
    def counts(self) -> dict[str, int]:
        with self._lock:
            self._load_manifest()
            return {plural: sum(a["type"] == kind for a in self._assets) for plural, kind in (("templates", "template"), ("images", "image"), ("sounds", "sound"))}

    @staticmethod
    def _unit(vector: np.ndarray) -> np.ndarray:
        vector = np.asarray(vector, dtype=np.float32).reshape(-1)
        norm = float(np.linalg.norm(vector))
        if not norm:
            raise ValueError("CLIP返回零向量。")
        return vector / norm

    @staticmethod
    def _embedding(session: Any, feeds: dict, expected: str) -> np.ndarray:
        values = session.run(None, feeds)
        names = [o.name for o in session.get_outputs()]
        if expected in names:
            return values[names.index(expected)][0]
        for value in values:
            if value.ndim == 2 and value.shape[-1] == 512:
                return value[0]
        raise ValueError(f"CLIP模型缺少{expected}投影输出。")

    def _clip_text(self, text: str) -> np.ndarray:
        encoding = self._tokenizer.encode(text)
        ids = np.asarray([encoding.ids], dtype=np.int64)
        mask = np.asarray([encoding.attention_mask], dtype=np.int64)
        feeds = {}
        for input_node in self._text_session.get_inputs():
            if input_node.name == "input_ids":
                feeds[input_node.name] = ids
            elif input_node.name == "attention_mask":
                feeds[input_node.name] = mask
            elif input_node.name == "position_ids":
                feeds[input_node.name] = np.arange(ids.shape[1], dtype=np.int64)[None, :]
            else:
                raise ValueError(f"未知CLIP输入：{input_node.name}")
        return self._unit(self._embedding(self._text_session, feeds, "text_embeds"))

    def _clip_image(self, path: Path) -> np.ndarray:
        from PIL import Image
        fingerprint = (path.stat().st_mtime_ns, path.stat().st_size)
        cached = self._image_vectors.get(str(path))
        if cached and cached[0] == fingerprint:
            return cached[1]
        config = json.loads((self.model_dir / "preprocessor_config.json").read_text(encoding="utf-8"))
        size = config.get("size", 224)
        short = size.get("shortest_edge", 224) if isinstance(size, dict) else size
        crop = config.get("crop_size", 224)
        height = crop.get("height", 224) if isinstance(crop, dict) else crop
        width = crop.get("width", 224) if isinstance(crop, dict) else crop
        with Image.open(path) as image:
            image = image.convert("RGB")
            ratio = short / min(image.size)
            image = image.resize((round(image.width * ratio), round(image.height * ratio)), Image.Resampling.BICUBIC)
            left, top = (image.width - width) // 2, (image.height - height) // 2
            image = image.crop((left, top, left + width, top + height))
            pixels = np.asarray(image, dtype=np.float32) / 255.0
        mean = np.asarray(config.get("image_mean", [0.48145466, 0.4578275, 0.40821073]), dtype=np.float32)
        std = np.asarray(config.get("image_std", [0.26862954, 0.26130258, 0.27577711]), dtype=np.float32)
        pixels = ((pixels - mean) / std).transpose(2, 0, 1)[None].astype(np.float32)
        feeds = {self._vision_session.get_inputs()[0].name: pixels}
        vector = self._unit(self._embedding(self._vision_session, feeds, "image_embeds"))
        self._image_vectors[str(path)] = (fingerprint, vector)
        return vector

    def search(self, query: str, kind: str = "all", limit: int = 12) -> dict:
        with self._lock:
            self._load_manifest()
            aliases = {"templates": "template", "text": "template", "images": "image", "sounds": "sound", "audio": "sound"}
            kind = aliases.get(kind, kind)
            if kind not in {"all", "template", "image", "sound"}:
                raise ValueError("素材类型必须是 all/template/image/sound。")
            limit = max(0, min(int(limit), 100))
            query = str(query or "").strip()[:1000]
            scores = (self._matrix @ self._vectorizer.transform([query]).T).toarray().reshape(-1) if self._assets else []
            ready = self._ensure_clip()
            translated = translate_clip_query(query)
            text_vector = None
            if query and ready and kind in {"all", "image"}:
                try:
                    text_vector = self._clip_text(translated["text"])
                except Exception as exc:
                    ready = False
                    self.clip_error = f"CLIP文本推理失败（{type(exc).__name__}）；图片使用标签文本向量降级。"
            results = []
            image_failures = []
            for index, asset in enumerate(self._assets):
                if kind != "all" and asset["type"] != kind:
                    continue
                score = float(scores[index]) if query else 0.0
                item_engine = "TF-IDF字符向量（标签文本降级）" if asset["type"] == "image" else "TF-IDF字符向量"
                if asset["type"] == "image" and text_vector is not None:
                    path = self._asset_path(asset)
                    try:
                        if path is None:
                            raise FileNotFoundError("素材缺少本地图像文件")
                        score = float(np.dot(text_vector, self._clip_image(path)))
                        item_engine = "ONNX CLIP图文余弦相似度"
                    except Exception as exc:
                        image_failures.append(f"{asset['id']}: {type(exc).__name__}")
                result = {k: asset.get(k, "" if k != "tags" else []) for k in ("id", "type", "title", "description", "url", "tags")}
                result.update(score=round(score, 6), engine=item_engine)
                results.append(result)
            results.sort(key=lambda row: row["score"], reverse=True)
            engine = "文本/音效：TF-IDF字符向量；图片：" + ("ONNX CLIP（英文编码器＋显式中文主题词典）" if ready else "标签文本向量降级，非CLIP")
            suggestions = {"query": query, "template_ids": [r["id"] for r in results if r["type"] == "template"][:2],
                           "image_ids": [r["id"] for r in results if r["type"] == "image"][:3],
                           "sound_ids": [r["id"] for r in results if r["type"] == "sound"][:2],
                           "visual_prompt_hint": translated["text"],
                           "usage": "依据检索素材选定故事背景，复用角色设定；图片与音效作为参考。相似度为检索分数，不是质量保证。"}
            return {"results": results[:limit], "engine": engine, "counts": self.counts, "clip_ready": ready,
                    "clip_query": translated, "warning": self.clip_error or ("部分图片CLIP推理失败，已逐条标注标签降级。" if image_failures else ""),
                    "image_errors": image_failures, "generation_suggestions": suggestions}
