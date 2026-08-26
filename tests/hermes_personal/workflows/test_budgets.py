import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from hermes_personal.storage.sqlite import connect
from hermes_personal.workflows.budgets import (
    BudgetAllocation,
    BudgetConflict,
    BudgetEngine,
    BudgetError,
    BudgetPolicy,
    BudgetRepository,
    check_budget,
    commit_budget,
    get_allocated_budget,
    init_default_engine,
    release_budget,
    reserve_budget,
)
import pytest


@pytest.fixture
def memory_connection():
    conn = connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def file_connection(tmp_path):
    db_path = tmp_path / "budget_test.sqlite"
    conn = connect(db_path)
    yield conn, db_path
    conn.close()


@pytest.fixture
def engine(memory_connection):
    policy = BudgetPolicy(max_total=1000, per_channel={"chanA": 500, "chanB": 300})
    return BudgetEngine(policy, connection=memory_connection)


# 1. Reserve under limit succeeds
def test_reserve_under_limit_succeeds(engine):
    alloc = engine.reserve_budget("chanA", 200)
    assert alloc.channel == "chanA"
    assert alloc.amount == 200
    assert alloc.state == "reserved"
    assert not alloc._committed


# 2. Total limit enforced
def test_total_limit_enforced(engine):
    engine.reserve_budget("chanA", 500)
    engine.reserve_budget("chanB", 300)
    # Total used = 800 out of max_total=1000. Next 300 on chanC exceeds max_total.
    with pytest.raises(BudgetError, match="total budget exceeds max_total"):
        engine.reserve_budget("chanC", 300)


# 3. Per-channel limit enforced
def test_per_channel_limit_enforced(engine):
    engine.reserve_budget("chanA", 400)
    with pytest.raises(BudgetError, match="channel 'chanA' exceeds its limit"):
        engine.reserve_budget("chanA", 200)


# 4. check_budget does not mutate state
def test_check_budget_does_not_mutate(engine):
    engine.check_budget("chanA", 300)
    assert engine.get_allocated("chanA") == 0

    # Total allocated remains 0
    alloc = engine.reserve_budget("chanA", 200)
    assert engine.get_allocated("chanA") == 0  # Only committed allocations count in get_allocated
    engine.commit_budget(alloc)
    assert engine.get_allocated("chanA") == 200


# 5. Reservation is counted exactly once
def test_reservation_counted_once(engine):
    engine.check_budget("chanA", 200)
    first = engine.reserve_budget("chanA", 200)
    engine.commit_budget(first)
    second = engine.reserve_budget("chanA", 300)
    engine.commit_budget(second)

    assert engine.get_allocated("chanA") == 500


# 6. Duplicate reserve with same key/digest returns same record
def test_duplicate_reserve_same_key_digest(engine):
    alloc1 = engine.reserve_budget("chanA", 200, idempotency_key="key-123")
    alloc2 = engine.reserve_budget("chanA", 200, idempotency_key="key-123")

    assert alloc1.reservation_id == alloc2.reservation_id
    assert alloc1.amount == alloc2.amount
    assert alloc1.idempotency_key == alloc2.idempotency_key


# 7. Same key with different amount/digest raises conflict
def test_same_key_different_amount_digest_conflict(engine):
    engine.reserve_budget("chanA", 200, idempotency_key="key-123")

    with pytest.raises(BudgetConflict, match="Idempotency conflict"):
        engine.reserve_budget("chanA", 300, idempotency_key="key-123")

    with pytest.raises(BudgetConflict, match="Idempotency conflict"):
        engine.reserve_budget("chanB", 200, idempotency_key="key-123")


# 8. Commit retry does not double-count
def test_commit_retry_no_double_count(engine):
    alloc = engine.reserve_budget("chanA", 200)
    assert not alloc._committed
    engine.commit_budget(alloc)
    assert alloc._committed
    assert engine.get_allocated("chanA") == 200

    # Retry commit
    engine.commit_budget(alloc)
    assert alloc._committed
    assert engine.get_allocated("chanA") == 200


# 9. Release retry does not double-release
def test_release_retry_no_double_release(engine):
    alloc = engine.reserve_budget("chanB", 100)
    engine.release_budget(alloc)
    assert alloc.state == "released"

    # Retry release
    engine.release_budget(alloc)
    assert alloc.state == "released"

    # Can reserve up to full limit again
    engine.reserve_budget("chanB", 300)


# 10. Restart preserves reserved/committed/released state
def test_restart_preserves_budget_state(file_connection):
    conn1, db_path = file_connection
    policy = BudgetPolicy(max_total=1000, per_channel={"chanA": 500})
    repo1 = BudgetRepository(conn1)

    alloc1 = repo1.reserve_budget(policy, "chanA", 200, idempotency_key="k1")
    repo1.commit_budget(alloc1)

    alloc2 = repo1.reserve_budget(policy, "chanA", 200, idempotency_key="k2")  # Reserved

    alloc3 = repo1.reserve_budget(policy, "chanA", 100, idempotency_key="k3")
    repo1.release_budget(alloc3)

    conn1.close()

    # Simulate process restart by reopening database
    conn2 = connect(db_path)
    try:
        repo2 = BudgetRepository(conn2)

        # Committed budget is preserved
        assert repo2.get_allocated(channel="chanA") == 200

        # Reserved (200) + Committed (200) = 400 total used. Remaining for chanA (limit 500) = 100.
        # Reserving 100 on chanA succeeds
        alloc4 = repo2.reserve_budget(policy, "chanA", 100, idempotency_key="k4")
        assert alloc4.amount == 100

        # Next reserve on chanA exceeds limit (500)
        with pytest.raises(BudgetError, match="channel 'chanA' exceeds its limit"):
            repo2.reserve_budget(policy, "chanA", 50, idempotency_key="k5")

        # Retry k1 returns committed allocation
        retry1 = repo2.reserve_budget(policy, "chanA", 200, idempotency_key="k1")
        assert retry1.state == "committed"
    finally:
        conn2.close()


# 11. Owner/scope isolation
def test_owner_budget_isolation(memory_connection):
    policy = BudgetPolicy(max_total=300, per_channel={"chanA": 300})
    repo = BudgetRepository(memory_connection)

    # Owner Alice reserves 250
    alice_alloc = repo.reserve_budget(
        policy, "chanA", 250, owner_user_id="alice", scope_id="scope1"
    )
    assert alice_alloc.owner_user_id == "alice"

    # Owner Bob reserves 250 on same channel/scope -> succeeds because Bob has distinct owner scope
    bob_alloc = repo.reserve_budget(
        policy, "chanA", 250, owner_user_id="bob", scope_id="scope1"
    )
    assert bob_alloc.owner_user_id == "bob"

    # Alice trying another 100 fails
    with pytest.raises(BudgetError):
        repo.reserve_budget(policy, "chanA", 100, owner_user_id="alice", scope_id="scope1")

    # Bob trying another 100 fails
    with pytest.raises(BudgetError):
        repo.reserve_budget(policy, "chanA", 100, owner_user_id="bob", scope_id="scope1")


# 12. Two concurrent reservations near limit - only one succeeds
def test_concurrent_reservations_race_condition(file_connection):
    _, db_path = file_connection
    policy = BudgetPolicy(max_total=300, per_channel={"chanA": 300})
    barrier = threading.Barrier(2)

    results = []
    errors = []

    def run_reservation(key_name: str):
        conn = connect(db_path)
        try:
            repo = BudgetRepository(conn)
            barrier.wait(timeout=5.0)
            alloc = repo.reserve_budget(policy, "chanA", 200, idempotency_key=key_name)
            results.append(alloc)
        except Exception as ex:
            errors.append(ex)
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(run_reservation, "race-1")
        f2 = executor.submit(run_reservation, "race-2")
        f1.result()
        f2.result()

    # Exactly one thread succeeds in reserving 200; the other fails because 200 + 200 > 300
    assert len(results) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], BudgetError)

    # Verify database total used = 200
    verify_conn = connect(db_path)
    try:
        repo_verify = BudgetRepository(verify_conn)
        row = verify_conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM budget_reservation WHERE state IN ('reserved', 'committed')"
        ).fetchone()
        assert row["total"] == 200
    finally:
        verify_conn.close()


# 13. Transaction rollback leaves no partial reservation
def test_transaction_rollback_no_partial_reservation(memory_connection):
    policy = BudgetPolicy(max_total=500, per_channel={})
    repo = BudgetRepository(memory_connection)

    # Simulate an error during execution
    with pytest.raises(BudgetError):
        # Exceeds total
        repo.reserve_budget(policy, "chanA", 600)

    rows = memory_connection.execute("SELECT * FROM budget_reservation").fetchall()
    assert len(rows) == 0


# 14. Backend/database failure fails closed
def test_database_failure_fails_closed(tmp_path):
    db_path = tmp_path / "closed.sqlite"
    conn = connect(db_path)
    repo = BudgetRepository(conn)
    policy = BudgetPolicy(max_total=500, per_channel={})
    conn.close()  # Close connection to simulate database failure

    with pytest.raises(BudgetError, match="database failure"):
        repo.check_budget(policy, "chanA", 100)

    with pytest.raises(BudgetError, match="database failure"):
        repo.reserve_budget(policy, "chanA", 100)


# 15. Existing caller compatibility
def test_existing_caller_compatibility():
    policy = BudgetPolicy(max_total=500, per_channel={})
    init_default_engine(policy)
    check_budget("any", 100)
    alloc = reserve_budget("any", 200)
    assert not alloc._committed
    commit_budget(alloc)
    assert alloc._committed
    assert get_allocated_budget("any") == 200
    with pytest.raises(BudgetError):
        reserve_budget("any", 400)
