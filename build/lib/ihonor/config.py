import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    icloud_apple_id: str
    icloud_password: str
    honor_id: str
    honor_password: str

    @staticmethod
    def from_env() -> "Config":
        def req(key: str) -> str:
            val = os.environ.get(key)
            if not val:
                raise RuntimeError(f"Missing required env var: {key}")
            return val

        return Config(
            icloud_apple_id=req("ICLOUD_APPLE_ID"),
            icloud_password=req("ICLOUD_PASSWORD"),
            honor_id=req("HONOR_ID"),
            honor_password=req("HONOR_PASSWORD"),
        )
