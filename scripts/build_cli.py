#!/usr/bin/env python3
"""Build a pinned official export and publish a verified, immutable adapter binary."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import tomllib
from migrate import prepare
from rust_compat import apply_compatibility

ROOT = Path(__file__).resolve().parents[1]
SUPPORTED = {
    '0.163.0': '83086188ae0614bd882818ff1aa23f3194962012',
    '0.165.0': '360319d8dee62d87e2d59fc0c21805d79519cfed',
}
DEFAULT_VERSION = '0.165.0'


def adapter_fingerprint(root=ROOT):
    root = Path(root)
    return hashlib.sha256((root / 'adapters/codex/companion_bridge.rs').read_bytes() +
                          (root / 'scripts/migrate.py').read_bytes() +
                          (root / 'scripts/rust_compat.py').read_bytes()).hexdigest()


def normalize_workspace_lock(source, version):
    """Repair release-tag package metadata while retaining every third-party pin.

    The official tag changes workspace.package.version but can retain 0.0.0
    for inherited workspace packages in Cargo.lock. Cargo --locked rejects
    that metadata-only mismatch before compiling anything.
    """
    workspace_root = Path(source) / 'codex-rs'
    workspace = tomllib.loads((workspace_root / 'Cargo.toml').read_text())['workspace']
    if workspace.get('package', {}).get('version') != version:
        raise ValueError('Workspace package version does not match the requested release')
    excluded = {p.resolve() for pattern in workspace.get('exclude', [])
                for p in workspace_root.glob(pattern)}
    names = set()
    workspace_root = workspace_root.resolve()
    queue = [p.resolve() for pattern in workspace['members'] for p in workspace_root.glob(pattern)]
    visited = set()
    manifests = {}
    def read_manifest(directory):
        if directory not in manifests:
            path = directory / 'Cargo.toml'
            manifests[directory] = tomllib.loads(path.read_text()) if path.is_file() else {}
        return manifests[directory]
    while queue:
        member = queue.pop()
        if member in visited:
            continue
        visited.add(member)
        if not member.is_relative_to(workspace_root) or any(member.is_relative_to(p) for p in excluded):
            continue
        # Cargo implicitly includes in-tree path dependencies, but a nested
        # workspace has its own version inheritance and must remain separate.
        cursor = member
        while cursor != workspace_root and 'workspace' not in read_manifest(cursor):
            cursor = cursor.parent
        if cursor != workspace_root:
            continue
        manifest = read_manifest(member)
        package = manifest.get('package', {})
        if 'workspace' in package and (member / package['workspace']).resolve() != workspace_root:
            continue
        if package.get('version') == {'workspace': True}:
            names.add(package['name'])
        for section in [manifest, *manifest.get('target', {}).values()]:
            for field in ('dependencies', 'dev-dependencies', 'build-dependencies'):
                for alias, dependency in section.get(field, {}).items():
                    if not isinstance(dependency, dict):
                        continue
                    base = member
                    if dependency.get('workspace'):
                        dependency = workspace.get('dependencies', {}).get(alias, {})
                        base = workspace_root
                    if isinstance(dependency, dict) and 'path' in dependency:
                        queue.append((base / dependency['path']).resolve())
    lock = workspace_root / 'Cargo.lock'
    original = lock.read_text()
    parsed = tomllib.loads(original)
    changed = {p['name'] for p in parsed.get('package', [])
               if p['name'] in names and 'source' not in p and p.get('version') == '0.0.0'}
    if not changed:
        return 0
    blocks = re.split(r'(?m)(?=^\[\[package\]\][ \t]*$)', original)
    for index, block in enumerate(blocks):
        if not block.startswith('[[package]]'):
            continue
        package = tomllib.loads(block)['package'][0]
        if package['name'] in changed and 'source' not in package and package.get('version') == '0.0.0':
            block, count = re.subn(r'(?m)^(version[ \t]*=[ \t]*)"0\.0\.0"',
                                   lambda match: match[1] + '"' + version + '"', block, count=1)
            if count != 1:
                raise ValueError('Unsupported workspace lock package version syntax')
        # Disambiguated local dependency identifiers carry an embedded version.
        # Source-qualified registry/git identifiers are deliberately not matched.
        def dependencies(match):
            value = match[0]
            for name in sorted(changed):
                value = re.sub(r'"' + re.escape(name) + r' 0\.0\.0"',
                               '"' + name + ' ' + version + '"', value)
            return value
        blocks[index] = re.sub(r'(?ms)^dependencies[ \t]*=[ \t]*\[.*?\]', dependencies, block)
    updated = ''.join(blocks)
    tomllib.loads(updated)
    lock.write_text(updated)
    return len(changed)


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def version_matches(binary, version):
    try:
        actual = subprocess.check_output([str(binary), '--version'], text=True,
                                         stderr=subprocess.STDOUT, timeout=10).strip()
        return actual == 'codex-cli ' + version
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return False


def cached_binary(marker, version, sha, fingerprint):
    """A different CLI base, tampered artifact or old incomplete manifest is a miss."""
    try:
        old = json.loads(Path(marker).read_text())
        if (old.get('version'), old.get('upstream_commit'), old.get('adapter_sha256')) != (version, sha, fingerprint):
            return None
        binary = Path(old['binary'])
        if not binary.is_file() or old.get('binary_sha256') != file_sha256(binary):
            return None
        return binary if version_matches(binary, version) else None
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None


def export_source(checkout, sha, destination):
    archive = subprocess.Popen(['git', '-C', str(checkout), 'archive', sha], stdout=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=archive.stdout, mode='r|') as stream:
            stream.extractall(destination, filter='data')
    except BaseException:
        archive.kill()
        archive.wait()
        raise
    finally:
        archive.stdout.close()
    if archive.wait() != 0:
        sys_exit('Source export failed')


def publish_binary(compiled, version, sha, fingerprint, marker):
    """Keep old binaries and the old pointer intact until every build check passes."""
    directory = ROOT / 'build/bin'
    directory.mkdir(parents=True, exist_ok=True)
    marker = Path(marker)
    marker.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.codex-stage-', dir=directory)
    os.close(fd)
    staged = Path(name)
    try:
        shutil.copy2(compiled, staged)
        if not version_matches(staged, version):
            sys_exit('Built binary version does not match the requested CLI; active installation is unchanged.')
        digest = file_sha256(staged)
        binary = directory / f'codex-{version}-theater-{fingerprint[:12]}-{digest[:12]}'
        if binary.exists():
            if file_sha256(binary) != digest:
                sys_exit('Artifact name collision; active installation is unchanged.')
        else:
            os.replace(staged, binary)
        info = {'version': version, 'upstream_commit': sha, 'adapter_sha256': fingerprint,
                'binary': str(binary), 'binary_sha256': digest}
        fd, pending_name = tempfile.mkstemp(prefix=marker.name + '.', suffix='.tmp', dir=marker.parent)
        pending = Path(pending_name)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(info, stream, indent=2)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(pending, marker)
        finally:
            pending.unlink(missing_ok=True)
        return info
    finally:
        staged.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--version', default=DEFAULT_VERSION)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--manifest', type=Path, default=ROOT / 'build/current.json',
                        help='Publish a candidate manifest here without changing the active pointer')
    args = parser.parse_args()
    if args.version not in SUPPORTED:
        sys_exit('Version has no verified adapter profile. Original installation is unchanged.')
    sha = subprocess.check_output(['git', '-C', str(args.source), 'rev-parse',
                                   'rust-v' + args.version + '^{commit}'], text=True).strip()
    if sha != SUPPORTED[args.version]:
        sys_exit('Official tag commit does not match the supported profile.')
    fingerprint = adapter_fingerprint(ROOT)
    marker = args.manifest.resolve()
    if not args.check:
        cached = cached_binary(marker, args.version, sha, fingerprint)
        if cached:
            print('Verified native adapter already built:', cached)
            return
    (ROOT / 'build').mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='codex-theater-source-', dir=ROOT / 'build') as temp:
        source = Path(temp)
        export_source(args.source, sha, source)
        prepare(source)
        normalized = normalize_workspace_lock(source, args.version)
        if normalized:
            print(f'Normalized release metadata for {normalized} local workspace packages; third-party pins unchanged.', flush=True)
        compatibility = apply_compatibility(source, args.version)
        if compatibility:
            print(f'Applied {compatibility} Rust 1.94 compatibility substitutions.', flush=True)
        print('Adapter compatible; original checkout and installed CLI unchanged.', flush=True)
        if args.check:
            return
        subprocess.run([os.sys.executable, str(ROOT / 'scripts/migrate.py'), str(source), '--apply'], check=True)
        env = dict(os.environ)
        env['CARGO_TARGET_DIR'] = str(Path(env.get('CARGO_TARGET_DIR', ROOT / 'build/target')).expanduser().resolve())
        env.setdefault('CARGO_BUILD_JOBS', '4')
        subprocess.run(['cargo', '+1.94.1', 'build', '--locked', '-p', 'codex-cli', '--bin', 'codex',
                        '--profile', 'dev-small'], cwd=source / 'codex-rs', env=env, check=True)
        info = publish_binary(Path(env['CARGO_TARGET_DIR']) / 'dev-small/codex',
                              args.version, sha, fingerprint, marker)
        print('Verified manifest:', marker)
        print('Binary:', info['binary'])
        if marker == (ROOT / 'build/current.json').resolve():
            print('Ready:', ROOT / 'scripts/codex-theater')


def sys_exit(message):
    raise SystemExit(message)


if __name__ == '__main__':
    main()
