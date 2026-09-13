#!/usr/bin/env sh
set -eu

fail=0

check_cmd() {
  if command -v "$1" >/dev/null 2>&1; then
    echo "PASS: $1 found"
  else
    echo "FAIL: $1 not found"
    fail=1
  fi
}

echo "AI Data Steward fresh-install preflight"
check_cmd docker
check_cmd python3
check_cmd curl

if docker compose version >/dev/null 2>&1; then
  echo "PASS: Docker Compose v2 available"
else
  echo "FAIL: Docker Compose v2 unavailable"
  fail=1
fi

if [ -f docker-compose.prod.yml ]; then
  echo "PASS: docker-compose.prod.yml found"
else
  echo "FAIL: docker-compose.prod.yml missing"
  fail=1
fi

if [ -f .env.production.example ]; then
  echo "PASS: .env.production.example found"
else
  echo "FAIL: .env.production.example missing"
  fail=1
fi

if [ "$fail" -ne 0 ]; then
  exit 1
fi

echo "Preflight passed."
