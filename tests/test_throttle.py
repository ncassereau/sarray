import os
import subprocess
from unittest.mock import patch

import pytest

from sarray.throttle import ThrottleConfig, cmd_throttle, parse_scontrol_fields

# ---------------------------------------------------------------------------
# _parse_fields
# ---------------------------------------------------------------------------


def test_parse_fields_basic():
    line = "JobId=123 JobState=RUNNING UserId=alice(1000) ArrayJobId=100"
    d = parse_scontrol_fields(line)
    assert d["JobId"] == "123"
    assert d["JobState"] == "RUNNING"
    assert d["UserId"] == "alice(1000)"
    assert d["ArrayJobId"] == "100"


def test_parse_fields_empty():
    assert parse_scontrol_fields("") == {}
    assert parse_scontrol_fields("   ") == {}


def test_parse_fields_no_equals():
    assert parse_scontrol_fields("sometoken anothertoken") == {}


def test_parse_fields_multiple_equals_in_value():
    # Only first = is the separator
    line = "Key=a=b"
    d = parse_scontrol_fields(line)
    assert d["Key"] == "a=b"


# ---------------------------------------------------------------------------
# cmd_throttle — mocked scontrol
# ---------------------------------------------------------------------------

UID = os.getuid()


def _make_record(jobid: str, state: str = "PENDING", array_job_id: str = "100") -> str:
    return (
        f"JobId={jobid} ArrayJobId={array_job_id} ArrayTaskId=0 "
        f"JobState={state} UserId=user({UID}) JobName=test"
    )


def _ok(stdout: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def _fail(stderr: str = "error") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=stderr)


@patch("sarray.throttle.scontrol")
def test_throttle_basic(mock_sc):
    record = _make_record("100_0")
    mock_sc.side_effect = [_ok(record + "\n"), _ok()]  # show job, update

    cmd_throttle(ThrottleConfig(jobid=100, max_tasks=2))

    mock_sc.assert_any_call("update", "JobId=100", "ArrayTaskThrottle=2")


@patch("sarray.throttle.scontrol")
def test_throttle_job_not_found(mock_sc):
    mock_sc.return_value = _fail("not found")

    with pytest.raises(SystemExit):
        cmd_throttle(ThrottleConfig(jobid=999, max_tasks=2))


@patch("sarray.throttle.scontrol")
def test_throttle_not_array(mock_sc):
    # Record without ArrayJobId
    record = f"JobId=100 JobState=RUNNING UserId=user({UID})"
    mock_sc.return_value = _ok(record + "\n")

    with pytest.raises(SystemExit):
        cmd_throttle(ThrottleConfig(jobid=100, max_tasks=2))


@patch("sarray.throttle.scontrol")
def test_throttle_wrong_owner(mock_sc):
    record = "JobId=100 ArrayJobId=100 JobState=RUNNING UserId=other(9999)"
    mock_sc.return_value = _ok(record + "\n")

    with pytest.raises(SystemExit):
        cmd_throttle(ThrottleConfig(jobid=100, max_tasks=2))


@patch("sarray.throttle.scontrol")
def test_throttle_kill_no_excess(mock_sc):
    # 2 running tasks, max_tasks=3 → nothing to requeue
    records = "\n".join(
        [
            _make_record("100_0", "RUNNING"),
            _make_record("100_1", "RUNNING"),
            _make_record("100_2", "PENDING"),
        ]
    )
    mock_sc.side_effect = [_ok(records + "\n"), _ok(), _ok(records + "\n")]

    cmd_throttle(ThrottleConfig(jobid=100, max_tasks=3, kill=True))

    # requeue should NOT be called
    requeue_calls = [
        c for c in mock_sc.call_args_list if c.args and c.args[0] == "requeue"
    ]
    assert requeue_calls == []


@patch("sarray.throttle.scontrol")
def test_throttle_requeue_requeues_excess(mock_sc):
    # 3 running tasks, max_tasks=1 → 2 excess to requeue
    records = "\n".join(
        [
            _make_record("100_0", "RUNNING"),
            _make_record("100_1", "RUNNING"),
            _make_record("100_2", "RUNNING"),
            _make_record("100_3", "PENDING"),
        ]
    )
    mock_sc.side_effect = [
        _ok(records + "\n"),  # show job (initial check)
        _ok(),  # update throttle
        _ok(),  # requeue 100_1
        _ok(),  # requeue 100_2
    ]

    cmd_throttle(ThrottleConfig(jobid=100, max_tasks=1, requeue=True))

    requeue_calls = [
        c for c in mock_sc.call_args_list if c.args and c.args[0] == "requeue"
    ]
    assert len(requeue_calls) == 2
    requeued_ids = {c.args[1] for c in requeue_calls}
    assert requeued_ids == {"100_1", "100_2"}


@patch("sarray.throttle.scontrol")
def test_throttle_update_failure(mock_sc):
    record = _make_record("100_0")
    mock_sc.side_effect = [_ok(record + "\n"), _fail("permission denied")]

    with pytest.raises(SystemExit):
        cmd_throttle(ThrottleConfig(jobid=100, max_tasks=2))
