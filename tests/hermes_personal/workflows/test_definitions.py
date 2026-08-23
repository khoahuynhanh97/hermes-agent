import pytest
from hermes_personal.workflows.definitions import DEFINITIONS

@pytest.mark.parametrize("name,aggregate", [(n, a) for n, a in DEFINITIONS.items()])
def test_initial_state_first(name, aggregate):
    # initial_state should be the first element in states list
    assert aggregate.states[0] == aggregate.initial_state

@pytest.mark.parametrize("name,aggregate", [(n, a) for n, a in DEFINITIONS.items()])
def test_legal_transitions(name, aggregate):
    for from_state, to_states in aggregate.transitions.items():
        for to_state in to_states:
            # should not raise IllegalTransition
            aggregate.validate_transition(from_state, to_state)

@pytest.mark.parametrize("name,aggregate", [(n, a) for n, a in DEFINITIONS.items()])
def test_illegal_transition_raises(name, aggregate):
    # pick a from_state that exists and a to_state not allowed
    from_state = aggregate.states[0]
    # ensure to_state is not in allowed list
    illegal = next(s for s in aggregate.states if s not in aggregate.transitions.get(from_state, []))
    with pytest.raises(Exception):
        aggregate.validate_transition(from_state, illegal)

def test_required_artifacts_nonempty():
    for agg in DEFINITIONS.values():
        for state, artifacts in agg.required_artifacts.items():
            assert artifacts, f"{agg.name}:{state} missing required artifacts"

def test_approval_requirements_boolean():
    for agg in DEFINITIONS.values():
        for state, req in agg.approval_required.items():
            assert isinstance(req, bool), f"{agg.name}:{state} approval flag not bool"
