"""
sbatch argument parser based on https://slurm.schedmd.com/sbatch.html
"""

from argparse import ArgumentParser
from pathlib import Path


def make_parser() -> ArgumentParser:
    p = ArgumentParser(add_help=False)

    def opt(*flags: str):
        p.add_argument(*flags, default=None)

    def flag(*flags: str):
        p.add_argument(*flags, action="store_true", default=False)

    def maybeopt(*flags: str):
        # nargs="?" with const=True: --flag → True, --flag=val → val, absent → None
        # Note: --flag value (space form) consumes the next token;
        # use --flag=value to avoid ambiguity with the script positional.
        p.add_argument(*flags, nargs="?", const=True, default=None)

    opt("--account", "-A")
    opt("--acctg-freq")
    opt("--array", "-a")
    opt("--batch")
    opt("--bb")
    opt("--bbf")
    opt("--begin", "-b")
    opt("--chdir", "-D")
    opt("--cluster-constraint")
    opt("--clusters", "-M")
    opt("--comment")
    flag("--consolidate-segments")
    opt("--constraint", "-C")
    opt("--container")
    opt("--container-id")
    flag("--contiguous")
    opt("--core-spec", "-S")
    opt("--cores-per-socket")
    opt("--cpu-freq")
    opt("--cpus-per-gpu")
    opt("--cpus-per-task", "-c")
    opt("--deadline")
    opt("--delay-boot")
    opt("--dependency", "-d")
    opt("--distribution", "-m")
    opt("--error", "-e")
    opt("--exclude", "-x")
    maybeopt("--exclusive")
    opt("--export")
    opt("--export-file")
    opt("--extra")
    opt("--extra-node-info", "-B")
    flag("--get-user-env")
    opt("--gid")
    opt("--gpu-bind")
    opt("--gpu-freq")
    opt("--gpus", "-G")
    opt("--gpus-per-node")
    opt("--gpus-per-socket")
    opt("--gpus-per-task")
    opt("--gres")
    opt("--gres-flags")
    flag("--hold", "-H")
    flag("--ignore-pbs")
    opt("--input", "-i")
    opt("--job-name", "-J")
    opt("--kill-on-invalid-dep")
    opt("--licenses", "-L")
    opt("--mail-type")
    opt("--mail-user")
    opt("--mcs-label")
    opt("--mem")
    opt("--mem-bind")
    opt("--mem-per-cpu")
    opt("--mem-per-gpu")
    opt("--mincpus")
    opt("--network")
    maybeopt("--nice")
    maybeopt("--no-kill", "-k")
    flag("--no-requeue")
    opt("--nodefile", "-F")
    opt("--nodelist", "-w")
    opt("--nodes", "-N")
    opt("--ntasks", "-n")
    opt("--ntasks-per-core")
    opt("--ntasks-per-gpu")
    opt("--ntasks-per-node")
    opt("--ntasks-per-socket")
    maybeopt("--oom-kill-step")
    opt("--open-mode")
    opt("--output", "-o")
    flag("--overcommit", "-O")
    flag("--oversubscribe", "-s")
    flag("--parsable")
    opt("--partition", "-p")
    opt("--prefer")
    opt("--priority")
    opt("--profile")
    maybeopt("--propagate")
    opt("--qos", "-q")
    flag("--quiet", "-Q")
    flag("--reboot")
    maybeopt("--requeue")
    opt("--reservation")
    opt("--resources")
    maybeopt("--resv-ports")
    opt("--segment")
    opt("--signal")
    opt("--sockets-per-node")
    flag("--spread-job")
    flag("--spread-segments")
    flag("--stepmgr")
    flag("--test-only")
    opt("--thread-spec")
    opt("--threads-per-core")
    opt("--time", "-t")
    opt("--time-min")
    opt("--tmp")
    opt("--tres-bind")
    opt("--uid")
    flag("--use-min-nodes")
    flag("--verbose", "-v")
    flag("--wait")
    opt("--wait-all-nodes")
    opt("--wckey")
    opt("--wrap")

    p.add_argument("script", nargs="?", type=Path, default=None)
    p.add_argument("script_args", nargs="*")

    return p


_PARSER = make_parser()


def parse_sbatch_argv(
    argv: list[str],
) -> tuple[dict[str, str | bool], Path | None, list[str]]:
    """Parse a sbatch argv (without the 'sbatch' command itself).

    Returns:
        sbatch_opts: explicitly-set options, keyed by long name with dashes
        script_file: path to the batch script, or None
        script_args: positional args passed to the script
    """
    ns, _ = _PARSER.parse_known_args(argv)
    d = vars(ns)
    script_file: Path | None = d.pop("script")
    script_args: list[str] = d.pop("script_args")
    # Normalize Python attr names (underscores) back to Slurm flag names (dashes)
    sbatch_opts = {
        k.replace("_", "-"): v for k, v in d.items() if v is not None and v is not False
    }
    return sbatch_opts, script_file, script_args
