# -*- coding: utf-8 -*-
"""用户相关接口：登录、注册、账号管理、个人中心、改密、token"""
from datetime import timedelta
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError, jwt

from config import DB_FILE, ACCESS_TOKEN_EXPIRE_MINUTES, SECRET_KEY, ALGORITHM
from auth import get_user, get_password_hash, verify_password, create_access_token, oauth2_scheme
from schemas import LoginItem, RegItem, AddUserItem, ToggleUserItem, RegisterItem, ChangePwdItem, AdminChangePwdItem, UpdateUserItem

router = APIRouter()


# 前端登录接口（JSON 格式，匹配 login.html 的 fetch）
@router.post("/api/login")
async def api_login(item: LoginItem):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id,password,role,status FROM users WHERE username=?", (item.username,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return {"code": 400, "msg": "账号或密码错误"}
    uid, pwd_hash, role, status = row
    if status != 1:
        return {"code": 400, "msg": "账号已禁用"}
    if not verify_password(item.password, pwd_hash):
        return {"code": 400, "msg": "账号或密码错误"}
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(uid), "role": role}, expires_delta=access_token_expires
    )
    return {"code": 200, "msg": "登录成功", "token": access_token}


# 前端注册接口
@router.post("/api/register")
async def api_register(item: RegItem):
    if not item.username or not item.password or not item.name or not item.role:
        return {"code": 400, "msg": "用户名、密码、公司名称、用户身份不能为空"}
    allow_roles = ["supplier", "purchaser", "agent"]
    if item.role not in allow_roles:
        return {"code": 400, "msg": "身份类型非法"}
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE username=?", (item.username,))
    if cur.fetchone():
        conn.close()
        return {"code": 400, "msg": "用户名已存在"}
    hash_pwd = get_password_hash(item.password)
    cur.execute("INSERT INTO users(username,password,role,name,status) VALUES (?,?,?,?,1)",
                (item.username, hash_pwd, item.role, item.name))
    conn.commit()
    conn.close()
    return {"code": 200, "msg": "注册成功，请登录"}


# 获取当前登录用户信息
@router.get("/api/user")
async def api_user(token: str | None = Depends(oauth2_scheme)):
    if not token:
        return {}
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        uid: str = payload.get("sub")
    except JWTError:
        return {}
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id,username,role,name,status FROM users WHERE id=?", (uid,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return {}
    return {"id": row[0], "username": row[1], "role": row[2], "name": row[3], "status": row[4]}


# 退出登录（前端清除 localStorage 里 token）
@router.post("/logout")
async def logout():
    return {"code": 200, "msg": "退出成功"}


# ========== 超级管理员账号管理接口 ==========
@router.get("/api/user_list")
async def api_user_list(user=Depends(get_user)):
    if user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT username,name,role,status FROM users")
    rows = cur.fetchall()
    conn.close()
    res = []
    for r in rows:
        res.append({"username": r[0], "name": r[1], "role": r[2], "status": r[3]})
    return {"code": 200, "data": res}


@router.post("/api/add_user")
async def api_add_user(item: AddUserItem, user=Depends(get_user)):
    if user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="权限不足")
    allow_all_roles = ["supplier", "purchaser", "agent", "super_admin"]
    if item.role not in allow_all_roles:
        return {"code": 400, "msg": "角色非法"}
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE username=?", (item.username,))
    if cur.fetchone():
        conn.close()
        return {"code": 400, "msg": "用户名已存在"}
    hash_pwd = get_password_hash(item.password)
    cur.execute("INSERT INTO users(username,password,role,name,status) VALUES (?,?,?,?,1)",
                (item.username, hash_pwd, item.role, item.name))
    conn.commit()
    conn.close()
    return {"code": 200, "msg": "新增账号成功"}


@router.post("/api/toggle_user_status")
async def api_toggle_user_status(item: ToggleUserItem, user=Depends(get_user)):
    if user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="权限不足")
    # 禁止操作自己（防止把自己禁用锁死）
    if item.username == user["username"]:
        raise HTTPException(status_code=400, detail="不能对当前登录账号进行操作")
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE username=?", (item.username,))
    if not cur.fetchone():
        conn.close()
        return {"code": 404, "msg": "用户不存在"}
    cur.execute("UPDATE users SET status=? WHERE username=?", (item.status, item.username))
    conn.commit()
    conn.close()
    return {"code": 200, "msg": "状态修改成功"}


# 超级管理员修改任意用户信息（用户名/公司名称/角色/密码，密码留空表示不修改）
@router.post("/api/update_user")
async def api_update_user(item: UpdateUserItem, user=Depends(get_user)):
    if user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="仅超级管理员可操作")
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id,username,name,role FROM users WHERE username=?", (item.username,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="用户不存在")
    uid, old_username, old_name, old_role = row
    # 新用户名唯一性
    new_username = (item.new_username or "").strip() or old_username
    if new_username != old_username:
        cur.execute("SELECT id FROM users WHERE username=? AND id!=?", (new_username, uid))
        if cur.fetchone():
            conn.close()
            raise HTTPException(status_code=400, detail="用户名已存在")
    # 公司名称
    new_name = (item.name or "").strip() or old_name
    # 角色
    new_role = (item.role or "").strip() or old_role
    allow_all_roles = ["supplier", "purchaser", "agent", "super_admin"]
    if new_role not in allow_all_roles:
        conn.close()
        raise HTTPException(status_code=400, detail="角色非法")
    # 禁止修改自己的角色（防止把自己锁死）
    if item.username == user["username"] and new_role != old_role:
        conn.close()
        raise HTTPException(status_code=400, detail="不能修改当前登录账号的角色")
    cur.execute("UPDATE users SET username=?, name=?, role=? WHERE id=?",
                (new_username, new_name, new_role, uid))
    # 密码：非空则修改（管理员改密不验证旧密码、不做位数限制）
    if item.new_password and item.new_password.strip():
        cur.execute("UPDATE users SET password=? WHERE id=?",
                    (get_password_hash(item.new_password.strip()), uid))
    conn.commit()
    conn.close()
    return {"code": 200, "msg": "信息修改成功"}


# ========== 个人中心 ==========
@router.get("/api/profile")
async def api_profile(user=Depends(get_user)):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT username,name,role,status,create_time FROM users WHERE id=?", (user["id"],))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="用户不存在")
    role_text = {"supplier": "供应方", "purchaser": "采购方", "agent": "代理机构", "super_admin": "超级管理员"}.get(row[2], row[2])
    status_text = "启用" if row[3] == 1 else "禁用"
    return {"code": 200, "data": {
        "username": row[0], "name": row[1], "role": row[2], "role_text": role_text,
        "status": row[3], "status_text": status_text, "create_time": row[4]
    }}


# 非管理员修改自己的密码
@router.post("/api/change_password")
async def api_change_password(item: ChangePwdItem, user=Depends(get_user)):
    if user["role"] == "super_admin":
        raise HTTPException(status_code=403, detail="管理员请在账号管理中修改密码")
    if not item.old_password or not item.new_password:
        raise HTTPException(status_code=400, detail="旧密码和新密码不能为空")
    if len(item.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码长度不能少于6位")
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT password FROM users WHERE id=?", (user["id"],))
    row = cur.fetchone()
    if not row or not verify_password(item.old_password, row[0]):
        conn.close()
        raise HTTPException(status_code=400, detail="旧密码不正确")
    cur.execute("UPDATE users SET password=? WHERE id=?", (get_password_hash(item.new_password), user["id"]))
    conn.commit()
    conn.close()
    return {"code": 200, "msg": "密码修改成功，请重新登录"}


# 超级管理员在账号管理里修改任意用户密码（不验证旧密码、不做位数限制）
@router.post("/api/admin_change_password")
async def api_admin_change_password(item: AdminChangePwdItem, user=Depends(get_user)):
    if user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="仅超级管理员可操作")
    if not item.new_password or not item.new_password.strip():
        raise HTTPException(status_code=400, detail="新密码不能为空")
    target = (item.username or "").strip() or user["username"]
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE username=?", (target,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="用户不存在")
    cur.execute("UPDATE users SET password=? WHERE id=?", (get_password_hash(item.new_password), row[0]))
    conn.commit()
    conn.close()
    return {"code": 200, "msg": "密码修改成功"}


# ========== 原有 token / register 接口（OAuth2 表单 / 兼容） ==========
@router.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id,password,role FROM users WHERE username=?", (form_data.username,))
    row = cur.fetchone()
    conn.close()
    if not row or not verify_password(form_data.password, row[1]):
        raise HTTPException(status_code=400, detail="用户名密码错误")
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(row[0]), "role": row[2]}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "role": row[2]}


@router.post("/register")
async def register(item: RegisterItem):
    if not item.username or not item.password or not item.name:
        raise HTTPException(status_code=400, detail="用户名、密码、名称不能为空")
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE username=?", (item.username,))
    if cur.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="用户名已存在")
    hash_pwd = get_password_hash(item.password)
    cur.execute("INSERT INTO users(username,password,role,name) VALUES (?,?,?,?)",
                (item.username, hash_pwd, item.role, item.name))
    conn.commit()
    conn.close()
    return {"msg": "注册成功"}


@router.get("/me")
async def me(user=Depends(get_user)):
    return user
