from __future__ import annotations

import getpass
import os
from pathlib import Path
from typing import Any


def cached_client(token_store: Path) -> Any:
    from garminconnect import Garmin

    client = Garmin()
    client.login(str(token_store))
    return client


def interactive_login(token_store: Path) -> Any:
    from garminconnect import Garmin

    email = os.environ.get("GARMIN_EMAIL") or input("Garmin email: ").strip()
    password = os.environ.get("GARMIN_PASSWORD") or getpass.getpass("Garmin password: ")
    token_store.mkdir(parents=True, exist_ok=True, mode=0o700)
    client = Garmin(
        email=email,
        password=password,
        prompt_mfa=lambda: input("Garmin MFA code: ").strip(),
    )
    password = ""
    client.login(str(token_store))
    return client
