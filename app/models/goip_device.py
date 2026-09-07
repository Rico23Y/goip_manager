from dataclasses import dataclass
from typing import Any


@dataclass
class GoipDevice:
    ip_address: str
    username: str
    password: str

    def to_dict(self) -> dict[str, str]:
        return {
            "ip": self.ip_address,
            "username": self.username,
            "password": self.password,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GoipDevice":
        return cls(
            ip_address=str(data.get("ip", "")),
            username=str(data.get("username", "")),
            password=str(data.get("password", "")),
        )