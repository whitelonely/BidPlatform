# -*- coding: utf-8 -*-
"""全局配置：路径、密钥、上传白名单等"""
import os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Vercel Serverless 环境文件系统只读（仅 /tmp 可写），自动切换数据目录；本地开发用项目目录下 proc.db / uploads
IS_VERCEL = bool(os.environ.get("VERCEL"))
if IS_VERCEL:
    DB_FILE = "/tmp/proc.db"
    UPLOAD_DIR = "/tmp/uploads"
else:
    DB_FILE = os.path.join(_BASE_DIR, "proc.db")
    UPLOAD_DIR = os.path.join(_BASE_DIR, "uploads")

os.makedirs(UPLOAD_DIR, exist_ok=True)

SECRET_KEY = "procurement-secret-key-2026"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120

# 上传文件类型白名单（浏览器可直接预览的类型）
ALLOW_UPLOAD_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".pdf", ".txt"}

# 静态资源目录（Vercel 下也基于 __file__ 定位，不依赖运行目录）
STATIC_DIR = os.path.join(_BASE_DIR, "static")

# 公告类型 → 中文名（全项目统一）
NOTICE_TYPE_MAP = {
    "purchase": "采购公告",
    "win": "中标公告",
    "change": "变更公告",
    "stop": "废标（终止）公告",
    "announce": "平台通知",
    "policy": "政策法规",
    "guide": "业务指南",
}

# 招投标相关公告类型（可报名/开标，详情地址用 /notice/{id}）
PROJECT_TYPES = ["purchase", "win", "change", "stop"]
# 非招投标公告类型（各自独立详情地址）
ARTICLE_TYPES = ["announce", "policy", "guide"]
