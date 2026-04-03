import os
import subprocess
import sys
from dataclasses import dataclass

import simple_parsing

from sarray.utils import console, err_console


@dataclass
class ThrottleConfig:
    jobid: int = simple_parsing.field(positional=True, metavar="JOBID")
    max_tasks: int = simple_parsing.field(
        alias=["-n", "--max", "--max-tasks"], metavar="N"
    )
    kill: bool = simple_parsing.field(default=False, alias=["-k", "--kill"])
    requeue: bool = simple_parsing.field(default=False, alias=["-r", "--requeue"])


def scontrol(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["scontrol", *args], capture_output=True, text=True)


def parse_scontrol_fields(line: str) -> dict[str, str]:
    """Parse a scontrol -o line into a key→value dict."""
    fields = {}
    for token in line.strip().split():
        if "=" in token:
            k, _, v = token.partition("=")
            fields[k] = v
    return fields


def cmd_throttle(config: ThrottleConfig):
    # 1. Fetch job info (one record per line with -o)
    result = scontrol("show", "-o", "job", str(config.jobid))
    if result.returncode != 0:
        err_console.print(f"[bold red]Error:[/] job {config.jobid} not found.")
        sys.exit(1)

    records = [
        parse_scontrol_fields(line)
        for line in result.stdout.splitlines()
        if line.strip()
    ]
    if not records:
        err_console.print(f"[bold red]Error:[/] job {config.jobid} not found.")
        sys.exit(1)

    first = records[0]

    # Check ownership
    uid_field = first.get("UserId", "")  # format: "username(uid)"
    if f"({os.getuid()})" not in uid_field:
        err_console.print(
            f"[bold red]Error:[/] job {config.jobid} does not belong to you."
        )
        sys.exit(1)

    # Check it's a job array
    if "ArrayJobId" not in first:
        err_console.print(f"[bold red]Error:[/] job {config.jobid} is not a job array.")
        sys.exit(1)

    # 2. Update throttle
    result = scontrol(
        "update", f"JobId={config.jobid}", f"ArrayTaskThrottle={config.max_tasks}"
    )
    if result.returncode != 0:
        err_console.print(f"[bold red]scontrol error:[/]\n{result.stderr.strip()}")
        sys.exit(result.returncode)
    console.print(
        f"[green]Throttle updated to [bold]{config.max_tasks}[/] "
        f"for job [bold]{config.jobid}[/].[/]"
    )

    # 3. Act on excess running tasks if requested
    if not config.kill and not config.requeue:
        return

    running = sorted(
        [r for r in records if r.get("JobState") == "RUNNING"],
        key=lambda r: r.get("StartTime", ""),
        reverse=False,
    )
    excess = running[config.max_tasks :]
    if not excess:
        console.print("[dim]No excess running tasks to act on.[/]")
        return

    if config.requeue:
        console.print(f"[yellow]Requeueing {len(excess)} excess running task(s)...[/]")
        for r in excess:
            jid = r["JobId"]
            display_id = f"{r['ArrayJobId']}_{r['ArrayTaskId']}"
            res = scontrol("requeue", jid)
            if res.returncode != 0:
                err_console.print(
                    f"[bold red]Failed to requeue {display_id}:[/] {res.stderr.strip()}"
                )
            else:
                console.print(f"  [dim]requeued {display_id}[/]")

    if config.kill:
        console.print(f"[yellow]Cancelling {len(excess)} excess running task(s)...[/]")
        for r in excess:
            jid = r["JobId"]
            display_id = f"{r['ArrayJobId']}_{r['ArrayTaskId']}"
            res = subprocess.run(["scancel", jid], capture_output=True, text=True)
            if res.returncode != 0:
                err_console.print(
                    f"[bold red]Failed to cancel {display_id}:[/] {res.stderr.strip()}"
                )
            else:
                console.print(f"  [dim]cancelled {display_id}[/]")
