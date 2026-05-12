import os
import pytest

@pytest.fixture(scope="session", autouse=True)
def force_exit_after_tests():
    """Force clean exit to avoid Qt/OpenGL crash on macOS during shutdown."""
    yield
    os._exit(0)  # bypass Python shutdown entirely
