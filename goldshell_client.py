"""Minimal client for the Goldshell miner web API: login and power-plan control.

Reverse-engineered from a Goldshell SC-LITE's web UI (bundled Vue.js app).
Confirmed working on the SC-LITE; other Goldshell models likely share the
same backend API but have not been tested.

Login: GET /user/login?username=admin&password=<enc>&cipher=true
  where <enc> is AES-128-CBC (zero IV, CryptoJS ZeroPadding), key "!!!!!!!!!!!!!!!!",
  hex-encoded ciphertext of the plaintext password.
Auth: Authorization: Bearer <JWT> on subsequent requests (token does not expire).
Power plan: GET/PUT /mcb/setting - "select" is the array index into "powerplans".
"""
from __future__ import annotations

import requests
from Crypto.Cipher import AES

AES_KEY = b"!" * 16
AES_IV = b"\x00" * 16


def _encrypt_password(password: str) -> str:
    data = password.encode("utf-8")
    pad_len = (-len(data)) % 16  # CryptoJS ZeroPadding: no-op if already block-aligned
    data += b"\x00" * pad_len
    cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
    return cipher.encrypt(data).hex()


class GoldshellError(Exception):
    pass


class GoldshellClient:
    def __init__(self, ip: str, password: str, timeout: float = 8.0):
        self.ip = ip
        self.password = password
        self.timeout = timeout
        self.base = f"http://{ip}"
        self._token: str | None = None
        self._session = requests.Session()  # reuse one TCP connection across calls to this device

    def login(self) -> str:
        enc = _encrypt_password(self.password)
        r = self._session.get(
            f"{self.base}/user/login",
            params={"username": "admin", "password": enc, "cipher": "true"},
            timeout=self.timeout,
        )
        r.raise_for_status()
        token = r.json().get("JWT Token")
        if not token:
            raise GoldshellError(f"login to {self.ip} did not return a token (wrong password?)")
        self._token = token
        return token

    def _headers(self) -> dict:
        if not self._token:
            self.login()
        return {"Authorization": f"Bearer {self._token}"}

    def _get(self, path: str) -> dict:
        r = self._session.get(f"{self.base}{path}", headers=self._headers(), timeout=self.timeout)
        if r.status_code == 401:
            self.login()
            r = self._session.get(f"{self.base}{path}", headers=self._headers(), timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def get_setting(self) -> dict:
        return self._get("/mcb/setting")

    @staticmethod
    def _parse_mhz(info: str) -> int:
        """'615 MHz 9100 V 40 RPM 40 RPM PV 9400' -> 615"""
        try:
            return int(info.strip().split(" MHz", 1)[0].split()[-1])
        except (ValueError, IndexError):
            return -1

    def apply_mode(self, mode: str | None = None, level: int | None = None) -> dict:
        """Switch to the power plan matching `mode` ('hashrate'/'idle', by MHz)
        or an explicit `level` number. Only issues a PUT if the plan actually changes."""
        setting = self.get_setting()
        plans = setting["powerplans"]

        if level is not None:
            target_index = next((i for i, p in enumerate(plans) if p.get("level") == level), None)
            if target_index is None:
                raise GoldshellError(f"{self.ip}: no power plan with level={level}")
        else:
            mhz = [(self._parse_mhz(p["info"]), i) for i, p in enumerate(plans)]
            if mode == "hashrate":
                target_index = max(mhz)[1]
            elif mode == "idle":
                target_index = min(mhz)[1]
            else:
                raise GoldshellError(f"{self.ip}: unknown mode {mode!r} (use 'hashrate', 'idle', or set 'level')")

        if setting["select"] == target_index:
            return {"changed": False, "select": target_index}

        setting["select"] = target_index
        r = self._session.put(f"{self.base}/mcb/setting", headers=self._headers(), json=setting, timeout=self.timeout)
        r.raise_for_status()
        return {"changed": True, "select": target_index}
