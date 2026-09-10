from .profile_validator import evaluate_profile
from .snapshot import build_asset_snapshot


def calculate_readiness(asset):
    return evaluate_profile(build_asset_snapshot(asset))
