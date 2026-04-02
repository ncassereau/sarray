import os
import sys
from pathlib import Path

from sarray.utils import console, err_console


def cmd_cancel():
    queue_file = os.environ.get("SARRAY_QUEUE_FILE")
    if not queue_file:
        err_console.print("[bold red]Error:[/] no active listen session.")
        sys.exit(1)

    Path(queue_file).unlink(missing_ok=True)
    console.print("[bold green]Listen session cancelled.[/]")
