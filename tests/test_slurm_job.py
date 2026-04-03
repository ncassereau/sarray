from pathlib import Path
from textwrap import dedent

import pytest

from sarray.slurm_job import SlurmJob, SlurmJobList

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_script(tmp_path, content: str, name: str = "job.slurm") -> Path:
    p = tmp_path / name
    p.write_text(dedent(content))
    return p


BASE_OPTS: dict[str, str | bool] = {
    "job-name": "test",
    "mem": "1GB",
    "time": "00:10:00",
}


def make_job(array: str, opts: dict | None = None) -> SlurmJob:
    o = {**BASE_OPTS, "array": array}
    if opts:
        o.update(opts)
    return SlurmJob(shebang="#!/bin/bash", slurm_options=o, script="echo hi", args=[])


# ---------------------------------------------------------------------------
# SlurmJob.from_sbatch_call — file parsing
# ---------------------------------------------------------------------------


def test_parse_shebang_and_options(tmp_path):
    f = make_script(
        tmp_path,
        """\
        #!/bin/bash
        #SBATCH --job-name=myjob
        #SBATCH --mem=4GB
        echo hello
    """,
    )
    job = SlurmJob.from_sbatch_call(f)
    assert job.shebang == "#!/bin/bash"
    assert job.slurm_options["job-name"] == "myjob"
    assert job.slurm_options["mem"] == "4GB"
    assert "echo hello" in job.script


def test_parse_no_shebang(tmp_path):
    f = make_script(
        tmp_path,
        """\
        #SBATCH --mem=2GB
        echo hi
    """,
    )
    job = SlurmJob.from_sbatch_call(f)
    assert job.shebang == "#!/bin/bash"
    assert job.slurm_options["mem"] == "2GB"


def test_parse_empty_file(tmp_path):
    f = tmp_path / "empty.slurm"
    f.write_text("")
    job = SlurmJob.from_sbatch_call(f)
    assert job.slurm_options == {}
    assert job.script == ""


def test_file_not_found():
    with pytest.raises(FileNotFoundError):
        SlurmJob.from_sbatch_call(Path("/nonexistent/job.slurm"))


def test_cli_overrides_file(tmp_path):
    f = make_script(tmp_path, "#SBATCH --mem=1GB\necho hi\n")
    job = SlurmJob.from_sbatch_call(f, {"mem": "16GB", "array": "0-9"})
    assert job.slurm_options["mem"] == "16GB"
    assert job.slurm_options["array"] == "0-9"


def test_positional_args_stored(tmp_path):
    f = make_script(tmp_path, "echo hi\n")
    job = SlurmJob.from_sbatch_call(f, {}, "foo", "bar")
    assert job.args == ["foo", "bar"]


# ---------------------------------------------------------------------------
# SlurmJob.from_sbatch_call — --wrap
# ---------------------------------------------------------------------------


def test_wrap_basic():
    job = SlurmJob.from_sbatch_call(None, {"wrap": "echo hello"})
    assert job.script == "echo hello"
    assert job.slurm_options == {}


def test_wrap_with_opts():
    job = SlurmJob.from_sbatch_call(
        None, {"wrap": "echo hi", "mem": "4GB", "array": "0-3"}
    )
    assert job.slurm_options["mem"] == "4GB"
    assert "wrap" not in job.slurm_options


def test_wrap_and_file_raises(tmp_path):
    f = make_script(tmp_path, "echo hi\n")
    with pytest.raises(ValueError, match="mutually exclusive"):
        SlurmJob.from_sbatch_call(f, {"wrap": "echo hi"})


def test_no_file_no_wrap_raises():
    with pytest.raises(ValueError, match="script file or --wrap"):
        SlurmJob.from_sbatch_call(None, {})


# ---------------------------------------------------------------------------
# SlurmJob.tasks — array range parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "array,expected",
    [
        ("0", [0]),
        ("3", [3]),
        ("0-2", [0, 1, 2]),
        ("1-5", [1, 2, 3, 4, 5]),
        ("0-6:2", [0, 2, 4, 6]),
        ("0,2,4", [0, 2, 4]),
        ("0-2,5,8-9", [0, 1, 2, 5, 8, 9]),
        ("0-4%2", [0, 1, 2, 3, 4]),  # throttle suffix stripped
    ],
)
def test_tasks(array, expected):
    job = SlurmJob(
        shebang="#!/bin/bash", slurm_options={"array": array}, script="", args=[]
    )
    assert job.tasks == expected


# ---------------------------------------------------------------------------
# SlurmJob.get_script — positional arg substitution
# ---------------------------------------------------------------------------


def test_get_script_dollar_at():
    job = SlurmJob(
        shebang="#!/bin/bash", slurm_options={}, script="run.py $@", args=["a", "b"]
    )
    assert job.get_script() == "run.py a b"


def test_get_script_positional():
    job = SlurmJob(
        shebang="#!/bin/bash", slurm_options={}, script="run.py $1 $2", args=["x", "y"]
    )
    assert job.get_script() == "run.py x y"


def test_get_script_no_args():
    job = SlurmJob(shebang="#!/bin/bash", slurm_options={}, script="echo hi", args=[])
    assert job.get_script() == "echo hi"


# ---------------------------------------------------------------------------
# SlurmJobList — compatibility & offsets
# ---------------------------------------------------------------------------


def test_compatible_jobs_merged():
    j1 = make_job("0-2")
    j2 = make_job("0-4")
    jl = SlurmJobList.from_slurm_jobs([j1, j2])
    assert jl.total_tasks == 3 + 5
    assert jl.offsets == [0, 3]


def test_single_job():
    j = make_job("0-2")
    jl = SlurmJobList.from_slurm_jobs([j])
    assert jl.total_tasks == 3
    assert jl.offsets == [0]


def test_incompatible_mem_raises():
    j1 = make_job("0-2")
    j2 = make_job("0-2", {"mem": "99GB"})
    with pytest.raises(ValueError, match="mem"):
        SlurmJobList.from_slurm_jobs([j1, j2])


def test_incompatible_missing_key_raises():
    j1 = make_job("0-2")
    j2 = SlurmJob(
        shebang="#!/bin/bash", slurm_options={"array": "0-2"}, script="", args=[]
    )
    with pytest.raises(ValueError):
        SlurmJobList.from_slurm_jobs([j1, j2])


def test_array_diff_is_not_incompatible():
    j1 = make_job("0-2")
    j2 = make_job("0-9")  # different array, same other opts
    jl = SlurmJobList.from_slurm_jobs([j1, j2])
    assert jl.total_tasks == 13


# ---------------------------------------------------------------------------
# SlurmJobList.get_job_info — global ID → (job, task_id) mapping
# ---------------------------------------------------------------------------


def test_get_job_info_first_job():
    j1 = make_job("0-2")  # tasks 0,1,2 → global 0,1,2
    j2 = make_job("0-3")  # tasks 0,1,2,3 → global 3,4,5,6
    jl = SlurmJobList.from_slurm_jobs([j1, j2])

    job, tid = jl.get_job_info(0)
    assert job is j1 and tid == 0

    job, tid = jl.get_job_info(2)
    assert job is j1 and tid == 2


def test_get_job_info_second_job():
    j1 = make_job("0-2")
    j2 = make_job("0-3")
    jl = SlurmJobList.from_slurm_jobs([j1, j2])

    job, tid = jl.get_job_info(3)
    assert job is j2 and tid == 0

    job, tid = jl.get_job_info(6)
    assert job is j2 and tid == 3


def test_get_job_info_with_step():
    # array 0-6:2 → tasks [0, 2, 4, 6]
    j = make_job("0-6:2")
    jl = SlurmJobList.from_slurm_jobs([j])

    _, tid = jl.get_job_info(0)
    assert tid == 0
    _, tid = jl.get_job_info(1)
    assert tid == 2
    _, tid = jl.get_job_info(3)
    assert tid == 6


def test_get_job_info_out_of_bounds():
    jl = SlurmJobList.from_slurm_jobs([make_job("0-2")])
    with pytest.raises(IndexError):
        jl.get_job_info(3)
    with pytest.raises(IndexError):
        jl.get_job_info(-1)


# ---------------------------------------------------------------------------
# SlurmJobList.make_slurm_job_array — submit-time overrides
# ---------------------------------------------------------------------------


def test_overrides_appear_in_script():
    jl = SlurmJobList.from_slurm_jobs([make_job("0-2")])
    script = jl.make_slurm_job_array(overrides={"dependency": "aftercorr:42"})
    assert "#SBATCH --dependency=aftercorr:42" in script


def test_overrides_replace_existing_option():
    jl = SlurmJobList.from_slurm_jobs([make_job("0-2")])
    script = jl.make_slurm_job_array(overrides={"mem": "99GB"})
    assert "#SBATCH --mem=99GB" in script
    assert "#SBATCH --mem=1GB" not in script


def test_overrides_do_not_mutate_jobs():
    j = make_job("0-2")
    jl = SlurmJobList.from_slurm_jobs([j])
    jl.make_slurm_job_array(overrides={"dependency": "aftercorr:42"})
    assert "dependency" not in j.slurm_options
