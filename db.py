# -*- coding: utf-8 -*-
"""数据库初始化：建表、补列、自动创建超级管理员"""
import sqlite3

from config import DB_FILE
from auth import get_password_hash


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    # users 表：status 1启用 0禁用
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
    # notices 表（统一存放全部类型公告，用 notice_type 区分）
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
    # 兼容旧库：notices 表缺列时自动补列（不删数据）
    for col, ddl in [("project_sn", "TEXT"), ("attach_file", "TEXT")]:
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
    # 开标记录表
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
