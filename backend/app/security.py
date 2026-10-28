import hashlib
import hmac
import secrets
import time

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .db import connect

bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600_000)
    return f'{salt}${digest.hex()}'


def verify_password(password: str, encoded: str) -> bool:
    salt, digest = encoded.split('$')
    actual = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600_000)
    return hmac.compare_digest(actual.hex(), digest)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if credentials:
        with connect() as db:
            user = db.execute(
                'SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id '
                'WHERE s.token_hash=? AND s.expires_at>?',
                (token_hash(credentials.credentials), int(time.time())),
            ).fetchone()
        if user:
            return dict(user)
    raise HTTPException(401, 'Please sign in', headers={'WWW-Authenticate': 'Bearer'})


def manager(user=Depends(current_user)):
    if user['role'] != 'manager':
        raise HTTPException(403, 'Manager access required')
    return user


def public_user(user):
    return {k: user[k] for k in ('id', 'name', 'email', 'role', 'phone', 'address')}
