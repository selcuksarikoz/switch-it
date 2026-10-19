"""Subprocess tests: all credentials, profiles and CLIs are temporary fakes."""

import base64
import fcntl
import json
import os
import pty
import select
import termios
import time
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'switch_it.py'


def auth(user, token):
    claims = base64.urlsafe_b64encode(json.dumps({'sub': user, 'email': user + '@example.test'}).encode()).decode().rstrip('=')
    return {'tokens': {'id_token': 'x.' + claims + '.x', 'access_token': token,
                       'refresh_token': 'fake', 'account_id': 'workspace'}}


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / 'codex-home'
        self.home.mkdir()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(('ANTHROPIC_', 'CLAUDE_', 'CODEX_'))}
        self.env.pop('NO_COLOR', None)
        self.env.update(CODEX_HOME=str(self.home), XDG_DATA_HOME=str(self.root / 'data'),
                        PATH=str(self.bin) + os.pathsep + os.environ['PATH'])
        self.work = auth('work', 'work-token')
        (self.home / 'auth.json').write_text(json.dumps(self.work))
        self.claude_store = self.root / 'data/switch-it/claude'
        self.fake('codex', '''import json, os, pathlib, sys
p = pathlib.Path(os.environ['CODEX_HOME']) / 'auth.json'
if 'login' in sys.argv:
    if os.environ.get('TEST_FAIL'): sys.exit(1)
    p.write_text(%r)
else:
    d = json.loads(p.read_text())
    d['tokens']['access_token'] = 'refreshed'
    p.write_text(json.dumps(d))
''' % json.dumps(auth('personal', 'personal-token')))
        self.fake('claude', '''import json, os, pathlib, sys
p = pathlib.Path(os.environ['CLAUDE_CONFIG_DIR'])
a = p / 'fake-login.json'
if sys.argv[1:3] == ['auth', 'login']:
    if os.environ.get('TEST_FAIL'): sys.exit(1)
    a.write_text(json.dumps({'loggedIn': True, 'authMethod': 'claude.ai', 'email': p.name + '@example.test'}))
elif sys.argv[1:3] == ['auth', 'status']:
    print(a.read_text() if a.exists() else '{"loggedIn": false}')
else:
    (p / 'launched').write_text(str(p))
''')

    def fake(self, name, body):
        p = self.bin / name
        p.write_text('#!' + sys.executable + '\n' + body)
        p.chmod(0o755)

    def run_cli(self, *args, success=True, extra=None):
        result = subprocess.run([sys.executable, str(SCRIPT), *args],
                                env={**self.env, **(extra or {})}, text=True, capture_output=True)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result

    def read(self, path):
        return json.loads(path.read_text())

    def test_codex_isolated_add_switch_and_refresh(self):
        self.run_cli('codex', 'save', 'work')
        self.run_cli('codex', 'add', 'personal')
        self.assertEqual(self.read(self.home / 'auth.json'), self.work)
        self.run_cli('codex', 'use', 'personal')
        saved = self.read(self.home / 'switch-codex/personal.json')
        self.assertEqual(saved['tokens']['access_token'], 'refreshed')
        self.run_cli('codex', 'use', 'work', '--no-start')
        self.assertEqual(self.read(self.home / 'auth.json'), self.work)
        self.assertRegex(self.run_cli('codex', 'list').stdout, r'work +work@example.test +\* Selected')
        self.assertEqual((self.home / 'auth.json').stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.home / 'switch-codex').stat().st_mode & 0o777, 0o700)

    def test_codex_preserves_unregistered_login(self):
        self.run_cli('codex', 'add', 'personal')
        self.run_cli('codex', 'use', 'personal', '--no-start')
        self.assertEqual(self.read(self.home / 'switch-codex/previous.json'), self.work)

    def test_codex_failed_login_and_invalid_target_leave_current_untouched(self):
        self.run_cli('codex', 'add', 'failed', success=False, extra={'TEST_FAIL': '1'})
        self.run_cli('codex', 'use', 'missing', success=False)
        self.run_cli('codex', 'save', '../escape', success=False)
        self.assertEqual(self.read(self.home / 'auth.json'), self.work)
        self.assertFalse((self.home / 'switch-codex/failed.json').exists())
        self.assertFalse(list((self.home / 'switch-codex').glob('login-*')))

    def test_codex_storage_and_lock_guards(self):
        self.run_cli('codex', 'save', 'work')
        self.run_cli('codex', 'save', 'work', success=False)
        with (self.home / 'switch-codex/.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.run_cli('codex', 'use', 'work', success=False)
        (self.home / 'config.toml').write_text('cli_auth_credentials_store = "keyring"\n')
        self.run_cli('codex', 'use', 'work', success=False)
        self.assertEqual(self.read(self.home / 'auth.json'), self.work)

    def test_claude_profiles_launch_in_separate_directories(self):
        for name in ('work', 'personal'):
            self.run_cli('claude', 'add', name)
        self.run_cli('claude', 'use', 'personal')
        self.assertTrue((self.claude_store / 'personal/launched').exists())
        self.assertFalse((self.claude_store / 'work/launched').exists())
        self.assertEqual(self.read(self.home / 'auth.json'), self.work)
        self.assertRegex(self.run_cli('claude', 'list').stdout, r'personal +personal@example.test +\* Selected')
        self.run_cli('claude', 'use', 'work')
        self.assertRegex(self.run_cli('claude', 'list').stdout, r'work +work@example.test +\* Selected')
        self.assertEqual((self.claude_store / 'work').stat().st_mode & 0o777, 0o700)

    def test_claude_failed_add_is_retryable(self):
        self.run_cli('claude', 'add', 'work', success=False, extra={'TEST_FAIL': '1'})
        self.assertNotIn('work@example.test', self.run_cli('claude', 'list').stdout)
        self.run_cli('claude', 'login', 'work')
        self.assertIn('work@example.test', self.run_cli('claude', 'list').stdout)
        self.run_cli('claude', 'add', 'work', success=False)

    def test_claude_rejects_overrides_missing_profiles_and_logged_out_accounts(self):
        self.run_cli('claude', 'add', 'work')
        self.run_cli('claude', 'use', 'work', success=False, extra={'ANTHROPIC_API_KEY': 'fake-secret'})
        self.run_cli('claude', 'use', 'missing', success=False)
        self.run_cli('claude', 'add', '../escape', success=False)
        self.assertFalse((self.claude_store / 'work/launched').exists())
        (self.claude_store / 'work/fake-login.json').unlink()
        self.run_cli('claude', 'use', 'work', success=False)

    def test_claude_lock_blocks_duplicate_session(self):
        self.run_cli('claude', 'add', 'work')
        with (self.claude_store / 'work/.switch-it.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.run_cli('claude', 'use', 'work', success=False)

    def test_combined_list_uses_matching_columns(self):
        self.run_cli('codex', 'save', 'work')
        self.run_cli('claude', 'add', 'personal')
        output = self.run_cli('list').stdout
        self.assertIn('Codex', output)
        self.assertIn('Claude', output)
        self.assertEqual(output.count('PROFILE'), 2)
        self.assertEqual(output.count('EMAIL'), 2)
        self.assertEqual(output.count('STATUS'), 2)
        self.assertNotIn('\033[', output)

    def interactive(self, steps):
        master, slave = pty.openpty()
        before = termios.tcgetattr(slave)
        process = subprocess.Popen([sys.executable, str(SCRIPT)], stdin=slave, stdout=slave,
                                   stderr=slave, env={**self.env, 'TERM': 'xterm-256color'})
        output = b''
        try:
            for expected, keys in steps:
                pending = b''
                deadline = time.monotonic() + 5
                while expected not in pending:
                    if time.monotonic() > deadline:
                        self.fail('Menu did not appear: ' + repr(pending))
                    if select.select([master], [], [], 0.1)[0]:
                        chunk = os.read(master, 65536)
                        pending += chunk
                        output += chunk
                os.write(master, keys)
            deadline = time.monotonic() + 5
            while process.poll() is None:
                if time.monotonic() > deadline:
                    self.fail('Menu did not exit: ' + repr(output))
                if select.select([master], [], [], 0.1)[0]:
                    output += os.read(master, 65536)
            self.assertEqual(process.returncode, 0)
            flags = termios.ECHO | termios.ICANON | termios.ISIG
            self.assertEqual(termios.tcgetattr(slave)[3] & flags, before[3] & flags)
            return output
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)
            os.close(slave)

    def test_arrow_keys_choose_provider_then_account(self):
        self.run_cli('claude', 'add', 'personal')
        self.run_cli('claude', 'add', 'work')
        output = self.interactive([(b'Choose a provider', b'\x1b[B\r'),
                                   (b'PROFILE', b'\x1b[B\r')])
        self.assertTrue((self.claude_store / 'work/launched').exists())
        self.assertFalse((self.claude_store / 'personal/launched').exists())
        self.assertIn(b'\x1b[1;36m', output)

    def test_escape_cancels_provider_menu_and_restores_terminal(self):
        self.interactive([(b'Choose a provider', b'\x1b')])
        self.assertEqual(self.read(self.home / 'auth.json'), self.work)



if __name__ == '__main__':
    unittest.main()
