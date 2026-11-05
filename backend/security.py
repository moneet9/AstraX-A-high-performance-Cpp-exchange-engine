import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
import redis
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.hash import pbkdf2_sha256

JWT_SECRET = os.environ.get("ASTRAX_JWT_SECRET", "")
JWT_ISSUER = os.getenv("ASTRAX_JWT_ISSUER", "astrax")
ACCESS_SECONDS = int(os.getenv("ASTRAX_ACCESS_SECONDS", "900"))
REFRESH_SECONDS = int(os.getenv("ASTRAX_REFRESH_SECONDS", "2592000"))
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
bearer = HTTPBearer(auto_error=False)


def password_hash(password: str) -> str:
    return pbkdf2_sha256.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pbkdf2_sha256.verify(password, hashed)


def _issue(user_id: int, kind: str, lifetime: int, family: str) -> str:
    now = datetime.now(timezone.utc)
    jti = secrets.token_urlsafe(24)
    claims = {"sub": str(user_id), "typ": kind, "jti": jti, "family": family,
              "iss": JWT_ISSUER, "iat": now, "exp": now + timedelta(seconds=lifetime)}
    token = jwt.encode(claims, JWT_SECRET, algorithm="HS256")
    if kind == "refresh":
        token_key = f"refresh:{hashlib.sha256(token.encode()).hexdigest()}"
        redis_client.setex(token_key, lifetime, family)
        redis_client.sadd(f"refresh-family:{family}", token_key)
        redis_client.expire(f"refresh-family:{family}", lifetime)
    return token


def token_pair(user_id: int, family: str | None = None) -> dict:
    family = family or secrets.token_urlsafe(24)
    redis_client.setex(f"session:{user_id}:{family}", REFRESH_SECONDS, "active")
    redis_client.sadd(f"sessions:{user_id}", family)
    redis_client.expire(f"sessions:{user_id}", REFRESH_SECONDS)
    return {"access_token": _issue(user_id, "access", ACCESS_SECONDS, family),
            "refresh_token": _issue(user_id, "refresh", REFRESH_SECONDS, family),
            "expires_in": ACCESS_SECONDS, "token_type": "bearer"}


def consume_refresh(token: str) -> tuple[int, str]:
    key = f"refresh:{hashlib.sha256(token.encode()).hexdigest()}"
    family = redis_client.get(key)
    if family is None:
        try:
            claims = jwt.decode(token, JWT_SECRET, algorithms=["HS256"], issuer=JWT_ISSUER)
            _revoke_family(int(claims["sub"]), claims["family"])
        except (jwt.PyJWTError, KeyError):
            pass
        raise HTTPException(401, "invalid or rotated refresh token")
    redis_client.delete(key)
    redis_client.srem(f"refresh-family:{family}", key)
    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=["HS256"], issuer=JWT_ISSUER)
        if claims.get("typ") != "refresh" or claims.get("family") != family:
            raise ValueError("invalid token family")
        return int(claims["sub"]), family
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise HTTPException(401, "invalid refresh token") from exc


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if credentials is None:
        raise HTTPException(401, "bearer token required")
    try:
        claims = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"], issuer=JWT_ISSUER)
        if claims.get("typ") != "access":
            raise ValueError("wrong token type")
        user_id, family = int(claims["sub"]), claims["family"]
        if not redis_client.exists(f"session:{user_id}:{family}"):
            raise ValueError("session revoked")
        return user_id
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise HTTPException(401, "invalid access token") from exc


def rate_limit(user_id: int, bucket: str, limit: int, window_seconds: int = 60):
    key = f"rate:{user_id}:{bucket}:{int(datetime.now(timezone.utc).timestamp()) // window_seconds}"
    count = redis_client.incr(key)
    if count == 1:
        redis_client.expire(key, window_seconds + 1)
    if count > limit:
        raise HTTPException(429, "rate limit exceeded", headers={"Retry-After": str(window_seconds)})


def revoke_refresh(token: str):
    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=["HS256"], issuer=JWT_ISSUER)
        user_id, family = int(claims["sub"]), claims["family"]
    except (jwt.PyJWTError, ValueError, KeyError):
        return
    _revoke_family(user_id, family)


def _revoke_family(user_id: int, family: str):
    token_keys = redis_client.smembers(f"refresh-family:{family}")
    if token_keys:
        redis_client.delete(*token_keys)
    redis_client.delete(f"refresh-family:{family}", f"session:{user_id}:{family}")
    redis_client.srem(f"sessions:{user_id}", family)


def revoke_user_sessions(user_id: int):
    families = redis_client.smembers(f"sessions:{user_id}")
    keys = [f"session:{user_id}:{family}" for family in families]
    for family in families:
        keys.append(f"refresh-family:{family}")
        keys.extend(redis_client.smembers(f"refresh-family:{family}"))
    keys.append(f"sessions:{user_id}")
    if keys:
        redis_client.delete(*keys)
