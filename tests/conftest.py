import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from microduck_eyes import config as config_mod


@pytest.fixture(scope="session")
def cfg():
    return config_mod.load()
