# -*- coding: utf-8 -*-
"""Pydantic 请求体模型"""
from pydantic import BaseModel


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
    username: str
    password: str
    name: str
    role: str


class AddUserItem(BaseModel):
    username: str
    password: str
    name: str
    role: str


class ToggleUserItem(BaseModel):
    username: str
    status: int


class SaveRecordItem(BaseModel):
    notice_id: int | None = None
    project_id: int | None = None
    record: str


class UpdateNoticeItem(BaseModel):
    id: int
    title: str
    notice_type: str
    project_sn: str = ""
    start_time: str = ""
    end_time: str = ""
    open_time: str = ""
    content: str = ""


class DeleteNoticeItem(BaseModel):
    id: int


class RegisterItem(BaseModel):
    username: str
    password: str
    role: str
    name: str


class ChangePwdItem(BaseModel):
    old_password: str
    new_password: str


class AdminChangePwdItem(BaseModel):
    username: str = ""
    new_password: str


class UpdateUserItem(BaseModel):
    username: str            # 原用户名（标识）
    new_username: str = ""   # 新用户名，留空表示不修改
    name: str = ""           # 公司名称，留空表示不修改
    role: str = ""           # 角色，留空表示不修改
    new_password: str = ""   # 新密码，留空表示不修改
