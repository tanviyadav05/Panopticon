"""Thin re-export: the actual ActorCritic class lives in common/
policy_network.py so it's identical for the trainer here and the
edge-inference wrappers in red-team/ and blue-team/. Kept as its own file
in training/ so existing imports (`from policy import ActorCritic`) don't
need to change just because the canonical definition moved.
"""
import os
import sys

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "common")))
from policy_network import ActorCritic  # noqa: F401,E402
