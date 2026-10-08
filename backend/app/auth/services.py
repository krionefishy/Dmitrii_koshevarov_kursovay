import math
from dataclasses import dataclass
from datetime import timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from backend.shared.config import Settings
from backend.shared.utils import AppError, Clock


@dataclass(frozen=True)
class AuthContext:
    login: str
    role: str

    def require(self, *roles: str) -> None:
        if self.role not in roles:
            raise AppError("Недостаточно прав", status_code=403)


class PasswordService:
    def __init__(self) -> None:
        self.hasher = PasswordHasher()

    def hash(self, password: str) -> str:
        return self.hasher.hash(password)

    def verify(self, encoded: str, password: str) -> bool:
        try:
            return self.hasher.verify(encoded, password)
        except (VerificationError, InvalidHashError):
            return False


class TokenService:
    def __init__(self, settings: Settings, clock: Clock) -> None:
        self.settings = settings
        self.clock = clock

    def issue(self, login: str, version: int) -> str:
        now = self.clock.now()
        return jwt.encode(
            {
                "sub": login,
                "ver": version,
                "iat": now,
                "exp": now + timedelta(seconds=self.settings.token_ttl),
                "iss": "coursework-helpdesk",
                "aud": "helpdesk-ui",
            },
            self.settings.jwt_secret,
            algorithm="HS256",
        )

    def decode(self, token: str) -> dict:
        try:
            payload = jwt.decode(
                token,
                self.settings.jwt_secret,
                algorithms=["HS256"],
                issuer="coursework-helpdesk",
                audience="helpdesk-ui",
                options={"require": ["sub", "ver", "iat", "exp"], "verify_exp": False, "verify_iat": False},
            )
            now = self.clock.now().timestamp()
            if not isinstance(payload["sub"], str) or type(payload["ver"]) is not int:
                raise ValueError
            if any(type(payload[key]) not in (int, float) or not math.isfinite(payload[key]) for key in ("exp", "iat")):
                raise ValueError
            if payload["exp"] <= now or payload["iat"] > now + 30:
                raise ValueError
            return payload
        except (jwt.PyJWTError, ValueError, TypeError, KeyError, OverflowError) as exc:
            raise AppError("Требуется вход в систему", status_code=401) from exc
