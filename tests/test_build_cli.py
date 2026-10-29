"""Versioned cache selection and failure-safe publication of native adapters."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest import mock

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'scripts'))
try:
    spec = importlib.util.spec_from_file_location('build_cli_under_test', PROJECT / 'scripts/build_cli.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
finally:
    sys.path.pop(0)


class BuildCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'adapters/codex').mkdir(parents=True)
        (self.root / 'scripts').mkdir()
        (self.root / 'adapters/codex/companion_bridge.rs').write_text('bridge fixture')
        (self.root / 'scripts/migrate.py').write_text('adapter fixture')
        (self.root / 'scripts/rust_compat.py').write_text('compatibility fixture')
        self.fingerprint = hashlib.sha256(b'bridge fixtureadapter fixturecompatibility fixture').hexdigest()
        self.version = '0.165.0'
        self.sha = builder.SUPPORTED[self.version]
        self.marker = self.root / 'build/current.json'
        self.checkout = self.root / 'upstream'
        self.checkout.mkdir()
        patch = mock.patch.object(builder, 'ROOT', self.root)
        patch.start()
        self.addCleanup(patch.stop)

    def binary(self, name='old-codex', version='0.165.0'):
        path = self.root / name
        path.write_text("#!/bin/sh\nprintf '%s\\n' 'codex-cli " + version + "'\n")
        path.chmod(0o755)
        return path

    def manifest(self, binary, **changes):
        info = {'version': self.version, 'upstream_commit': self.sha,
                'adapter_sha256': self.fingerprint, 'binary': str(binary),
                'binary_sha256': builder.file_sha256(binary)}
        info.update(changes)
        self.marker.parent.mkdir(parents=True, exist_ok=True)
        self.marker.write_text(json.dumps(info))
        return info

    def cached(self):
        return builder.cached_binary(self.marker, self.version, self.sha, self.fingerprint)

    def test_cache_requires_correct_base_and_adapter_not_just_the_same_fingerprint(self):
        binary = self.binary()
        for changes in ({'version': '0.163.0'}, {'upstream_commit': 'other-tag'},
                        {'adapter_sha256': 'older-adapter'}, {'binary_sha256': 'bad-hash'}):
            with self.subTest(changes=changes):
                self.manifest(binary, **changes)
                self.assertIsNone(self.cached())
        self.manifest(binary)
        self.assertEqual(self.cached(), binary)

    def test_cache_rejects_modified_or_mislabeled_native_binary(self):
        binary = self.binary()
        self.manifest(binary)
        binary.write_text(binary.read_text() + '# modified\n')
        self.assertIsNone(self.cached())
        old_version = self.binary('wrong-version', '0.163.0')
        self.manifest(old_version)
        self.assertIsNone(self.cached())

    def main_context(self, arguments, compile_failure=False):
        real_output = subprocess.check_output
        real_run = subprocess.run
        target = self.root / 'cargo-target'
        def output(command, **kwargs):
            if command[0] == 'git':
                return self.sha + '\n'
            return real_output(command, **kwargs)
        def export(checkout, sha, destination):
            (destination / 'codex-rs').mkdir()
            (destination / 'codex-rs/source.txt').write_text(sha)
            (destination / 'codex-rs/Cargo.toml').write_text('[workspace]\nmembers=[]\n[workspace.package]\nversion="0.165.0"\n')
            (destination / 'codex-rs/Cargo.lock').write_text('version=4\n')
        def run(command, **kwargs):
            if command[0] not in ('cargo', sys.executable):
                return real_run(command, **kwargs)
            if command[0] == 'cargo':
                self.assertIn('--locked', command)
                self.assertIn('+1.94.1', command)
                if compile_failure:
                    raise subprocess.CalledProcessError(101, command)
                built = target / 'dev-small/codex'
                built.parent.mkdir(parents=True)
                executable = self.binary('compiled')
                built.write_bytes(executable.read_bytes())
                built.chmod(0o755)
            return subprocess.CompletedProcess(command, 0)
        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(mock.patch.object(sys, 'argv', ['build_cli.py', '--source', str(self.checkout)] + arguments))
        stack.enter_context(mock.patch.dict(os.environ, {'CARGO_TARGET_DIR': str(target)}))
        stack.enter_context(mock.patch.object(builder.subprocess, 'check_output', side_effect=output))
        stack.enter_context(mock.patch.object(builder.subprocess, 'run', side_effect=run))
        export_mock = stack.enter_context(mock.patch.object(builder, 'export_source', side_effect=export))
        prepare_mock = stack.enter_context(mock.patch.object(builder, 'prepare'))
        self.compatibility = stack.enter_context(mock.patch.object(builder, 'apply_compatibility', return_value=0))
        return stack, export_mock, prepare_mock

    def test_check_still_validates_source_when_a_matching_binary_is_cached(self):
        self.manifest(self.binary())
        before = self.marker.read_bytes()
        stack, export, prepare = self.main_context(['--check'])
        with stack:
            builder.main()
        export.assert_called_once()
        prepare.assert_called_once()
        self.compatibility.assert_called_once()
        self.assertEqual(self.marker.read_bytes(), before)
        self.assertFalse((self.root / 'build/bin').exists())

    def test_compatibility_changes_invalidate_an_otherwise_matching_cache(self):
        binary = self.binary()
        self.manifest(binary)
        before = builder.adapter_fingerprint(self.root)
        self.assertEqual(builder.cached_binary(self.marker, self.version, self.sha, before), binary)
        compatibility = self.root / 'scripts/rust_compat.py'
        compatibility.write_text(compatibility.read_text() + '\n# changed substitution\n')
        after = builder.adapter_fingerprint(self.root)
        self.assertNotEqual(before, after)
        self.assertIsNone(builder.cached_binary(self.marker, self.version, self.sha, after))

    def test_failed_build_preserves_active_manifest_and_old_executable(self):
        old = self.binary(version='0.163.0')
        self.manifest(old, version='0.163.0')
        before = self.marker.read_bytes()
        binary_before = old.read_bytes()
        stack, _, _ = self.main_context([], compile_failure=True)
        with stack, self.assertRaises(subprocess.CalledProcessError):
            builder.main()
        self.assertEqual(self.marker.read_bytes(), before)
        self.assertEqual(old.read_bytes(), binary_before)
        self.assertFalse((self.root / 'build/bin').exists())

    def test_successful_candidate_build_does_not_activate_and_has_verified_hash(self):
        old = self.binary(version='0.163.0')
        self.manifest(old, version='0.163.0')
        before = self.marker.read_bytes()
        candidate = self.root / 'build/candidate.json'
        stack, _, _ = self.main_context(['--manifest', str(candidate)])
        with stack:
            builder.main()
        info = json.loads(candidate.read_text())
        produced = Path(info['binary'])
        self.assertEqual(info['version'], self.version)
        self.assertEqual(info['upstream_commit'], self.sha)
        self.assertEqual(info['binary_sha256'], builder.file_sha256(produced))
        self.assertTrue(builder.version_matches(produced, self.version))
        self.assertEqual(self.marker.read_bytes(), before)
        self.assertIn(self.fingerprint[:12], produced.name)
        self.assertTrue(old.exists())

    def test_version_mismatch_cannot_publish_any_manifest(self):
        old = self.binary()
        self.manifest(old)
        before = self.marker.read_bytes()
        wrong = self.binary('wrong-build', '0.163.0')
        with self.assertRaisesRegex(SystemExit, 'version does not match'):
            builder.publish_binary(wrong, self.version, self.sha, self.fingerprint, self.marker)
        self.assertEqual(self.marker.read_bytes(), before)
        self.assertEqual(list((self.root / 'build/bin').iterdir()), [])

    def test_failed_manifest_replace_leaves_previous_active_pointer_untouched(self):
        old = self.binary()
        self.manifest(old)
        before = self.marker.read_bytes()
        compiled = self.binary('new-build')
        real_replace = os.replace
        def replace(source, destination):
            if Path(destination) == self.marker:
                raise OSError('simulated manifest publication failure')
            return real_replace(source, destination)
        with mock.patch.object(builder.os, 'replace', side_effect=replace), self.assertRaises(OSError):
            builder.publish_binary(compiled, self.version, self.sha, self.fingerprint, self.marker)
        self.assertEqual(self.marker.read_bytes(), before)
        self.assertTrue(old.exists())
        self.assertFalse(list(self.marker.parent.glob('*.tmp')))
        self.assertFalse(list((self.root / 'build/bin').glob('.codex-stage-*')))

    def test_release_lock_normalization_only_changes_inherited_local_packages(self):
        workspace = self.root / 'release/codex-rs'
        for name in ('cli', 'utils/helper', 'fixed', 'ignored'):
            (workspace / name).mkdir(parents=True)
        (workspace / 'Cargo.toml').write_text('''[workspace]
members=["cli", "utils/*", "fixed", "ignored"]
exclude=["ignored"]
[workspace.package]
version="0.165.0"
''')
        for name in ('cli', 'utils/helper', 'ignored'):
            (workspace / name / 'Cargo.toml').write_text('[package]\nname="'+name.split('/')[-1]+'"\nversion.workspace=true\n')
        (workspace / 'fixed/Cargo.toml').write_text('[package]\nname="fixed"\nversion="0.0.0"\n')
        registry = '''[[package]]
name = "helper"
version = "0.0.0"
source = "registry+https://example.invalid/index"
checksum = "keep-this-checksum"
'''
        source = '''# Cargo release fixture
version = 4

[[package]]
name = "cli"
version = "0.0.0" # inherited release version
dependencies = [
 "helper 0.0.0",
 "helper 0.0.0 (registry+https://example.invalid/index)",
 "fixed 0.0.0",
]

[[package]]
name = "helper"
version = "0.0.0"

[[package]]
name = "fixed"
version = "0.0.0"

[[package]]
name = "ignored"
version = "0.0.0"

''' + registry
        lock = workspace / 'Cargo.lock'
        lock.write_text(source)
        changed = builder.normalize_workspace_lock(workspace.parent, self.version)
        result = lock.read_text()
        packages = tomllib.loads(result)['package']
        self.assertEqual(changed, 2)
        self.assertEqual(packages[0]['version'], '0.165.0')
        self.assertEqual(packages[0]['dependencies'], ['helper 0.165.0',
            'helper 0.0.0 (registry+https://example.invalid/index)', 'fixed 0.0.0'])
        self.assertEqual(packages[1]['version'], '0.165.0')
        self.assertEqual(packages[2]['version'], '0.0.0')
        self.assertEqual(packages[3]['version'], '0.0.0')
        self.assertIn(registry, result)
        self.assertIn('# inherited release version', result)
        self.assertEqual(builder.normalize_workspace_lock(workspace.parent, self.version), 0)
        self.assertEqual(lock.read_text(), result)

    def test_implicit_path_members_inherit_the_release_but_nested_workspaces_do_not(self):
        workspace = self.root / 'implicit/codex-rs'
        for name in ('cli', 'chatgpt', 'core/tests/common', 'windows-sandbox-rs',
                     'nested/inside', 'excluded', 'not-referenced'):
            (workspace / name).mkdir(parents=True)
        (workspace / 'Cargo.toml').write_text('''[workspace]
members=["cli"]
exclude=["excluded"]
[workspace.package]
version="0.165.0"
[workspace.dependencies]
chatgpt={path="chatgpt"}
''')
        (workspace / 'cli/Cargo.toml').write_text('''[package]
name="cli"
version.workspace=true
[dependencies]
chatgpt.workspace=true
excluded={path="../excluded"}
nested={path="../nested/inside"}
[dev-dependencies]
support={path="../core/tests/common"}
[target.'cfg(windows)'.build-dependencies]
sandbox={path="../windows-sandbox-rs"}
''')
        for path, name in (('chatgpt','codex-chatgpt'),('core/tests/common','core_test_support'),
                           ('windows-sandbox-rs','codex-windows-sandbox'),('nested/inside','nested'),
                           ('excluded','excluded'),('not-referenced','unused')):
            (workspace / path / 'Cargo.toml').write_text('[package]\nname="'+name+'"\nversion.workspace=true\n')
        (workspace / 'nested/Cargo.toml').write_text('[workspace]\nmembers=["inside"]\n[workspace.package]\nversion="0.1.0"\n')
        lock = workspace / 'Cargo.lock'
        lock.write_text('version=4\n' + ''.join('\n[[package]]\nname="'+name+'"\nversion="0.0.0"\n'
            for name in ('cli','codex-chatgpt','core_test_support','codex-windows-sandbox','nested','excluded','unused')))
        self.assertEqual(builder.normalize_workspace_lock(workspace.parent, self.version), 4)
        packages = {p['name']:p['version'] for p in tomllib.loads(lock.read_text())['package']}
        for name in ('cli','codex-chatgpt','core_test_support','codex-windows-sandbox'):
            self.assertEqual(packages[name], self.version)
        for name in ('nested','excluded','unused'):
            self.assertEqual(packages[name], '0.0.0')


if __name__ == '__main__':
    unittest.main()
