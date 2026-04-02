import io
from pathlib import Path
from textwrap import dedent

import pytest

from sarray.submit import parse_lines


def lines(text: str):
    return io.StringIO(dedent(text))


def make_slurm(tmp_path, array="0-2", name="job.slurm") -> Path:
    p = tmp_path / name
    p.write_text(f"#!/bin/bash\n#SBATCH --array={array}\n#SBATCH --mem=1GB\necho hi\n")
    return p


# ---------------------------------------------------------------------------
# Basic parsing
# ---------------------------------------------------------------------------


def test_simple_script(tmp_path):
    f = make_slurm(tmp_path)
    jobs = parse_lines(lines(f"sbatch {f}\n"))
    assert len(jobs) == 1
    assert jobs[0].slurm_options["array"] == "0-2"


def test_sbatch_prefix_stripped(tmp_path):
    f = make_slurm(tmp_path)
    jobs = parse_lines(lines(f"sbatch {f}"))
    assert len(jobs) == 1


def test_no_sbatch_prefix(tmp_path):
    f = make_slurm(tmp_path)
    jobs = parse_lines(lines(str(f)))
    assert len(jobs) == 1


def test_script_args_captured(tmp_path):
    f = make_slurm(tmp_path)
    jobs = parse_lines(lines(f"sbatch {f} arg1 arg2"))
    assert jobs[0].args == ["arg1", "arg2"]


def test_cli_opts_override(tmp_path):
    f = make_slurm(tmp_path, array="0-2")
    jobs = parse_lines(lines(f"sbatch --array 0-9 {f}"))
    assert jobs[0].slurm_options["array"] == "0-9"


def test_multiple_jobs(tmp_path):
    f1 = make_slurm(tmp_path, array="0-2", name="j1.slurm")
    f2 = make_slurm(tmp_path, array="0-4", name="j2.slurm")
    jobs = parse_lines(lines(f"sbatch {f1}\nsbatch {f2}\n"))
    assert len(jobs) == 2


def test_comments_and_blank_lines_ignored(tmp_path):
    f = make_slurm(tmp_path)
    jobs = parse_lines(lines(f"\n# comment\nsbatch {f}\n\n"))
    assert len(jobs) == 1


def test_wrap_line():
    jobs = parse_lines(lines('sbatch --wrap "echo hello" --array 0-2 --mem 1GB'))
    assert len(jobs) == 1
    assert jobs[0].script == "echo hello"
    assert jobs[0].slurm_options["array"] == "0-2"


def test_wrap_and_file_mixed(tmp_path):
    f = make_slurm(tmp_path)
    with pytest.raises(ValueError, match="mutually exclusive"):
        parse_lines(lines(f'sbatch --wrap "echo hi" {f}'))


def test_args_with_spaces_quoted(tmp_path):
    f = make_slurm(tmp_path)
    jobs = parse_lines(lines(f"sbatch {f} 'hello world' foo"))
    assert jobs[0].args == ["hello world", "foo"]


def test_no_file_no_wrap_skipped():
    # A line with only flags and no script/wrap should be skipped silently
    jobs = parse_lines(lines("sbatch --mem 4GB\n"))
    assert jobs == []
