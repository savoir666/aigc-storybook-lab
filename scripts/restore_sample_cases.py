"""Copy verified sample cases into local storage, without API calls or overwrites."""
import argparse
import json
from pathlib import Path
import shutil
from verify_submission import verify_case

ROOT = Path(__file__).resolve().parents[1]


def restore(destination_root):
    destination_root = destination_root.resolve()
    target = destination_root / 'data/projects'
    source = ROOT / 'outputs/final-cases'
    restored, skipped = [], []
    for folder in sorted(source.iterdir()):
        if not folder.is_dir():
            continue
        result = verify_case(folder)
        if result['errors']:
            raise ValueError('Sample verification failed: ' + str(result))
        destination = target / folder.name
        if destination.exists():
            skipped.append(folder.name)
            continue
        target.mkdir(parents=True, exist_ok=True)
        shutil.copytree(folder, destination)
        restored.append(folder.name)
    return {'restored': restored, 'skipped_existing': skipped, 'target': str(target)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT, help='Local project directory; defaults to this repository.')
    args = parser.parse_args()
    print(json.dumps(restore(args.root), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
