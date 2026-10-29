"""Version-gated compatibility must fail closed before changing any source."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('rust_compat',ROOT/'scripts/rust_compat.py')
compat=importlib.util.module_from_spec(spec)
spec.loader.exec_module(compat)
RUSTUP=Path(os.environ.get('RUSTUP_HOME',str(Path.home()/'.rustup')))
RUSTC_194=next((RUSTUP/'toolchains').glob('1.94.*-*/bin/rustc'),None)


class RustCompatibilityTests(unittest.TestCase):
    def source(self, root):
        for name,anchor in compat.ANCHORS.items():
            file=root/'codex-rs'/name
            file.parent.mkdir(parents=True,exist_ok=True)
            file.write_text('// known isolated source\n'+anchor+';\n')
        return {p:p.read_text() for p in root.rglob('*.rs')}

    def test_supported_export_patches_production_and_test_calls(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);original=self.source(root)
            planned=compat.prepare(root,'0.165.0')
            self.assertEqual(original,{p:p.read_text() for p in original})
            self.assertEqual(compat.apply_compatibility(root,'0.165.0'),5)
            for path,before in original.items():
                if '.try_update(' in before:
                    self.assertEqual(path.read_text(),before.replace('.try_update(','.fetch_update('))
                else:
                    self.assertNotIn('if let',path.read_text())
                    self.assertIn('match args.as_slice()',path.read_text())
                    self.assertIn('"expected one executor for this call"',path.read_text())
                self.assertEqual(path.read_text(),planned[path])

    def test_last_missing_anchor_leaves_every_earlier_file_untouched(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.source(root)
            last=root/'codex-rs'/list(compat.ANCHORS)[-1]
            last.write_text(last.read_text().replace('args.as_slice()','args.iter()'))
            before={p:p.read_text() for p in root.rglob('*.rs')}
            with self.assertRaisesRegex(ValueError,'anchor count 0'):
                compat.apply_compatibility(root,'0.165.0')
            self.assertEqual(before,{p:p.read_text() for p in before})

    def test_reapplied_partial_and_duplicate_sources_are_rejected(self):
        for variant in ('patched','partial','duplicate'):
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);self.source(root)
                if variant=='patched':compat.apply_compatibility(root,'0.165.0')
                else:
                    file=root/'codex-rs'/next(iter(compat.ANCHORS))
                    file.write_text(file.read_text().replace('.try_update(','.fetch_update(') if variant=='partial' else file.read_text()+'.try_update(unexpected);\n')
                before={p:p.read_text() for p in root.rglob('*.rs')}
                with self.assertRaises(ValueError):compat.apply_compatibility(root,'0.165.0')
                self.assertEqual(before,{p:p.read_text() for p in before})

    def test_old_version_is_noop_and_unknown_version_is_not_guessed(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);before=self.source(root)
            self.assertEqual(compat.apply_compatibility(root,'0.163.0'),0)
            with self.assertRaisesRegex(ValueError,'unsupported Rust compatibility profile'):
                compat.apply_compatibility(root,'0.166.0')
            self.assertEqual(before,{p:p.read_text() for p in before})

    @unittest.skipUnless(RUSTC_194,'Rust 1.94 toolchain is not installed')
    def test_stable_atomic_spelling_preserves_bound_and_overflow_semantics(self):
        code='''use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};
#[test]
fn saturating_gauge() {
    let gauge = AtomicU64::new(0);
    assert_eq!(gauge.fetch_update(Ordering::Relaxed, Ordering::Relaxed, |v| Some(v.saturating_sub(1))), Ok(0));
    assert_eq!(gauge.load(Ordering::Relaxed), 0);
    gauge.store(2, Ordering::Relaxed);
    assert_eq!(gauge.fetch_update(Ordering::Relaxed, Ordering::Relaxed, |v| Some(v.saturating_sub(1))), Ok(2));
    assert_eq!(gauge.load(Ordering::Relaxed), 1);
}
#[test]
fn checked_cell_allocation() {
    let cell = AtomicU64::new(u64::MAX);
    assert_eq!(cell.fetch_update(Ordering::Relaxed, Ordering::Relaxed, |v| v.checked_add(1)), Err(u64::MAX));
    assert_eq!(cell.load(Ordering::Relaxed), u64::MAX);
    cell.store(7, Ordering::Relaxed);
    assert_eq!(cell.fetch_update(Ordering::Relaxed, Ordering::Relaxed, |v| v.checked_add(1)), Ok(7));
    assert_eq!(cell.load(Ordering::Relaxed), 8);
}
#[test]
fn bounded_direct_call_reservation() {
    let pending = AtomicUsize::new(1);
    let reserve = |v| (v < 2).then_some(v + 1);
    assert_eq!(pending.fetch_update(Ordering::Relaxed, Ordering::Relaxed, reserve), Ok(1));
    assert_eq!(pending.fetch_update(Ordering::Relaxed, Ordering::Relaxed, reserve), Err(2));
    assert_eq!(pending.load(Ordering::Relaxed), 2);
}
#[test]
fn checked_failure_budget() {
    let remaining = AtomicUsize::new(1);
    assert_eq!(remaining.fetch_update(Ordering::SeqCst, Ordering::SeqCst, |v| v.checked_sub(1)), Ok(1));
    assert_eq!(remaining.fetch_update(Ordering::SeqCst, Ordering::SeqCst, |v| v.checked_sub(1)), Err(0));
    assert_eq!(remaining.load(Ordering::SeqCst), 0);
}
'''
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'atomic_compat.rs';source.write_text(code)
            binary=Path(temp)/'atomic_compat'
            subprocess.run([str(RUSTC_194),'--edition=2024','--test',str(source),'-o',str(binary)],check=True,capture_output=True,text=True)
            result=subprocess.run([str(binary)],check=True,capture_output=True,text=True)
            self.assertIn('4 passed',result.stdout)

    @unittest.skipUnless(RUSTC_194,'Rust 1.94 toolchain is not installed')
    def test_nested_executor_match_preserves_arguments_and_all_selection(self):
        code='''use std::sync::Arc;
#[derive(Debug, PartialEq)]
struct TurnEnvironment { id: u8 }
struct TurnEnvironmentSnapshot { primary: Option<TurnEnvironment> }
enum ToolEnvironments {
    Arguments(Vec<(&'static str, Arc<TurnEnvironment>)>),
    All,
    Terminal,
    Mcp,
}
#[derive(Debug, PartialEq)]
enum FunctionCallError { Fatal(String) }
fn resolve_tool_environment<'a>(snapshot: &'a TurnEnvironmentSnapshot, id: Option<&str>) -> Result<&'a TurnEnvironment, FunctionCallError> {
    assert_eq!(id, None);
    snapshot.primary.as_ref().ok_or_else(|| FunctionCallError::Fatal("no primary executor".to_string()))
}
fn selected_executor<'a>(environments: &'a ToolEnvironments, snapshot: &'a TurnEnvironmentSnapshot) -> Result<&'a TurnEnvironment, FunctionCallError> {
    match environments {
__REPLACEMENT__
        // Direct handler callers may supply only the step context.
        ToolEnvironments::All => resolve_tool_environment(snapshot, /*environment_id*/ None),
        _ => Err(FunctionCallError::Fatal(
            "expected one executor for this call".to_string(),
        )),
    }
}
fn snapshot() -> TurnEnvironmentSnapshot {
    TurnEnvironmentSnapshot { primary: Some(TurnEnvironment { id: 9 }) }
}
fn expected_error() -> FunctionCallError {
    FunctionCallError::Fatal("expected one executor for this call".to_string())
}
#[test]
fn zero_arguments_fail() {
    assert_eq!(selected_executor(&ToolEnvironments::Arguments(vec![]), &snapshot()), Err(expected_error()));
}
#[test]
fn one_argument_returns_the_same_environment_reference() {
    let env = Arc::new(TurnEnvironment { id: 7 });
    let args = ToolEnvironments::Arguments(vec![("environment_id", Arc::clone(&env))]);
    let snapshot = snapshot();
    let selected = selected_executor(&args, &snapshot).expect("one executor");
    assert!(std::ptr::eq(selected, env.as_ref()));
}
#[test]
fn two_arguments_are_ambiguous() {
    let args = ToolEnvironments::Arguments(vec![("first", Arc::new(TurnEnvironment { id: 1 })), ("second", Arc::new(TurnEnvironment { id: 2 }))]);
    assert_eq!(selected_executor(&args, &snapshot()), Err(expected_error()));
}
#[test]
fn all_retains_default_resolution_and_its_error() {
    assert_eq!(selected_executor(&ToolEnvironments::All, &snapshot()), Ok(&TurnEnvironment { id: 9 }));
    let no_primary = TurnEnvironmentSnapshot { primary: None };
    assert_eq!(selected_executor(&ToolEnvironments::All, &no_primary), Err(FunctionCallError::Fatal("no primary executor".to_string())));
}
#[test]
fn other_variants_keep_the_original_error() {
    for envs in [ToolEnvironments::Terminal, ToolEnvironments::Mcp] {
        assert_eq!(selected_executor(&envs, &snapshot()), Err(expected_error()));
    }
}
'''.replace('__REPLACEMENT__',compat.REPLACEMENTS['core/src/tools/handlers/mod.rs'])
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'executor_compat.rs';source.write_text(code)
            binary=Path(temp)/'executor_compat'
            subprocess.run([str(RUSTC_194),'--edition=2024','--test',str(source),'-o',str(binary)],check=True,capture_output=True,text=True)
            result=subprocess.run([str(binary)],check=True,capture_output=True,text=True)
            self.assertIn('5 passed',result.stdout)


if __name__=='__main__':unittest.main()
