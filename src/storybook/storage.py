"""Atomic, path-constrained project persistence."""
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from .config import PROJECTS, DATA

_lock = threading.RLock()

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def project_dir(pid: str) -> Path:
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,70}', pid):
        raise ValueError('作品编号无效。')
    return PROJECTS / pid

def new_id():
    return uuid4().hex[:16]

def save_project(project: dict):
    folder = project_dir(project['id'])
    folder.mkdir(parents=True, exist_ok=True)
    with _lock:
        project['updated_at'] = now()
        tmp = folder / 'project.json.tmp'
        tmp.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(folder / 'project.json')
    return project

def load_project(pid):
    path = project_dir(pid) / 'project.json'
    if not path.exists():
        raise FileNotFoundError('没有找到这本故事。')
    return json.loads(path.read_text(encoding='utf-8'))

def list_projects():
    PROJECTS.mkdir(parents=True, exist_ok=True)
    result = []
    for p in PROJECTS.glob('*/project.json'):
        try:
            result.append(json.loads(p.read_text(encoding='utf-8')))
        except (OSError, json.JSONDecodeError):
            continue
    return sorted(result, key=lambda p: p.get('created_at', ''), reverse=True)

def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def log_event(event: dict):
    DATA.mkdir(parents=True, exist_ok=True)
    with _lock, (DATA / 'api_usage.jsonl').open('a', encoding='utf-8') as handle:
        handle.write(json.dumps({'time': now(), **event}, ensure_ascii=False) + '\n')
