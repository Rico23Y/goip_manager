from dataclasses import dataclass
from typing import Any


@dataclass
class GoipDevice:
    goip: str
    ip_address: str
    username: str
    password: str
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "goip": self.goip,
            "ip": self.ip_address,
            "username": self.username,
            "password": self.password,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GoipDevice":
        return cls(
            goip=str(data.get("goip", "")),
            ip_address=str(data.get("ip", "")),
            username=str(data.get("username", "")),
            password=str(data.get("password", "")),
            enabled=bool(data.get("enabled", True)),
        )