"""Snapshot and restore file-based Codex CLI logins."""

import argparse
import base64
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib

from .common import validate_name, write_json
from .ui import Account, choose_account, show_accounts

HOME = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser().resolve()
STORE = HOME / "switch-codex"
AUTH = HOME / "auth.json"


def read_auth(path):
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        tokens = data.get("tokens") or {}
        if not isinstance(tokens, dict) or not (tokens.get("access_token") or data.get("OPENAI_API_KEY")):
            raise ValueError()
        return data
    except (ValueError, AttributeError):
        raise ValueError(f"Invalid authentication file: {path}") from None


def claims(data):
    try:
        token = data["tokens"]["id_token"].split(".")[1]
        value = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
        return value if isinstance(value, dict) else {}
    except (KeyError, TypeError, ValueError, IndexError, AttributeError):
        return {}


def identity(data):
    if not data:
        return None
    if data.get("OPENAI_API_KEY"):
        return ("api", data["OPENAI_API_KEY"])
    info = claims(data)
    workspace = (data.get("tokens") or {}).get("account_id")
    # JWT claims are only local labels, never a verification of token validity.
    if info.get("sub") and workspace:
        return ("chatgpt", info["sub"], workspace)
    return ("token", (data.get("tokens") or {}).get("access_token"))


def label(data):
    if data.get("OPENAI_API_KEY"):
        return "API key"
    info = claims(data)
    workspace = (data.get("tokens") or {}).get("account_id", "unknown")
    return f"{info.get('email', 'ChatGPT')} / workspace {workspace}"


def profile(name):
    validate_name(name)
    return STORE / f"{name}.json"


def profiles():
    return [(p.stem, read_auth(p)) for p in sorted(STORE.glob("*.json"))]


def preserve_current():
    current = read_auth(AUTH)
    if not current:
        return
    matches = [name for name, data in profiles() if identity(data) == identity(current)]
    if not matches:
        name = "previous"
        number = 1
        while profile(name).exists():
            number += 1
            name = f"previous-{number}"
        matches = [name]
        print(f"Current login saved as '{name}'.")
    for name in matches:
        write_json(profile(name), current)


SELECTION_NOTE = '* Selected = current local Codex login.'


def account_rows():
    active = identity(read_auth(AUTH))
    return [Account(name, 'API key' if data.get('OPENAI_API_KEY') else claims(data).get('email', 'ChatGPT'),
                    identity(data) == active, label(data)) for name, data in profiles()]


def show():
    rows = account_rows()
    show_accounts('Codex', rows, SELECTION_NOTE)
    if identity(read_auth(AUTH)) and not any(row.selected for row in rows):
        print('  Current login is not saved. Run: switch_it codex save NAME')


def ensure_file_storage():
    path = HOME / "config.toml"
    config = tomllib.loads(path.read_text()) if path.exists() else {}
    if config.get("cli_auth_credentials_store", "file") != "file":
        raise ValueError('This tool requires cli_auth_credentials_store = "file" in CODEX_HOME/config.toml.')


def run(argv):
    parser = argparse.ArgumentParser(description=__doc__, prog="switch_it codex")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("list", help="List saved accounts (* = locally active)")
    save = commands.add_parser("save", help="Save the current Codex login")
    save.add_argument("name")
    add = commands.add_parser("add", help="Sign in separately and save another account")
    add.add_argument("name")
    add.add_argument("--device-auth", action="store_true")
    use = commands.add_parser("use", help="Activate a saved account and launch Codex")
    use.add_argument("name")
    use.add_argument("--no-start", action="store_true", help="Only change the active login")
    args = parser.parse_args(argv)
    ensure_file_storage()
    STORE.mkdir(parents=True, exist_ok=True, mode=0o700)
    STORE.chmod(0o700)
    # Keep the lock for the launched CLI's lifetime: another switch must not
    # overwrite its refresh tokens. Independently started Codex is not locked.
    lock_fd = os.open(STORE / ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(lock_fd, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Another switch_it codex session is running. Exit it first.") from None
        if args.command == "list":
            show()
            return 0
        if args.command in ("save", "add"):
            target = profile(args.name)
            if target.exists():
                raise ValueError(f"Profile '{args.name}' already exists; choose another name.")
            if args.command == "save":
                data = read_auth(AUTH)
                if not data:
                    raise ValueError("No current file-based login. Run switch_it codex add NAME.")
            else:
                if not shutil.which("codex"):
                    raise ValueError("codex is not on PATH.")
                with tempfile.TemporaryDirectory(prefix="login-", dir=STORE) as temporary:
                    command = ["codex", "-c", 'cli_auth_credentials_store="file"', "login"]
                    if args.device_auth:
                        command.append("--device-auth")
                    result = subprocess.run(command, env={**os.environ, "CODEX_HOME": temporary})
                    if result.returncode:
                        return result.returncode
                    data = read_auth(Path(temporary) / "auth.json")
                    if not data:
                        raise ValueError("Login did not produce a file-based session.")
            write_json(target, data)
            print(f"Saved '{args.name}' ({label(data)}). Run switch_it codex to choose it.")
            return 0
        if args.command == "use":
            name = args.name
        else:
            name = choose_account('Codex', account_rows(), SELECTION_NOTE)
            if name is None:
                return 0
        target = profile(name)
        if not target.exists():
            raise ValueError(f"Unknown profile: {name}")
        read_auth(target)  # Validate before touching current authentication.
        launch = not getattr(args, "no_start", False)
        if launch and not shutil.which("codex"):
            raise ValueError("codex is not on PATH.")
        preserve_current()
        selected = read_auth(target)  # May have just saved refreshed credentials.
        write_json(AUTH, selected)
        print(f"Active: {name} ({label(selected)})", flush=True)
        if launch:
            try:
                return subprocess.run(["codex"]).returncode
            finally:
                preserve_current()
        return 0



