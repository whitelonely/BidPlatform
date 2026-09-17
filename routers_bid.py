# -*- coding: utf-8 -*-
"""投标/开标接口：报名、撤回、投标文件、报价、二次报价、开标室、流程、结果"""
from datetime import datetime
import os
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File, Form
from fastapi.responses import FileResponse
from jose import jwt

from config import DB_FILE, UPLOAD_DIR, SECRET_KEY, ALGORITHM
from auth import get_user
from utils import _check_biz_notice, notice_status_text, check_upload_ext
from schemas import SaveRecordItem

router = APIRouter()


# ========== 开标室 ==========
# 当前用户有权限的项目列表（超管全部 / 发布人 / 已报名供应方）
@router.get("/api/bid_room_list")
async def api_bid_room_list(user=Depends(get_user)):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "SELECT n.id,n.title,n.notice_type,n.project_sn,n.status,n.start_time,n.end_time,n.open_time "
        "FROM notices n "
        "WHERE n.notice_type = 'purchase' "
        "AND (? = 'super_admin' OR n.publish_uid = ? OR n.id IN (SELECT notice_id FROM tender_signup WHERE user_id = ?)) "
        "ORDER BY n.create_time DESC"
        , (user["role"], user["id"], user["id"]))
    rows = cur.fetchall()
    conn.close()
    res = []
    for r in rows:
        res.append({
            "id": r[0],
            "title": r[1],
            "notice_type": r[2],
            "type_text": "采购公告",
            "project_sn": r[3] or "",
            "status": r[4],
            "status_text": notice_status_text(r[5], r[6], r[7], r[4]),
            "start_time": r[5] or "",
            "end_time": r[6] or "",
            "open_time": r[7] or ""
        })
    return {"code": 200, "data": res}


@router.get("/api/bid_room")
async def api_bid_room(project_id: int | None = None, notice_id: int | None = None, user=Depends(get_user)):
    nid = project_id if project_id is not None else notice_id
    if nid is None:
        raise HTTPException(status_code=400, detail="缺少项目编号")
    _check_biz_notice(nid)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    # 查询公告
    cur.execute("SELECT id,title,notice_type,publish_uid,project_sn,status,start_time,end_time,open_time FROM notices WHERE id=?", (nid,))
    notice_row = cur.fetchone()
    if not notice_row:
        conn.close()
        raise HTTPException(status_code=404, detail="项目公告不存在")
    nid, title, ntype, publish_uid, project_sn, nstatus, st_str, et_str, ot_str = notice_row
    # 权限判定：超级管理员 OR 公告发布人 OR 已经报名的供应方
    is_super = user["role"] == "super_admin"
    is_publisher = user["id"] == publish_uid
    cur.execute("SELECT id FROM tender_signup WHERE notice_id=? AND user_id=?", (nid, user["id"]))
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
    ''', (nid,))
    sup_rows = cur.fetchall()
    supplier_list = []
    for s in sup_rows:
        supplier_list.append({
            "username": s[1],
            "name": s[2],
            "apply_status": "已报名",
            "file_name": s[3],
            "is_upload": s[4],
            "price": s[5],
            "second_price": s[6],
            "result": s[7],
            "file_url": (f"/download_bid/{nid}/{s[0]}" if s[4] == 1 and s[3] else "")
        })
    # 查询开标记录
    cur.execute("SELECT record FROM bid_record WHERE notice_id=?", (nid,))
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
        "code": 200,
        "data": {
            "title": title,
            "notice_id": nid,
            "notice_type": ntype,
            "project_sn": project_sn,
            "status": nstatus,
            "status_text": notice_status_text(st_str, et_str, ot_str, nstatus),
            "record": record_txt,
            "is_open": is_open,
            "can_publish": can_publish,
            "can_close": can_close,
            "supplier_list": supplier_list
        }
    }


# 投标文件下载/预览（开标室权限内可访问；支持 header 或 ?token= 两种认证）
@router.get("/download_bid/{notice_id}/{user_id}")
async def download_bid(notice_id: int, user_id: int, token: str | None = None,
                       authorization: str | None = Header(default=None), inline: bool = False):
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
    cur.execute("SELECT publish_uid FROM notices WHERE id=?", (notice_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="公告不存在")
    pub_uid = row[0]
    is_super = urow[1] == "super_admin"
    is_publisher = uid == pub_uid
    cur.execute("SELECT id FROM tender_signup WHERE notice_id=? AND user_id=?", (notice_id, uid))
    is_signup = bool(cur.fetchone())
    if not (is_super or is_publisher or is_signup):
        conn.close()
        raise HTTPException(status_code=403, detail="无权查看该投标文件")
    cur.execute("SELECT file_path,file_name FROM tender_signup WHERE notice_id=? AND user_id=? AND is_upload=1", (notice_id, user_id))
    fr = cur.fetchone()
    conn.close()
    if not fr or not fr[0] or not os.path.exists(fr[0]):
        raise HTTPException(status_code=404, detail="文件不存在")
    if inline:
        # 不带 filename 参数 → 浏览器内联预览（PDF/图片直接显示，不下载）
        return FileResponse(fr[0])
    return FileResponse(fr[0], filename=fr[1])


# 供应方二次报价（开标进行中，未结束前）
@router.post("/api/second_bid/{notice_id}")
async def api_second_bid(notice_id: int, second_price: float = Form(...), user=Depends(get_user)):
    if user["role"] != "supplier":
        raise HTTPException(status_code=403, detail="仅供应方可二次报价")
    if second_price is None or second_price <= 0:
        raise HTTPException(status_code=400, detail="二次报价必须填写且大于0")
    _check_biz_notice(notice_id)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT open_time,status FROM notices WHERE id=?", (notice_id,))
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
    cur.execute("SELECT id FROM tender_signup WHERE notice_id=? AND user_id=?", (notice_id, user["id"]))
    sig = cur.fetchone()
    if not sig:
        conn.close()
        raise HTTPException(status_code=400, detail="请先报名")
    # 二次报价只能提交一次
    cur.execute("SELECT second_price FROM bid_price WHERE notice_id=? AND user_id=?", (notice_id, user["id"]))
    bp0 = cur.fetchone()
    if bp0 and bp0[0] is not None:
        conn.close()
        raise HTTPException(status_code=400, detail="已提交过二次报价，不能重复提交")
    # 结果确认后不能再修改
    cur.execute("SELECT id FROM bid_result WHERE notice_id=? AND user_id=?", (notice_id, user["id"]))
    if cur.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="已确认开标结果，不能修改二次报价")
    cur.execute("SELECT id FROM bid_price WHERE notice_id=? AND user_id=?", (notice_id, user["id"]))
    bp = cur.fetchone()
    if bp:
        cur.execute("UPDATE bid_price SET second_price=?, second_time=datetime('now','localtime') WHERE id=?", (second_price, bp[0]))
    else:
        cur.execute("INSERT INTO bid_price(notice_id,user_id,price,second_price) VALUES (?,?,?,?)", (notice_id, user["id"], 0, second_price))
    conn.commit()
    conn.close()
    return {"code": 200, "msg": "二次报价提交成功"}


# 供应方结果确认
@router.post("/api/confirm_result/{notice_id}")
async def api_confirm_result(notice_id: int, result: str = Form("已确认"), user=Depends(get_user)):
    if user["role"] != "supplier":
        raise HTTPException(status_code=403, detail="仅供应方可确认结果")
    _check_biz_notice(notice_id)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id FROM notices WHERE id=?", (notice_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="公告不存在")
    cur.execute("SELECT id FROM tender_signup WHERE notice_id=? AND user_id=?", (notice_id, user["id"]))
    sig = cur.fetchone()
    if not sig:
        conn.close()
        raise HTTPException(status_code=400, detail="请先报名")
    cur.execute("SELECT id FROM bid_result WHERE notice_id=? AND user_id=?", (notice_id, user["id"]))
    br = cur.fetchone()
    if br:
        cur.execute("UPDATE bid_result SET result=?, confirm_time=datetime('now','localtime') WHERE id=?", (result, br[0]))
    else:
        cur.execute("INSERT INTO bid_result(notice_id,user_id,result) VALUES (?,?,?)", (notice_id, user["id"], result))
    conn.commit()
    conn.close()
    return {"code": 200, "msg": "结果确认成功"}


# 开标流程动态：获取
@router.get("/api/bid_flow_list")
async def api_bid_flow_list(notice_id: int, user=Depends(get_user)):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "SELECT bf.content, bf.create_time, u.name "
        "FROM bid_flow bf LEFT JOIN users u ON bf.user_id = u.id "
        "WHERE bf.notice_id=? ORDER BY bf.create_time DESC"
        , (notice_id,))
    rows = cur.fetchall()
    conn.close()
    res = []
    for r in rows:
        res.append({"content": r[0], "create_time": r[1], "name": r[2] or ""})
    return {"code": 200, "data": res}


# 开标流程动态：发布（采购方/代理机构，开标进行中）
@router.post("/api/bid_flow_add")
async def api_bid_flow_add(item: SaveRecordItem, user=Depends(get_user)):
    _check_biz_notice(item.notice_id)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT publish_uid,open_time,status FROM notices WHERE id=?", (item.notice_id,))
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
    cur.execute("INSERT INTO bid_flow(notice_id,content,user_id) VALUES (?,?,?)", (item.notice_id, content, user["id"]))
    conn.commit()
    conn.close()
    return {"code": 200, "msg": "发布成功"}


# 结束开标流程（代理机构/超管/发布人）
@router.post("/api/bid_room_close")
async def api_bid_room_close(item: SaveRecordItem, user=Depends(get_user)):
    _check_biz_notice(item.notice_id)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT publish_uid,status FROM notices WHERE id=?", (item.notice_id,))
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
    cur.execute("UPDATE notices SET status='closed' WHERE id=?", (item.notice_id,))
    conn.commit()
    conn.close()
    return {"code": 200, "msg": "开标流程已结束"}


# 保存开标记录
@router.post("/api/save_bid_record")
async def api_save_bid_record(item: SaveRecordItem, user=Depends(get_user)):
    rid = item.notice_id if item.notice_id is not None else item.project_id
    if rid is None:
        raise HTTPException(status_code=400, detail="缺少项目编号")
    _check_biz_notice(rid)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id FROM bid_record WHERE notice_id=?", (rid,))
    rec = cur.fetchone()
    if rec:
        cur.execute("UPDATE bid_record SET record=? WHERE notice_id=?", (item.record, rid))
    else:
        cur.execute("INSERT INTO bid_record(notice_id,record) VALUES (?,?)", (rid, item.record))
    conn.commit()
    conn.close()
    return {"code": 200, "msg": "保存成功"}


# ========== 报名 / 投标文件 ==========
@router.post("/signup/{notice_id}")
async def signup(notice_id: int, user=Depends(get_user)):
    if user["role"] != "supplier":
        raise HTTPException(status_code=403, detail="仅供应商可报名")
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
                raise HTTPException(status_code=400, detail="已过投标截止时间，不能报名")
        except Exception:
            pass
    cur.execute("SELECT id FROM tender_signup WHERE notice_id=? AND user_id=?", (notice_id, user["id"]))
    if cur.fetchone():
        conn.close()
        return {"code": 200, "msg": "已报名"}
    cur.execute("INSERT INTO tender_signup(notice_id,user_id) VALUES (?,?)", (notice_id, user["id"]))
    conn.commit()
    conn.close()
    return {"code": 200, "msg": "报名成功"}


@router.post("/api/signup/{notice_id}")
async def api_signup(notice_id: int, user=Depends(get_user)):
    return await signup(notice_id, user)


# 供应方撤回报名（投标截止前）
@router.post("/api/cancel_signup/{notice_id}")
async def api_cancel_signup(notice_id: int, user=Depends(get_user)):
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
    return {"code": 200, "msg": "报名已撤回"}


# 供应方撤回投标文件（投标截止前）
@router.post("/api/cancel_file/{notice_id}")
async def api_cancel_file(notice_id: int, user=Depends(get_user)):
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
    return {"code": 200, "msg": "投标文件已撤回"}


@router.post("/upload_file/{notice_id}")
async def upload_file(notice_id: int, file: UploadFile = File(...), price: float = Form(...), user=Depends(get_user)):
    now = datetime.now()
    if price is None or price <= 0:
        raise HTTPException(status_code=400, detail="投标报价必须填写且大于0")
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
            if now >= end_dt:
                conn.close()
                raise HTTPException(status_code=400, detail="已过投标截止时间，禁止上传投标文件")
        except Exception:
            pass
    cur.execute("SELECT id FROM tender_signup WHERE notice_id=? AND user_id=?", (notice_id, user["id"]))
    sig = cur.fetchone()
    if not sig:
        conn.close()
        raise HTTPException(status_code=400, detail="请先报名")
    check_upload_ext(file.filename)
    save_filename = f"{user['id']}_{file.filename}"
    save_path = os.path.join(UPLOAD_DIR, save_filename)
    with open(save_path, "wb") as f:
        f.write(await file.read())
    cur.execute("UPDATE tender_signup SET file_name=?,file_path=?,is_upload=1 WHERE id=?",
                (file.filename, save_path, sig[0]))
    # 投标报价记入 bid_price（重复上传覆盖报价）
    cur.execute("SELECT id FROM bid_price WHERE notice_id=? AND user_id=?", (notice_id, user["id"]))
    bp = cur.fetchone()
    if bp:
        cur.execute("UPDATE bid_price SET price=?, bid_time=datetime('now','localtime') WHERE id=?", (price, bp[0]))
    else:
        cur.execute("INSERT INTO bid_price(notice_id,user_id,price) VALUES (?,?,?)", (notice_id, user["id"], price))
    conn.commit()
    conn.close()
    return {"code": 200, "msg": "文件上传成功"}


@router.post("/api/upload_file/{notice_id}")
async def api_upload_file(notice_id: int, file: UploadFile = File(...), price: float = Form(...), user=Depends(get_user)):
    return await upload_file(notice_id, file, price, user)


@router.get("/signup_list/{notice_id}")
async def signup_list(notice_id: int, user=Depends(get_user)):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute('''
    SELECT ts.id, ts.user_id, u.name, ts.file_name, ts.is_upload
    FROM tender_signup ts LEFT JOIN users u ON ts.user_id=u.id
    WHERE notice_id=?''', (notice_id,))
    rows = cur.fetchall()
    cols = [c[0] for c in cur.description]
    conn.close()
    return {"code": 200, "data": [dict(zip(cols, r)) for r in rows]}


@router.post("/bid_price/{notice_id}")
async def bid_price(notice_id: int, price: float = Form(...), user=Depends(get_user)):
    now = datetime.now()
    _check_biz_notice(notice_id)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT open_time,status FROM notices WHERE id=?", (notice_id,))
    ot_str, status = cur.fetchone()
    open_dt = datetime.fromisoformat(ot_str)
    if now < open_dt:
        conn.close()
        raise HTTPException(status_code=400, detail="尚未到开标时间，不能报价")
    cur.execute("INSERT INTO bid_price(notice_id,user_id,price) VALUES (?,?,?)", (notice_id, user["id"], price))
    cur.execute("UPDATE notices SET status='open' WHERE id=?", (notice_id,))
    conn.commit()
    conn.close()
    return {"code": 200, "msg": "报价提交成功"}


@router.get("/bid_price_list/{notice_id}")
async def bid_price_list(notice_id: int):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute('''
    SELECT bp.price,bp.bid_time,u.name
    FROM bid_price bp LEFT JOIN users u ON bp.user_id=u.id
    WHERE notice_id=? ORDER BY price ASC''', (notice_id,))
    rows = cur.fetchall()
    cols = [c[0] for c in cur.description]
    conn.close()
    return {"code": 200, "data": [dict(zip(cols, r)) for r in rows]}
