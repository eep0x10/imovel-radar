"""Audit tracked content without printing matched secrets. No third-party service."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    'google-key': rb'AIza[0-9A-Za-z_-]{35}',
    'github-token': rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})',
    'private-key': rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'personal-path': rb'(?:[A-Za-z]:[\\/]Users[\\/][A-Za-z0-9_.-]+[\\/]|/home/[A-Za-z0-9_.-]+/)',
}
PRIVATE = re.compile(r'(^|/)(?:\.env(?:\..*)?|data|output|prototype)(/|$)|\.(?:xlsx|sqlite3|db|log|bundle)$', re.I)


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--history', action='store_true')
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'PUBLIC_ASSETS.json').read_text(encoding='utf-8'))
    findings, checked = [], set()
    commits = git('rev-list', '--all').decode().splitlines() if args.history else [None]
    for commit in commits:
        paths = git('ls-tree', '-rz', '--name-only', commit).split(b'\0') if commit else git('ls-files', '-z').split(b'\0')
        for raw in paths:
            if not raw:
                continue
            path = raw.decode('utf-8')
            if path == '.env.example':
                pass
            elif PRIVATE.search(path):
                findings.append((path, 'private-file'))
            content = git('show', f'{commit}:{path}') if commit else (ROOT / path).read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            if (path, digest) in checked:
                continue
            checked.add((path, digest))
            if path.endswith(('.png', '.jpg', '.webp')):
                if manifest.get(path) != digest:
                    findings.append((path, 'unapproved-binary'))
                continue
            for label, pattern in PATTERNS.items():
                if re.search(pattern, content):
                    findings.append((path, label))
    for path, label in sorted(set(findings)):
        print(f'FAIL {label}: {path}')
    print(json.dumps({'checked_versions':len(checked), 'findings':len(set(findings)), 'history':args.history}))
    return bool(findings)


if __name__ == '__main__':
    raise SystemExit(main())
