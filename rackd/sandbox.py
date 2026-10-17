"""The demo sandbox: a made-up network shown by a SEPARATE demo copy of Rack Live (RL_DEMO=1, RL_SCENE=<scene>) on its own port, with its own empty data folder.

It has no access to the real installation: no devices, no logins, no saved settings, nothing is shared except the program code. One sandbox at a time; it stops by itself after
SANDBOX_MINUTES or on request, and always when Rack Live stops."""
import json, os, socket, subprocess, sys, tempfile, threading, time, urllib.request

SANDBOX_MINUTES = 45


class Sandbox:
    def __init__(self, root):
        self.root = root
        self.proc = None
        self.info = {}
        self.dir = None
        self.timer = None

    def _free_port(self):
        for _ in range(30):
            s = socket.socket()
            s.bind(('0.0.0.0', 0))
            port = s.getsockname()[1]
            s.close()
            if port > 1024:
                return port
        raise RuntimeError('не нашёл свободный порт для демо')

    def status(self):
        if self.proc and self.proc.poll() is None:
            return dict(self.info, running=True, left=max(0, int(self.info['until'] - time.time())))
        return {'running': False}

    def stop(self):
        if self.timer:
            self.timer.cancel()
            self.timer = None
        p, self.proc = self.proc, None
        if p and p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=5)
            except Exception:
                p.kill()
        if self.dir:
            try:
                import shutil
                shutil.rmtree(self.dir, ignore_errors=True)
            except Exception:
                pass
            self.dir = None
        self.info = {}

    def start(self, scene_ref, scene_json=None, title=''):
        """scene_ref: 'builtin:campus' | 'builtin:starter' | None with scene_json = a CHECKED scene (written to a file the demo copy reads)"""
        self.stop()
        self.dir = tempfile.mkdtemp(prefix='rl-sandbox-')
        src = scene_ref
        if scene_json is not None:
            src = os.path.join(self.dir, 'scene.json')
            with open(src, 'w', encoding='utf-8') as f:
                json.dump(scene_json, f, ensure_ascii=False)
        port = self._free_port()
        env = {k: v for k, v in os.environ.items() if not k.startswith(('RL_',))}      # nothing of the real installation's settings is passed on
        env.update(RL_DEMO='1', RL_PORT=str(port), RL_DATA=os.path.join(self.dir, 'data'), RL_SCENE=src, PYTHONUNBUFFERED='1')
        env['RL_WEB'] = os.environ.get('RL_WEB', os.path.join(self.root, 'web'))
        errlog = os.path.join(self.dir, 'err.log')
        self.proc = subprocess.Popen([sys.executable, '-m', 'rackd'], cwd=self.root, env=env, stdout=subprocess.DEVNULL, stderr=open(errlog, 'wb'))
        for _ in range(60):                                   # up to ~30 s for the copy to answer
            if self.proc.poll() is not None:
                try:
                    err = open(errlog, encoding='utf-8', errors='replace').read().strip().splitlines()[-1:] or ['демо не запустилось']
                except OSError:
                    err = ['демо не запустилось']
                self.stop()
                raise RuntimeError(err[0][:200])
            try:
                urllib.request.urlopen(f'http://127.0.0.1:{port}/api/state', timeout=1).read(1)
                break
            except Exception:
                time.sleep(.5)
        else:
            self.stop()
            raise RuntimeError('демо не ответило за 30 секунд')
        self.info = {'port': port, 'title': title, 'until': time.time() + SANDBOX_MINUTES * 60, 'started': int(time.time())}
        self.timer = threading.Timer(SANDBOX_MINUTES * 60, self.stop)
        self.timer.daemon = True
        self.timer.start()
        return self.status()
