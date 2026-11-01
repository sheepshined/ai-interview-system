from agent.protocol import command_allowed, phase_error


def test_protocol_phase_guards():
    assert command_allowed("answer", "await_answer")
    assert command_allowed("answer", "await_followup")
    assert not command_allowed("answer", "await_report")

    assert command_allowed("end", "await_answer")
    assert not command_allowed("end", "completed")

    assert command_allowed("report", "await_report")
    assert not command_allowed("report", "completed")
    assert not command_allowed("report", "await_answer")
    assert "await_answer" in phase_error("report", "await_answer")
