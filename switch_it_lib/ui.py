"""Shared terminal presentation and keyboard navigation for both providers."""

from dataclasses import dataclass
import os
import select
import shutil
import sys
import termios
import tty


@dataclass
class Account:
    name: str
    email: str
    selected: bool = False
    detail: str = ''


def color(text, code):
    enabled = sys.stdout.isatty() and 'NO_COLOR' not in os.environ and os.environ.get('TERM') != 'dumb'
    return f'\033[{code}m{text}\033[0m' if enabled else text


def clean(value):
    return ''.join(c if c.isprintable() else ' ' for c in str(value))


def cell(value, width):
    value = clean(value)
    return (value if len(value) <= width else value[:width - 1] + '…').ljust(width)


def account_table(provider, accounts, note, focus=None):
    width = min(shutil.get_terminal_size((88, 24)).columns, 100)
    compact = width < 64
    name_width = 18
    email_width = max(12, width - 42)
    lines = ['', '  ' + color(provider, '1;36') + color(f'  /  {len(accounts)} accounts', '2'), '']
    if accounts:
        if not compact:
            lines += ['      ' + color(cell('PROFILE', name_width) + '  ' + cell('EMAIL', email_width) + '  STATUS', '2'),
                      '  ' + color('─' * (width - 4), '2')]
        for i, account in enumerate(accounts):
            pointer = '›' if i == focus else ' '
            status = '* Selected' if account.selected else 'Saved'
            if compact:
                row = f'{pointer} {i + 1}. {account.name}  {status}'
                lines.append('  ' + color(clean(row), '1;32' if account.selected else '1' if i == focus else '0'))
                lines.append('     ' + cell(account.email, max(8, width - 6)).rstrip())
            else:
                row = f'{pointer} {i + 1:<2} ' + cell(account.name, name_width) + '  ' + cell(account.email, email_width) + '  ' + status
                lines.append(' ' + color(row, '1;32' if account.selected else '1' if i == focus else '0'))
        lines += ['', '  ' + color(note, '2')]
        if focus is not None and accounts[focus].detail:
            lines.append('  ' + color(clean(accounts[focus].detail), '2'))
    else:
        lines += ['  No saved accounts yet.', '  ' + color(f'Add one: switch_it {provider.lower()} add NAME', '36')]
    return '\n'.join(lines) + '\n'


def show_accounts(provider, accounts, note):
    print(account_table(provider, accounts, note))


def keyboard_menu(items, render):
    if not items:
        return None
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ValueError('Use an interactive terminal, or run switch_it PROVIDER use NAME.')
    fd = sys.stdin.fileno()
    previous = termios.tcgetattr(fd)
    index = 0
    number = ''
    try:
        tty.setraw(fd)
        sys.stdout.write('\033[?1049h\033[?25l')
        while True:
            view = render(index) + '\n  ↑/↓ move · Enter select · Esc cancel'
            if number:
                view += f' · Number: {number}'
            sys.stdout.write('\033[H\033[2J' + view.replace('\n', '\r\n'))
            sys.stdout.flush()
            key = os.read(fd, 1)
            if key == b'\x03':
                raise KeyboardInterrupt
            if key == b'\x1b':
                if not select.select([fd], [], [], 0.08)[0]:
                    return None
                sequence = os.read(fd, 1)
                if sequence in (b'[', b'O') and select.select([fd], [], [], 0.08)[0]:
                    direction = os.read(fd, 1)
                    if direction == b'A':
                        index = (index - 1) % len(items)
                    elif direction == b'B':
                        index = (index + 1) % len(items)
                number = ''
            elif key in (b'j', b'k'):
                index = (index + (1 if key == b'j' else -1)) % len(items)
                number = ''
            elif key in (b'q', b'\x04'):
                return None
            elif key in (b'\r', b'\n'):
                if number:
                    if not 1 <= int(number) <= len(items):
                        number = ''
                        continue
                    index = int(number) - 1
                return items[index]
            elif key.isdigit():
                number = (number + key.decode())[-4:]
            elif key in (b'\x7f', b'\x08'):
                number = number[:-1]
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, previous)
        sys.stdout.write('\033[?25h\033[?1049l')
        sys.stdout.flush()


def choose_provider(providers):
    def render(focus):
        lines = ['', '  ' + color('switch_it', '1;36'), '  Choose a provider', '']
        for i, name in enumerate(providers):
            text = f"  {'›' if focus == i else ' '} {i + 1}. {name.title()}"
            lines.append(color(text, '1;36' if focus == i else '0'))
        return '\n'.join(lines) + '\n'
    return keyboard_menu(providers, render)


def choose_account(provider, accounts, note):
    if not accounts:
        show_accounts(provider, accounts, note)
        return None
    chosen = keyboard_menu(accounts, lambda focus: account_table(provider, accounts, note, focus))
    return chosen.name if chosen else None
