"""Command routing for switch_it."""

import sys
import shutil

from . import claude, codex
from .ui import choose_provider


def main():
    argv = sys.argv[1:]
    if argv and argv[0] in ("-h", "--help"):
        print("switch_it [codex|claude] [list|add NAME|use NAME]\n"
              "switch_it list                 List both providers\n"
              "switch_it codex save NAME      Save current Codex login\n"
              "switch_it claude login NAME    Re-authenticate a Claude profile\n"
              "No arguments: choose provider, then account.")
        return 0
    if argv == ["list"]:
        codex.run(["list"])
        return claude.run(["list"])
    available = [name for name, saved in (
        ('codex', any(codex.STORE.glob('*.json'))),
        ('claude', any(claude.CLAUDE_STORE.glob('*/.switch-it.json'))),
    ) if shutil.which(name) or saved]
    if not argv and not available:
        print('No providers found. Install Codex CLI or Claude Code first.')
        return 0
    provider = argv.pop(0) if argv else choose_provider(available)
    if provider is None:
        return 0
    if provider not in ("codex", "claude"):
        raise ValueError("Choose codex or claude. See switch_it --help.")
    return codex.run(argv) if provider == "codex" else claude.run(argv)


