from shimeji_dual_mode_agent import DualModeAgent


class DummyCM:
    def __init__(self):
        self.latest_context = {"foo": "bar"}
        self.updated = []

    def _update_context(self, value):
        self.latest_context = value
        self.updated.append(value)


class DummyAgent(DualModeAgent):
    def __init__(self):
        # Avoid running the real DualModeAgent constructor; only set context manager
        self._context_manager = DummyCM()


def test_set_latest_context():
    agent = DummyAgent()
    new_ctx = {"title": "UnitTest", "application": "pytest", "pid": 123}
    agent._latest_context = new_ctx
    assert agent._context_manager.updated[-1] == new_ctx
