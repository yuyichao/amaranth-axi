import os
import pytest

def pytest_runtest_setup(item):
    os.environ["__TRANSACTRON_LOG_FILTER"] = ".*"
    os.environ["__TRANSACTRON_LOG_LEVEL"] = "WARNING"
