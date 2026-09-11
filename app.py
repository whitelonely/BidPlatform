from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta
import sqlite3
import os
# ===================== 密码哈希配置（只定义一次）=====================
pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")
def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)
# --------------------------配置---------------------------
SECRET_KEY = "procurement-secret-key-2026"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120
app = FastAPI(title="采购管理平台")
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 静态资源由显式路由返回（Vercel Serverless 下 StaticFiles mount 不生效，统一走 FastAPI 路由）
@app.get("/static/{path:path}")
async def static_file(path: str):
    _full = os.path.normpath(os.path.join(_BASE_DIR, "static", path))
    if not _full.startswith(os.path.join(_BASE_DIR, "static")) or not os.path.isfile(_full):
        raise HTTPException(status_code=404, detail="Not Found")
    return FileResponse(_full)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
# Vercel Serverless 环境文件系统只读（仅 /tmp 可写），自动切换数据目录；本地开发仍用项目目录下 proc.db / uploads
IS_VERCEL = bool(os.environ.get("VERCEL"))
if IS_VERCEL:
    DB_FILE = "/tmp/proc.db"
    UPLOAD_DIR = "/tmp/uploads"
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DB_FILE = os.path.join(_BASE_DIR, "proc.db")
    UPLOAD_DIR = os.path.join(_BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
# 已由上方 DB_FILE/UPLOAD_DIR 逻辑覆盖（Vercel 用 /tmp）
os.makedirs(UPLOAD_DIR, exist_ok=True)
# ===================== Pydantic 模型（补上NoticeItem，消除波浪线）=====================
class NoticeItem(BaseModel):
    title: str
    notice_type: str
    content: str
    start_time: str
    end_time: str
    open_time: str
class LoginItem(BaseModel):
    username: str
    password: str
class RegItem(BaseModel):
    username:str
    password:str
    name:str
    role:str
class AddUserItem(BaseModel):
    username:str
    password:str
    name:str
    role:str
class ToggleUserItem(BaseModel):
    username:str
    status:int
class SaveRecordItem(BaseModel):
    notice_id: int | None = None
    project_id: int | None = None
    record: str
class UpdateNoticeItem(BaseModel):
    id:int
    title:str
    notice_type:str
    project_sn:str=""
    start_time:str=""
    end_time:str=""
    open_time:str=""
    content:str=""
class DeleteNoticeItem(BaseModel):
    id:int
class RegisterItem(BaseModel):
    username:str
    password:str
    role:str
    name:str
class ChangePwdItem(BaseModel):
    old_password: str
    new_password: str
class AdminChangePwdItem(BaseModel):
    username: str = ""
    new_password: str
# --------------------------数据库初始化---------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    # users表新增status：1启用，0禁用
    cur.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL,
        name TEXT,
        status INTEGER DEFAULT 1,
        create_time DATETIME DEFAULT (datetime('now','localtime'))
    )
    ''')
    # ===========notices表新增attach_file字段，保存公告附件文件名===========
    cur.execute('''
        CREATE TABLE IF NOT EXISTS notices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        notice_type TEXT NOT NULL,
        content TEXT,
        publish_uid INTEGER,
        project_sn TEXT,
        start_time TEXT,
        end_time TEXT,
        open_time TEXT,
        attach_file TEXT,
        status TEXT DEFAULT "normal",
        create_time DATETIME DEFAULT (datetime('now','localtime'))
    )
    ''')
    # 兼容旧库：notices表缺列时自动补列（不删数据）
    for col, ddl in [("project_sn","TEXT"), ("attach_file","TEXT")]:
        try:
            cur.execute(f"ALTER TABLE notices ADD COLUMN {col} {ddl}")
        except sqlite3.OperationalError:
            pass
    cur.execute('''
    CREATE TABLE IF NOT EXISTS tender_signup (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        notice_id INTEGER,
        user_id INTEGER,
        signup_time DATETIME DEFAULT (datetime('now','localtime')),
        file_name TEXT,
        file_path TEXT,
        is_upload INTEGER DEFAULT 0,
        FOREIGN KEY(notice_id) REFERENCES notices(id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    ''')
    cur.execute('''
    CREATE TABLE IF NOT EXISTS bid_price (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        notice_id INTEGER,
        user_id INTEGER,
        price REAL,
        second_price REAL,
        bid_time DATETIME DEFAULT (datetime('now','localtime')),
        second_time DATETIME,
        FOREIGN KEY(notice_id) REFERENCES notices(id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    ''')
    # 兼容旧库：补 second_price / second_time 列
    try:
        cur.execute("ALTER TABLE bid_price ADD COLUMN second_price REAL")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE bid_price ADD COLUMN second_time DATETIME")
    except Exception:
        pass
    # 新增开标记录表
    cur.execute('''
    CREATE TABLE IF NOT EXISTS bid_record (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        notice_id INTEGER,
        record TEXT,
        create_time DATETIME DEFAULT (datetime('now','localtime')),
        FOREIGN KEY(notice_id) REFERENCES notices(id)
    )
    ''')
    # 开标结果确认表
    cur.execute('''
    CREATE TABLE IF NOT EXISTS bid_result (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        notice_id INTEGER,
        user_id INTEGER,
        result TEXT,
        confirm_time DATETIME DEFAULT (datetime('now','localtime')),
        FOREIGN KEY(notice_id) REFERENCES notices(id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    ''')
    # 开标室流程动态表
    cur.execute(
        "CREATE TABLE IF NOT EXISTS bid_flow ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "notice_id INTEGER,"
        "content TEXT,"
        "user_id INTEGER,"
        "create_time DATETIME DEFAULT (datetime('now','localtime')),"
        "FOREIGN KEY(notice_id) REFERENCES notices(id),"
        "FOREIGN KEY(user_id) REFERENCES users(id)"
        ")"
    )
    conn.commit()
    # 自动创建超级管理员 admin / admin123
    cur.execute("SELECT id FROM users WHERE username=?", ("admin",))
    if not cur.fetchone():
        hash_pwd = get_password_hash("admin123")
        cur.execute("INSERT INTO users(username,password,role,name,status) VALUES (?,?,?,?,?)",
                    ("admin", hash_pwd, "super_admin", "平台超级管理员", 1))
        conn.commit()
    conn.close()
init_db()
# --------------------------工具函数---------------------------
import re as _re

def sanitize_html(s: str) -> str:
    """公告内容入库前的简单安全过滤：去掉script标签与on*事件属性"""
    if not s:
        return s
    s = _re.sub(r'(?is)<script.*?</script>', '', s)
    s = _re.sub(r'(?i)\s+on\w+\s*=\s*"[^"]*"', '', s)
    s = _re.sub(r"(?i)\s+on\w+\s*=\s*'[^']*'", '', s)
    return s

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
# 按时间计算公告中文状态：未开始/报名中/已截止/已开标
def _check_biz_notice(notice_id):
    """报名/投标/开标业务仅允许采购公告"""
    _conn = sqlite3.connect(DB_FILE)
    _cur = _conn.cursor()
    _cur.execute("SELECT notice_type FROM notices WHERE id=?", (notice_id,))
    _row = _cur.fetchone()
    _conn.close()
    if not _row:
        raise HTTPException(status_code=404, detail="公告不存在")
    if _row[0] != "purchase":
        raise HTTPException(status_code=400, detail="仅采购公告支持该操作")

def notice_status_text(start_time, end_time, open_time, status):
    try:
        now = datetime.now()
        def to_dt(s):
            if not s:
                return None
            try:
                return datetime.fromisoformat(str(s))
            except Exception:
                return None
        if status == "closed":
            return "已结束"
        if status == "open":
            return "已开标"
        ot = to_dt(open_time)
        et = to_dt(end_time)
        st = to_dt(start_time)
        if ot and now >= ot:
            return "已开标"
        if et and now >= et:
            return "报名已截止"
        if st and now >= st:
            return "报名中"
        if st:
            return "未开始"
        return "报名中"
    except Exception:
        return "报名中"

# 上传文件类型白名单（浏览器可直接预览的类型）
ALLOW_UPLOAD_EXT = {".jpg",".jpeg",".png",".gif",".bmp",".webp",".pdf",".txt"}
def check_upload_ext(filename):
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOW_UPLOAD_EXT:
        raise HTTPException(status_code=400, detail="仅支持上传图片、PDF、TXT 等可在线预览的文件")

def get_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证身份",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        uid: str = payload.get("sub")
        role: str = payload.get("role")
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
    return {"id":uid_db,"username":uname,"role":urole,"name":uname_full,"status":ustatus}
# ======================【页面路由 完全保留原有】======================
@app.get("/")
async def root():
    return FileResponse("static/index.html")
@app.get("/login")
async def page_login():
    return FileResponse("static/login.html")
@app.get("/notice")
async def page_notice():
    return FileResponse("static/notice.html")
@app.get("/announce")
async def page_announce():
    return FileResponse("static/announce.html")
@app.get("/policy")
async def page_policy():
    return FileResponse("static/policy.html")
@app.get("/guide")
async def page_guide():
    return FileResponse("static/guide.html")
@app.get("/publish")
async def page_publish():
    return FileResponse("static/publish.html")
# 修正路由名称，前端统一访问 /tender_detail
@app.get("/tender_detail")
async def page_tender_detail():
    return FileResponse("static/tender_detail.html")
@app.get("/bid_room")
async def page_bid_room():
    return FileResponse("static/bid_room.html")
# 兼容旧的带html后缀的访问方式，防止旧链接404
@app.get("/login.html")
async def page_login_html():
    return FileResponse("static/login.html")
@app.get("/notice.html")
async def page_notice_html():
    return FileResponse("static/notice.html")
@app.get("/publish.html")
async def page_publish_html():
    return FileResponse("static/publish.html")
@app.get("/tender_detail.html")
async def page_tender_detail_html():
    return FileResponse("static/tender_detail.html")
@app.get("/bid_room.html")
async def page_bid_room_html():
    return FileResponse("static/bid_room.html")
@app.get("/policy.html")
async def page_policy_html():
    return FileResponse("static/policy.html")
@app.get("/guide.html")
async def page_guide_html():
    return FileResponse("static/guide.html")
@app.get("/announce.html")
async def page_announce_html():
    return FileResponse("static/announce.html")
@app.get("/profile")
async def page_profile():
    return FileResponse("static/profile.html")
@app.get("/user_manage")
async def page_user_manage():
    return FileResponse("static/user_manage.html")
@app.get("/user_manage.html")
async def page_user_manage_html():
    return FileResponse("static/user_manage.html")
# ====================== 新增：全部公告列表页 + 各类型详情直达页 ======================
@app.get("/all_notice")
async def page_all_notice():
    return FileResponse("static/all_notice.html")
@app.get("/all_notice.html")
async def page_all_notice_html():
    return FileResponse("static/all_notice.html")
# 各类型公告详情直达（统一复用公告详情页）
@app.get("/win/{nid}")
async def page_win_detail(nid:int):
    return FileResponse("static/tender_detail.html")
@app.get("/announce/{nid}")
async def page_announce_detail(nid:int):
    return FileResponse("static/tender_detail.html")
@app.get("/policy/{nid}")
async def page_policy_detail(nid:int):
    return FileResponse("static/tender_detail.html")
@app.get("/guide/{nid}")
async def page_guide_detail(nid:int):
    return FileResponse("static/tender_detail.html")
# ======================【前端页面需要的API接口 新增/修改】======================
# 获取采购信息
@app.get("/api/purchase")
async def api_purchase():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id,title, create_time FROM notices WHERE notice_type='purchase' ORDER BY create_time DESC")
    rows = cur.fetchall()
    conn.close()
    res = []
    for r in rows:
        res.append({"id":r[0],"title": r[1], "type":"purchase", "create_time": r[2]})
    return {"code":200,"data":res}
# 获取中标信息
@app.get("/api/win")
async def api_win():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id,title, create_time FROM notices WHERE notice_type='win' ORDER BY create_time DESC")
    rows = cur.fetchall()
    conn.close()
    res = []
    for r in rows:
        res.append({"id":r[0],"title": r[1], "type":"win", "create_time": r[2]})
    return {"code":200,"data":res}
# 获取平台通知
@app.get("/api/announce")
async def api_announce():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id,title, create_time FROM notices WHERE notice_type='announce' ORDER BY create_time DESC")
    rows = cur.fetchall()
    conn.close()
    res = []
    for r in rows:
        res.append({"id":r[0],"title": r[1], "type":"announce", "create_time": r[2]})
    return {"code":200,"data":res}
# 获取政策法规
@app.get("/api/policy")
async def api_policy():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id,title,create_time FROM notices WHERE notice_type='policy' ORDER BY create_time DESC")
    rows = cur.fetchall()
    conn.close()
    res = []
    for r in rows:
        res.append({"id":r[0],"title": r[1], "type":"policy", "create_time": r[2]})
    return {"code":200,"data":res}
# 获取业务指南
@app.get("/api/guide")
async def api_guide():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id,title,create_time FROM notices WHERE notice_type='guide' ORDER BY create_time DESC")
    rows = cur.fetchall()
    conn.close()
    res = []
    for r in rows:
        res.append({"id":r[0],"title": r[1], "type":"guide", "create_time": r[2]})
    return {"code":200,"data":res}
# ============【新增首页信息查询：全部公告接口】============
@app.get("/api/all_notice")
async def api_all_notice():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id,title,notice_type,project_sn,content,create_time FROM notices ORDER BY create_time DESC")
    rows = cur.fetchall()
    conn.close()
    res = []
    type_map = {
        "purchase":"采购公告",
        "win":"中标公告",
        "change":"变更公告",
        "stop":"终止公告",
        "announce":"平台通知",
        "policy":"政策法规",
        "guide":"业务指南"
    }
    for r in rows:
        res.append({
            "id":r[0],
            "title": r[1],
            "type": r[2],
            "type_text": type_map.get(r[2],r[2]),
            "project_sn": r[3] or "",
            "content": r[4] or "",
            "create_time": r[5]
        })
    return {"code":200,"data":res}

# 前端登录接口（JSON格式，匹配login.html的fetch）
@app.post("/api/login")
async def api_login(item: LoginItem):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id,password,role,status FROM users WHERE username=?", (item.username,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return {"code":400, "msg":"账号或密码错误"}
    uid, pwd_hash, role, status = row
    if status !=1:
        return {"code":400, "msg":"账号已禁用"}
    if not verify_password(item.password, pwd_hash):
        return {"code":400, "msg":"账号或密码错误"}
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(uid), "role": role}, expires_delta=access_token_expires
    )
    # 前端需要把token存到localStorage
    return {"code":200, "msg":"登录成功", "token":access_token}
# 前端注册接口
@app.post("/api/register")
async def api_register(item:RegItem):
    if not item.username or not item.password or not item.name or not item.role:
        return {"code":400, "msg":"用户名、密码、姓名、用户身份不能为空"}
    allow_roles = ["supplier", "purchaser", "agent"]
    if item.role not in allow_roles:
        return {"code":400, "msg":"身份类型非法"}
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE username=?", (item.username,))
    if cur.fetchone():
        conn.close()
        return {"code":400, "msg":"用户名已存在"}
    hash_pwd = get_password_hash(item.password)
    cur.execute("INSERT INTO users(username,password,role,name,status) VALUES (?,?,?,?,1)",
                (item.username,hash_pwd,item.role,item.name))
    conn.commit()
    conn.close()
    return {"code":200, "msg":"注册成功，请登录"}
# 获取当前登录用户信息
@app.get("/api/user")
async def api_user(token:str|None = Depends(oauth2_scheme)):
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
    return {"id":row[0],"username":row[1],"role":row[2],"name":row[3],"status":row[4]}
# 退出登录（前端清除localStorage里token）
@app.post("/logout")
async def logout():
    return {"code":200,"msg":"退出成功"}
# ===================== 新增：超级管理员账号管理接口 =====================
# 获取全部用户列表
@app.get("/api/user_list")
async def api_user_list(user = Depends(get_user)):
    if user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT username,name,role,status FROM users")
    rows = cur.fetchall()
    conn.close()
    res = []
    for r in rows:
        res.append({"username":r[0],"name":r[1],"role":r[2],"status":r[3]})
    return {"code":200, "data":res}
# 新增账号（超级管理员）
@app.post("/api/add_user")
async def api_add_user(item:AddUserItem, user = Depends(get_user)):
    if user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="权限不足")
    allow_all_roles = ["supplier", "purchaser", "agent", "super_admin"]
    if item.role not in allow_all_roles:
        return {"code":400,"msg":"角色非法"}
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE username=?",(item.username,))
    if cur.fetchone():
        conn.close()
        return {"code":400,"msg":"用户名已存在"}
    hash_pwd = get_password_hash(item.password)
    cur.execute("INSERT INTO users(username,password,role,name,status) VALUES (?,?,?,?,1)",
                (item.username,hash_pwd,item.role,item.name))
    conn.commit()
    conn.close()
    return {"code":200,"msg":"新增账号成功"}
# 启用/禁用账号
@app.post("/api/toggle_user_status")
async def api_toggle_user_status(item:ToggleUserItem, user = Depends(get_user)):
    if user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="权限不足")
    # 禁止操作自己（防止把自己禁用锁死）
    if item.username == user["username"]:
        raise HTTPException(status_code=400, detail="不能对当前登录账号进行操作")
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE username=?",(item.username,))
    if not cur.fetchone():
        conn.close()
        return {"code":404,"msg":"用户不存在"}
    cur.execute("UPDATE users SET status=? WHERE username=?",(item.status,item.username))
    conn.commit()
    conn.close()
    return {"code":200,"msg":"状态修改成功"}
# ===================== 新增：开标室接口 =====================
# 当前用户有权限的项目列表（超管全部 / 发布人 / 已报名供应方）
@app.get("/api/bid_room_list")
async def api_bid_room_list(user=Depends(get_user)):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "SELECT n.id,n.title,n.notice_type,n.project_sn,n.status,n.start_time,n.end_time,n.open_time "
        "FROM notices n "
        "WHERE n.notice_type = 'purchase' "
        "AND (? = 'super_admin' OR n.publish_uid = ? OR n.id IN (SELECT notice_id FROM tender_signup WHERE user_id = ?)) "
        "ORDER BY n.create_time DESC"
    ,(user["role"], user["id"], user["id"]))
    rows = cur.fetchall()
    conn.close()
    res = []
    for r in rows:
        res.append({
            "id":r[0],
            "title":r[1],
            "notice_type":r[2],
            "type_text":"采购公告",
            "project_sn":r[3] or "",
            "status":r[4],
            "status_text":notice_status_text(r[5], r[6], r[7], r[4]),
            "start_time":r[5] or "",
            "end_time":r[6] or "",
            "open_time":r[7] or ""
        })
    return {"code":200,"data":res}

@app.get("/api/bid_room")
async def api_bid_room(project_id: int | None = None, notice_id: int | None = None, user=Depends(get_user)):
    nid = project_id if project_id is not None else notice_id
    if nid is None:
        raise HTTPException(status_code=400, detail="缺少项目编号")
    _check_biz_notice(nid)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    # 查询公告
    cur.execute("SELECT id,title,notice_type,publish_uid,project_sn,status,start_time,end_time,open_time FROM notices WHERE id=?",(nid,))
    notice_row = cur.fetchone()
    if not notice_row:
        conn.close()
        raise HTTPException(status_code=404, detail="项目公告不存在")
    nid, title, ntype, publish_uid, project_sn, nstatus, st_str, et_str, ot_str = notice_row
    # 权限判定：超级管理员 OR 公告发布人 OR 已经报名的供应方
    is_super = user["role"] == "super_admin"
    is_publisher = user["id"] == publish_uid
    cur.execute("SELECT id FROM tender_signup WHERE notice_id=? AND user_id=?",(nid, user["id"]))
    signup_row = cur.fetchone()
    is_signup = bool(signup_row)
    if not (is_super or is_publisher or is_signup):
        conn.close()
        raise HTTPException(status_code=403, detail="您无权进入该开标室")
    # 查询报名供应方列表（含投标报价/二次报价/结果确认）
    cur.execute('''
        SELECT ts.user_id, u.username, u.name, ts.file_name, ts.is_upload,
               bp.price, bp.second_price,
               (SELECT br.result FROM bid_result br WHERE br.notice_id=ts.notice_id AND br.user_id=ts.user_id) AS result
        FROM tender_signup ts
        LEFT JOIN users u ON ts.user_id = u.id
        LEFT JOIN bid_price bp ON bp.notice_id = ts.notice_id AND bp.user_id = ts.user_id
        WHERE ts.notice_id=?
    ''',(nid,))
    sup_rows = cur.fetchall()
    supplier_list = []
    for s in sup_rows:
        supplier_list.append({
            "username":s[1],
            "name":s[2],
            "apply_status":"已报名",
            "file_name":s[3],
            "is_upload":s[4],
            "price":s[5],
            "second_price":s[6],
            "result":s[7],
            "file_url": (f"/download_bid/{nid}/{s[0]}" if s[4] == 1 and s[3] else "")
        })
    # 查询开标记录
    cur.execute("SELECT record FROM bid_record WHERE notice_id=?",(nid,))
    rec_row = cur.fetchone()
    record_txt = rec_row[0] if rec_row else ""
    conn.close()
    # 是否已到开标时间（开标进行中）
    is_open = False
    if ot_str:
        try:
            is_open = datetime.now() >= datetime.fromisoformat(str(ot_str))
        except Exception:
            is_open = False
    # 可发布流程：超管/发布人 且 开标中且未结束
    can_publish = (is_super or is_publisher) and nstatus != "closed" and is_open
    # 可结束开标：超管/代理机构/发布人 且 开标中且未结束
    can_close = (is_super or is_publisher or user["role"] == "agent") and nstatus != "closed" and is_open
    return {
        "code":200,
        "data":{
            "title":title,
            "notice_id":nid,
            "notice_type":ntype,
            "project_sn":project_sn,
            "status":nstatus,
            "status_text":notice_status_text(st_str, et_str, ot_str, nstatus),
            "record":record_txt,
            "is_open":is_open,
            "can_publish":can_publish,
            "can_close":can_close,
            "supplier_list":supplier_list
        }
    }
# 保存开标记录
# 投标文件下载/预览（开标室权限内可访问；支持 header 或 ?token= 两种认证）
@app.get("/download_bid/{notice_id}/{user_id}")
async def download_bid(notice_id:int, user_id:int, token: str | None = None,
                       authorization: str | None = Header(default=None)):
    auth_token = (authorization or "").replace("Bearer ", "").strip() or token
    if not auth_token:
        raise HTTPException(status_code=401, detail="未登录，无法查看文件")
    try:
        payload = jwt.decode(auth_token, SECRET_KEY, algorithms=[ALGORITHM])
        uid = int(payload.get("sub"))
    except Exception:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    _check_biz_notice(notice_id)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id,role FROM users WHERE id=?", (uid,))
    urow = cur.fetchone()
    if not urow:
        conn.close()
        raise HTTPException(status_code=401, detail="用户不存在或已被禁用")
    cur.execute("SELECT status FROM users WHERE id=?", (uid,))
    if cur.fetchone()[0] != 1:
        conn.close()
        raise HTTPException(status_code=403, detail="账号已被禁用")
    cur.execute("SELECT publish_uid FROM notices WHERE id=?",(notice_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="公告不存在")
    pub_uid = row[0]
    is_super = urow[1] == "super_admin"
    is_publisher = uid == pub_uid
    cur.execute("SELECT id FROM tender_signup WHERE notice_id=? AND user_id=?",(notice_id, uid))
    is_signup = bool(cur.fetchone())
    if not (is_super or is_publisher or is_signup):
        conn.close()
        raise HTTPException(status_code=403, detail="无权查看该投标文件")
    cur.execute("SELECT file_path,file_name FROM tender_signup WHERE notice_id=? AND user_id=? AND is_upload=1",(notice_id,user_id))
    fr = cur.fetchone()
    conn.close()
    if not fr or not fr[0] or not os.path.exists(fr[0]):
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(fr[0], filename=fr[1])

# 供应方二次报价（开标进行中，未结束前）
@app.post("/api/second_bid/{notice_id}")
async def api_second_bid(notice_id:int, second_price:float=Form(...), user=Depends(get_user)):
    if user["role"] != "supplier":
        raise HTTPException(status_code=403, detail="仅供应方可二次报价")
    if second_price is None or second_price <= 0:
        raise HTTPException(status_code=400, detail="二次报价必须填写且大于0")
    _check_biz_notice(notice_id)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT open_time,status FROM notices WHERE id=?",(notice_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="公告不存在")
    ot_str, nstatus = row
    if nstatus == "closed":
        conn.close()
        raise HTTPException(status_code=400, detail="开标已结束，不能二次报价")
    if ot_str:
        try:
            if datetime.now() < datetime.fromisoformat(str(ot_str)):
                conn.close()
                raise HTTPException(status_code=400, detail="尚未到开标时间，不能二次报价")
        except Exception:
            pass
    cur.execute("SELECT id FROM tender_signup WHERE notice_id=? AND user_id=?",(notice_id,user["id"]))
    sig = cur.fetchone()
    if not sig:
        conn.close()
        raise HTTPException(status_code=400, detail="请先报名")
    # 二次报价只能提交一次
    cur.execute("SELECT second_price FROM bid_price WHERE notice_id=? AND user_id=?",(notice_id,user["id"]))
    bp0 = cur.fetchone()
    if bp0 and bp0[0] is not None:
        conn.close()
        raise HTTPException(status_code=400, detail="已提交过二次报价，不能重复提交")
    # 结果确认后不能再修改
    cur.execute("SELECT id FROM bid_result WHERE notice_id=? AND user_id=?",(notice_id,user["id"]))
    if cur.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="已确认开标结果，不能修改二次报价")
    cur.execute("SELECT id FROM bid_price WHERE notice_id=? AND user_id=?",(notice_id,user["id"]))
    bp = cur.fetchone()
    if bp:
        cur.execute("UPDATE bid_price SET second_price=?, second_time=datetime('now','localtime') WHERE id=?",(second_price,bp[0]))
    else:
        cur.execute("INSERT INTO bid_price(notice_id,user_id,price,second_price) VALUES (?,?,?,?)",(notice_id,user["id"],0,second_price))
    conn.commit()
    conn.close()
    return {"code":200,"msg":"二次报价提交成功"}

# 供应方结果确认
@app.post("/api/confirm_result/{notice_id}")
async def api_confirm_result(notice_id:int, result:str=Form("已确认"), user=Depends(get_user)):
    if user["role"] != "supplier":
        raise HTTPException(status_code=403, detail="仅供应方可确认结果")
    _check_biz_notice(notice_id)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id FROM notices WHERE id=?",(notice_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="公告不存在")
    cur.execute("SELECT id FROM tender_signup WHERE notice_id=? AND user_id=?",(notice_id,user["id"]))
    sig = cur.fetchone()
    if not sig:
        conn.close()
        raise HTTPException(status_code=400, detail="请先报名")
    cur.execute("SELECT id FROM bid_result WHERE notice_id=? AND user_id=?",(notice_id,user["id"]))
    br = cur.fetchone()
    if br:
        cur.execute("UPDATE bid_result SET result=?, confirm_time=datetime('now','localtime') WHERE id=?",(result,br[0]))
    else:
        cur.execute("INSERT INTO bid_result(notice_id,user_id,result) VALUES (?,?,?)",(notice_id,user["id"],result))
    conn.commit()
    conn.close()
    return {"code":200,"msg":"结果确认成功"}

# 开标流程动态：获取
@app.get("/api/bid_flow_list")
async def api_bid_flow_list(notice_id:int, user=Depends(get_user)):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "SELECT bf.content, bf.create_time, u.name "
        "FROM bid_flow bf LEFT JOIN users u ON bf.user_id = u.id "
        "WHERE bf.notice_id=? ORDER BY bf.create_time ASC"
    ,(notice_id,))
    rows = cur.fetchall()
    conn.close()
    res = []
    for r in rows:
        res.append({"content":r[0], "create_time":r[1], "name":r[2] or ""})
    return {"code":200,"data":res}

# 开标流程动态：发布（采购方/代理机构，开标进行中）
@app.post("/api/bid_flow_add")
async def api_bid_flow_add(item:SaveRecordItem, user=Depends(get_user)):
    _check_biz_notice(item.notice_id)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT publish_uid,open_time,status FROM notices WHERE id=?",(item.notice_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="项目公告不存在")
    pub_uid, ot_str, nstatus = row
    is_super = user["role"] == "super_admin"
    is_publisher = user["id"] == pub_uid
    if not (is_super or is_publisher):
        conn.close()
        raise HTTPException(status_code=403, detail="仅采购方或代理机构可发布开标流程")
    if nstatus == "closed":
        conn.close()
        raise HTTPException(status_code=400, detail="开标已结束，不能发布")
    if ot_str:
        try:
            ot = datetime.fromisoformat(str(ot_str))
            if datetime.now() < ot:
                conn.close()
                raise HTTPException(status_code=400, detail="尚未到开标时间")
        except Exception:
            pass
    content = (item.record or "").strip()
    if not content:
        conn.close()
        raise HTTPException(status_code=400, detail="内容不能为空")
    cur.execute("INSERT INTO bid_flow(notice_id,content,user_id) VALUES (?,?,?)",(item.notice_id,content,user["id"]))
    conn.commit()
    conn.close()
    return {"code":200,"msg":"发布成功"}

# 结束开标流程（代理机构/超管/发布人）
@app.post("/api/bid_room_close")
async def api_bid_room_close(item:SaveRecordItem, user=Depends(get_user)):
    _check_biz_notice(item.notice_id)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT publish_uid,status FROM notices WHERE id=?",(item.notice_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="项目公告不存在")
    pub_uid, nstatus = row
    is_super = user["role"] == "super_admin"
    is_publisher = user["id"] == pub_uid
    if not (is_super or is_publisher or user["role"] == "agent"):
        conn.close()
        raise HTTPException(status_code=403, detail="仅代理机构或管理员可结束开标")
    if nstatus == "closed":
        conn.close()
        raise HTTPException(status_code=400, detail="开标已结束")
    cur.execute("UPDATE notices SET status='closed' WHERE id=?",(item.notice_id,))
    conn.commit()
    conn.close()
    return {"code":200,"msg":"开标流程已结束"}

@app.post("/api/save_bid_record")
async def api_save_bid_record(item:SaveRecordItem, user=Depends(get_user)):
    rid = item.notice_id if item.notice_id is not None else item.project_id
    if rid is None:
        raise HTTPException(status_code=400, detail="缺少项目编号")
    _check_biz_notice(rid)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id FROM bid_record WHERE notice_id=?",(rid,))
    rec = cur.fetchone()
    if rec:
        cur.execute("UPDATE bid_record SET record=? WHERE notice_id=?",(item.record,rid))
    else:
        cur.execute("INSERT INTO bid_record(notice_id,record) VALUES (?,?)",(rid,item.record))
    conn.commit()
    conn.close()
    return {"code":200,"msg":"保存成功"}
# --------------------------原有老业务接口【修改发布公告权限】---------------------------
# 发布中标/变更/终止公告时可选择的项目（已过开标时间、未发布过同类型公告）
@app.get("/api/publishable_projects")
async def api_publishable_projects(notice_type: str = "win", user=Depends(get_user)):
    role_allow_type = {
        "super_admin": ["purchase","win","change","stop","announce","policy","guide"],
        "agent":["purchase","win","change"],
        "purchaser":["purchase"],
        "supplier":[]
    }
    allow_types = role_allow_type.get(user["role"],[])
    if notice_type not in allow_types:
        raise HTTPException(status_code=403, detail="当前角色不允许发布该类型公告")
    now = datetime.now()
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id,project_sn,title,open_time FROM notices WHERE notice_type='purchase' AND open_time IS NOT NULL AND open_time != '' ORDER BY open_time DESC")
    rows = cur.fetchall()
    res = []
    for r in rows:
        rid, psn, ptitle, ot_str = r
        try:
            ot = datetime.fromisoformat(str(ot_str))
            if ot > now:
                continue
        except Exception:
            # 开标时间格式异常时不过滤，避免漏掉可选项
            pass
        if notice_type == "win" and psn:
            cur.execute("SELECT id FROM notices WHERE notice_type='win' AND project_sn=?", (psn,))
            if cur.fetchone():
                continue
        if notice_type == "stop" and psn:
            cur.execute("SELECT id FROM notices WHERE notice_type='stop' AND project_sn=?", (psn,))
            if cur.fetchone():
                continue
        if notice_type == "change" and psn:
            cur.execute("SELECT id FROM notices WHERE notice_type='stop' AND project_sn=?", (psn,))
            if cur.fetchone():
                continue
        res.append({"id": rid, "project_sn": psn or "", "title": ptitle, "no_sn": not psn})
    conn.close()
    return {"code":200, "data": res}

@app.post("/publish_notice")
async def publish_notice(
    title: str = Form(...),
    notice_type: str = Form(...),
    content: str = Form(...),
    project_sn: str = Form(None),
    start_time: str = Form(None),
    end_time: str = Form(None),
    open_time: str = Form(None),
    user = Depends(get_user)
):
    # 角色允许发布的公告类型配置【修改：超管全部7种】
    role_allow_type = {
        "super_admin": ["purchase","win","change","stop","announce","policy","guide"],
        "agent":["purchase","win","change"],
        "purchaser":["purchase"],
        "supplier":[]
    }
    allow_types = role_allow_type.get(user["role"],[])
    if notice_type not in allow_types:
        raise HTTPException(status_code=403, detail="当前角色不允许发布该类型公告")
    content = sanitize_html(content)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute('''
    INSERT INTO notices(title,notice_type,content,publish_uid,project_sn,start_time,end_time,open_time,attach_file)
    VALUES (?,?,?,?,?,?,?,?,?)''',(title,notice_type,content,user["id"],project_sn,start_time,end_time,open_time,""))
    notice_id = cur.lastrowid
    conn.commit()
    conn.close()
    # 返回公告id，前端拿到id之后，如果选了文件，再调用上传接口
    return {"code":200, "msg":"发布成功", "notice_id": notice_id}
# 发布公告上传公告附件（管理员/采购方用，不需要报名）
@app.post("/upload_notice_attach/{notice_id}")
async def upload_notice_attach(notice_id:int, file:UploadFile=File(...), user=Depends(get_user)):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    # 校验：必须是公告发布人或者超级管理员才能上传公告附件
    cur.execute("SELECT publish_uid FROM notices WHERE id=?",(notice_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404,detail="公告不存在")
    pub_uid = row[0]
    if user["id"] != pub_uid and user["role"] != "super_admin":
        conn.close()
        raise HTTPException(status_code=403,detail="仅公告发布人或超管可上传公告附件")
    check_upload_ext(file.filename)
    save_filename = f"notice_{notice_id}_{file.filename}"
    save_path = os.path.join(UPLOAD_DIR, save_filename)
    with open(save_path,"wb") as f:
        f.write(await file.read())
    # 更新notices表保存附件名称
    cur.execute("UPDATE notices SET attach_file=? WHERE id=?",(save_filename,notice_id))
    conn.commit()
    conn.close()
    return {"code":200,"msg":"公告附件上传成功"}

# ==========【新增附件下载接口】==========
@app.get("/download/{filename}")
async def download_file(filename:str):
    full_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404,detail="文件不存在")
    return FileResponse(full_path, filename=filename)

@app.get("/list_notice")
async def list_notice(notice_type:str=None):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    if notice_type:
        cur.execute("SELECT * FROM notices WHERE notice_type=? ORDER BY create_time DESC",(notice_type,))
    else:
        cur.execute("SELECT * FROM notices ORDER BY create_time DESC")
    res = cur.fetchall()
    cols = [c[0] for c in cur.description]
    conn.close()
    return [dict(zip(cols,r)) for r in res]

# =========公告详情页路由（列表页跳 /notice/5 打开详情页面）=========
@app.get("/notice/{nid}")
async def page_notice_detail(nid:int):
    return FileResponse("static/tender_detail.html")

# =========公告详情接口（返回JSON，前端 /api/notice/{nid} 调用）=========
@app.get("/api/notice/{nid}")
async def get_notice(nid:int, authorization: str | None = Header(default=None)):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT * FROM notices WHERE id=?",(nid,))
    row = cur.fetchone()
    cols = [c[0] for c in cur.description]
    if not row:
        conn.close()
        raise HTTPException(status_code=404,detail="公告不存在")
    data = dict(zip(cols,row))
    # 增加中文类型名称，前端直接渲染
    type_map = {
        "purchase":"采购公告",
        "win":"中标公告",
        "change":"变更公告",
        "stop":"终止公告",
        "announce":"平台通知",
        "policy":"政策法规",
        "guide":"业务指南"
    }
    data["type_text"] = type_map.get(data["notice_type"], data["notice_type"])
    # 附件列表（下载链接）
    attachments = []
    if data.get("attach_file"):
        af = data["attach_file"]
        prefix = f"notice_{nid}_"
        display = af[len(prefix):] if af.startswith(prefix) else af
        attachments.append({"id": af, "filename": display, "url": f"/download/{af}"})
    data["attachments"] = attachments
    # 中文状态（按时间计算）
    data["status_text"] = notice_status_text(
        data.get("start_time"), data.get("end_time"), data.get("open_time"), data.get("status")
    )
    # 当前用户是否已报名 / 是否已上传投标文件（未登录返回False）
    data["has_signup"] = False
    data["has_file"] = False
    if authorization and authorization.startswith("Bearer "):
        try:
            payload = jwt.decode(authorization[7:], SECRET_KEY, algorithms=[ALGORITHM])
            uid = int(payload.get("sub"))
            cur.execute("SELECT is_upload,file_name FROM tender_signup WHERE notice_id=? AND user_id=?",(nid,uid))
            sig = cur.fetchone()
            data["has_signup"] = bool(sig)
            data["has_file"] = bool(sig and sig[0] == 1 and sig[1])
        except Exception:
            pass
    conn.close()
    return {"code":200, "data": data}


# ========= 公告管理：修改/删除（仅超级管理员） =========
@app.post("/api/update_notice")
async def api_update_notice(item:UpdateNoticeItem, user=Depends(get_user)):
    if user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="仅超级管理员可修改公告")
    if not item.title.strip():
        raise HTTPException(status_code=400, detail="公告标题不能为空")
    if not item.content.strip():
        raise HTTPException(status_code=400, detail="公告内容不能为空")
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id FROM notices WHERE id=?",(item.id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="公告不存在")
    content = sanitize_html(item.content)
    cur.execute("UPDATE notices SET title=?,notice_type=?,project_sn=?,start_time=?,end_time=?,open_time=?,content=? WHERE id=?",
        (item.title.strip(), item.notice_type, (item.project_sn or "").strip(),
         item.start_time, item.end_time, item.open_time, content, item.id))
    conn.commit()
    conn.close()
    return {"code":200,"msg":"公告修改成功"}

@app.post("/api/delete_notice")
async def api_delete_notice(item:DeleteNoticeItem, user=Depends(get_user)):
    if user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="仅超级管理员可删除公告")
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT attach_file FROM notices WHERE id=?",(item.id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="公告不存在")
    attach = row[0]
    # 收集需要删除的文件（公告附件 + 已报名供应方的投标文件）
    cur.execute("SELECT file_path FROM tender_signup WHERE notice_id=?",(item.id,))
    paths = [r[0] for r in cur.fetchall() if r[0]]
    if attach:
        paths.append(attach)
    # 级联删除业务数据
    cur.execute("DELETE FROM tender_signup WHERE notice_id=?",(item.id,))
    cur.execute("DELETE FROM bid_price WHERE notice_id=?",(item.id,))
    cur.execute("DELETE FROM bid_record WHERE notice_id=?",(item.id,))
    cur.execute("DELETE FROM bid_flow WHERE notice_id=?",(item.id,))
    cur.execute("DELETE FROM bid_result WHERE notice_id=?",(item.id,))
    cur.execute("DELETE FROM notices WHERE id=?",(item.id,))
    conn.commit()
    conn.close()
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except Exception:
            pass
    return {"code":200,"msg":"公告已删除"}

@app.post("/signup/{notice_id}")
async def signup(notice_id:int, user = Depends(get_user)):
    if user["role"]!="supplier":
        raise HTTPException(status_code=403,detail="仅供应商可报名")
    _check_biz_notice(notice_id)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT end_time FROM notices WHERE id=?",(notice_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404,detail="公告不存在")
    end_str = row[0]
    if end_str:
        try:
            end_dt = datetime.fromisoformat(str(end_str))
            if datetime.now() >= end_dt:
                conn.close()
                raise HTTPException(status_code=400, detail="已过投标截止时间，不能报名")
        except Exception:
            pass
    cur.execute("SELECT id FROM tender_signup WHERE notice_id=? AND user_id=?",(notice_id,user["id"]))
    if cur.fetchone():
        conn.close()
        return {"code":200,"msg":"已报名"}
    cur.execute("INSERT INTO tender_signup(notice_id,user_id) VALUES (?,?)",(notice_id,user["id"]))
    conn.commit()
    conn.close()
    return {"code":200,"msg":"报名成功"}

@app.post("/api/signup/{notice_id}")
async def api_signup(notice_id:int, user=Depends(get_user)):
    return await signup(notice_id, user)

# 供应方撤回报名（投标截止前）
@app.post("/api/cancel_signup/{notice_id}")
async def api_cancel_signup(notice_id:int, user=Depends(get_user)):
    if user["role"] != "supplier":
        raise HTTPException(status_code=403, detail="仅供应方可撤回报名")
    _check_biz_notice(notice_id)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT end_time FROM notices WHERE id=?", (notice_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="公告不存在")
    end_str = row[0]
    if end_str:
        try:
            end_dt = datetime.fromisoformat(str(end_str))
            if datetime.now() >= end_dt:
                conn.close()
                raise HTTPException(status_code=400, detail="已过投标截止时间，不能撤回报名")
        except Exception:
            pass
    cur.execute("SELECT id FROM tender_signup WHERE notice_id=? AND user_id=?", (notice_id, user["id"]))
    sig = cur.fetchone()
    if not sig:
        conn.close()
        raise HTTPException(status_code=400, detail="未报名，无法撤回")
    cur.execute("DELETE FROM tender_signup WHERE id=?", (sig[0],))
    conn.commit()
    conn.close()
    return {"code":200, "msg":"报名已撤回"}

# 供应方撤回投标文件（投标截止前）
@app.post("/api/cancel_file/{notice_id}")
async def api_cancel_file(notice_id:int, user=Depends(get_user)):
    if user["role"] != "supplier":
        raise HTTPException(status_code=403, detail="仅供应方可撤回投标文件")
    _check_biz_notice(notice_id)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT end_time FROM notices WHERE id=?", (notice_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="公告不存在")
    end_str = row[0]
    if end_str:
        try:
            end_dt = datetime.fromisoformat(str(end_str))
            if datetime.now() >= end_dt:
                conn.close()
                raise HTTPException(status_code=400, detail="已过投标截止时间，不能撤回投标文件")
        except Exception:
            pass
    cur.execute("SELECT id FROM tender_signup WHERE notice_id=? AND user_id=?", (notice_id, user["id"]))
    sig = cur.fetchone()
    if not sig:
        conn.close()
        raise HTTPException(status_code=400, detail="请先报名")
    cur.execute("UPDATE tender_signup SET file_name=NULL,file_path=NULL,is_upload=0 WHERE id=?", (sig[0],))
    conn.commit()
    conn.close()
    return {"code":200, "msg":"投标文件已撤回"}

@app.post("/upload_file/{notice_id}")
async def upload_file(notice_id:int, file:UploadFile=File(...), price:float=Form(...), user=Depends(get_user)):
    now = datetime.now()
    if price is None or price <= 0:
        raise HTTPException(status_code=400, detail="投标报价必须填写且大于0")
    _check_biz_notice(notice_id)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT end_time FROM notices WHERE id=?",(notice_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404,detail="公告不存在")
    end_str = row[0]
    if end_str:
        try:
            end_dt = datetime.fromisoformat(str(end_str))
            if now >= end_dt:
                conn.close()
                raise HTTPException(status_code=400, detail="已过投标截止时间，禁止上传投标文件")
        except Exception:
            pass
    cur.execute("SELECT id FROM tender_signup WHERE notice_id=? AND user_id=?",(notice_id,user["id"]))
    sig = cur.fetchone()
    if not sig:
        conn.close()
        raise HTTPException(status_code=400,detail="请先报名")
    check_upload_ext(file.filename)
    save_filename = f"{user['id']}_{file.filename}"
    save_path = os.path.join(UPLOAD_DIR, save_filename)
    with open(save_path,"wb") as f:
        f.write(await file.read())
    cur.execute("UPDATE tender_signup SET file_name=?,file_path=?,is_upload=1 WHERE id=?",
                (file.filename,save_path,sig[0]))
    # 投标报价记入 bid_price（重复上传覆盖报价）
    cur.execute("SELECT id FROM bid_price WHERE notice_id=? AND user_id=?",(notice_id,user["id"]))
    bp = cur.fetchone()
    if bp:
        cur.execute("UPDATE bid_price SET price=?, bid_time=datetime('now','localtime') WHERE id=?",(price,bp[0]))
    else:
        cur.execute("INSERT INTO bid_price(notice_id,user_id,price) VALUES (?,?,?)",(notice_id,user["id"],price))
    conn.commit()
    conn.close()
    return {"code":200,"msg":"文件上传成功"}

@app.post("/api/upload_file/{notice_id}")
async def api_upload_file(notice_id:int, file:UploadFile=File(...), price:float=Form(...), user=Depends(get_user)):
    return await upload_file(notice_id, file, price, user)

@app.get("/signup_list/{notice_id}")
async def signup_list(notice_id:int, user=Depends(get_user)):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute('''
    SELECT ts.id, ts.user_id, u.name, ts.file_name, ts.is_upload
    FROM tender_signup ts LEFT JOIN users u ON ts.user_id=u.id
    WHERE notice_id=?''',(notice_id,))
    rows = cur.fetchall()
    cols = [c[0] for c in cur.description]
    conn.close()
    return {"code":200,"data":[dict(zip(cols,r)) for r in rows]}

@app.post("/bid_price/{notice_id}")
async def bid_price(notice_id:int, price:float=Form(...), user=Depends(get_user)):
    now = datetime.now()
    _check_biz_notice(notice_id)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT open_time,status FROM notices WHERE id=?",(notice_id,))
    ot_str,status = cur.fetchone()
    open_dt = datetime.fromisoformat(ot_str)
    if now < open_dt:
        conn.close()
        raise HTTPException(status_code=400,detail="尚未到开标时间，不能报价")
    cur.execute("INSERT INTO bid_price(notice_id,user_id,price) VALUES (?,?,?)",(notice_id,user["id"],price))
    cur.execute("UPDATE notices SET status='open' WHERE id=?",(notice_id,))
    conn.commit()
    conn.close()
    return {"code":200,"msg":"报价提交成功"}

@app.get("/bid_price_list/{notice_id}")
async def bid_price_list(notice_id:int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute('''
    SELECT bp.price,bp.bid_time,u.name
    FROM bid_price bp LEFT JOIN users u ON bp.user_id=u.id
    WHERE notice_id=? ORDER BY price ASC''',(notice_id,))
    rows = cur.fetchall()
    cols = [c[0] for c in cur.description]
    conn.close()
    return {"code":200,"data":[dict(zip(cols,r)) for r in rows]}

@app.get("/me")
async def me(user=Depends(get_user)):
    return user

# 个人中心：获取当前用户信息（含注册时间）
@app.get("/api/profile")
async def api_profile(user = Depends(get_user)):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT username,name,role,status,create_time FROM users WHERE id=?",(user["id"],))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="用户不存在")
    role_text = {"supplier":"供应方","purchaser":"采购方","agent":"代理机构","super_admin":"超级管理员"}.get(row[2], row[2])
    status_text = "启用" if row[3] == 1 else "禁用"
    return {"code":200,"data":{
        "username":row[0],"name":row[1],"role":row[2],"role_text":role_text,
        "status":row[3],"status_text":status_text,"create_time":row[4]
    }}

# 非管理员修改自己的密码
@app.post("/api/change_password")
async def api_change_password(item:ChangePwdItem, user = Depends(get_user)):
    if user["role"] == "super_admin":
        raise HTTPException(status_code=403, detail="管理员请在账号管理中修改密码")
    if not item.old_password or not item.new_password:
        raise HTTPException(status_code=400, detail="旧密码和新密码不能为空")
    if len(item.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码长度不能少于6位")
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT password FROM users WHERE id=?",(user["id"],))
    row = cur.fetchone()
    if not row or not verify_password(item.old_password, row[0]):
        conn.close()
        raise HTTPException(status_code=400, detail="旧密码不正确")
    cur.execute("UPDATE users SET password=? WHERE id=?",(get_password_hash(item.new_password), user["id"]))
    conn.commit()
    conn.close()
    return {"code":200,"msg":"密码修改成功，请重新登录"}

# 超级管理员在账号管理里修改任意用户密码（不验证旧密码）
@app.post("/api/admin_change_password")
async def api_admin_change_password(item:AdminChangePwdItem, user = Depends(get_user)):
    if user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="仅超级管理员可操作")
    if not item.new_password or not item.new_password.strip():
        raise HTTPException(status_code=400, detail="新密码不能为空")
    target = (item.username or "").strip() or user["username"]
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE username=?",(target,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="用户不存在")
    cur.execute("UPDATE users SET password=? WHERE id=?",(get_password_hash(item.new_password), row[0]))
    conn.commit()
    conn.close()
    return {"code":200,"msg":"密码修改成功"}
# --------------------------原有token、register接口不动---------------------------
@app.post("/token")
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

@app.post("/register")
async def register(item:RegisterItem):
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
                (item.username,hash_pwd,item.role,item.name))
    conn.commit()
    conn.close()
    return {"msg":"注册成功"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
