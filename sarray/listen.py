import os
import shutil
import subprocess
import tempfile
from pathlib import Path

_BASH_INIT = """\
_SARRAY_DIR=$(pwd)
_SARRAY_PATH=$PATH
_SARRAY_CONDA=${CONDA_PREFIX:-}
[ -f ~/.bashrc ] && source ~/.bashrc
export PATH=$_SARRAY_PATH
[ -n "$_SARRAY_CONDA" ] && export CONDA_PREFIX=$_SARRAY_CONDA
cd "$_SARRAY_DIR"
unset _SARRAY_DIR _SARRAY_PATH _SARRAY_CONDA
sarray() {
    command sarray "$@"
    local _ret=$?
    [[ "$1" == submit || "$1" == cancel ]] && { exec 2>/dev/null; exit $_ret; }
    return $_ret
}
PS1='\\[\\e[1;33m\\][sarray]\\[\\e[0m\\] '$PS1
"""


def cmd_listen():
    with tempfile.TemporaryDirectory(prefix="sarray_") as tmpdir:
        tmpdir_path = Path(tmpdir)
        queue_file = tmpdir_path / "queue.conf"
        queue_file.touch()

        sbatch_fake = tmpdir_path / "sbatch"
        sbatch_fake.write_text(
            "#!/bin/bash\n"
            "printf -v _args '%q ' \"$@\"\n"
            'echo "sbatch ${_args% }" >> "$SARRAY_QUEUE_FILE"\n'
        )
        sbatch_fake.chmod(0o755)

        init_file = tmpdir_path / "bashrc"
        init_file.write_text(_BASH_INIT)

        env = os.environ.copy()
        real_sbatch = shutil.which("sbatch") or "sbatch"
        env["PATH"] = f"{tmpdir}:{env.get('PATH', '')}"
        env["SARRAY_QUEUE_FILE"] = str(queue_file)
        env["SARRAY_REAL_SBATCH"] = real_sbatch

        subprocess.run(["bash", "--rcfile", str(init_file)], env=env)
