# -*- coding: utf-8 -*-
"""认证与用户工具：密码哈希、JWT、当前用户依赖"""
from datetime import datetime, timedelta
import sqlite3

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from config import DB_FILE, SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES

pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证身份",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        uid: str = payload.get("sub")
        if uid is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id,username,role,name,status FROM users WHERE id=?", (uid,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise credentials_exception
    uid_db, uname, urole, uname_full, ustatus = row
    # 账号禁用直接抛异常
    if ustatus != 1:
        raise HTTPException(status_code=403, detail="账号已被禁用")
    return {"id": uid_db, "username": uname, "role": urole, "name": uname_full, "status": ustatus}
