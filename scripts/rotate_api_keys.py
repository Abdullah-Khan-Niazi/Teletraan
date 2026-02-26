#!/usr/bin/env python3
"""Rotate API keys and update .env file.

Generates new values for sensitive environment variables and updates
the .env file. Optionally rotates the Fernet encryption key (requires
re-encryption of existing data).

Usage:
    python scripts/rotate_api_keys.py --keys APP_SECRET_KEY,ADMIN_API_KEY
    python scripts/rotate_api_keys.py --keys ENCRYPTION_KEY --confirm
    python scripts/rotate_api_keys.py --keys META_VERIFY_TOKEN

WARNING: Rotating ENCRYPTION_KEY requires re-encrypting all encrypted
data in the database. Use --confirm to acknowledge this.

Signed-off-by: Abdullah-Khan-Niazi
"""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

GENERATORS: dict[str, callable] = {
    "APP_SECRET_KEY": lambda: secrets.token_hex(32),
    "ADMIN_API_KEY": lambda: secrets.token_urlsafe(32),
    "META_VERIFY_TOKEN": lambda: secrets.token_urlsafe(24),
}


def generate_fernet_key() -> str:
    """Generate a new Fernet encryption key."""
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode()


def rotate_keys(keys: list[str], confirm: bool = False) -> None:
    """Rotate the specified keys in the .env file."""
    if not ENV_FILE.exists():
        print(f"ERROR: .env file not found at {ENV_FILE}")
        sys.exit(1)

    # Read current .env
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()

    rotated = []
    for key in keys:
        key = key.strip()

        if key == "ENCRYPTION_KEY":
            if not confirm:
                print(
                    f"WARNING: Rotating ENCRYPTION_KEY requires re-encrypting "
                    f"all encrypted DB fields. Pass --confirm to proceed."
                )
                continue
            new_value = generate_fernet_key()
        elif key in GENERATORS:
            new_value = GENERATORS[key]()
        else:
            # Generic rotation — generate a random token
            new_value = secrets.token_urlsafe(32)

        # Find and replace in .env
        found = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
                old_value = stripped.split("=", 1)[1].strip().strip('"').strip("'")
                lines[i] = f'{key}="{new_value}"'
                found = True
                print(f"  Rotated {key}")
                print(f"    Old: {old_value[:8]}...{old_value[-4:]}")
                print(f"    New: {new_value[:8]}...{new_value[-4:]}")
                break

        if not found:
            # Append new key
            lines.append(f'{key}="{new_value}"')
            print(f"  Added {key} (was not in .env)")
            print(f"    New: {new_value[:8]}...{new_value[-4:]}")

        rotated.append(key)

    if rotated:
        # Write back
        ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\nRotated {len(rotated)} key(s). Restart the application to apply.")
    else:
        print("No keys were rotated.")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Rotate API keys in .env")
    parser.add_argument(
        "--keys",
        required=True,
        help="Comma-separated list of keys to rotate",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm dangerous rotations (e.g., ENCRYPTION_KEY)",
    )

    args = parser.parse_args()
    key_list = [k.strip() for k in args.keys.split(",") if k.strip()]

    if not key_list:
        print("ERROR: No keys specified.")
        sys.exit(1)

    print(f"Rotating {len(key_list)} key(s): {', '.join(key_list)}\n")
    rotate_keys(key_list, confirm=args.confirm)


if __name__ == "__main__":
    main()
