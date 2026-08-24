import time
import pytest
from hermes_personal.workflows.jobs import JobDispatcher, JobSpec, JobStatus, JobResult

def test_dispatch_successful_job():
    dispatcher = JobDispatcher()

    def dummy(x):
        return x * 2

    spec = JobSpec(job_id="j1", func=dummy, args=(21,))
    res = dispatcher.dispatch(spec)
    assert res.status == JobStatus.PENDING

    # Wait for completion
    time.sleep(0.1)
    result = dispatcher.get_result("j1")
    assert result is not None
    assert result.status == JobStatus.SUCCESS
    assert result.result == 42
    assert result.attempts == 1
    assert any(e["type"] == "job_success" and e["job_id"] == "j1" for e in dispatcher.events)

def test_dispatch_failing_job_with_retries():
    dispatcher = JobDispatcher()

    def fail_func():
        raise ValueError("failed operation")

    spec = JobSpec(job_id="j2", func=fail_func, max_retries=2, timeout=2)
    dispatcher.dispatch(spec)

    time.sleep(0.3)
    result = dispatcher.get_result("j2")
    assert result is not None
    assert result.status == JobStatus.FAILURE
    assert isinstance(result.error, ValueError)
    assert result.attempts == 3
    assert any(e["type"] == "job_failure" and e["job_id"] == "j2" for e in dispatcher.events)

def test_job_timeout():
    dispatcher = JobDispatcher()

    def slow_func():
        time.sleep(2.0)
        return "done"

    spec = JobSpec(job_id="j3", func=slow_func, timeout=1, max_retries=0)
    dispatcher.dispatch(spec)

    time.sleep(1.3)
    result = dispatcher.get_result("j3")
    assert result is not None
    assert result.status == JobStatus.FAILURE
    assert isinstance(result.error, TimeoutError)
