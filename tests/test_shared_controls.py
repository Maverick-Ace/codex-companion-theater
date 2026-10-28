"""MCP is launched by the daemon, without the foreground client's environment."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from theater.service import Theater, UnixServer
from theater.render import ROOT

class SharedControlTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.home=Path(self.temp.name)
        self.registry=self.home/'.cache/codex-companion-theater/instances'
        self.registry.mkdir(parents=True)
        self.servers=[]
        self.worlds={}

    def tearDown(self):
        for server,thread in self.servers:
            server.shutdown();server.server_close();thread.join()
        self.temp.cleanup()

    def add_instance(self,name):
        theater=Theater(self.home/name);sock=theater.runtime/'control.sock'
        server=UnixServer(sock,theater)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.servers.append((server,thread));self.worlds[name]=theater
        (self.registry/(name+'.json')).write_text(json.dumps({'v':1,'id':name,'socket':str(sock),'cwd':str(self.home/name)}))

    def call(self,arguments):
        env=dict(os.environ,HOME=str(self.home));env.pop('CODEX_THEATER_SOCKET',None)
        message={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'theater_scene','arguments':arguments}}
        p=subprocess.run([sys.executable,str(ROOT/'plugin/scripts/mcp_server.py')],env=env,input=json.dumps(message)+'\n',text=True,capture_output=True,check=True)
        return json.loads(p.stdout)['result']

    def test_daemon_control_discovers_single_live_foreground(self):
        self.add_instance('window-a')
        result=self.call({'name':'paperball'})
        self.assertFalse(result['isError'])
        self.assertEqual(self.worlds['window-a'].world.scene,'paperball')

    def test_multiple_windows_require_selection(self):
        self.add_instance('window-a');self.add_instance('window-b')
        result=self.call({'name':'paperball'})
        self.assertTrue(result['isError'])
        reply=json.loads(result['content'][0]['text'])
        self.assertEqual(len(reply['instances']),2)
        self.assertTrue(all(t.world.scene=='roam' for t in self.worlds.values()))

    def test_explicit_instance_only_controls_selected_window(self):
        self.add_instance('window-a');self.add_instance('window-b')
        result=self.call({'name':'paperball','instance_id':'window-b'})
        self.assertFalse(result['isError'])
        self.assertEqual(self.worlds['window-a'].world.scene,'roam')
        self.assertEqual(self.worlds['window-b'].world.scene,'paperball')

    def test_cli_without_foreground_environment_can_control_one_window(self):
        self.add_instance('window-a')
        env=dict(os.environ,HOME=str(self.home));env.pop('CODEX_THEATER_SOCKET',None)
        result=subprocess.run([sys.executable,'-m','theater.cli','scene','tea'],env=env,cwd=ROOT,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.worlds['window-a'].world.scene,'tea')

    def test_cli_multiple_windows_requires_explicit_selection(self):
        self.add_instance('window-a');self.add_instance('window-b')
        env=dict(os.environ,HOME=str(self.home),CODEX_THEATER_SOCKET=str(self.worlds['window-a'].runtime/'control.sock'))
        command=[sys.executable,'-m','theater.cli']
        refused=subprocess.run(command+['scene','tea'],env=env,cwd=ROOT,text=True,capture_output=True)
        self.assertEqual(refused.returncode,2)
        selected=subprocess.run(command+['--instance','window-b','scene','tea'],env=env,cwd=ROOT,text=True,capture_output=True)
        self.assertEqual(selected.returncode,0,selected.stderr)
        self.assertEqual(self.worlds['window-a'].world.scene,'roam')
        self.assertEqual(self.worlds['window-b'].world.scene,'tea')

if __name__=='__main__':unittest.main()
