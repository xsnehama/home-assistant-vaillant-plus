#!/usr/bin/env python3
"""Compare the Git source tree with the deployed integration, without writing."""
import hashlib
import json
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
SOURCE = REPO / 'custom_components/vaillant_plus'
TARGET = pathlib.Path('/var/apps/docker-home-assistantan/shares/home-assistant/config/custom_components/vaillant_plus')

def inventory(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob('*'))
        if p.is_file() and '__pycache__' not in p.parts and not p.name.endswith('.pyc')
    }

def main():
    if not SOURCE.is_dir() or not TARGET.is_dir():
        print('ERROR: source or deployment directory is missing', file=sys.stderr)
        return 2
    expected, actual = inventory(SOURCE), inventory(TARGET)
    report = {
        'commit': subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip(),
        'git_worktree_dirty': bool(subprocess.check_output(['git', '-C', str(REPO), 'status', '--porcelain'])),
        'source': str(SOURCE),
        'deployment': str(TARGET),
        'deployment_contains_git': (TARGET / '.git').exists(),
        'missing': sorted(expected.keys() - actual.keys()),
        'unexpected': sorted(actual.keys() - expected.keys()),
        'changed': [n for n in sorted(expected.keys() & actual.keys()) if expected[n] != actual[n]],
        'source_files': len(expected),
    }
    report['match'] = not any(report[k] for k in ['git_worktree_dirty', 'deployment_contains_git', 'missing', 'unexpected', 'changed'])
    print(json.dumps(report, indent=2))
    return 0 if report['match'] else 1

if __name__ == '__main__':
    sys.exit(main())
