import importlib.util
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from storybook.config import ROOT, public_settings
from storybook.retrieval import AssetSearch
from storybook.media import ffmpeg_path
search = AssetSearch(ROOT)
print(json.dumps({'python':sys.version.split()[0], 'dependencies':{m:bool(importlib.util.find_spec(m)) for m in ['fastapi','edge_tts','langchain_core','onnxruntime','tokenizers']}, 'ffmpeg':ffmpeg_path(), 'assets':search.counts,'clip_ready':search.clip_ready,'settings':public_settings()},ensure_ascii=False,indent=2))
