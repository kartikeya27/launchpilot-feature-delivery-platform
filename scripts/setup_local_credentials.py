#!/usr/bin/env python3
"""Create ignored local secrets for the disposable Compose integration stack."""
import argparse
import os
from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
KEYS = (
    "DEMO_ADMIN_PASSWORD",
    "DEMO_VIEWER_PASSWORD",
    "KEYCLOAK_ADMIN_PASSWORD",
    "GRAFANA_ADMIN_PASSWORD",
)


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ci", action="store_true", help="Export generated credentials to GitHub Actions")
    args = parser.parse_args()

    existing = read_env(ENV_FILE)
    empty = [key for key in KEYS if key in existing and not existing[key]]
    if empty:
        parser.error("Empty password values in .env: " + ", ".join(empty))

    new_values = {key: secrets.token_hex(20) for key in KEYS if key not in existing}
    if new_values:
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
        fd = os.open(ENV_FILE, flags, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as out:
            if ENV_FILE.stat().st_size:
                out.write("\n")
            out.write("# Auto-generated local-only Compose credentials; never commit this file.\n")
            for key, value in new_values.items():
                out.write(f"{key}={value}\n")
    os.chmod(ENV_FILE, 0o600)

    values = {**existing, **new_values}
    if args.ci:
        github_env = os.getenv("GITHUB_ENV")
        if not github_env:
            parser.error("--ci requires GITHUB_ENV")
        with open(github_env, "a", encoding="utf-8") as out:
            for key in KEYS:
                print("::add-mask::" + values[key])
                out.write(f"{key}={values[key]}\n")

    print("Local Compose credentials ready in ignored .env (permissions: owner only).")
    if not args.ci:
        print("View your local demo passwords with:")
        print("  grep -E '^DEMO_(ADMIN|VIEWER)_PASSWORD=' .env")
        print("They are intended for localhost only; do not share or commit them.")


if __name__ == "__main__":
    main()
