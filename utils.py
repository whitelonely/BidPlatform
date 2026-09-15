# -*- coding: utf-8 -*-
"""通用工具函数：HTML 清洗、公告状态、业务校验、上传校验"""
import os
import re as _re
import sqlite3
from datetime import datetime

from fastapi import HTTPException
import sqlite3
from config import DB_FILE, ALLOW_UPLOAD_EXT


def sanitize_html(s: str) -> str:
    """公告内容入库前的简单安全过滤：去掉 script 标签与 on* 事件属性"""
    if not s:
        return s
    s = _re.sub(r'(?is)<script.*?</script>', '', s)
    s = _re.sub(r'(?i)\s+on\w+\s*=\s*"[^"]*"', '', s)
    s = _re.sub(r"(?i)\s+on\w+\s*=\s*'[^']*'", '', s)
    return s


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
    """按时间计算公告中文状态：未开始/报名中/报名已截止/已开标/已结束"""
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


def check_upload_ext(filename):
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOW_UPLOAD_EXT:
        raise HTTPException(status_code=400, detail="仅支持上传图片、PDF、TXT 等可在线预览的文件")
