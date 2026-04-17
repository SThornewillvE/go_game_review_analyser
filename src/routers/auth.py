import os
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel

from src.pipeline import db

router = APIRouter(prefix="/auth", tags=["auth"])

SECRET_KEY = os.environ.get("GGRA_SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 43200  # 30 days

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


class RegisterRequest(BaseModel):
    username: str
    password: str


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def _create_access_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": username, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.get_user_by_username(username)
    if user is None:
        raise credentials_exception
    return user


@router.post("/register", status_code=201)
def register(req: RegisterRequest):
    if db.get_user_by_username(req.username):
        raise HTTPException(status_code=400, detail="Username already taken")
    db.create_user(req.username, _hash_password(req.password))
    return {"message": "User created"}


@router.post("/token")
def login(form: OAuth2PasswordRequestForm = Depends()):
    user = db.get_user_by_username(form.username)
    if not user or not _verify_password(form.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = _create_access_token(user["username"])
    return {"access_token": token, "token_type": "bearer"}
