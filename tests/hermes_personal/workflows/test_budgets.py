import pytest
from hermes_personal.workflows.budgets import (
    BudgetPolicy,
    BudgetEngine,
    BudgetError,
    init_default_engine,
    check_budget,
    reserve_budget,
    commit_budget,
    release_budget,
)

@pytest.fixture
def engine():
    policy = BudgetPolicy(max_total=1000, per_channel={"chanA": 500, "chanB": 300})
    return BudgetEngine(policy)

def test_check_budget_success(engine):
    engine.check_budget("chanA", 200)
    engine.check_budget("chanC", 100)  # falls back to max_total

def test_check_budget_exceeds_channel(engine):
    with pytest.raises(BudgetError):
        engine.check_budget("chanA", 600)

def test_check_budget_exceeds_total(engine):
    engine.check_budget("chanA", 400)
    engine.check_budget("chanB", 300)
    with pytest.raises(BudgetError):
        engine.check_budget("chanC", 400)

def test_reserve_and_commit(engine):
    alloc = engine.reserve_budget("chanA", 200)
    assert not alloc._committed
    engine.commit_budget(alloc)
    assert alloc._committed
    assert engine._allocated["chanA"] == 200

def test_release_budget(engine):
    alloc = engine.reserve_budget("chanB", 100)
    engine.release_budget(alloc)
    assert alloc not in engine._pending

def test_default_engine():
    policy = BudgetPolicy(max_total=500, per_channel={})
    init_default_engine(policy)
    check_budget("any", 100)
    alloc = reserve_budget("any", 200)
    commit_budget(alloc)
    with pytest.raises(BudgetError):
        reserve_budget("any", 400)  # exceeds max_total
