"""Exercise the launcher's real subprocess boundary without starting a TUI."""
import json
import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]

class LauncherTests(unittest.TestCase):
    def test_preserves_resume_arguments_and_shared_daemon_eligibility(self):
        self.exercise_launcher()

    def test_socket_path_is_canonical_when_runtime_directory_is_a_symlink(self):
        calls,canonical=self.exercise_launcher(symlink_runtime=True)
        for (argv,kwargs),resolved in zip(calls,canonical):
            socket_path=Path(kwargs['env']['CODEX_THEATER_SOCKET'])
            self.assertEqual(socket_path,resolved)

    def exercise_launcher(self,symlink_runtime=False):
        module=runpy.run_path(str(ROOT/'scripts/codex-theater'))
        main=module['main']
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);(folder/'build').mkdir()
            binary=folder/'native-codex';binary.touch()
            (folder/'build/current.json').write_text(json.dumps({'binary':str(binary)}))
            main.__globals__['ROOT']=folder
            engine=Mock();engine.poll.return_value=None;engine.wait.return_value=0
            cli=Mock();cli.wait.return_value=0
            calls=[]
            canonical=[]
            def spawn(argv,**kwargs):
                calls.append((argv,kwargs))
                canonical.append(Path(kwargs['env']['CODEX_THEATER_SOCKET']).resolve())
                if '--runtime' in argv:
                    (Path(argv[argv.index('--runtime')+1])/'control.sock').touch()
                    return engine
                return cli
            home=folder/'codex-state';home.mkdir()
            runtime=folder/'runtime';runtime.mkdir()
            if symlink_runtime:
                alias=folder/'runtime-link';alias.symlink_to(runtime,target_is_directory=True)
                runtime=alias
            with patch('sys.argv',['codex-theater','resume','--all']), \
                 patch.dict(os.environ,{'CODEX_HOME':str(home),'XDG_RUNTIME_DIR':str(runtime)}), \
                 patch('subprocess.Popen',side_effect=spawn),patch('signal.signal'), \
                 patch('pathlib.Path.home',return_value=folder):
                self.assertEqual(main(),0)
            argv,kwargs=calls[-1]
            # A launcher-injected -c tui.pet override makes upstream daemon_startup
            # select embedded mode, disabling the empty-composer Left shortcut.
            self.assertEqual(argv,[str(binary),'resume','--all'])
            self.assertEqual(kwargs['env']['CODEX_HOME'],str(home))
            self.assertIn('CODEX_THEATER_SOCKET',kwargs['env'])
            engine.terminate.assert_called_once()
            self.assertEqual(list((folder/'.cache/codex-companion-theater/instances').glob('*.json')),[])
            return calls,canonical

if __name__=='__main__':unittest.main()
