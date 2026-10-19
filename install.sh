#!/bin/sh
# Build a Python zipapp and replace the local installation. Safe to rerun.
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
uv_bin=$(command -v uv) || {
    echo 'uv is required. Install it first: https://docs.astral.sh/uv/' >&2
    exit 1
}

"$uv_bin" run --no-project --python '>=3.11' python - "$project_dir" "$uv_bin" <<'PY'
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import zipapp

source = Path(sys.argv[1])
uv = str(Path(sys.argv[2]).resolve())
dist = source / 'dist'
install_dir = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'switch-it/bin'
bin_dir = Path.home() / '.local/bin'
for directory in (dist, install_dir, bin_dir):
    directory.mkdir(parents=True, exist_ok=True)


def replace_file(destination, content, mode):
    fd, temporary = tempfile.mkstemp(prefix='.switch-it-', dir=destination.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, destination)  # Replace symlinks, never their targets.
    finally:
        Path(temporary).unlink(missing_ok=True)


with tempfile.TemporaryDirectory(prefix='switch-it-build-') as temporary:
    build = Path(temporary) / 'app'
    build.mkdir()
    shutil.copy2(source / 'switch_it.py', build / '__main__.py')
    shutil.copytree(source / 'switch_it_lib', build / 'switch_it_lib',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    archive = Path(temporary) / 'switch_it.pyz'
    zipapp.create_archive(build, archive, compressed=True)
    # Validate the actual build before replacing an existing installation.
    subprocess.run([sys.executable, str(archive), '--help'], check=True, stdout=subprocess.DEVNULL)
    content = archive.read_bytes()
    replace_file(dist / 'switch_it.pyz', content, 0o644)
    installed = install_dir / 'switch_it.pyz'
    replace_file(installed, content, 0o644)

launcher = ('#!/bin/sh\nexec ' + shlex.quote(uv)
            + " run --no-project --python '>=3.11' python "
            + shlex.quote(str(installed)) + ' "$@"\n')
replace_file(bin_dir / 'switch_it', launcher.encode(), 0o755)
print(f'Built:     {dist / "switch_it.pyz"}')
print(f'Installed: {bin_dir / "switch_it"}')
print('Run: switch_it')
if str(bin_dir) not in os.environ.get('PATH', '').split(os.pathsep):
    print('Add this to ~/.zshrc or ~/.bashrc, then open a new terminal:')
    print('  export PATH="$HOME/.local/bin:$PATH"')
PY
