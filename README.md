# switch-it

**Pick an account. Open Codex or Claude Code with that account.**

Use this when you have a work account and a personal account and do not want to sign out and sign in every time.

```sh
switch_it              # Choose Codex or Claude, then choose an account
switch_it list         # See all accounts you have added
```

This is a local terminal tool for **macOS and Linux**. It does not switch accounts in desktop apps or browser tabs. It is not an official OpenAI or Anthropic tool.

## 1. What you need

Install these first:

- [uv](https://docs.astral.sh/uv/getting-started/installation/), which runs the Python code.
- [Codex CLI](https://developers.openai.com/codex/cli/) if you want to switch Codex accounts.
- [Claude Code](https://code.claude.com/docs/en/setup) if you want to switch Claude accounts.

You only need the CLI you plan to use. Python 3.11 or newer is required; `uv` can download it for you. There are no third-party Python dependencies.

## 2. Try it without installing a command

Open a terminal in the folder containing this project:

```sh
cd ~/Documents/projects/switch-it
uv run switch_it.py --help
uv run switch_it.py list
```

If you cloned the project somewhere else, use that folder instead.

You can always use `uv run switch_it.py` instead of `switch_it` in the examples below.

## 3. Install or update with one command

From the project folder, run:

```sh
./install.sh
```

That's it. Now you can run `switch_it` from any folder.

The installer builds `dist/switch_it.pyz`, checks that it starts, and installs it in `~/.local/share/switch-it/bin/`. It creates the launcher `~/.local/bin/switch_it`. If `XDG_DATA_HOME` is set, the installed archive goes under that directory instead.

**Run the same command whenever you update the code.** It replaces the existing build and launcher automatically, including an older symlink. Your saved accounts are kept separately and are not changed. No `sudo` is needed.

This is a Python archive, not a native binary. `uv` is still required to run it. The installed copy does not depend on the project folder, so moving the source folder does not break the command.

If your terminal says `command not found: switch_it`, add this line to your `~/.zshrc` (Zsh) or `~/.bashrc` (Bash), then open a new terminal:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

## 4. Add your Codex accounts

Suppose Codex is currently signed in to your work account.

**First, save that login:**

```sh
switch_it codex save work
```

`work` is just a name you choose. You could call it `sirket`, `personal`, or `my-account`.

**Next, add your personal account:**

```sh
switch_it codex add personal
```

A Codex login flow opens. Sign in with your **personal** account in the browser. Check which account the browser selects: it may remember your work login.

This new login happens in a separate temporary folder. It does **not** overwrite your current Codex login.

**Now choose an account and start Codex:**

```sh
switch_it codex
```

Use the Up/Down arrow keys and press Enter. You can also type an account number and press Enter. Codex starts in your terminal using that account and your current working directory.

Or skip the menu:

```sh
switch_it codex use personal
```

Already used the old `switch_codex` tool? Your saved profiles are still available. Use the new `switch_it` command; the old `switch_codex` shortcut is no longer needed. For example, an existing `sirket` profile does not need to be saved again.

## 5. Add your Claude accounts

Add each Claude account once:

```sh
switch_it claude add work
switch_it claude add personal
```

Each command opens Claude's login flow. Choose the matching account in your browser each time.

Then choose an account and start Claude:

```sh
switch_it claude
```

Or start one directly:

```sh
switch_it claude use personal
```

**Claude works differently from Codex:** each account gets its own permanent configuration folder. Claude stores and refreshes the login itself. The tool does not copy tokens out of macOS Keychain.

That means:

- You must sign in once for each new Claude profile, even if ordinary `claude` is already logged in.
- There is no `switch_it claude save` command. Use `add` instead.
- Settings, history, and setup belong to each profile separately.
- Running plain `claude` still uses your usual Claude configuration. Use `switch_it claude` to open one of these saved accounts.
- This supports **claude.ai subscription accounts**, including Pro, Max, Teams and Enterprise. Claude Console/API-key and cloud-provider accounts are not supported by this account picker.

## Everyday commands

| Command | What it does |
| --- | --- |
| `switch_it` | Choose the tool, choose the account, start the CLI |
| `switch_it list` | List saved accounts for both tools |
| `switch_it codex list` | List saved Codex accounts |
| `switch_it claude list` | List saved Claude accounts |
| `switch_it codex save NAME` | Save the current Codex login |
| `switch_it codex add NAME` | Sign in to another Codex account and save it |
| `switch_it claude add NAME` | Create a separate Claude profile and sign in |
| `switch_it codex use NAME` | Activate that Codex account and start Codex |
| `switch_it claude use NAME` | Start Claude using that account's configuration |
| `switch_it codex use NAME --no-start` | Change the active Codex login without starting the CLI |
| `switch_it claude login NAME` | Retry or renew a login in an existing Claude profile |

Names can contain letters, numbers, hyphens and underscores, up to 64 characters. Use Up/Down (or j/k) to move, Enter to select, and Esc or q to cancel. With no arguments, the provider menu shows installed CLIs and providers with saved accounts.

Both providers use the same colored table: profile, email and status. Color is disabled when output is redirected or `NO_COLOR` is set. On narrow terminals, both use the same compact layout.

### What does `* Selected` mean?

For **Codex**, it marks a saved account matching the current local `auth.json`. It is not an online check that the token is still valid.

For **Claude**, it marks the profile you last launched with `switch_it`. It does not mean that ordinary `claude` or a desktop app uses that profile. The list shows the email recorded at the last login or launch; launching checks Claude's auth status again.

## How accounts are kept separate

Codex normally has one active login file. This tool saves a copy for each account. Before switching, it saves the latest version of the outgoing login, including refreshed tokens. If that account has no saved name, it is preserved as `previous` (or `previous-2`, etc.). After the launched CLI exits, its updated login is saved again.

Claude uses a separate `CLAUDE_CONFIG_DIR` for each account. Those directories stay at the same paths because Claude's macOS Keychain entries are tied to them. Failed login folders are kept so you can retry with `switch_it claude login NAME`.

Neither provider discovers old logins or accounts in your browser. Only accounts you explicitly add or save appear in the list.

## Where is my data?

Account data stays **outside this Git repository**:

| Data | Default location |
| --- | --- |
| Codex saved logins | `~/.codex/switch-codex/NAME.json` |
| Codex active login | `~/.codex/auth.json` |
| Claude profile folders | `~/.local/share/switch-it/claude/NAME/` |

The old `switch-codex` storage name is intentionally kept so existing Codex profiles continue to work. `CODEX_HOME` changes the Codex base folder. `XDG_DATA_HOME` changes the Claude storage base folder.

Codex snapshots contain plaintext credentials. Their files are created with permission `600` and the profile directory with `700`. Treat them like passwords; never commit or share them. Claude manages its own credential storage, including Keychain on macOS. The tool does not print tokens.

## Common problems

**“Profile already exists”**

The tool will not silently overwrite an account. For Claude, use `switch_it claude login NAME` to sign in again. For Codex, add a new profile name when you need a fresh login.

**The browser keeps choosing the wrong account**

Choose the intended account in the browser before completing login. The profile name is only a label; naming a profile `personal` cannot force the browser to choose your personal account.

**Codex login cannot open a browser callback**

Try `switch_it codex add NAME --device-auth`. Your account or workspace must allow device-code login.

**Codex uses Keychain or another credential store**

This tool supports Codex's file-based storage only. An explicit `keyring`, `auto`, or `ephemeral` setting is rejected. It does not change your credential-storage settings or bypass organization policies.

**Another Codex session is open**

Close other Codex CLI, IDE, or desktop sessions before switching. They can keep an old login in memory or write back to the shared login file. This tool prevents a second switch while its own Codex child is running. Codex profiles share normal Codex settings and history; they are not separate work environments.

**Claude reports authentication environment variables**

An API key, OAuth token, or cloud-provider setting in your shell can override a selected login. The tool names the conflicting variables and stops. Use a shell without those overrides for subscription accounts. It does not print their values or remove them for you. Project-level and managed Claude settings still apply.

**I want to switch the desktop app**

This tool launches terminal CLIs. It does not switch desktop app sessions.

## Project layout

```text
install.sh                # Build and overwrite the local installation
switch_it.py              # Executable entry point; uv metadata
switch_it_lib/
  cli.py                  # Command routing and provider menu
  codex.py                # Codex login snapshots and switching
  claude.py               # Isolated Claude profiles and launching
  common.py               # Name validation and atomic JSON writes
  ui.py                   # Shared tables, colors and arrow-key menus
  __init__.py
tests/
  test_switch_it.py       # Tests with fake CLIs and temporary account data
```

Run tests:

```sh
uv run --python '>=3.11' python -m unittest discover -s tests -v
```

Tests do not log in to real accounts or modify your real credentials.

## References

- [OpenAI: Codex authentication](https://developers.openai.com/codex/auth/)
- [Anthropic: multiple Claude accounts](https://code.claude.com/docs/en/authentication#log-in-with-multiple-accounts)
