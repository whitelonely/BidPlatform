# -*- coding: utf-8 -*-
"""页面路由：各 HTML 页面 + 公告详情直达地址"""
from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()


@router.get("/")
async def root():
    return FileResponse("static/index.html")


@router.get("/login")
async def page_login():
    return FileResponse("static/login.html")


@router.get("/notice")
async def page_notice():
    return FileResponse("static/notice.html")


@router.get("/announce")
async def page_announce():
    return FileResponse("static/announce.html")


@router.get("/policy")
async def page_policy():
    return FileResponse("static/policy.html")


@router.get("/guide")
async def page_guide():
    return FileResponse("static/guide.html")


@router.get("/publish")
async def page_publish():
    return FileResponse("static/publish.html")


@router.get("/tender_detail")
async def page_tender_detail():
    return FileResponse("static/tender_detail.html")


@router.get("/tender_details")
async def page_tender_details():
    return FileResponse("static/tender_detail.html")


@router.get("/bid_room")
async def page_bid_room():
    return FileResponse("static/bid_room.html")


@router.get("/profile")
async def page_profile():
    return FileResponse("static/profile.html")


@router.get("/user_manage")
async def page_user_manage():
    return FileResponse("static/user_manage.html")


# 全部公告列表页（招投标信息查询）
@router.get("/all_notice")
async def page_all_notice():
    return FileResponse("static/all_notice.html")


# 兼容旧的带 html 后缀的访问方式，防止旧链接 404
@router.get("/login.html")
async def page_login_html():
    return FileResponse("static/login.html")


@router.get("/notice.html")
async def page_notice_html():
    return FileResponse("static/notice.html")


@router.get("/publish.html")
async def page_publish_html():
    return FileResponse("static/publish.html")


@router.get("/tender_detail.html")
async def page_tender_detail_html():
    return FileResponse("static/tender_detail.html")


@router.get("/tender_details.html")
async def page_tender_details_html():
    return FileResponse("static/tender_detail.html")


@router.get("/bid_room.html")
async def page_bid_room_html():
    return FileResponse("static/bid_room.html")


@router.get("/policy.html")
async def page_policy_html():
    return FileResponse("static/policy.html")


@router.get("/guide.html")
async def page_guide_html():
    return FileResponse("static/guide.html")


@router.get("/announce.html")
async def page_announce_html():
    return FileResponse("static/announce.html")


@router.get("/user_manage.html")
async def page_user_manage_html():
    return FileResponse("static/user_manage.html")


@router.get("/all_notice.html")
async def page_all_notice_html():
    return FileResponse("static/all_notice.html")


# ========== 各类型公告详情直达（统一复用公告详情页 tender_detail.html）==========
# 招投标类：采购/中标/变更/废标（终止）→ /notice/{id}
@router.get("/notice/{nid}")
async def page_notice_detail(nid: int):
    return FileResponse("static/tender_detail.html")


@router.get("/win/{nid}")
async def page_win_detail(nid: int):
    return FileResponse("static/tender_detail.html")


@router.get("/change/{nid}")
async def page_change_detail(nid: int):
    return FileResponse("static/tender_detail.html")


@router.get("/stop/{nid}")
async def page_stop_detail(nid: int):
    return FileResponse("static/tender_detail.html")


# 非招投标类：平台通知/政策法规/业务指南 → 各自地址
@router.get("/announce/{nid}")
async def page_announce_detail(nid: int):
    return FileResponse("static/tender_detail.html")


@router.get("/policy/{nid}")
async def page_policy_detail(nid: int):
    return FileResponse("static/tender_detail.html")


@router.get("/guide/{nid}")
async def page_guide_detail(nid: int):
    return FileResponse("static/tender_detail.html")
