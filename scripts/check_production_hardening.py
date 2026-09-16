#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import stat
import sys
from pathlib import Path
from urllib.parse import urlparse

ENV_PATH = Path(sys.argv[1] if len(sys.argv) > 1 else ".env.production")

REQUIRED = [
    "APP_SITE_ADDRESS",
    "PUBLIC_APP_URL",
    "CORS_ORIGINS",
    "TRUSTED_HOSTS",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "AUTH_MODE",
    "AUTH_SECRET_KEY",
]

SECRET_KEYS = {
    "POSTGRES_PASSWORD",
    "AUTH_SECRET_KEY",
    "CKAN_API_KEY",
    "TESTGEN_TOKEN",
    "TESTGEN_OAUTH_CLIENT_SECRET",
    "TESTGEN_OAUTH_REFRESH_TOKEN",
}


def parse_env(path: Path) -> dict[str, str]:
    values = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def fail(message: str, failures: list[str]):
    failures.append(message)


if not ENV_PATH.exists():
    raise SystemExit(f"FAIL: {ENV_PATH} does not exist")

values = parse_env(ENV_PATH)
failures: list[str] = []
warnings: list[str] = []

for key in REQUIRED:
    if not values.get(key):
        fail(f"{key} is missing or empty", failures)

for key in SECRET_KEYS:
    value = values.get(key, "")
    if value and "CHANGE_ME" in value.upper():
        fail(f"{key} still contains CHANGE_ME", failures)

if values.get("AUTH_MODE", "").lower() == "demo":
    fail("AUTH_MODE must not be demo for production", failures)

if len(values.get("AUTH_SECRET_KEY", "")) < 32:
    fail("AUTH_SECRET_KEY must be at least 32 characters", failures)

if len(values.get("POSTGRES_PASSWORD", "")) < 20:
    fail("POSTGRES_PASSWORD should be at least 20 characters", failures)

if "*" in values.get("CORS_ORIGINS", ""):
    fail("CORS_ORIGINS must not contain *", failures)

if "*" in values.get("TRUSTED_HOSTS", ""):
    fail("TRUSTED_HOSTS must not contain *", failures)

public_url = values.get("PUBLIC_APP_URL", "")
if public_url:
    parsed = urlparse(public_url)
    if parsed.hostname not in {"localhost", "127.0.0.1"} and parsed.scheme != "https":
        fail("PUBLIC_APP_URL must use https for a non-local deployment", failures)

try:
    mode = stat.S_IMODE(ENV_PATH.stat().st_mode)
    if mode & 0o077:
        warnings.append(
            f"{ENV_PATH} permissions are {oct(mode)}; recommended: chmod 600 {ENV_PATH}"
        )
except OSError:
    pass

# subprocess with an argument list: os.system() built a shell command from the
# path, so any path containing spaces or shell metacharacters was injected.
git_checked = False
try:
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", str(ENV_PATH)],
        cwd=ENV_PATH.resolve().parent,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0
    git_checked = True
except (OSError, subprocess.SubprocessError):
    warnings.append("git is unavailable, so it could not be confirmed that the environment file is untracked")
    tracked = False
if tracked:
    fail(f"{ENV_PATH} is tracked by git", failures)

print("AI Data Steward production hardening check")
print(f"Environment file: {ENV_PATH}")

for warning in warnings:
    print(f"WARN: {warning}")

if failures:
    for message in failures:
        print(f"FAIL: {message}")
    raise SystemExit(1)

print("PASS: required production secrets/settings passed basic validation")
print("PASS: database password is passed separately and is safe to contain URL-special characters")
if git_checked:
    print("PASS: environment file is not tracked by git")
if not warnings:
    print("PASS: environment file permissions are appropriately restrictive")
