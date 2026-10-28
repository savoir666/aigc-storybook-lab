"""Bind a completed Agent run to its actual final story and media files."""
import hashlib
import json
from pathlib import Path
from .storage import write_json, now


def story_digest(project):
    content = {k:project.get(k) for k in ('inputs', 'title', 'characters', 'scenes', 'moral')}
    # Media URLs and timing are included so changes invalidate the binding.
    return hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def file_digest(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(project, folder, job_id):
    folder = Path(folder)
    names = ['agent_trace.json', 'prompt-record.json', 'revision-record.json', 'human-intervention.json', 'human-intervention-retry.json', 'image-review.json', 'audio-proof.json', 'video-proof.json', 'story.mp3', 'story.mp4', 'book.pdf']
    names += [f'scene-{i+1:02}.png' for i in range(len(project['scenes']))]
    names += [f'scene-{i+1:02}.proof.json' for i in range(len(project['scenes']))]
    names += [f'scene-{i+1:02}.response.json' for i in range(len(project['scenes']))]
    # Export names are defined by the media module rather than guessed.
    names = [n for n in names if (folder/n).is_file()]
    for key in ('audio_url', 'video_url', 'pdf_url'):
        name = str(project.get(key,'')).rsplit('/',1)[-1]
        if name and name not in names:
            names.append(name)
    manifest = {'schema':1, 'created_at':now(), 'project_id':project['id'], 'job_id':job_id,
                'story_sha256':story_digest(project), 'inputs':project['inputs'],
                'files':{name:{'sha256':file_digest(folder/name),'bytes':(folder/name).stat().st_size} for name in names}}
    write_json(folder/'agent-final-manifest.json', manifest)
    return manifest


def verify_manifest(project, folder):
    folder = Path(folder)
    try:
        manifest = json.loads((folder/'agent-final-manifest.json').read_text(encoding='utf-8'))
        if manifest['story_sha256'] != story_digest(project):
            return False
        for name, proof in manifest['files'].items():
            if Path(name).name != name or not (folder/name).is_file():
                return False
            if (folder/name).stat().st_size != proof['bytes'] or file_digest(folder/name) != proof['sha256']:
                return False
        return bool(manifest['files'])
    except (OSError, ValueError, KeyError, TypeError):
        return False
