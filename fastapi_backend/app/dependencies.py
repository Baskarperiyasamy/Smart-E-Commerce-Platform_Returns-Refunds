from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.database import get_db
from app.security import decode_token
from app import models

# HTTPBearer (instead of OAuth2PasswordBearer) makes Swagger's "Authorize"
# button show a simple "paste your token" box, since our /auth/login takes
# a JSON body rather than OAuth2's form-encoded username/password.
bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        raise credentials_exception

    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None or not user.is_active:
        raise credentials_exception

    return user


def require_roles(*allowed_roles: str):
    """Usage: Depends(require_roles("admin", "staff"))"""

    def role_checker(current_user: models.User = Depends(get_current_user)) -> models.User:
        if current_user.role.value not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return current_user

    return role_checker


def get_current_user_ws(token: str, db: Session):
    """WebSocket equivalent of get_current_user. Browsers can't attach custom
    Authorization headers to a WebSocket handshake, so the access token is
    passed as a query parameter instead (?token=...). Returns None instead of
    raising, since the caller needs to close the socket, not send an HTTP
    error response."""
    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        return None

    user_id = payload.get("sub")
    if user_id is None:
        return None

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None or not user.is_active:
        return None

    return user
