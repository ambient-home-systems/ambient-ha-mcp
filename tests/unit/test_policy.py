from ambient_ha.policy import OperationClass, PolicyEngine


def test_phase_one_policy_allows_reads_and_denies_controls() -> None:
    engine = PolicyEngine()

    assert engine.evaluate(OperationClass.READ).allowed is True
    assert engine.evaluate(OperationClass.NORMAL_CONTROL).allowed is False
    assert engine.evaluate(OperationClass.SENSITIVE_CONTROL).allowed is False
    assert engine.evaluate(OperationClass.ADMINISTRATIVE).allowed is False
