import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import IO

import simple_parsing
from rich.syntax import Syntax

from sarray.sbatch_parser import parse_sbatch_argv
from sarray.slurm_job import SlurmJob, SlurmJobList
from sarray.utils import console, err_console


@dataclass
class SubmitConfig:
    filename: Path | None = simple_parsing.field(
        positional=True,
        default=None,
        metavar="FILE|-",
        help=(
            "Config file listing jobs, or - for stdin. "
            "Omit to use the active listen session."
        ),
    )
    output: Path = simple_parsing.field(
        default=Path("sarray.slurm"),
        type=Path,
        alias=["-o", "--output"],
        help="Save the generated script to this file (and still submit it)",
    )
    throttle: int | None = simple_parsing.field(
        default=None,
        alias=["-t", "--throttle"],
        help="Max number of simultaneously running tasks (adds %%N to --array)",
    )
    dry_run: bool = simple_parsing.field(
        default=False,
        alias=["-n", "--dry-run"],
        action="store_true",
        help="Write the generated script to disk and print it, but do not submit",
    )


def parse_lines(lines: IO[str]) -> list[SlurmJob]:
    jobs = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = shlex.split(line)
        if not parts:
            continue
        if parts[0] == "sbatch":
            parts = parts[1:]
        sbatch_opts, script_file, script_args = parse_sbatch_argv(parts)
        if script_file is None and "wrap" not in sbatch_opts:
            continue
        jobs.append(SlurmJob.from_sbatch_call(script_file, sbatch_opts, *script_args))
    return jobs


def submit(
    jobs: list[SlurmJob], script_file: Path, throttle: int | None, dry_run: bool
):
    script = SlurmJobList.from_slurm_jobs(jobs).make_slurm_job_array(throttle=throttle)
    script_file.write_text(script)
    if dry_run:
        console.print(Syntax(script, "bash", theme="monokai", line_numbers=True))
        return
    real_sbatch = os.environ.get("SARRAY_REAL_SBATCH", "sbatch")
    result = subprocess.run(
        [real_sbatch, str(script_file)], capture_output=True, text=True
    )
    sys.stdout.write(result.stdout)
    if result.returncode != 0:
        err_console.print(f"[bold red]sbatch error:[/]\n{result.stderr.strip()}")
        sys.exit(result.returncode)


def cmd_submit(config: SubmitConfig):

    if config.filename is not None:
        if config.filename == Path("-"):
            jobs = parse_lines(sys.stdin)
        else:
            with config.filename.open() as f:
                jobs = parse_lines(f)
        submit(jobs, config.output, config.throttle, config.dry_run)
        return

    # No file given: use the active listen session queue
    queue_file = os.environ.get("SARRAY_QUEUE_FILE")
    if not queue_file:
        err_console.print(
            "[bold red]Error:[/] no file given and SARRAY_QUEUE_FILE is not set."
            " Did you run [bold]sarray listen[/]?"
        )
        sys.exit(1)

    queue_path = Path(queue_file)
    if not queue_path.exists() or queue_path.stat().st_size == 0:
        err_console.print("[yellow]No jobs in queue.[/]")
        return

    with queue_path.open("r") as f:
        jobs = parse_lines(f)

    if not jobs:
        err_console.print("[yellow]No jobs in queue.[/]")
        return

    try:
        submit(jobs, config.output, config.throttle, config.dry_run)
    finally:
        if not config.dry_run:
            queue_path.unlink(missing_ok=True)
