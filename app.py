# -*- coding: utf-8 -*-
"""采购管理平台 - 主入口
启动方式：python app.py（或 uvicorn app:app）
模块说明：
    config.py         全局配置（路径、密钥、上传白名单、公告类型映射）
    db.py             数据库初始化（建表、补列、自动创建管理员）
    auth.py           认证工具（密码哈希、JWT、当前用户依赖）
    utils.py          通用工具（HTML 清洗、公告状态、业务校验）
    schemas.py        Pydantic 请求体模型
    routers_page.py   页面路由（HTML 页面 + 公告详情直达）
    routers_user.py   用户接口（登录/注册/账号管理/个人中心/改密）
    routers_notice.py 公告接口（列表/发布/详情/管理/附件）
    routers_bid.py    投标/开标接口（报名/投标文件/报价/开标室/流程/结果）
"""
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from config import STATIC_DIR
import db  # noqa: F401  启动即初始化数据库（建表、自动创建 admin）
from routers_page import router as router_page
from routers_user import router as router_user
from routers_notice import router as router_notice
from routers_bid import router as router_bid

app = FastAPI(title="采购管理平台")

# 静态资源由显式路由返回（Vercel Serverless 下 StaticFiles mount 不生效，统一走 FastAPI 路由）
@app.get("/static/{path:path}")
async def static_file(path: str):
    _full = os.path.normpath(os.path.join(STATIC_DIR, path))
    if not _full.startswith(STATIC_DIR) or not os.path.isfile(_full):
        raise HTTPException(status_code=404, detail="Not Found")
    return FileResponse(_full)

# 业务路由挂载
app.include_router(router_page)
app.include_router(router_user)
app.include_router(router_notice)
app.include_router(router_bid)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
