from pathlib import Path

from sarray.sbatch_parser import parse_sbatch_argv


def test_simple_script():
    opts, script, args = parse_sbatch_argv(["job.slurm"])
    assert script == Path("job.slurm")
    assert opts == {}
    assert args == []


def test_script_with_positional_args():
    opts, script, args = parse_sbatch_argv(["job.slurm", "arg1", "arg2"])
    assert script == Path("job.slurm")
    assert args == ["arg1", "arg2"]


def test_long_flag_with_space():
    opts, script, args = parse_sbatch_argv(["--ntasks", "4", "job.slurm"])
    assert opts["ntasks"] == "4"
    assert script == Path("job.slurm")


def test_long_flag_with_equals():
    opts, script, args = parse_sbatch_argv(["--ntasks=4", "job.slurm"])
    assert opts["ntasks"] == "4"


def test_short_flag():
    opts, script, args = parse_sbatch_argv(["-n", "4", "job.slurm"])
    assert opts["ntasks"] == "4"


def test_array_flag():
    opts, script, args = parse_sbatch_argv(["--array", "0-5", "job.slurm"])
    assert opts["array"] == "0-5"
    assert script == Path("job.slurm")


def test_array_does_not_steal_script():
    # --array takes a value, so "0-5" must not be mistaken for the script
    opts, script, args = parse_sbatch_argv(["--array", "0-5", "job.slurm"])
    assert script == Path("job.slurm")
    assert opts["array"] == "0-5"


def test_boolean_flag():
    opts, script, args = parse_sbatch_argv(["--oversubscribe", "job.slurm"])
    assert opts.get("oversubscribe") is True
    assert script == Path("job.slurm")


def test_optional_flag_without_value():
    # --flag alone (no script after it) → True
    opts, script, args = parse_sbatch_argv(["--exclusive"])
    assert opts.get("exclusive") is True


def test_optional_flag_without_value_before_script():
    # nargs="?" would eat the script as value; use = form to avoid ambiguity
    opts, script, args = parse_sbatch_argv(["--exclusive=user", "job.slurm"])
    assert opts["exclusive"] == "user"
    assert script == Path("job.slurm")


def test_optional_flag_with_value():
    opts, script, args = parse_sbatch_argv(["--exclusive=user", "job.slurm"])
    assert opts["exclusive"] == "user"


def test_wrap_no_script():
    opts, script, args = parse_sbatch_argv(["--wrap", "echo hello"])
    assert script is None
    assert opts["wrap"] == "echo hello"


def test_wrap_with_extra_opts():
    opts, script, args = parse_sbatch_argv(
        ["--wrap", "echo hi", "--mem=4GB", "--array", "0-2"]
    )
    assert opts["wrap"] == "echo hi"
    assert opts["mem"] == "4GB"
    assert opts["array"] == "0-2"
    assert script is None


def test_multiple_flags():
    opts, script, args = parse_sbatch_argv(
        [
            "--job-name",
            "myjob",
            "--mem=8GB",
            "-t",
            "01:00:00",
            "job.slurm",
        ]
    )
    assert opts["job-name"] == "myjob"
    assert opts["mem"] == "8GB"
    assert opts["time"] == "01:00:00"
    assert script == Path("job.slurm")


def test_unknown_flags_ignored():
    # Unknown flags in = form don't disturb positional arg parsing
    opts, script, args = parse_sbatch_argv(["--some-future-flag=val", "job.slurm"])
    assert script == Path("job.slurm")


def test_no_args():
    opts, script, args = parse_sbatch_argv([])
    assert script is None
    assert opts == {}
    assert args == []
