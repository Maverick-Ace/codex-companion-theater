"""Narrow, versioned source compatibility for the Rust 1.94 build.

Rust 1.94's core/src/sync/atomic.rs calls try_update an unstable alias of
fetch_update, and its implementation directly forwards to fetch_update. Keep
the ordering, closure and result untouched while using the stable spelling.
Only isolated, verified source exports should be passed to this module.
The single if-let match guard is expressed as a nested slice match so empty
or ambiguous executor arguments retain the same error on Rust 1.94.
"""
from pathlib import Path

ANCHORS = {
    'diagnostics/src/lib.rs': '''            .try_update(Ordering::Relaxed, Ordering::Relaxed, |value| {
                Some(value.saturating_sub(1))
            })''',
    'code-mode-runtime/src/session_runtime/mod.rs': '''            .try_update(Ordering::Relaxed, Ordering::Relaxed, |next_cell_id| {
                next_cell_id.checked_add(1)
            })''',
    'core/src/tools/executed_tool_calls.rs': '''            .try_update(Ordering::Relaxed, Ordering::Relaxed, |pending| {
                (pending < MAX_PENDING_EXECUTED_TOOL_CALLS).then_some(pending + 1)
            })''',
    'core/tests/common/apps_test_server.rs': '''                            .try_update(Ordering::SeqCst, Ordering::SeqCst, |remaining| {
                                remaining.checked_sub(1)
                            })''',
    'core/src/tools/handlers/mod.rs': '''        ToolEnvironments::Arguments(args) if let [(_, env)] = args.as_slice() => Ok(env),''',
}

REPLACEMENTS = {name: anchor.replace('.try_update(', '.fetch_update(')
                for name, anchor in ANCHORS.items()}
REPLACEMENTS['core/src/tools/handlers/mod.rs'] = '''        ToolEnvironments::Arguments(args) => match args.as_slice() {
            [(_, env)] => Ok(env),
            _ => Err(FunctionCallError::Fatal(
                "expected one executor for this call".to_string(),
            )),
        },'''


def prepare(source, version):
    """Validate the entire known profile before returning any replacement text."""
    if version == '0.163.0':
        return {}
    if version != '0.165.0':
        raise ValueError(f'unsupported Rust compatibility profile: {version}')
    output = {}
    for name, anchor in ANCHORS.items():
        path = Path(source)/'codex-rs'/name
        if not path.is_file():
            raise ValueError(f'unsupported Rust compatibility source: missing {name}')
        original = path.read_text()
        count = original.count(anchor)
        calls = original.count('.try_update(') if '.try_update(' in anchor else count
        if count != 1 or calls != 1:
            raise ValueError(f'unsupported Rust compatibility source: {name}: anchor count {count}, try_update calls {calls}; no changes applied')
        output[path] = original.replace(anchor, REPLACEMENTS[name], 1)
    return output


def apply_compatibility(source, version):
    """Apply only after every anchor validated; return the number of files patched."""
    output = prepare(source, version)
    for path, content in output.items():
        path.write_text(content)
    return len(output)
