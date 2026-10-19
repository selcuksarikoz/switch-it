"""Launch each Claude subscription account in its own configuration directory."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from .common import validate_name, write_json
from .ui import Account, choose_account, show_accounts

CLAUDE_STORE = Path(os.environ.get("XDG_DATA_HOME", "~/.local/share")).expanduser() / "switch-it" / "claude"


def claude_env(directory):
    # Explicit environment credentials would override the chosen login.
    overrides = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN",
                 "CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR", "ANTHROPIC_PROFILE",
                 "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY")
    present = [key for key in overrides if os.environ.get(key)]
    if present:
        raise ValueError("Unset authentication overrides before choosing an account: " + ", ".join(present))
    return {**os.environ, "CLAUDE_CONFIG_DIR": str(directory.resolve())}


def claude_status(directory):
    result = subprocess.run(["claude", "auth", "status", "--json"],
                            env=claude_env(directory), capture_output=True, text=True)
    try:
        data = json.loads(result.stdout)
        if not isinstance(data, dict):
            raise ValueError()
    except ValueError:
        raise ValueError("Could not read Claude auth status; check your Claude Code installation.") from None
    if not data.get("loggedIn"):
        raise ValueError("Claude profile is logged out. Run switch_it claude login NAME.")
    if data.get("authMethod") != "claude.ai":
        raise ValueError("Only claude.ai subscription logins are supported for Claude profiles.")
    return data


def run(argv):
    parser = argparse.ArgumentParser(prog="switch_it claude", description="Isolated Claude Code subscription accounts")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("list", help="List profiles (* = last selected by switch_it)")
    for command in ("add", "login", "use"):
        sub = commands.add_parser(command)
        sub.add_argument("name")
    args = parser.parse_args(argv)
    CLAUDE_STORE.mkdir(parents=True, exist_ok=True, mode=0o700)
    CLAUDE_STORE.chmod(0o700)
    items = sorted(p.name for p in CLAUDE_STORE.iterdir() if p.is_dir() and (p / ".switch-it.json").exists())
    active_file = CLAUDE_STORE / "selected.json"
    selected = json.loads(active_file.read_text()).get("name") if active_file.exists() else None
    rows = [Account(name, json.loads((CLAUDE_STORE / name / '.switch-it.json').read_text()).get('email', 'Claude'),
                    name == selected) for name in items]
    note = '* Selected = last Claude profile launched with switch_it.'
    if args.command == "list":
        show_accounts('Claude', rows, note)
        return 0
    if not shutil.which("claude"):
        raise ValueError("claude is not on PATH.")
    name = args.name if args.command else choose_account('Claude', rows, note)
    if name is None:
        return 0
    validate_name(name)
    directory = CLAUDE_STORE / name
    env = claude_env(directory)
    if args.command == "add":
        if directory.exists():
            raise ValueError("Profile already exists. Use switch_it claude login NAME to retry login.")
        directory.mkdir(mode=0o700)
    elif not directory.is_dir():
        raise ValueError(f"Unknown Claude profile: {name}")
    # A persistent directory also gives macOS a stable Keychain identity.
    # Failed logins remain retryable; never rename the directory after login.
    fd = os.open(directory / ".switch-it.lock", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("This Claude profile is already running in switch_it.") from None
        if args.command in ("add", "login"):
            result = subprocess.run(["claude", "auth", "login", "--claudeai"], env=env)
            if result.returncode:
                print(f"Login incomplete. Retry: switch_it claude login {name}", file=sys.stderr)
                return result.returncode
        status = claude_status(directory)
        write_json(directory / ".switch-it.json", {"email": status.get("email", "Claude")})
        if args.command in ("add", "login"):
            print(f"Saved '{name}'. Run switch_it claude to choose it.")
            return 0
        write_json(active_file, {"name": name})
        print(f"Starting Claude: {name} ({status.get('email', 'Claude')})", flush=True)
        return subprocess.run(["claude"], env=env).returncode


