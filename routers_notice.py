# -*- coding: utf-8 -*-
"""公告接口：列表、发布、详情、管理、附件"""
from datetime import datetime, timedelta
import os
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File, Form
from fastapi.responses import FileResponse
from jose import jwt

from config import DB_FILE, UPLOAD_DIR, NOTICE_TYPE_MAP, PROJECT_TYPES, SECRET_KEY, ALGORITHM
from auth import get_user
from utils import sanitize_html, notice_status_text, check_upload_ext
from schemas import UpdateNoticeItem, DeleteNoticeItem

router = APIRouter()

# 各角色允许发布的公告类型：超管全部 7 类；代理机构含废标（终止）公告
ROLE_ALLOW_TYPE = {
    "super_admin": ["purchase", "win", "change", "stop", "announce", "policy", "guide"],
    "agent": ["purchase", "win", "change", "stop"],
    "purchaser": ["purchase"],
    "supplier": [],
}


# ========== 各类型公告列表接口 ==========
@router.get("/api/purchase")
async def api_purchase():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id,title, create_time FROM notices WHERE notice_type='purchase' ORDER BY create_time DESC")
    rows = cur.fetchall()
    conn.close()
    res = []
    for r in rows:
        res.append({"id": r[0], "title": r[1], "type": "purchase", "create_time": r[2]})
    return {"code": 200, "data": res}


@router.get("/api/win")
async def api_win():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id,title, create_time FROM notices WHERE notice_type='win' ORDER BY create_time DESC")
    rows = cur.fetchall()
    conn.close()
    res = []
    for r in rows:
        res.append({"id": r[0], "title": r[1], "type": "win", "create_time": r[2]})
    return {"code": 200, "data": res}


@router.get("/api/announce")
async def api_announce():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id,title, create_time FROM notices WHERE notice_type='announce' ORDER BY create_time DESC")
    rows = cur.fetchall()
    conn.close()
    res = []
    for r in rows:
        res.append({"id": r[0], "title": r[1], "type": "announce", "create_time": r[2]})
    return {"code": 200, "data": res}


@router.get("/api/policy")
async def api_policy():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id,title,create_time FROM notices WHERE notice_type='policy' ORDER BY create_time DESC")
    rows = cur.fetchall()
    conn.close()
    res = []
    for r in rows:
        res.append({"id": r[0], "title": r[1], "type": "policy", "create_time": r[2]})
    return {"code": 200, "data": res}


@router.get("/api/guide")
async def api_guide():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id,title,create_time FROM notices WHERE notice_type='guide' ORDER BY create_time DESC")
    rows = cur.fetchall()
    conn.close()
    res = []
    for r in rows:
        res.append({"id": r[0], "title": r[1], "type": "guide", "create_time": r[2]})
    return {"code": 200, "data": res}


# 首页信息查询：全部公告
@router.get("/api/all_notice")
async def api_all_notice():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    # 仅返回招投标相关公告（采购/中标/变更/废标），平台通知/政策法规/业务指南不在此展示
    placeholders = ",".join("?" * len(PROJECT_TYPES))
    cur.execute(f"SELECT id,title,notice_type,project_sn,content,create_time FROM notices WHERE notice_type IN ({placeholders}) ORDER BY create_time DESC", PROJECT_TYPES)
    rows = cur.fetchall()
    conn.close()
    res = []
    for r in rows:
        res.append({
            "id": r[0],
            "title": r[1],
            "type": r[2],
            "type_text": NOTICE_TYPE_MAP.get(r[2], r[2]),
            "project_sn": r[3] or "",
            "content": r[4] or "",
            "create_time": r[5]
        })
    return {"code": 200, "data": res}


# ========== 发布公告 ==========
# 发布中标/变更/废标公告时可选择的项目（已过开标时间、未发布过同类型公告）
@router.get("/api/publishable_projects")
async def api_publishable_projects(notice_type: str = "win", user=Depends(get_user)):
    allow_types = ROLE_ALLOW_TYPE.get(user["role"], [])
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
    return {"code": 200, "data": res}


@router.post("/publish_notice")
async def publish_notice(
    title: str = Form(...),
    notice_type: str = Form(...),
    content: str = Form(...),
    project_sn: str = Form(None),
    start_time: str = Form(None),
    end_time: str = Form(None),
    open_time: str = Form(None),
    user=Depends(get_user)
):
    allow_types = ROLE_ALLOW_TYPE.get(user["role"], [])
    if notice_type not in allow_types:
        raise HTTPException(status_code=403, detail="当前角色不允许发布该类型公告")
    content = sanitize_html(content)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute('''
    INSERT INTO notices(title,notice_type,content,publish_uid,project_sn,start_time,end_time,open_time,attach_file,create_time)
    VALUES (?,?,?,?,?,?,?,?,?,datetime('now','localtime'))''', (title, notice_type, content, user["id"], project_sn, start_time, end_time, open_time, ""))
    notice_id = cur.lastrowid
    conn.commit()
    conn.close()
    # 返回公告id，前端拿到id之后，如果选了文件，再调用上传接口
    return {"code": 200, "msg": "发布成功", "notice_id": notice_id}


# 发布公告上传公告附件（管理员/采购方用，不需要报名）
@router.post("/upload_notice_attach/{notice_id}")
async def upload_notice_attach(notice_id: int, file: UploadFile = File(...), user=Depends(get_user)):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT publish_uid FROM notices WHERE id=?", (notice_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="公告不存在")
    pub_uid = row[0]
    if user["id"] != pub_uid and user["role"] != "super_admin":
        conn.close()
        raise HTTPException(status_code=403, detail="仅公告发布人或超管可上传公告附件")
    check_upload_ext(file.filename)
    save_filename = f"notice_{notice_id}_{file.filename}"
    save_path = os.path.join(UPLOAD_DIR, save_filename)
    with open(save_path, "wb") as f:
        f.write(await file.read())
    cur.execute("UPDATE notices SET attach_file=? WHERE id=?", (save_filename, notice_id))
    conn.commit()
    conn.close()
    return {"code": 200, "msg": "公告附件上传成功"}


# 公告附件下载（inline=1 时浏览器内联预览，不触发下载）
@router.get("/download/{filename}")
async def download_file(filename: str, inline: bool = False):
    full_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="文件不存在")
    if inline:
        # 不带 filename 参数 → 无 Content-Disposition: attachment，浏览器直接预览
        return FileResponse(full_path)
    return FileResponse(full_path, filename=filename)


# ========== 公告详情 ==========
@router.get("/list_notice")
async def list_notice(notice_type: str = None):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    if notice_type:
        cur.execute("SELECT * FROM notices WHERE notice_type=? ORDER BY create_time DESC", (notice_type,))
    else:
        cur.execute("SELECT * FROM notices ORDER BY create_time DESC")
    res = cur.fetchall()
    cols = [c[0] for c in cur.description]
    conn.close()
    return [dict(zip(cols, r)) for r in res]


@router.get("/api/notice/{nid}")
async def get_notice(nid: int, authorization: str | None = Header(default=None)):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT * FROM notices WHERE id=?", (nid,))
    row = cur.fetchone()
    cols = [c[0] for c in cur.description]
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="公告不存在")
    data = dict(zip(cols, row))
    data["type_text"] = NOTICE_TYPE_MAP.get(data["notice_type"], data["notice_type"])
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
    # 当前用户是否已报名 / 是否已上传投标文件（未登录返回 False）
    data["has_signup"] = False
    data["has_file"] = False
    if authorization and authorization.startswith("Bearer "):
        try:
            payload = jwt.decode(authorization[7:], SECRET_KEY, algorithms=[ALGORITHM])
            uid = int(payload.get("sub"))
            cur.execute("SELECT is_upload,file_name FROM tender_signup WHERE notice_id=? AND user_id=?", (nid, uid))
            sig = cur.fetchone()
            data["has_signup"] = bool(sig)
            data["has_file"] = bool(sig and sig[0] == 1 and sig[1])
        except Exception:
            pass
    conn.close()
    return {"code": 200, "data": data}


# ========== 公告管理：修改/删除（仅超级管理员） ==========
@router.post("/api/update_notice")
async def api_update_notice(item: UpdateNoticeItem, user=Depends(get_user)):
    if user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="仅超级管理员可修改公告")
    if not item.title.strip():
        raise HTTPException(status_code=400, detail="公告标题不能为空")
    if not item.content.strip():
        raise HTTPException(status_code=400, detail="公告内容不能为空")
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id FROM notices WHERE id=?", (item.id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="公告不存在")
    content = sanitize_html(item.content)
    cur.execute("UPDATE notices SET title=?,notice_type=?,project_sn=?,start_time=?,end_time=?,open_time=?,content=? WHERE id=?",
                (item.title.strip(), item.notice_type, (item.project_sn or "").strip(),
                 item.start_time, item.end_time, item.open_time, content, item.id))
    conn.commit()
    conn.close()
    return {"code": 200, "msg": "公告修改成功"}


@router.post("/api/delete_notice")
async def api_delete_notice(item: DeleteNoticeItem, user=Depends(get_user)):
    if user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="仅超级管理员可删除公告")
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT attach_file FROM notices WHERE id=?", (item.id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="公告不存在")
    attach = row[0]
    # 收集需要删除的文件（公告附件 + 已报名供应方的投标文件）
    cur.execute("SELECT file_path FROM tender_signup WHERE notice_id=?", (item.id,))
    paths = [r[0] for r in cur.fetchall() if r[0]]
    if attach:
        paths.append(attach)
    # 级联删除业务数据
    cur.execute("DELETE FROM tender_signup WHERE notice_id=?", (item.id,))
    cur.execute("DELETE FROM bid_price WHERE notice_id=?", (item.id,))
    cur.execute("DELETE FROM bid_record WHERE notice_id=?", (item.id,))
    cur.execute("DELETE FROM bid_flow WHERE notice_id=?", (item.id,))
    cur.execute("DELETE FROM bid_result WHERE notice_id=?", (item.id,))
    cur.execute("DELETE FROM notices WHERE id=?", (item.id,))
    conn.commit()
    conn.close()
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except Exception:
            pass
    return {"code": 200, "msg": "公告已删除"}
