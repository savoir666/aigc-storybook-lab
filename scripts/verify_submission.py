"""Verify exported final cases without network, optional models or API keys."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify_case(folder):
    manifest = json.loads((folder / 'agent-final-manifest.json').read_text(encoding='utf-8'))
    project = json.loads((folder / 'project.json').read_text(encoding='utf-8'))
    errors = []
    if project['id'] != folder.name or manifest['project_id'] != folder.name:
        errors.append('project ID mismatch')
    content = {key: project.get(key) for key in ('inputs', 'title', 'characters', 'scenes', 'moral')}
    digest = hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    if digest != manifest['story_sha256']:
        errors.append('story binding mismatch')
    for name, proof in manifest['files'].items():
        if Path(name).name != name:
            errors.append('unsafe filename')
            continue
        path = folder / name
        if not path.is_file():
            errors.append('missing: ' + name)
            continue
        if path.stat().st_size != proof['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest() != proof['sha256']:
            errors.append('hash mismatch: ' + name)
    return {'case': folder.name, 'files_verified': len(manifest['files']), 'errors': errors}


def main():
    folders = sorted((ROOT / 'outputs/final-cases').glob('*'))
    cases = [verify_case(folder) for folder in folders if folder.is_dir()]
    result = {'cases': cases, 'all_passed': len(cases) == 2 and not any(c['errors'] for c in cases)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['all_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
