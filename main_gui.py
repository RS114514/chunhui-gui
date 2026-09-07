#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""浙江省春晖中学校园网图形界面客户端 (chunhui-gui)

超轻量、高性能、原生独立桌面视窗客户端。
基于 pywebview (macOS WKWebView / Windows WebView2) 与本地微内核架构构建。
秒级启动，杜绝 Tk 8.5 兼容问题，内存占用极低 (<25MB)。
彻底对齐 ch_cli 后端内网接口，支持账号密码验证码登录、Cookie 会话管理与真实数据渲染。
无网络连接或数据为空时真实呈现断网/空白状态，绝不伪造虚假数据。
"""

import os
import sys

# 优先确保从项目虚拟环境中加载 pywebview
try:
    import webview
except ImportError:
    venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "bin", "python")
    if os.path.exists(venv_python) and sys.executable != venv_python:
        os.execv(venv_python, [venv_python] + sys.argv)
    webview = None

import re
import json
import time
import math
import socket
import threading
import urllib.parse
import urllib.request
import tempfile

# 引入底层 CLI 逻辑模块
try:
    import ch_cli
except ImportError:
    ch_cli = None

CAMPUS_IP = "10.181.200.3"
CAMPUS_BASE_URL = "http://10.181.200.3"

# 全局状态缓存
CACHED_IS_ONLINE = False
LAST_CHECK_TIME = 0

def check_intranet_connection(timeout=1.5, force=False):
    """检测校园内网 10.181.200.3 是否真实可达（默认包含15秒短效缓存）"""
    global CACHED_IS_ONLINE, LAST_CHECK_TIME
    now = time.time()
    if not force and (now - LAST_CHECK_TIME < 15):
        return CACHED_IS_ONLINE
        
    if ch_cli and hasattr(ch_cli, "check_intranet_connection"):
        CACHED_IS_ONLINE = ch_cli.check_intranet_connection(timeout=timeout)
    else:
        try:
            req = urllib.request.Request(f"{CAMPUS_BASE_URL}/account/login4Stu/", headers={"User-Agent": "ChunhuiClient/1.3"}, method="HEAD")
            with urllib.request.urlopen(req, timeout=timeout):
                CACHED_IS_ONLINE = True
        except urllib.error.HTTPError:
            CACHED_IS_ONLINE = True
        except Exception:
            CACHED_IS_ONLINE = False
    LAST_CHECK_TIME = time.time()
    return CACHED_IS_ONLINE

# ----------------------------------------------------------------------
# 原生 JavaScript API 交互桥梁 (通过 pywebview.api 暴露给前端页面)
# ----------------------------------------------------------------------

class ChunhuiApi:
    def __init__(self):
        self._cached_captcha_cookies = {}

    def get_status(self, force_refresh=False):
        """返回网络连接状态和本地会话状态"""
        is_online = check_intranet_connection(timeout=1.5, force=force_refresh)
        session = ch_cli.load_session() if ch_cli else {}
        has_session = bool(session.get("sessionid"))
        return {
            "is_online": is_online,
            "campus_ip": CAMPUS_IP,
            "has_session": has_session,
            "sessionid_preview": (session.get("sessionid", "")[:6] + "...") if has_session else "",
            "timestamp": int(time.time())
        }

    # ----- 登录与会话认证 -----

    def get_captcha(self):
        """获取登录图形验证码（Base64）及临时会话"""
        if not check_intranet_connection():
            return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
        res = ch_cli.get_captcha()
        if res.get("success"):
            self._cached_captcha_cookies = res.get("cookies", {})
        return res

    def login_account(self, username, password, code):
        """通过学号/用户名、密码与验证码登录"""
        if not check_intranet_connection():
            return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
        username = (username or "").strip()
        password = (password or "").strip()
        code = (code or "").strip()
        if not username or not password or not code:
            return {"success": False, "error": "请完整填写用户名、密码和验证码"}
        res = ch_cli.login_with_credentials(username, password, code, self._cached_captcha_cookies)
        return res

    def login_cookie(self, cookie_str):
        """通过直接粘贴 Cookie 导入会话"""
        cookie_str = (cookie_str or "").strip()
        if not cookie_str:
            return {"success": False, "error": "Cookie 内容不能为空"}
        res = ch_cli.login_with_cookie(cookie_str)
        return res

    def logout(self):
        """清除本地会话并退出登录"""
        if ch_cli:
            ch_cli.clear_session()
        self._cached_captcha_cookies = {}
        return {"success": True, "message": "已成功退出登录并清除本地会话"}

    # ----- 1. 个人信件 (收件箱) -----

    def get_messages(self, page=1):
        """获取收件箱信件列表"""
        if not check_intranet_connection():
            return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
        try:
            status, body, _ = ch_cli.make_request(f"/sitemessage/message-Receive-list/?page={page}", method="GET")
            if status != 200:
                return {"success": False, "error": f"服务器响应异常 (HTTP {status})"}
            html_content = body.decode("utf-8", errors="ignore")
            trs = re.findall(r'<tr[^>]*>(.*?)</tr>', html_content, re.DOTALL)
            rows = []
            for tr in trs:
                if "show-Message" in tr or "del_siteMessage" in tr:
                    id_m = re.search(r'/sitemessage/show-Message/(\d+)/\s*', tr)
                    msg_id = id_m.group(1) if id_m else ""
                    if not msg_id:
                        id_m = re.search(r'del_siteMessage\(this,(\d+)\)', tr)
                        if id_m:
                            msg_id = id_m.group(1)
                    tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL)
                    if len(tds) >= 3:
                        title = ch_cli.clean_html(tds[1])
                        sender = ch_cli.clean_html(tds[2])
                        date = ch_cli.clean_html(tds[3]) if len(tds) > 3 else ""
                        is_unread = ("未阅" in tr or "未读" in tr or "font-weight" in tr)
                        rows.append({
                            "id": msg_id,
                            "title": title,
                            "sender": sender,
                            "time": date,
                            "unread": is_unread
                        })
            return {"success": True, "data": rows, "page": page}
        except Exception as e:
            return {"success": False, "error": f"获取信件失败: {e}"}

    def get_message_detail(self, msg_id):
        """获取信件正文与附件列表"""
        if not check_intranet_connection():
            return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
        try:
            status, body, _ = ch_cli.make_request(f"/sitemessage/show-Message/{msg_id}/", method="GET")
            if status != 200:
                return {"success": False, "error": f"获取信件详情失败 (HTTP {status})"}
            html_content = body.decode("utf-8", errors="ignore")
            
            title = "无标题"
            m = re.search(r'<div class="ArticleTitle">(.*?)</div>', html_content, re.DOTALL)
            if m:
                title = ch_cli.clean_html(m.group(1))
                
            sender = "未知"
            m = re.search(r'发送者：\s*([^\s<]+)', html_content)
            if m:
                sender = m.group(1).strip()
                
            send_time = "未知"
            m = re.search(r'发送时间：\s*([^\s<]+(?:\s+[^\s<]+)?)', html_content)
            if m:
                send_time = m.group(1).strip()
                
            content = ""
            m = re.search(r'<div class="ArticleContent[^>]*>(.*?)</div>\s*</div>', html_content, re.DOTALL)
            if not m:
                m = re.search(r'<div class="ArticleContent[^>]*>(.*?)</div>', html_content, re.DOTALL)
            if m:
                content = ch_cli.render_html_content(m.group(1))
                
            recipients_all = "无"
            m = re.search(r'id="multiCollapseExample1">\s*<div class="card card-body">\s*(.*?)\s*</div>', html_content, re.DOTALL)
            if m:
                recipients_all = ch_cli.clean_html(m.group(1))
                
            recipients_unread = "无"
            m = re.search(r'id="multiCollapseExample2">\s*<div class="card card-body">\s*(.*?)\s*</div>', html_content, re.DOTALL)
            if m:
                recipients_unread = ch_cli.clean_html(m.group(1))
                
            # 提取附件链接
            links = []
            for lk in re.findall(r'href=["\'](.*?)["\']', html_content):
                lk = lk.strip()
                if not lk or lk == "#" or "javascript:" in lk:
                    continue
                lower = lk.lower()
                is_file = any(ext in lower for ext in ('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.zip', '.rar', '.png', '.jpg', '.txt', '.mp4'))
                if is_file or "/fileaccess/" in lk:
                    if any(k in lk for k in ("Logo", "newFunc", "sydw")):
                        continue
                    full = lk if lk.startswith("http") else f"{CAMPUS_BASE_URL}{lk}" if lk.startswith("/") else f"{CAMPUS_BASE_URL}/{lk}"
                    filename = urllib.parse.unquote(full.split('/')[-1].split('?')[0])
                    if not any(item["url"] == full for item in links):
                        links.append({"name": filename, "url": full})
                        
            return {
                "success": True,
                "data": {
                    "id": msg_id,
                    "title": title,
                    "sender": sender,
                    "time": send_time,
                    "content": content,
                    "recipients_all": recipients_all,
                    "recipients_unread": recipients_unread,
                    "attachments": links
                }
            }
        except Exception as e:
            return {"success": False, "error": f"解析信件异常: {e}"}

    # ----- 2. 校园通知与公告 (News) -----

    def get_news(self, column="16", page=1):
        """获取校内公告与资讯列表 (16=通知公告, 13=新闻聚焦, 19=校内公示, 51=值周小结)"""
        if not check_intranet_connection():
            return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
        try:
            status, body, _ = ch_cli.make_request(f"/article/column-detail/{column}/?page={page}", method="GET")
            if status != 200:
                return {"success": False, "error": f"获取资讯列表失败 (HTTP {status})"}
            html_content = body.decode("utf-8", errors="ignore")
            trs = re.findall(r'<tr[^>]*>(.*?)</tr>', html_content, re.DOTALL)
            rows = []
            for tr in trs:
                if "/article/article-detail/" in tr:
                    id_m = re.search(r'/article/article-detail/(\d+)/\s*', tr)
                    art_id = id_m.group(1) if id_m else ""
                    tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL)
                    if len(tds) >= 2:
                        title = ch_cli.clean_html(tds[0])
                        date = ch_cli.clean_html(tds[1])
                        rows.append({"id": art_id, "title": title, "date": date})
            return {"success": True, "data": rows, "column": column, "page": page}
        except Exception as e:
            return {"success": False, "error": f"获取文章资讯异常: {e}"}

    def get_news_detail(self, article_id):
        """获取资讯文章详细正文"""
        if not check_intranet_connection():
            return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
        try:
            status, body, _ = ch_cli.make_request(f"/article/article-detail/{article_id}/", method="GET", follow_redirects=True)
            if status != 200:
                return {"success": False, "error": f"获取文章详情失败 (HTTP {status})"}
            html_content = body.decode("utf-8", errors="ignore")
            
            title = "无标题"
            m = re.search(r'<div class="ArticleTitle[^>]*>(.*?)</div>', html_content, re.DOTALL)
            if m:
                title = ch_cli.clean_html(m.group(1))
                
            source = "校内发布"
            m = re.search(r'来源：\s*([^<]+)', html_content)
            if m:
                source = ch_cli.clean_html(m.group(1))
                
            pub_time = "未知"
            m = re.search(r'发布时间：\s*([^\s<]+(?:\s+[^\s<]+)?)', html_content)
            if m:
                pub_time = m.group(1).strip()
                
            content = ""
            m = re.search(r'<div class="ArticleContent(?:\s+[^>]*|)\s*>(.*?)</div>', html_content, re.DOTALL)
            if m:
                content = ch_cli.render_html_content(m.group(1))
                
            links = []
            for lk in re.findall(r'href=["\'](.*?)["\']', html_content):
                lk = lk.strip()
                if any(lk.lower().endswith(ext) for ext in ('.pdf', '.docx', '.doc', '.xlsx', '.xls', '.zip', '.rar', '.png', '.jpg')) or '/fileaccess/' in lk:
                    full = lk if lk.startswith("http") else f"{CAMPUS_BASE_URL}{lk}" if lk.startswith("/") else f"{CAMPUS_BASE_URL}/{lk}"
                    filename = urllib.parse.unquote(full.split('/')[-1].split('?')[0])
                    if not any(item["url"] == full for item in links):
                        links.append({"name": filename, "url": full})
                        
            return {
                "success": True,
                "data": {
                    "id": article_id,
                    "title": title,
                    "source": source,
                    "time": pub_time,
                    "content": content,
                    "attachments": links
                }
            }
        except Exception as e:
            return {"success": False, "error": f"解析文章详情异常: {e}"}

    # ----- 3. 班级课表查询系统 (Schedule) -----

    def get_classes(self, grade_id):
        """根据年级ID (1=高一, 2=高二, 3=高三) 获取全部班级列表"""
        if not check_intranet_connection():
            return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
        try:
            status, body, _ = ch_cli.make_request("/subjectArrangement/getClassFromGradeForSelect/", method="POST", data={"theGradeID": grade_id})
            if status != 200:
                return {"success": False, "error": f"获取班级列表失败 (HTTP {status})"}
            classes = json.loads(body.decode("utf-8"))
            return {"success": True, "data": classes}
        except Exception as e:
            return {"success": False, "error": f"解析班级列表异常: {e}"}

    def get_schedule(self, grade_id, class_id):
        """获取指定班级的周课表矩阵和任课教师列表"""
        if not check_intranet_connection():
            return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
        try:
            data_post = {
                "chGradeIDForName": grade_id,
                "chClassIDForName": class_id
            }
            status, body_html, _ = ch_cli.make_request("/subjectArrangement/ClassClassArrangement_JustForView/", method="POST", data=data_post)
            if status != 200:
                return {"success": False, "error": f"查询课表失败 (HTTP {status})"}
            html_content = body_html.decode("utf-8", errors="ignore")
            
            match = re.search(r'dataObj\s*=\s*(\[\[.*?\]\])\s*;', html_content)
            if not match:
                return {"success": False, "error": "页面中未找到课表数据矩阵 (可能未排课)"}
            data_obj = json.loads(match.group(1))
            
            main_manager = "未知"
            sub_manager = "未知"
            m1 = re.search(r'班主任：\s*([^\s<]+)', html_content)
            if m1:
                main_manager = m1.group(1).strip()
            m2 = re.search(r'副班主任：\s*([^\s<]+)', html_content)
            if m2:
                sub_manager = m2.group(1).strip()
                
            teachers = []
            tm = re.search(r'id="ClassSubjectTeacher"[^>]*>(.*?)</div>\s*</div>', html_content, re.DOTALL)
            if tm:
                uls = re.findall(r'<ul>(.*?)</ul>', tm.group(1), re.DOTALL)
                for ul in uls:
                    clean = re.sub(r'<[^>]+>', '', ul).strip()
                    clean = re.sub(r'\s+', ' ', clean)
                    if clean:
                        teachers.append(clean)
                        
            return {
                "success": True,
                "data": {
                    "matrix": data_obj,
                    "main_manager": main_manager,
                    "sub_manager": sub_manager,
                    "teachers": teachers
                }
            }
        except Exception as e:
            return {"success": False, "error": f"课表解析异常: {e}"}

    # ----- 4. 常规卫生与纪律考评 (Hygiene) -----

    def get_hygiene(self, page=1):
        """获取纪律卫生违纪检查列表"""
        if not check_intranet_connection():
            return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
        try:
            status, body, _ = ch_cli.make_request(f"/classappraise/hygienePictures_receive_list/?page={page}", method="GET")
            if status != 200:
                return {"success": False, "error": f"获取考评记录失败 (HTTP {status})"}
            html_content = body.decode("utf-8", errors="ignore")
            trs = re.findall(r'<tr[^>]*>(.*?)</tr>', html_content, re.DOTALL)
            rows = []
            for tr in trs:
                if "show-Message" in tr:
                    id_m = re.search(r'/classappraise/show-Message/(\d+)/\s*', tr)
                    rec_id = id_m.group(1) if id_m else ""
                    tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL)
                    if len(tds) >= 4:
                        location = ch_cli.clean_html(tds[1])
                        desc = ch_cli.clean_html(tds[2])
                        date = ch_cli.clean_html(tds[3])
                        rows.append({"id": rec_id, "location": location, "desc": desc, "date": date})
            return {"success": True, "data": rows, "page": page}
        except Exception as e:
            return {"success": False, "error": f"获取考评记录异常: {e}"}

    def get_hygiene_detail(self, record_id):
        """获取考评多媒体现场记录及通报情况"""
        if not check_intranet_connection():
            return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
        try:
            status, body, _ = ch_cli.make_request(f"/classappraise/show-Message/{record_id}/", method="GET")
            if status != 200:
                return {"success": False, "error": f"获取考评详情失败 (HTTP {status})"}
            html_content = body.decode("utf-8", errors="ignore")
            
            desc = "未知违纪描述"
            m = re.search(r'<div class="ArticleContent[^>]*>(.*?)</div>', html_content, re.DOTALL)
            if m:
                desc = ch_cli.render_html_content(m.group(1))
                
            media_urls = []
            for img in re.findall(r'<img[^>]+src=["\'](.*?)["\']', html_content):
                if not any(k in img for k in ("Logo", "newFunc", "sydw")):
                    full = img if img.startswith("http") else f"{CAMPUS_BASE_URL}{img}" if img.startswith("/") else f"{CAMPUS_BASE_URL}/{img}"
                    if full not in media_urls:
                        media_urls.append({"type": "image", "url": full})
            for vid in re.findall(r'<video[^>]+src=["\'](.*?)["\']', html_content):
                full = vid if vid.startswith("http") else f"{CAMPUS_BASE_URL}{vid}" if vid.startswith("/") else f"{CAMPUS_BASE_URL}/{vid}"
                if full not in [item["url"] for item in media_urls]:
                    media_urls.append({"type": "video", "url": full})
                    
            recipients_all = "无"
            m = re.search(r'id="multiCollapseExample1">\s*<div class="card card-body">\s*(.*?)\s*</div>', html_content, re.DOTALL)
            if m:
                recipients_all = ch_cli.clean_html(m.group(1))
                
            recipients_unread = "无"
            m = re.search(r'id="multiCollapseExample2">\s*<div class="card card-body">\s*(.*?)\s*</div>', html_content, re.DOTALL)
            if m:
                recipients_unread = ch_cli.clean_html(m.group(1))
                
            return {
                "success": True,
                "data": {
                    "id": record_id,
                    "desc": desc,
                    "media_urls": media_urls,
                    "recipients_all": recipients_all,
                    "recipients_unread": recipients_unread
                }
            }
        except Exception as e:
            return {"success": False, "error": f"解析考评详情异常: {e}"}

    # ----- 5. 寝室纪律内务 (Bedroom) -----

    def get_bedroom_hygiene(self, dorm="1", start="", end="", show_all=False):
        """查询宿舍楼宇考评扣分总表 (dorm 1~9 对应 3号楼~11号楼)"""
        if not check_intranet_connection():
            return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
        try:
            if not start:
                start = time.strftime("%Y-%m-%d", time.localtime(time.time() - 30 * 86400))
            if not end:
                end = time.strftime("%Y-%m-%d")
            post_data = {
                "chDormitoryForName": dorm,
                "theBeginDateForName": start,
                "theEndDateForName": end
            }
            status, body, _ = ch_cli.make_request("/classappraise/BedRoom_DisciplineHygiene_JustForView/", method="POST", data=post_data)
            if status != 200:
                return {"success": False, "error": f"查询宿舍考评失败 (HTTP {status})"}
            html_content = body.decode("utf-8", errors="ignore")
            trs = re.findall(r'<tr[^>]*>(.*?)</tr>', html_content, re.DOTALL)
            rows = []
            for tr in trs:
                tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL)
                if len(tds) >= 4:
                    room = ch_cli.clean_html(tds[0])
                    cls_name = ch_cli.clean_html(tds[1])
                    hyg = ch_cli.clean_html(tds[2])
                    disc = ch_cli.clean_html(tds[3])
                    total = ch_cli.clean_html(tds[4]) if len(tds) > 4 else ""
                    if not show_all and (not total or total.strip() in ("", "0")):
                        continue
                    rows.append({
                        "room": room,
                        "class": cls_name,
                        "hygiene": hyg or "-",
                        "discipline": disc or "-",
                        "total": total or "-"
                    })
            return {"success": True, "data": rows, "dorm": dorm, "start": start, "end": end}
        except Exception as e:
            return {"success": False, "error": f"解析宿舍记录异常: {e}"}

    def get_bedroom_class(self, grade_id, class_name):
        """查询班级寝室分配对应"""
        if not check_intranet_connection():
            return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
        try:
            res = ch_cli.find_class_id(int(grade_id), class_name)
            if not res:
                return {"success": False, "error": f"在所选年级中未找到班级: {class_name}"}
            class_id, resolved_name = res
            post_data = {
                "chGradeIDForName": grade_id,
                "chClassIDForName": class_id
            }
            status, body, _ = ch_cli.make_request("/classappraise/QueryBedroomsByClassID_JustForView/", method="POST", data=post_data)
            if status != 200:
                return {"success": False, "error": f"查询班级寝室失败 (HTTP {status})"}
            html_content = body.decode("utf-8", errors="ignore")
            m = re.search(r'class="alert alert-primary"[^>]*>\s*(.*?)\s*</div>', html_content, re.DOTALL)
            if m:
                info = ch_cli.clean_html(m.group(1))
                return {"success": True, "class_name": resolved_name, "info": info}
            return {"success": True, "class_name": resolved_name, "info": "该班级暂未登记寝室分配数据"}
        except Exception as e:
            return {"success": False, "error": f"查询寝室异常: {e}"}

    # ----- 6. 行政值周安排 (Duty) -----

    def get_duty(self):
        """获取教师行政值周周次排班总表"""
        if not check_intranet_connection():
            return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
        try:
            status, body, _ = ch_cli.make_request("/classappraise/TeacherDutyWeek_JustForView/", method="GET")
            if status != 200:
                return {"success": False, "error": f"获取值周安排失败 (HTTP {status})"}
            html_content = body.decode("utf-8", errors="ignore")
            blocks = re.findall(r'<ul class="list-group"\s*>(.*?)</ul>', html_content, re.DOTALL)
            duties = []
            for block in blocks:
                is_current = "list-group-item-success" in block
                lis = re.findall(r'<li[^>]*>(.*?)</li>', block, re.DOTALL)
                if not lis:
                    continue
                week_name = re.sub(r'<[^>]+>', '', lis[0]).strip()
                date_range = re.sub(r'<[^>]+>', '', lis[1]).strip() if len(lis) > 1 else ""
                details = {}
                for li in lis[2:]:
                    clean = re.sub(r'<[^>]+>', '', li).strip()
                    if "：" in clean:
                        k, v = clean.split("：", 1)
                        details[k.strip()] = v.strip()
                duties.append({
                    "is_current": is_current,
                    "week": week_name,
                    "date": date_range,
                    "admin": details.get("行政值周", ""),
                    "group1": details.get("第一小组", ""),
                    "group2": details.get("第二小组", ""),
                    "group3": details.get("第三小组", ""),
                    "duty_class": details.get("值周班级", ""),
                    "talk": details.get("旗下讲话", "")
                })
            return {"success": True, "data": duties}
        except Exception as e:
            return {"success": False, "error": f"解析值周数据异常: {e}"}

    # ----- 7. 全校失物招领 (Lost & Found) -----

    def get_lostfound(self, page=1):
        """获取失物招领列表"""
        if not check_intranet_connection():
            return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
        try:
            status, body, _ = ch_cli.make_request(f"/lostAndFound/?page={page}", method="GET")
            if status != 200:
                return {"success": False, "error": f"获取失物招领失败 (HTTP {status})"}
            html_content = body.decode("utf-8", errors="ignore")
            trs = re.findall(r'<tr[^>]*>(.*?)</tr>', html_content, re.DOTALL)
            rows = []
            for tr in trs:
                if "/lostAndFound/lostAndFoundDetail/" in tr:
                    tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL)
                    if len(tds) >= 7:
                        id_m = re.search(r'href=["\']/lostAndFound/lostAndFoundDetail/(\d+)/["\']', tds[2])
                        lf_id = id_m.group(1) if id_m else ""
                        cat = ch_cli.clean_html(tds[1])
                        title = ch_cli.clean_html(tds[2])
                        reporter = ch_cli.clean_html(tds[3])
                        date = ch_cli.clean_html(tds[6])
                        st = ch_cli.clean_html(tds[8]) if len(tds) > 8 else ""
                        rows.append({
                            "id": lf_id,
                            "category": cat,
                            "title": title,
                            "reporter": reporter,
                            "date": date,
                            "status": st
                        })
            return {"success": True, "data": rows, "page": page}
        except Exception as e:
            return {"success": False, "error": f"解析招领列表异常: {e}"}

    def get_lostfound_detail(self, item_id):
        """获取失物招领详细说明与认领联系方式"""
        if not check_intranet_connection():
            return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
        try:
            status, body, _ = ch_cli.make_request(f"/lostAndFound/lostAndFoundDetail/{item_id}/", method="GET", follow_redirects=True)
            if status != 200:
                return {"success": False, "error": f"获取招领详情失败 (HTTP {status})"}
            html_content = body.decode("utf-8", errors="ignore")
            
            title = "无标题"
            m = re.search(r'<div class="ArticleTitle[^>]*>(.*?)</div>', html_content, re.DOTALL)
            if m:
                title = ch_cli.clean_html(m.group(1))
                
            reporter = "未知"
            m = re.search(r'来源：\s*([^<]+)', html_content)
            if m:
                reporter = ch_cli.clean_html(m.group(1))
                
            reviewer = "未知"
            m = re.search(r'审核人：\s*([^<]+)', html_content)
            if m:
                reviewer = ch_cli.clean_html(m.group(1))
                
            pub_time = "未知"
            m = re.search(r'发布时间：\s*([^\s<]+(?:\s+[^\s<]+)?)', html_content)
            if m:
                pub_time = m.group(1).strip()
                
            content = ""
            m = re.search(r'<div class="ArticleContent(?:\s+[^>]*|)\s*>(.*?)</div>', html_content, re.DOTALL)
            if m:
                content = ch_cli.render_html_content(m.group(1))
                
            return {
                "success": True,
                "data": {
                    "id": item_id,
                    "title": title,
                    "reporter": reporter,
                    "reviewer": reviewer,
                    "time": pub_time,
                    "content": content
                }
            }
        except Exception as e:
            return {"success": False, "error": f"解析招领详情异常: {e}"}

    # ----- 8. 校内文件寄取处 (File Station) -----

    def retrieve_file(self, code):
        """输入 6 位取件密码查询远端文件详情"""
        if not check_intranet_connection():
            return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
        code = (code or "").strip()
        if len(code) != 6 or not code.isdigit():
            return {"success": False, "error": "请输入有效的 6 位数字取件密码"}
        try:
            post_data = {"thePasswordTheUserEntered": code}
            status, body, _ = ch_cli.make_request("/fileaccess/get-AccessFile/", method="POST", data=post_data)
            if status != 200:
                return {"success": False, "error": f"查询提取码失败 (HTTP {status})"}
            res_json = json.loads(body.decode("utf-8"))
            if res_json.get("error") != "0":
                err_msg = res_json.get("msg", "提取码不存在、错误或文件已过期")
                return {"success": False, "error": err_msg}
            file_path_name = res_json.get("filePathName")
            file_name = res_json.get("fileNameForDisplay")
            if not file_path_name or not file_name:
                return {"success": False, "error": "服务端返回的文件信息不完整"}
            download_url = f"{CAMPUS_BASE_URL}/static/fileaccess/{file_path_name}"
            return {
                "success": True,
                "filename": file_name,
                "download_url": download_url,
                "code": code
            }
        except Exception as e:
            return {"success": False, "error": f"提取文件查询异常: {e}"}

    def choose_file(self):
        """调出原生系统文件选择器"""
        if webview and webview.windows:
            win = webview.windows[0]
            chosen = win.create_file_dialog(webview.OPEN_DIALOG)
            if chosen and len(chosen) > 0:
                fpath = chosen[0]
                fname = os.path.basename(fpath)
                fsize = os.path.getsize(fpath)
                return {"success": True, "path": fpath, "name": fname, "size": fsize}
        return {"success": False, "error": "未选择文件"}

    def upload_file(self, file_path):
        """执行真实 100MB 逻辑分片上传并返回提取密码"""
        if not check_intranet_connection():
            return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
        session = ch_cli.load_session() if ch_cli else {}
        if not session.get("sessionid"):
            return {"success": False, "error": "文件上传需要校园网账号认证，请先点击右上角登录"}
        if not file_path or not os.path.exists(file_path):
            return {"success": False, "error": "所选文件不存在"}
            
        try:
            file_size = os.path.getsize(file_path)
            file_name = os.path.basename(file_path)
            chunk_size = 100 * 1024 * 1024
            total_chunks = math.ceil(file_size / chunk_size) if file_size > 0 else 1
            file_guid = str(urllib.parse.quote(file_name)) + "_" + str(int(time.time()))
            
            with open(file_path, "rb") as f:
                for chunk_idx in range(total_chunks):
                    chunk_data = f.read(chunk_size)
                    boundary = "----WebKitFormBoundary" + os.urandom(8).hex()
                    body_parts = []
                    fields = {
                        "id": f"WU_FILE_{chunk_idx}",
                        "name": file_name,
                        "type": "application/octet-stream",
                        "lastModifiedDate": time.strftime("%a %b %d %Y %H:%M:%S GMT+0800"),
                        "size": str(file_size),
                        "chunks": str(total_chunks),
                        "chunk": str(chunk_idx),
                        "guid": file_guid
                    }
                    for k, v in fields.items():
                        body_parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode("utf-8"))
                    body_parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{file_name}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode("utf-8"))
                    body_parts.append(chunk_data)
                    body_parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
                    full_body = b"".join(body_parts)
                    
                    headers = {
                        "Content-Type": f"multipart/form-data; boundary={boundary}",
                        "Content-Length": str(len(full_body))
                    }
                    status, _, _ = ch_cli.make_request("/fileaccess/files_upload/", method="POST", data=full_body, headers=headers)
                    if status != 200:
                        return {"success": False, "error": f"分片 {chunk_idx+1}/{total_chunks} 上传失败 (HTTP {status})"}
                        
            # 合并分片请求
            complete_data = {
                "guid": file_guid,
                "fileName": file_name
            }
            status_c, body_c, _ = ch_cli.make_request("/fileaccess/upload_complete/", method="POST", data=complete_data)
            if status_c != 200:
                return {"success": False, "error": f"合并分片失败 (HTTP {status_c})"}
            pwd = body_c.decode("utf-8", errors="ignore").strip()
            pwd = ch_cli.clean_html(pwd)
            return {"success": True, "code": pwd, "filename": file_name}
        except Exception as e:
            return {"success": False, "error": f"文件上传异常: {e}"}

    def save_download(self, download_url, filename):
        """调出原生保存对话框并下载远端文件"""
        if not check_intranet_connection():
            return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
        if webview and webview.windows:
            win = webview.windows[0]
            dest = win.create_file_dialog(webview.SAVE_DIALOG, save_filename=filename)
            if dest:
                target_path = dest if isinstance(dest, str) else dest[0]
                try:
                    status, body, _ = ch_cli.make_request(download_url, method="GET")
                    if status == 200:
                        with open(target_path, "wb") as f:
                            f.write(body)
                        return {"success": True, "path": target_path}
                    return {"success": False, "error": f"下载失败 (HTTP {status})"}
                except Exception as e:
                    return {"success": False, "error": f"保存文件失败: {e}"}
        return {"success": False, "error": "取消保存"}

# ----------------------------------------------------------------------
# 原生 HTML/CSS/JS 界面定义 (零外部依赖、极速现代设计、无 Mock 真实反馈)
# ----------------------------------------------------------------------

DESKTOP_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>春晖中学校园网客户端</title>
<style>
:root {
  --bg-main: #f8fafc;
  --bg-card: #ffffff;
  --bg-sidebar: #0f172a;
  --text-main: #0f172a;
  --text-muted: #64748b;
  --primary: #1d4ed8;
  --primary-hover: #1e40af;
  --border: #e2e8f0;
  --danger: #dc2626;
  --success: #16a34a;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", "Microsoft YaHei", sans-serif;
  background-color: var(--bg-main);
  color: var(--text-main);
  display: flex;
  height: 100vh;
  overflow: hidden;
  user-select: none;
}
#sidebar {
  width: 216px;
  background-color: var(--bg-sidebar);
  color: #f8fafc;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}
.brand {
  padding: 18px 16px 14px;
  border-bottom: 1px solid rgba(255,255,255,0.08);
}
.brand h1 { font-size: 14.5px; font-weight: 700; color: #fff; }
.brand p { font-size: 11px; color: #94a3b8; margin-top: 3px; }
.nav-menu {
  flex: 1;
  overflow-y: auto;
  padding: 10px 6px;
}
.nav-item {
  display: flex;
  align-items: center;
  padding: 8.5px 12px;
  margin-bottom: 3px;
  border-radius: 6px;
  font-size: 12.5px;
  color: #cbd5e1;
  cursor: pointer;
  transition: all 0.15s ease;
}
.nav-item:hover {
  background-color: rgba(255,255,255,0.08);
  color: #fff;
}
.nav-item.active {
  background-color: var(--primary);
  color: #fff;
  font-weight: 600;
}
.nav-icon { margin-right: 9px; font-size: 14px; }
.sidebar-footer {
  padding: 10px 14px;
  border-top: 1px solid rgba(255,255,255,0.08);
  font-size: 11px;
  color: #64748b;
  display: flex;
  justify-content: space-between;
}
#main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
header {
  height: 50px;
  background-color: #ffffff;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 18px;
  flex-shrink: 0;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.page-title { font-size: 15px; font-weight: 700; color: #1e293b; }
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 9px;
  border-radius: 9999px;
  font-size: 11px;
  font-weight: 600;
}
.status-pill.offline { background-color: #f1f5f9; color: #64748b; border: 1px solid #cbd5e1; }
.status-pill.online { background-color: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; }
.status-dot { width: 7px; height: 7px; border-radius: 50%; background-color: currentColor; }
.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.session-pill {
  font-size: 11.5px;
  padding: 3px 8px;
  border-radius: 4px;
  font-weight: 500;
}
.session-pill.logged { background: #e0f2fe; color: #0369a1; }
.session-pill.guest { background: #f1f5f9; color: #64748b; }

.btn {
  padding: 5.5px 12px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  border: 1px solid var(--border);
  background-color: #fff;
  color: #334155;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  transition: all 0.15s ease;
}
.btn:hover { background-color: #f8fafc; border-color: #cbd5e1; }
.btn-primary { background-color: var(--primary); color: #fff; border: 1px solid var(--primary); }
.btn-primary:hover { background-color: var(--primary-hover); }
.btn-danger { background-color: #ef4444; color: #fff; border: 1px solid #ef4444; }
.btn-danger:hover { background-color: #dc2626; }
.content-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
}
.tab-pane { display: none; }
.tab-pane.active { display: block; }
.card {
  background: var(--bg-card);
  border-radius: 8px;
  border: 1px solid var(--border);
  box-shadow: 0 1px 3px rgba(0,0,0,0.02);
  overflow: hidden;
  margin-bottom: 14px;
}
.toolbar {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.search-input {
  padding: 6px 11px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 12px;
  width: 240px;
  outline: none;
  background: #fff;
}
.search-input:focus { border-color: var(--primary); }
table.data-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  font-size: 12.5px;
}
table.data-table th {
  background-color: #f8fafc;
  color: #475569;
  font-weight: 600;
  padding: 9.5px 14px;
  border-bottom: 1px solid var(--border);
}
table.data-table td {
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  color: #1e293b;
}
table.data-table tr:hover td {
  background-color: #f8fafc;
  cursor: pointer;
}
.tag {
  display: inline-block;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}
.tag-blue { background: #dbeafe; color: #1e40af; }
.tag-gray { background: #e2e8f0; color: #475569; }
.tag-red { background: #fee2e2; color: #b91c1c; }
.tag-green { background: #dcfce7; color: #15803d; }
.grid-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
.form-group { margin-bottom: 12px; }
.form-group label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: #475569;
  margin-bottom: 4px;
}
.form-control {
  width: 100%;
  padding: 7px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 12px;
  outline: none;
}
.form-control:focus { border-color: var(--primary); }

/* 空状态与错误断网卡片 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  text-align: center;
  color: var(--text-muted);
}
.empty-icon { font-size: 40px; margin-bottom: 12px; }
.empty-title { font-size: 15px; font-weight: 600; color: #334155; margin-bottom: 6px; }
.empty-desc { font-size: 12px; max-width: 420px; line-height: 1.6; margin-bottom: 16px; }

/* 模态框通用 */
.modal-overlay {
  display: none;
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(15, 23, 42, 0.45);
  backdrop-filter: blur(2px);
  z-index: 1000;
  align-items: center;
  justify-content: center;
}
.modal-card {
  width: 620px;
  max-width: 92vw;
  max-height: 86vh;
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 20px 25px -5px rgba(0,0,0,0.1);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.modal-header {
  padding: 12px 18px;
  border-bottom: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #f8fafc;
}
.modal-header h3 { font-size: 14.5px; font-weight: 700; color: #0f172a; }
.modal-close {
  font-size: 20px;
  font-weight: bold;
  color: #94a3b8;
  cursor: pointer;
  border: none;
  background: none;
  padding: 0 4px;
}
.modal-close:hover { color: #0f172a; }
.modal-body {
  padding: 18px 20px;
  overflow-y: auto;
  font-size: 13px;
  line-height: 1.6;
  color: #334155;
  user-select: text;
}
.modal-footer {
  padding: 10px 18px;
  border-top: 1px solid var(--border);
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  background: #f8fafc;
}

/* 课表表格矩阵样式 */
.sched-table {
  width: 100%;
  border-collapse: collapse;
  text-align: center;
  font-size: 12px;
}
.sched-table th {
  background: #f1f5f9;
  color: #334155;
  padding: 8px 6px;
  border: 1px solid #cbd5e1;
  font-weight: 600;
}
.sched-table td {
  border: 1px solid #e2e8f0;
  padding: 8px 4px;
  color: #1e293b;
  min-height: 36px;
}
.sched-table tr:nth-child(even) td { background-color: #fafafa; }
.sched-subject { font-weight: 600; color: #1d4ed8; }

/* 登录选项卡 */
.auth-tabs {
  display: flex;
  border-bottom: 1px solid var(--border);
  margin-bottom: 16px;
}
.auth-tab-btn {
  padding: 8px 16px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted);
  border-bottom: 2px solid transparent;
}
.auth-tab-btn.active {
  color: var(--primary);
  border-bottom-color: var(--primary);
}
.captcha-container {
  display: flex;
  gap: 8px;
  align-items: center;
}
.captcha-img {
  height: 34px;
  border: 1px solid var(--border);
  border-radius: 4px;
  cursor: pointer;
  background: #f8fafc;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  color: var(--text-muted);
  min-width: 100px;
}
</style>
</head>
<body>

<div id="sidebar">
  <div class="brand">
    <h1>春晖中学校园网</h1>
    <p>桌面客户端 (CLI 接口直连版)</p>
  </div>
  <div class="nav-menu">
    <div class="nav-item active" data-tab="inbox" onclick="switchTab('inbox')"><span class="nav-icon">📬</span>个人信件 (收件箱)</div>
    <div class="nav-item" data-tab="news" onclick="switchTab('news')"><span class="nav-icon">📢</span>校园通知与公告</div>
    <div class="nav-item" data-tab="schedule" onclick="switchTab('schedule')"><span class="nav-icon">📅</span>班级课表查询</div>
    <div class="nav-item" data-tab="hygiene" onclick="switchTab('hygiene')"><span class="nav-icon">🧹</span>常规卫生考评</div>
    <div class="nav-item" data-tab="dorm" onclick="switchTab('dorm')"><span class="nav-icon">🛏️</span>寝室纪律内务</div>
    <div class="nav-item" data-tab="duty" onclick="switchTab('duty')"><span class="nav-icon">🛡️</span>行政值周安排</div>
    <div class="nav-item" data-tab="lostfound" onclick="switchTab('lostfound')"><span class="nav-icon">🎒</span>全校失物招领</div>
    <div class="nav-item" data-tab="filestation" onclick="switchTab('filestation')"><span class="nav-icon">📦</span>校内文件寄取处</div>
    <div class="nav-item" data-tab="settings" onclick="switchTab('settings')"><span class="nav-icon">⚙️</span>网络与会话状态</div>
  </div>
  <div class="sidebar-footer">
    <span>chunhui-gui v1.3.0</span>
  </div>
</div>

<div id="main-content">
  <header>
    <div class="header-left">
      <div class="page-title" id="current-title">个人信件 (收件箱)</div>
      <div id="network-badge" class="status-pill offline">
        <span class="status-dot"></span>
        <span id="network-text">检测中...</span>
      </div>
    </div>
    <div class="header-right">
      <div id="session-badge" class="session-pill guest">⚪ 未登录</div>
      <button id="auth-btn" class="btn btn-primary" onclick="openAuthModal()">登录账号</button>
      <button class="btn" onclick="checkNetwork(true)">🔄 检测网络</button>
    </div>
  </header>

  <div class="content-body">
    <!-- 1. 个人信件 (收件箱) -->
    <div id="tab-inbox" class="tab-pane active">
      <div class="toolbar">
        <input type="text" class="search-input" placeholder="筛选信件标题、发件人..." oninput="filterTable('inbox-table', this.value)">
        <button class="btn" onclick="loadInbox(currentInboxPage)">刷新列表</button>
        <span style="font-size:12px; color:var(--text-muted); margin-left:auto;">当前第 <span id="inbox-page-num">1</span> 页</span>
        <button class="btn" onclick="prevInboxPage()">上一页</button>
        <button class="btn" onclick="nextInboxPage()">下一页</button>
      </div>
      <div class="card" id="inbox-card">
        <table class="data-table" id="inbox-table">
          <thead>
            <tr>
              <th style="width: 80px;">编号</th>
              <th>标题</th>
              <th style="width: 130px;">发件人</th>
              <th style="width: 150px;">发送时间</th>
              <th style="width: 85px;">状态</th>
            </tr>
          </thead>
          <tbody id="inbox-rows"></tbody>
        </table>
      </div>
    </div>

    <!-- 2. 校园通知与公告 (News) -->
    <div id="tab-news" class="tab-pane">
      <div class="toolbar">
        <select id="news-column-select" class="form-control" style="width: 170px;" onchange="loadNews(this.value, 1)">
          <option value="16">📢 通知公告 (16)</option>
          <option value="13">📰 新闻聚焦 (13)</option>
          <option value="19">📋 校内公示 (19)</option>
          <option value="51">📝 值周小结 (51)</option>
        </select>
        <input type="text" class="search-input" placeholder="筛选标题..." oninput="filterTable('news-table', this.value)">
        <button class="btn" onclick="loadNews(document.getElementById('news-column-select').value, currentNewsPage)">刷新</button>
        <span style="font-size:12px; color:var(--text-muted); margin-left:auto;">第 <span id="news-page-num">1</span> 页</span>
        <button class="btn" onclick="prevNewsPage()">上一页</button>
        <button class="btn" onclick="nextNewsPage()">下一页</button>
      </div>
      <div class="card" id="news-card">
        <table class="data-table" id="news-table">
          <thead>
            <tr>
              <th style="width: 85px;">文章ID</th>
              <th>文章标题</th>
              <th style="width: 140px;">发布日期</th>
            </tr>
          </thead>
          <tbody id="news-rows"></tbody>
        </table>
      </div>
    </div>

    <!-- 3. 班级课表查询 (Schedule) -->
    <div id="tab-schedule" class="tab-pane">
      <div class="toolbar">
        <label style="font-size:12px; font-weight:600;">年级：</label>
        <select id="sched-grade-select" class="form-control" style="width: 130px;" onchange="handleSchedGradeChange(this.value)">
          <option value="1">高一年级</option>
          <option value="2">高二年级</option>
          <option value="3">高三年级</option>
        </select>
        <label style="font-size:12px; font-weight:600; margin-left:8px;">班级：</label>
        <select id="sched-class-select" class="form-control" style="width: 170px;">
          <option value="">正在获取班级列表...</option>
        </select>
        <button class="btn btn-primary" onclick="querySchedule()">查询课表</button>
      </div>
      <div id="schedule-container"></div>
    </div>

    <!-- 4. 常规卫生考评 (Hygiene) -->
    <div id="tab-hygiene" class="tab-pane">
      <div class="toolbar">
        <input type="text" class="search-input" placeholder="搜索违纪地点、说明..." oninput="filterTable('hygiene-table', this.value)">
        <button class="btn" onclick="loadHygiene(currentHygienePage)">刷新</button>
        <span style="font-size:12px; color:var(--text-muted); margin-left:auto;">第 <span id="hygiene-page-num">1</span> 页</span>
        <button class="btn" onclick="prevHygienePage()">上一页</button>
        <button class="btn" onclick="nextHygienePage()">下一页</button>
      </div>
      <div class="card" id="hygiene-card">
        <table class="data-table" id="hygiene-table">
          <thead>
            <tr>
              <th style="width: 80px;">编号</th>
              <th style="width: 180px;">违纪地点</th>
              <th>考评记录说明</th>
              <th style="width: 140px;">检查时间</th>
            </tr>
          </thead>
          <tbody id="hygiene-rows"></tbody>
        </table>
      </div>
    </div>

    <!-- 5. 寝室纪律内务 (Dorm) -->
    <div id="tab-dorm" class="tab-pane">
      <div class="toolbar">
        <label style="font-size:12px; font-weight:600;">宿舍楼宇：</label>
        <select id="dorm-select" class="form-control" style="width: 130px;">
          <option value="1">3号楼 (男寝)</option>
          <option value="2">4号楼 (男寝)</option>
          <option value="3">5号楼 (男寝)</option>
          <option value="4">6号楼 (男寝)</option>
          <option value="5">7号楼 (女寝)</option>
          <option value="6">8号楼 (女寝)</option>
          <option value="7">9号楼 (女寝)</option>
          <option value="8">10号楼 (女寝)</option>
          <option value="9">11号楼 (女寝)</option>
        </select>
        <label style="font-size:12px; font-weight:600; margin-left:6px;">起止日期：</label>
        <input type="date" id="dorm-start-date" class="form-control" style="width: 130px;">
        <span>至</span>
        <input type="date" id="dorm-end-date" class="form-control" style="width: 130px;">
        <label style="font-size:12px; margin-left:6px; display:inline-flex; align-items:center; gap:4px; cursor:pointer;">
          <input type="checkbox" id="dorm-show-all"> 显示全部宿舍
        </label>
        <button class="btn btn-primary" onclick="queryDormHygiene()">查询楼宇考评</button>
        <button class="btn" style="margin-left:auto;" onclick="openClassRoomQueryModal()">查询班级寝室号</button>
      </div>
      <div class="card" id="dorm-card">
        <table class="data-table" id="dorm-table">
          <thead>
            <tr>
              <th style="width: 140px;">寝室房号</th>
              <th style="width: 160px;">所属班级</th>
              <th style="width: 110px;">卫生扣分</th>
              <th style="width: 110px;">纪律扣分</th>
              <th style="width: 110px;">合计扣分</th>
            </tr>
          </thead>
          <tbody id="dorm-rows"></tbody>
        </table>
      </div>
    </div>

    <!-- 6. 行政值周安排 (Duty) -->
    <div id="tab-duty" class="tab-pane">
      <div class="toolbar">
        <input type="text" class="search-input" placeholder="搜索值周组长、教师、班级..." oninput="filterTable('duty-table', this.value)">
        <button class="btn" onclick="loadDuty()">刷新安排表</button>
      </div>
      <div class="card" id="duty-card">
        <table class="data-table" id="duty-table">
          <thead>
            <tr>
              <th style="width: 95px;">周次</th>
              <th style="width: 140px;">日期范围</th>
              <th style="width: 110px;">行政值周</th>
              <th>值周小组 (一/二/三组)</th>
              <th style="width: 120px;">值周班级</th>
              <th style="width: 130px;">旗下讲话</th>
            </tr>
          </thead>
          <tbody id="duty-rows"></tbody>
        </table>
      </div>
    </div>

    <!-- 7. 全校失物招领 (Lost & Found) -->
    <div id="tab-lostfound" class="tab-pane">
      <div class="toolbar">
        <input type="text" class="search-input" placeholder="筛选物品名称、发布处..." oninput="filterTable('lostfound-table', this.value)">
        <button class="btn" onclick="loadLostfound(currentLostfoundPage)">刷新</button>
        <span style="font-size:12px; color:var(--text-muted); margin-left:auto;">第 <span id="lf-page-num">1</span> 页</span>
        <button class="btn" onclick="prevLostfoundPage()">上一页</button>
        <button class="btn" onclick="nextLostfoundPage()">下一页</button>
      </div>
      <div class="card" id="lostfound-card">
        <table class="data-table" id="lostfound-table">
          <thead>
            <tr>
              <th style="width: 80px;">编号</th>
              <th style="width: 100px;">类别</th>
              <th>物品名称</th>
              <th style="width: 140px;">发布处</th>
              <th style="width: 130px;">登记日期</th>
              <th style="width: 90px;">状态</th>
            </tr>
          </thead>
          <tbody id="lostfound-rows"></tbody>
        </table>
      </div>
    </div>

    <!-- 8. 校内文件寄取处 (File Station) -->
    <div id="tab-filestation" class="tab-pane">
      <div class="grid-2">
        <div class="card" style="padding: 18px;">
          <h3 style="font-size: 14px; margin-bottom: 8px;">📥 寄存寄件 (本地文件上传)</h3>
          <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 14px; line-height: 1.5;">
            遵循校内网 100MB 逻辑分片上传规范。文件上传成功后服务端自动分配 6 位取件密码。注：上传需要账号登录认证。
          </p>
          <div class="form-group">
            <label>待上传文件：</label>
            <div style="display:flex; gap:8px;">
              <input type="text" id="chosen-file-path" class="form-control" placeholder="请选择本地文件..." readonly>
              <button class="btn" onclick="chooseLocalFile()">浏览文件</button>
            </div>
          </div>
          <button class="btn btn-primary" onclick="handleUploadFile()">开始分片上传并生成提取码</button>
          <div id="upload-result-box" style="margin-top: 14px; display:none;"></div>
        </div>

        <div class="card" style="padding: 18px;">
          <h3 style="font-size: 14px; margin-bottom: 8px;">📤 凭码提取 (文件下载)</h3>
          <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 14px; line-height: 1.5;">
            输入发送方提供的 6 位数字取件密码，验证有效后可将文件直接下载保存到本地磁盘。
          </p>
          <div class="form-group">
            <label>6 位取件密码：</label>
            <input type="text" id="retrieve-code-input" class="form-control" placeholder="例如：789123" maxlength="6">
          </div>
          <button class="btn btn-primary" onclick="handleRetrieveFile()">验证并提取文件</button>
          <div id="retrieve-result-box" style="margin-top: 14px; display:none;"></div>
        </div>
      </div>
    </div>

    <!-- 9. 网络与会话状态 (Settings) -->
    <div id="tab-settings" class="tab-pane">
      <div class="card" style="padding: 18px;">
        <h3 style="font-size: 14.5px; margin-bottom: 12px;">校园网环境与节点状态</h3>
        <p style="font-size: 13px; color: #334155; line-height: 2;">
          • 核心网关节点：<strong>10.181.200.3</strong><br>
          • 校园连通性：<span id="settings-net-text">正在检测...</span><br>
          • 客户端模式：<strong>真实内网接口对齐模式 (去伪真机环境)</strong><br>
          • 登录认证状态：<span id="settings-auth-text">未配置会话</span>
        </p>
        <div style="margin-top: 16px; display:flex; gap:10px;">
          <button class="btn btn-primary" onclick="checkNetwork(true)">重新检测校园内网连接</button>
          <button class="btn" onclick="openAuthModal()">账号登录 / 导入 Cookie</button>
          <button class="btn btn-danger" onclick="handleLogout()">清除登录会话</button>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- 详情模态弹窗 -->
<div id="modal-overlay" class="modal-overlay" onclick="closeModal(event)">
  <div class="modal-card">
    <div class="modal-header">
      <h3 id="modal-title">详情查看</h3>
      <button class="modal-close" onclick="closeModal()">&times;</button>
    </div>
    <div class="modal-body" id="modal-content"></div>
    <div class="modal-footer" id="modal-footer">
      <button class="btn" onclick="closeModal()">关闭</button>
    </div>
  </div>
</div>

<!-- 登录/会话认证模态弹窗 -->
<div id="auth-modal-overlay" class="modal-overlay" onclick="closeAuthModal(event)">
  <div class="modal-card" style="width: 460px;">
    <div class="modal-header">
      <h3>春晖校园网登录认证</h3>
      <button class="modal-close" onclick="closeAuthModal()">&times;</button>
    </div>
    <div class="modal-body">
      <div class="auth-tabs">
        <div class="auth-tab-btn active" id="auth-tab-btn-acc" onclick="switchAuthTab('acc')">账号密码登录</div>
        <div class="auth-tab-btn" id="auth-tab-btn-cookie" onclick="switchAuthTab('cookie')">导入浏览器 Cookie</div>
      </div>

      <!-- 账号密码表单 -->
      <div id="auth-tab-acc">
        <div class="form-group">
          <label>学号 / 用户名：</label>
          <input type="text" id="login-username" class="form-control" placeholder="请输入学号或用户名">
        </div>
        <div class="form-group">
          <label>登录密码：</label>
          <input type="password" id="login-password" class="form-control" placeholder="请输入密码">
        </div>
        <div class="form-group">
          <label>图形验证码：</label>
          <div class="captcha-container">
            <input type="text" id="login-code" class="form-control" style="width:140px;" placeholder="4位验证码" maxlength="6">
            <div id="captcha-img-box" class="captcha-img" onclick="refreshCaptcha()" title="点击刷新验证码">
              <span>点击加载验证码</span>
            </div>
          </div>
        </div>
        <button class="btn btn-primary" style="width:100%; margin-top:6px;" onclick="submitAccountLogin()">登录</button>
      </div>

      <!-- Cookie 导入表单 -->
      <div id="auth-tab-cookie" style="display:none;">
        <div class="form-group">
          <label>浏览器 Cookie 字符串：</label>
          <textarea id="login-cookie-input" class="form-control" style="height: 100px; resize:none; font-family:monospace; font-size:11px;" placeholder="粘贴形如: sessionid=xxx; csrftoken=yyy"></textarea>
        </div>
        <p style="font-size:11px; color:var(--text-muted); margin-bottom:12px; line-height:1.5;">
          提示：可在校园网内网登录后的浏览器 F12 开发者工具 Network 面板请求头中复制 Cookie。
        </p>
        <button class="btn btn-primary" style="width:100%;" onclick="submitCookieLogin()">导入并保存会话</button>
      </div>

      <div id="auth-msg-box" style="margin-top:12px; display:none; padding:8px 12px; border-radius:6px; font-size:12px;"></div>
    </div>
  </div>
</div>

<script>
const tabTitles = {
  'inbox': '个人信件 (收件箱)',
  'news': '校园通知与公告',
  'schedule': '班级课表查询系统',
  'hygiene': '常规纪律卫生考评',
  'dorm': '寝室纪律内务',
  'duty': '行政值周安排',
  'lostfound': '全校失物招领',
  'filestation': '校内文件寄取处',
  'settings': '网络与会话状态'
};

let currentTab = 'inbox';
let currentStatus = { is_online: false, has_session: false };
let currentInboxPage = 1;
let currentNewsPage = 1;
let currentHygienePage = 1;
let currentLostfoundPage = 1;
let chosenFilePath = '';

function switchTab(tabId) {
  currentTab = tabId;
  document.querySelectorAll('.tab-pane').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  
  const target = document.getElementById('tab-' + tabId);
  if (target) target.classList.add('active');
  const navItem = document.querySelector(`.nav-item[data-tab="${tabId}"]`);
  if (navItem) navItem.classList.add('active');

  document.getElementById('current-title').innerText = tabTitles[tabId] || '春晖中学校园网';
  loadTabData(tabId);
}

function filterTable(tableId, query) {
  const q = (query || '').trim().toLowerCase();
  const rows = document.querySelectorAll('#' + tableId + ' tbody tr');
  rows.forEach(row => {
    row.style.display = row.innerText.toLowerCase().includes(q) ? '' : 'none';
  });
}

function renderErrorCard(containerId, errorMsg, retryFn) {
  const container = document.getElementById(containerId);
  if (!container) return;
  const isOff = !currentStatus.is_online || (errorMsg && errorMsg.includes('未连接'));
  container.innerHTML = `
    <div class="empty-state">
      <div class="empty-icon">${isOff ? '🔌' : '⚠️'}</div>
      <div class="empty-title">${isOff ? '未连接到校园内网 (10.181.200.3)' : '数据加载失败'}</div>
      <div class="empty-desc">${errorMsg || '请求校园网内网服务器超时或服务未开启。请确认已连入学校 Wi-Fi 或校内网络。'}</div>
      ${retryFn ? `<button class="btn btn-primary" onclick="${retryFn}">🔄 重新尝试</button>` : ''}
    </div>
  `;
}

function renderEmptyState(containerId, tip) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = `
    <div class="empty-state">
      <div class="empty-icon">📭</div>
      <div class="empty-title">暂无数据记录</div>
      <div class="empty-desc">${tip || '该分类或时间段内暂无任何数据记录。'}</div>
    </div>
  `;
}

function openModal(title, htmlContent, footerHtml) {
  document.getElementById('modal-title').innerText = title;
  document.getElementById('modal-content').innerHTML = htmlContent;
  const footer = document.getElementById('modal-footer');
  if (footerHtml) {
    footer.innerHTML = footerHtml + '<button class="btn" onclick="closeModal()">关闭</button>';
  } else {
    footer.innerHTML = '<button class="btn" onclick="closeModal()">关闭</button>';
  }
  document.getElementById('modal-overlay').style.display = 'flex';
}

function closeModal(e) {
  if (!e || e.target === document.getElementById('modal-overlay') || e.target.classList.contains('modal-close') || e.target.innerText === '关闭') {
    document.getElementById('modal-overlay').style.display = 'none';
  }
}

// ----- 网络与登录状态 -----

async function checkNetwork(force) {
  try {
    const data = await window.pywebview.api.get_status(force);
    currentStatus = data;
    const badge = document.getElementById('network-badge');
    const text = document.getElementById('network-text');
    const sessBadge = document.getElementById('session-badge');
    const authBtn = document.getElementById('auth-btn');
    const setNet = document.getElementById('settings-net-text');
    const setAuth = document.getElementById('settings-auth-text');

    if (data.is_online) {
      badge.className = 'status-pill online';
      text.innerText = '校园内网已连接 (在线)';
      setNet.innerHTML = '<strong style="color:var(--success);">● 已成功建立通信 (10.181.200.3)</strong>';
    } else {
      badge.className = 'status-pill offline';
      text.innerText = '未连接校园内网 (10.181.200.3)';
      setNet.innerHTML = '<span style="color:var(--danger);">○ 无法连接至校园内网服务器 (10.181.200.3)</span>';
    }

    if (data.has_session) {
      sessBadge.className = 'session-pill logged';
      sessBadge.innerText = '● 已登录 (' + data.sessionid_preview + ')';
      authBtn.innerText = '切换账号';
      setAuth.innerHTML = '<strong style="color:var(--success);">● 已配置有效会话凭据</strong>';
    } else {
      sessBadge.className = 'session-pill guest';
      sessBadge.innerText = '⚪ 未登录';
      authBtn.innerText = '登录账号';
      setAuth.innerHTML = '<span style="color:var(--text-muted);">○ 本地未配置会话信息</span>';
    }
  } catch (err) {
    console.error(err);
  }
}

function openAuthModal() {
  document.getElementById('auth-modal-overlay').style.display = 'flex';
  document.getElementById('auth-msg-box').style.display = 'none';
  refreshCaptcha();
}

function closeAuthModal(e) {
  if (!e || e.target === document.getElementById('auth-modal-overlay') || e.target.classList.contains('modal-close')) {
    document.getElementById('auth-modal-overlay').style.display = 'none';
  }
}

function switchAuthTab(type) {
  const btnAcc = document.getElementById('auth-tab-btn-acc');
  const btnCookie = document.getElementById('auth-tab-btn-cookie');
  const tabAcc = document.getElementById('auth-tab-acc');
  const tabCookie = document.getElementById('auth-tab-cookie');
  document.getElementById('auth-msg-box').style.display = 'none';

  if (type === 'acc') {
    btnAcc.classList.add('active');
    btnCookie.classList.remove('active');
    tabAcc.style.display = 'block';
    tabCookie.style.display = 'none';
    refreshCaptcha();
  } else {
    btnAcc.classList.remove('active');
    btnCookie.classList.add('active');
    tabAcc.style.display = 'none';
    tabCookie.style.display = 'block';
  }
}

async function refreshCaptcha() {
  const box = document.getElementById('captcha-img-box');
  box.innerHTML = '<span>加载中...</span>';
  try {
    const res = await window.pywebview.api.get_captcha();
    if (res.success && res.image) {
      box.innerHTML = `<img src="${res.image}" style="height:32px; border-radius:3px;">`;
    } else {
      box.innerHTML = '<span style="color:var(--danger);font-size:10px;">获取失败(离线)</span>';
    }
  } catch (e) {
    box.innerHTML = '<span style="color:var(--danger);font-size:10px;">网络异常</span>';
  }
}

async function submitAccountLogin() {
  const u = document.getElementById('login-username').value.trim();
  const p = document.getElementById('login-password').value.trim();
  const c = document.getElementById('login-code').value.trim();
  const msg = document.getElementById('auth-msg-box');
  msg.style.display = 'block';
  msg.style.background = '#eff6ff';
  msg.style.color = '#1d4ed8';
  msg.innerText = '正在向校园网服务器验证登录...';

  try {
    const res = await window.pywebview.api.login_account(u, p, c);
    if (res.success) {
      msg.style.background = '#f0fdf4';
      msg.style.color = '#15803d';
      msg.innerText = '✅ 登录成功！';
      setTimeout(() => {
        closeAuthModal();
        checkNetwork(true);
        loadTabData(currentTab);
      }, 700);
    } else {
      msg.style.background = '#fef2f2';
      msg.style.color = '#b91c1c';
      msg.innerText = '❌ ' + (res.error || '登录失败');
      refreshCaptcha();
    }
  } catch (e) {
    msg.style.background = '#fef2f2';
    msg.style.color = '#b91c1c';
    msg.innerText = '❌ 请求异常: ' + e;
  }
}

async function submitCookieLogin() {
  const c = document.getElementById('login-cookie-input').value.trim();
  const msg = document.getElementById('auth-msg-box');
  msg.style.display = 'block';
  msg.style.background = '#eff6ff';
  msg.style.color = '#1d4ed8';
  msg.innerText = '正在验证 Cookie...';

  try {
    const res = await window.pywebview.api.login_cookie(c);
    if (res.success) {
      msg.style.background = '#f0fdf4';
      msg.style.color = '#15803d';
      msg.innerText = '✅ ' + (res.message || 'Cookie 导入成功');
      setTimeout(() => {
        closeAuthModal();
        checkNetwork(true);
        loadTabData(currentTab);
      }, 700);
    } else {
      msg.style.background = '#fef2f2';
      msg.style.color = '#b91c1c';
      msg.innerText = '❌ ' + (res.error || '验证失败');
    }
  } catch (e) {
    msg.style.background = '#fef2f2';
    msg.style.color = '#b91c1c';
    msg.innerText = '❌ 异常: ' + e;
  }
}

async function handleLogout() {
  if (confirm('确认退出当前登录并清除本地保存的会话？')) {
    await window.pywebview.api.logout();
    checkNetwork(true);
  }
}

// ----- 数据加载调度 -----

function loadTabData(tabId) {
  if (tabId === 'inbox') loadInbox(currentInboxPage);
  else if (tabId === 'news') loadNews(document.getElementById('news-column-select').value, currentNewsPage);
  else if (tabId === 'schedule') initScheduleTab();
  else if (tabId === 'hygiene') loadHygiene(currentHygienePage);
  else if (tabId === 'dorm') queryDormHygiene();
  else if (tabId === 'duty') loadDuty();
  else if (tabId === 'lostfound') loadLostfound(currentLostfoundPage);
  else if (tabId === 'settings') checkNetwork(false);
}

// ----- 1. 收件箱 -----

async function loadInbox(page) {
  currentInboxPage = page;
  document.getElementById('inbox-page-num').innerText = page;
  const tbody = document.getElementById('inbox-rows');
  tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-muted);padding:24px;">正在加载收件箱...</td></tr>';

  try {
    const res = await window.pywebview.api.get_messages(page);
    if (!res.success) {
      renderErrorCard('inbox-card', res.error, `loadInbox(${page})`);
      return;
    }
    const list = res.data || [];
    if (list.length === 0) {
      renderEmptyState('inbox-card', '当前收件箱没有信件记录');
      return;
    }
    document.getElementById('inbox-card').innerHTML = `
      <table class="data-table" id="inbox-table">
        <thead>
          <tr>
            <th style="width: 80px;">编号</th>
            <th>标题</th>
            <th style="width: 130px;">发件人</th>
            <th style="width: 150px;">发送时间</th>
            <th style="width: 85px;">状态</th>
          </tr>
        </thead>
        <tbody id="inbox-rows"></tbody>
      </table>
    `;
    const tb = document.getElementById('inbox-rows');
    list.forEach(item => {
      const tr = document.createElement('tr');
      tr.onclick = () => showMessageDetail(item.id);
      tr.innerHTML = `
        <td><span class="tag tag-gray">${item.id}</span></td>
        <td><strong>${item.title}</strong></td>
        <td>${item.sender}</td>
        <td style="color:#64748b;">${item.time}</td>
        <td>${item.unread ? '<span class="tag tag-red">未阅</span>' : '<span class="tag tag-green">已阅</span>'}</td>
      `;
      tb.appendChild(tr);
    });
  } catch (e) {
    renderErrorCard('inbox-card', e.toString(), `loadInbox(${page})`);
  }
}

async function showMessageDetail(msgId) {
  openModal('信件详情', '正在获取详情数据...');
  try {
    const res = await window.pywebview.api.get_message_detail(msgId);
    if (!res.success) {
      document.getElementById('modal-content').innerHTML = `<div style="color:var(--danger);">⚠️ ${res.error}</div>`;
      return;
    }
    const d = res.data;
    let attHtml = '';
    if (d.attachments && d.attachments.length > 0) {
      attHtml = `<div style="margin-top:14px; padding-top:12px; border-top:1px solid var(--border);">
        <strong style="color:var(--primary);">📎 关联附件列表：</strong>
        <div style="margin-top:6px;">
          ${d.attachments.map(a => `<div style="margin:4px 0;"><a href="javascript:void(0)" onclick="downloadRemoteFile('${a.url}', '${a.name}')" style="color:var(--primary); text-decoration:underline;">${a.name}</a></div>`).join('')}
        </div>
      </div>`;
    }
    document.getElementById('modal-content').innerHTML = `
      <div style="font-size:16px; font-weight:bold; margin-bottom:8px; color:#0f172a;">${d.title}</div>
      <div style="font-size:12px; color:var(--text-muted); margin-bottom:14px; border-bottom:1px solid var(--border); padding-bottom:8px;">
        发件人：<strong>${d.sender}</strong> &nbsp;|&nbsp; 发送时间：${d.time}
      </div>
      <div style="line-height:1.7; font-size:13px; white-space:pre-wrap;">${d.content || '（信件无正文文字）'}</div>
      <div style="margin-top:16px; font-size:12px; color:var(--text-muted); line-height:1.6; background:#f8fafc; padding:10px; border-radius:6px;">
        <div><strong>全体收件人：</strong>${d.recipients_all}</div>
        <div style="margin-top:4px;"><strong>未阅收件人：</strong><span style="color:var(--danger);">${d.recipients_unread}</span></div>
      </div>
      ${attHtml}
    `;
  } catch (e) {
    document.getElementById('modal-content').innerHTML = `<div style="color:var(--danger);">⚠️ 获取失败: ${e}</div>`;
  }
}

function prevInboxPage() { if (currentInboxPage > 1) loadInbox(currentInboxPage - 1); }
function nextInboxPage() { loadInbox(currentInboxPage + 1); }

// ----- 2. 校园资讯与公告 (News) -----

async function loadNews(column, page) {
  currentNewsPage = page;
  document.getElementById('news-page-num').innerText = page;
  const card = document.getElementById('news-card');
  card.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:24px;">正在加载公告资讯...</div>';

  try {
    const res = await window.pywebview.api.get_news(column, page);
    if (!res.success) {
      renderErrorCard('news-card', res.error, `loadNews('${column}', ${page})`);
      return;
    }
    const list = res.data || [];
    if (list.length === 0) {
      renderEmptyState('news-card', '该栏目暂无公告记录');
      return;
    }
    card.innerHTML = `
      <table class="data-table" id="news-table">
        <thead>
          <tr>
            <th style="width: 85px;">文章ID</th>
            <th>文章标题</th>
            <th style="width: 140px;">发布日期</th>
          </tr>
        </thead>
        <tbody id="news-rows"></tbody>
      </table>
    `;
    const tb = document.getElementById('news-rows');
    list.forEach(item => {
      const tr = document.createElement('tr');
      tr.onclick = () => showNewsDetail(item.id);
      tr.innerHTML = `
        <td><span class="tag tag-gray">${item.id}</span></td>
        <td><strong>${item.title}</strong></td>
        <td style="color:#64748b;">${item.date}</td>
      `;
      tb.appendChild(tr);
    });
  } catch (e) {
    renderErrorCard('news-card', e.toString(), `loadNews('${column}', ${page})`);
  }
}

async function showNewsDetail(artId) {
  openModal('文章详情', '正在获取内容...');
  try {
    const res = await window.pywebview.api.get_news_detail(artId);
    if (!res.success) {
      document.getElementById('modal-content').innerHTML = `<div style="color:var(--danger);">⚠️ ${res.error}</div>`;
      return;
    }
    const d = res.data;
    let attHtml = '';
    if (d.attachments && d.attachments.length > 0) {
      attHtml = `<div style="margin-top:14px; padding-top:12px; border-top:1px solid var(--border);">
        <strong style="color:var(--primary);">📎 附件下载：</strong>
        <div style="margin-top:6px;">
          ${d.attachments.map(a => `<div style="margin:4px 0;"><a href="javascript:void(0)" onclick="downloadRemoteFile('${a.url}', '${a.name}')" style="color:var(--primary); text-decoration:underline;">${a.name}</a></div>`).join('')}
        </div>
      </div>`;
    }
    document.getElementById('modal-content').innerHTML = `
      <div style="font-size:16px; font-weight:bold; margin-bottom:8px; color:#0f172a;">${d.title}</div>
      <div style="font-size:12px; color:var(--text-muted); margin-bottom:14px; border-bottom:1px solid var(--border); padding-bottom:8px;">
        来源：${d.source} &nbsp;|&nbsp; 发布时间：${d.time}
      </div>
      <div style="line-height:1.8; font-size:13px; white-space:pre-wrap;">${d.content || '（暂无详细正文内容）'}</div>
      ${attHtml}
    `;
  } catch (e) {
    document.getElementById('modal-content').innerHTML = `<div style="color:var(--danger);">⚠️ 获取失败: ${e}</div>`;
  }
}

function prevNewsPage() { if (currentNewsPage > 1) loadNews(document.getElementById('news-column-select').value, currentNewsPage - 1); }
function nextNewsPage() { loadNews(document.getElementById('news-column-select').value, currentNewsPage + 1); }

// ----- 3. 班级课表查询 (Schedule) -----

let scheduleInitialized = false;
async function initScheduleTab() {
  if (scheduleInitialized) return;
  scheduleInitialized = true;
  await handleSchedGradeChange('1');
}

async function handleSchedGradeChange(gradeId) {
  const sel = document.getElementById('sched-class-select');
  sel.innerHTML = '<option value="">正在获取班级...</option>';
  try {
    const res = await window.pywebview.api.get_classes(gradeId);
    if (res.success && res.data && res.data.length > 0) {
      sel.innerHTML = res.data.map(c => `<option value="${c.CHClassID}">${c.CHClassName}</option>`).join('');
      querySchedule();
    } else {
      sel.innerHTML = '<option value="">未连接校园内网</option>';
      renderErrorCard('schedule-container', res.error || '获取班级列表失败', `handleSchedGradeChange('${gradeId}')`);
    }
  } catch (e) {
    sel.innerHTML = '<option value="">未连接校园内网</option>';
    renderErrorCard('schedule-container', e.toString(), `handleSchedGradeChange('${gradeId}')`);
  }
}

async function querySchedule() {
  const g = document.getElementById('sched-grade-select').value;
  const c = document.getElementById('sched-class-select').value;
  const box = document.getElementById('schedule-container');
  if (!c) {
    box.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-muted);">请选择有效班级</div>';
    return;
  }
  box.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-muted);">正在查询班级课表矩阵...</div>';
  try {
    const res = await window.pywebview.api.get_schedule(g, c);
    if (!res.success) {
      renderErrorCard('schedule-container', res.error, 'querySchedule()');
      return;
    }
    const d = res.data;
    const matrix = d.matrix || [];
    if (matrix.length === 0) {
      renderEmptyState('schedule-container', '该班级未编排课表');
      return;
    }

    let tblHtml = '<table class="sched-table"><thead><tr>';
    matrix[0].forEach(h => {
      tblHtml += `<th>${(h || '').replace('★', '')}</th>`;
    });
    tblHtml += '</tr></thead><tbody>';
    for (let r = 1; r < matrix.length; r++) {
      tblHtml += '<tr>';
      matrix[r].forEach((cell, ci) => {
        let text = (cell || '').toString().trim().replace('★', '');
        let isSub = ci > 0 && text !== '' && text !== '-';
        tblHtml += `<td class="${isSub ? 'sched-subject' : ''}">${text || '-'}</td>`;
      });
      tblHtml += '</tr>';
    }
    tblHtml += '</tbody></table>';

    let teachersHtml = '';
    if (d.teachers && d.teachers.length > 0) {
      teachersHtml = `<div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(180px, 1fr)); gap:8px; margin-top:10px;">
        ${d.teachers.map(t => `<div style="background:#f8fafc; border:1px solid var(--border); padding:6px 10px; border-radius:5px; font-size:12px;">👨‍🏫 ${t}</div>`).join('')}
      </div>`;
    }

    box.innerHTML = `
      <div class="card" style="padding:14px; margin-bottom:12px;">
        <div style="font-size:13px; font-weight:bold; margin-bottom:6px; color:#1e293b;">
          班级管理：班主任 <span style="color:var(--success);">${d.main_manager}</span> &nbsp;|&nbsp; 副班主任 <span style="color:var(--success);">${d.sub_manager}</span>
        </div>
        ${teachersHtml}
      </div>
      <div class="card" style="overflow-x:auto;">${tblHtml}</div>
    `;
  } catch (e) {
    renderErrorCard('schedule-container', e.toString(), 'querySchedule()');
  }
}

// ----- 4. 卫生考评 (Hygiene) -----

async function loadHygiene(page) {
  currentHygienePage = page;
  document.getElementById('hygiene-page-num').innerText = page;
  const card = document.getElementById('hygiene-card');
  card.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:24px;">正在查询考评记录...</div>';
  try {
    const res = await window.pywebview.api.get_hygiene(page);
    if (!res.success) {
      renderErrorCard('hygiene-card', res.error, `loadHygiene(${page})`);
      return;
    }
    const list = res.data || [];
    if (list.length === 0) {
      renderEmptyState('hygiene-card', '当前暂无违纪卫生通报');
      return;
    }
    card.innerHTML = `
      <table class="data-table" id="hygiene-table">
        <thead>
          <tr>
            <th style="width: 80px;">编号</th>
            <th style="width: 180px;">违纪地点</th>
            <th>考评记录说明</th>
            <th style="width: 140px;">检查时间</th>
          </tr>
        </thead>
        <tbody id="hygiene-rows"></tbody>
      </table>
    `;
    const tb = document.getElementById('hygiene-rows');
    list.forEach(item => {
      const tr = document.createElement('tr');
      tr.onclick = () => showHygieneDetail(item.id);
      tr.innerHTML = `
        <td><span class="tag tag-gray">${item.id}</span></td>
        <td><strong>${item.location}</strong></td>
        <td>${item.desc}</td>
        <td style="color:#64748b;">${item.date}</td>
      `;
      tb.appendChild(tr);
    });
  } catch (e) {
    renderErrorCard('hygiene-card', e.toString(), `loadHygiene(${page})`);
  }
}

async function showHygieneDetail(recId) {
  openModal('卫生考评详情', '正在拉取多媒体现场记录...');
  try {
    const res = await window.pywebview.api.get_hygiene_detail(recId);
    if (!res.success) {
      document.getElementById('modal-content').innerHTML = `<div style="color:var(--danger);">⚠️ ${res.error}</div>`;
      return;
    }
    const d = res.data;
    let mediaHtml = '';
    if (d.media_urls && d.media_urls.length > 0) {
      mediaHtml = `<div style="margin-top:14px; border-top:1px solid var(--border); padding-top:12px;">
        <strong style="color:var(--primary);">📸 现场影像资料 (${d.media_urls.length} 项)：</strong>
        <div style="display:flex; flex-wrap:wrap; gap:10px; margin-top:8px;">
          ${d.media_urls.map(m => {
            if (m.type === 'image') {
              return `<a href="javascript:void(0)" onclick="downloadRemoteFile('${m.url}', 'hygiene_${d.id}.jpg')"><img src="${m.url}" style="max-height:120px; border-radius:4px; border:1px solid var(--border);" title="点击保存"></a>`;
            } else {
              return `<video src="${m.url}" controls style="max-height:140px; border-radius:4px;"></video>`;
            }
          }).join('')}
        </div>
      </div>`;
    }
    document.getElementById('modal-content').innerHTML = `
      <div style="font-size:14.5px; font-weight:bold; margin-bottom:8px; color:#b91c1c;">⚠️ 纪律卫生通报 [ID: ${d.id}]</div>
      <div style="line-height:1.7; font-size:13px; background:#fef2f2; border:1px solid #fee2e2; padding:12px; border-radius:6px; margin-bottom:12px;">
        ${d.desc}
      </div>
      <div style="font-size:12px; color:var(--text-muted); line-height:1.6; background:#f8fafc; padding:10px; border-radius:6px;">
        <div><strong>通报人员：</strong>${d.recipients_all}</div>
        <div style="margin-top:4px;"><strong>未阅人员：</strong><span style="color:var(--danger);">${d.recipients_unread}</span></div>
      </div>
      ${mediaHtml}
    `;
  } catch (e) {
    document.getElementById('modal-content').innerHTML = `<div style="color:var(--danger);">⚠️ 获取失败: ${e}</div>`;
  }
}

function prevHygienePage() { if (currentHygienePage > 1) loadHygiene(currentHygienePage - 1); }
function nextHygienePage() { loadHygiene(currentHygienePage + 1); }

// ----- 5. 寝室考评 (Dorm) -----

async function queryDormHygiene() {
  const d = document.getElementById('dorm-select').value;
  const s = document.getElementById('dorm-start-date').value;
  const e = document.getElementById('dorm-end-date').value;
  const all = document.getElementById('dorm-show-all').checked;
  const card = document.getElementById('dorm-card');
  card.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:24px;">正在查询楼宇考评表...</div>';

  try {
    const res = await window.pywebview.api.get_bedroom_hygiene(d, s, e, all);
    if (!res.success) {
      renderErrorCard('dorm-card', res.error, 'queryDormHygiene()');
      return;
    }
    const list = res.data || [];
    if (list.length === 0) {
      renderEmptyState('dorm-card', '该楼宇在选定时间段内无扣分记录');
      return;
    }
    card.innerHTML = `
      <table class="data-table" id="dorm-table">
        <thead>
          <tr>
            <th style="width: 140px;">寝室房号</th>
            <th style="width: 160px;">所属班级</th>
            <th style="width: 110px;">卫生扣分</th>
            <th style="width: 110px;">纪律扣分</th>
            <th style="width: 110px;">合计扣分</th>
          </tr>
        </thead>
        <tbody id="dorm-rows"></tbody>
      </table>
    `;
    const tb = document.getElementById('dorm-rows');
    list.forEach(item => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><strong>${item.room}</strong></td>
        <td>${item.class}</td>
        <td><span class="tag tag-red">${item.hygiene}</span></td>
        <td><span class="tag tag-red">${item.discipline}</span></td>
        <td><strong style="color:var(--danger);">${item.total}</strong></td>
      `;
      tb.appendChild(tr);
    });
  } catch (err) {
    renderErrorCard('dorm-card', err.toString(), 'queryDormHygiene()');
  }
}

function openClassRoomQueryModal() {
  const html = `
    <div style="display:flex; gap:8px; margin-bottom:12px;">
      <select id="modal-cr-grade" class="form-control" style="width:120px;">
        <option value="1">高一年级</option>
        <option value="2">高二年级</option>
        <option value="3">高三年级</option>
      </select>
      <input type="text" id="modal-cr-class" class="form-control" placeholder="班级名称或数字 (如: 1 或 1班)">
      <button class="btn btn-primary" onclick="submitClassRoomQuery()">查询</button>
    </div>
    <div id="modal-cr-result" style="padding:14px; background:#f8fafc; border-radius:6px; min-height:60px; font-size:13px;">请输入年级和班级后查询</div>
  `;
  openModal('查询班级寝室分配', html);
}

async function submitClassRoomQuery() {
  const g = document.getElementById('modal-cr-grade').value;
  const c = document.getElementById('modal-cr-class').value.trim();
  const box = document.getElementById('modal-cr-result');
  if (!c) {
    box.innerHTML = '<span style="color:var(--danger);">请输入班级名称</span>';
    return;
  }
  box.innerHTML = '正在查询...';
  try {
    const res = await window.pywebview.api.get_bedroom_class(g, c);
    if (res.success) {
      box.innerHTML = `<div><strong>${res.class_name}</strong> 寝室分配：</div><div style="margin-top:6px; color:#0369a1; line-height:1.6;">${res.info}</div>`;
    } else {
      box.innerHTML = `<span style="color:var(--danger);">⚠️ ${res.error}</span>`;
    }
  } catch (e) {
    box.innerHTML = `<span style="color:var(--danger);">⚠️ 异常: ${e}</span>`;
  }
}

// ----- 6. 行政值周安排 (Duty) -----

async function loadDuty() {
  const card = document.getElementById('duty-card');
  card.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:24px;">正在加载行政值周排班表...</div>';
  try {
    const res = await window.pywebview.api.get_duty();
    if (!res.success) {
      renderErrorCard('duty-card', res.error, 'loadDuty()');
      return;
    }
    const list = res.data || [];
    if (list.length === 0) {
      renderEmptyState('duty-card', '暂无值周安排表');
      return;
    }
    card.innerHTML = `
      <table class="data-table" id="duty-table">
        <thead>
          <tr>
            <th style="width: 95px;">周次</th>
            <th style="width: 140px;">日期范围</th>
            <th style="width: 110px;">行政值周</th>
            <th>值周小组</th>
            <th style="width: 120px;">值周班级</th>
            <th style="width: 130px;">旗下讲话</th>
          </tr>
        </thead>
        <tbody id="duty-rows"></tbody>
      </table>
    `;
    const tb = document.getElementById('duty-rows');
    list.forEach(item => {
      const tr = document.createElement('tr');
      if (item.is_current) {
        tr.style.backgroundColor = '#ecfdf5';
      }
      tr.innerHTML = `
        <td><strong>${item.week}</strong> ${item.is_current ? '<span class="tag tag-green">本周</span>' : ''}</td>
        <td style="color:#64748b;">${item.date}</td>
        <td><strong style="color:#1e40af;">${item.admin}</strong></td>
        <td style="font-size:12px; line-height:1.5;">${item.group1 ? '组一: ' + item.group1 : ''} ${item.group2 ? '<br>组二: ' + item.group2 : ''} ${item.group3 ? '<br>组三: ' + item.group3 : ''}</td>
        <td>${item.duty_class}</td>
        <td>${item.talk}</td>
      `;
      tb.appendChild(tr);
    });
  } catch (e) {
    renderErrorCard('duty-card', e.toString(), 'loadDuty()');
  }
}

// ----- 7. 全校失物招领 (Lost & Found) -----

async function loadLostfound(page) {
  currentLostfoundPage = page;
  document.getElementById('lf-page-num').innerText = page;
  const card = document.getElementById('lostfound-card');
  card.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:24px;">正在加载失物招领...</div>';
  try {
    const res = await window.pywebview.api.get_lostfound(page);
    if (!res.success) {
      renderErrorCard('lostfound-card', res.error, `loadLostfound(${page})`);
      return;
    }
    const list = res.data || [];
    if (list.length === 0) {
      renderEmptyState('lostfound-card', '当前暂无失物招领登记记录');
      return;
    }
    card.innerHTML = `
      <table class="data-table" id="lostfound-table">
        <thead>
          <tr>
            <th style="width: 80px;">编号</th>
            <th style="width: 100px;">类别</th>
            <th>物品名称</th>
            <th style="width: 140px;">发布处</th>
            <th style="width: 130px;">登记日期</th>
            <th style="width: 90px;">状态</th>
          </tr>
        </thead>
        <tbody id="lostfound-rows"></tbody>
      </table>
    `;
    const tb = document.getElementById('lostfound-rows');
    list.forEach(item => {
      const tr = document.createElement('tr');
      tr.onclick = () => showLostfoundDetail(item.id);
      const isPending = item.status.includes('未') || item.status.includes('处理');
      tr.innerHTML = `
        <td><span class="tag tag-gray">${item.id}</span></td>
        <td><span class="tag ${item.category.includes('丢') ? 'tag-red' : 'tag-blue'}">${item.category}</span></td>
        <td><strong>${item.title}</strong></td>
        <td>${item.reporter}</td>
        <td style="color:#64748b;">${item.date}</td>
        <td><span class="tag ${isPending ? 'tag-red' : 'tag-green'}">${item.status}</span></td>
      `;
      tb.appendChild(tr);
    });
  } catch (e) {
    renderErrorCard('lostfound-card', e.toString(), `loadLostfound(${page})`);
  }
}

async function showLostfoundDetail(itemId) {
  openModal('失物招领详情', '正在拉取招领详情...');
  try {
    const res = await window.pywebview.api.get_lostfound_detail(itemId);
    if (!res.success) {
      document.getElementById('modal-content').innerHTML = `<div style="color:var(--danger);">⚠️ ${res.error}</div>`;
      return;
    }
    const d = res.data;
    document.getElementById('modal-content').innerHTML = `
      <div style="font-size:16px; font-weight:bold; margin-bottom:8px; color:#0f172a;">${d.title}</div>
      <div style="font-size:12px; color:var(--text-muted); margin-bottom:14px; border-bottom:1px solid var(--border); padding-bottom:8px;">
        发布部门：${d.reporter} &nbsp;|&nbsp; 审核人：${d.reviewer} &nbsp;|&nbsp; 时间：${d.time}
      </div>
      <div style="line-height:1.7; font-size:13px; white-space:pre-wrap;">${d.content || '（暂无详细补充说明）'}</div>
    `;
  } catch (e) {
    document.getElementById('modal-content').innerHTML = `<div style="color:var(--danger);">⚠️ 获取失败: ${e}</div>`;
  }
}

function prevLostfoundPage() { if (currentLostfoundPage > 1) loadLostfound(currentLostfoundPage - 1); }
function nextLostfoundPage() { loadLostfound(currentLostfoundPage + 1); }

// ----- 8. 文件寄取 (File Station) -----

async function chooseLocalFile() {
  try {
    const res = await window.pywebview.api.choose_file();
    if (res.success) {
      chosenFilePath = res.path;
      document.getElementById('chosen-file-path').value = `${res.name} (${(res.size / 1024 / 1024).toFixed(2)} MB)`;
    }
  } catch (e) {
    console.error(e);
  }
}

async function handleUploadFile() {
  const box = document.getElementById('upload-result-box');
  if (!chosenFilePath) {
    alert('请先选择要上传的本地文件');
    return;
  }
  box.style.display = 'block';
  box.innerHTML = '<div style="color:#0369a1; padding:10px; background:#e0f2fe; border-radius:6px;">正在执行 100MB 逻辑分片上传，请勿关闭窗口...</div>';
  try {
    const res = await window.pywebview.api.upload_file(chosenFilePath);
    if (res.success) {
      box.innerHTML = `
        <div style="background:#f0fdf4; border:1px solid #bbf7d0; padding:14px; border-radius:6px; color:#15803d;">
          <div style="font-weight:bold; font-size:14px; margin-bottom:6px;">✅ 文件上传并合并成功！</div>
          <div>文件名：<strong>${res.filename}</strong></div>
          <div style="margin-top:8px;">6位提取密码：<strong style="font-size:18px; color:#1d4ed8; letter-spacing:2px;">${res.code}</strong></div>
          <div style="font-size:11px; color:#64748b; margin-top:4px;">接收方可在校内网凭借此码直接提取文件。</div>
        </div>
      `;
    } else {
      box.innerHTML = `<div style="color:var(--danger); padding:10px; background:#fef2f2; border-radius:6px;">⚠️ 上传失败: ${res.error}</div>`;
    }
  } catch (e) {
    box.innerHTML = `<div style="color:var(--danger); padding:10px; background:#fef2f2; border-radius:6px;">⚠️ 异常: ${e}</div>`;
  }
}

async function handleRetrieveFile() {
  const code = document.getElementById('retrieve-code-input').value.trim();
  const box = document.getElementById('retrieve-result-box');
  if (code.length !== 6) {
    alert('请输入 6 位数字取件密码');
    return;
  }
  box.style.display = 'block';
  box.innerHTML = '<div style="color:#0369a1; padding:10px; background:#e0f2fe; border-radius:6px;">正在向服务器查询提取码对应文件...</div>';
  try {
    const res = await window.pywebview.api.retrieve_file(code);
    if (res.success) {
      box.innerHTML = `
        <div style="background:#f0fdf4; border:1px solid #bbf7d0; padding:14px; border-radius:6px; color:#15803d;">
          <div style="font-weight:bold; font-size:14px; margin-bottom:6px;">📦 匹配到取件文件</div>
          <div>文件名：<strong>${res.filename}</strong></div>
          <button class="btn btn-primary" style="margin-top:10px;" onclick="downloadRemoteFile('${res.download_url}', '${res.filename}')">保存文件到本地</button>
        </div>
      `;
    } else {
      box.innerHTML = `<div style="color:var(--danger); padding:10px; background:#fef2f2; border-radius:6px;">⚠️ ${res.error}</div>`;
    }
  } catch (e) {
    box.innerHTML = `<div style="color:var(--danger); padding:10px; background:#fef2f2; border-radius:6px;">⚠️ 异常: ${e}</div>`;
  }
}

async function downloadRemoteFile(url, filename) {
  try {
    const res = await window.pywebview.api.save_download(url, filename);
    if (res.success) {
      alert('✅ 文件已成功保存至：\\n' + res.path);
    } else {
      if (res.error !== '取消保存') {
        alert('⚠️ 下载保存失败: ' + res.error);
      }
    }
  } catch (e) {
    alert('⚠️ 下载异常: ' + e);
  }
}

// ----- 启动初始化 -----

let appStarted = false;
async function initClientApp() {
  if (appStarted) return;
  appStarted = true;
  await checkNetwork(false);
  loadTabData('inbox');
}

function isApiReady() {
  return Boolean(window.pywebview && window.pywebview.api && typeof window.pywebview.api.get_status === 'function');
}

if (isApiReady()) {
  initClientApp();
} else {
  window.addEventListener('pywebviewready', () => {
    let checkCount = 0;
    const t = setInterval(() => {
      checkCount++;
      if (isApiReady() || checkCount > 50) {
        clearInterval(t);
        if (isApiReady()) initClientApp();
      }
    }, 30);
  });
  let pollCount = 0;
  const pollTimer = setInterval(() => {
    pollCount++;
    if (isApiReady()) {
      clearInterval(pollTimer);
      initClientApp();
    } else if (pollCount > 80) {
      clearInterval(pollTimer);
    }
  }, 40);
}
</script>
</body>
</html>
"""

def main():
    if webview is None:
        print("[!] 错误：未检测到 pywebview 桌面视窗依赖。", file=sys.stderr)
        print("    请使用 .venv/bin/python main_gui.py 或执行 pip install pywebview 启动。", file=sys.stderr)
        sys.exit(1)

    print("=" * 60)
    print("  浙江省春晖中学校园网图形界面客户端 (chunhui-gui)")
    print("  正在启动原生桌面应用视窗...")
    print("=" * 60)

    api = ChunhuiApi()
    window = webview.create_window(
        title="浙江省春晖中学校园网客户端",
        html=DESKTOP_HTML,
        js_api=api,
        width=1100,
        height=740,
        min_size=(900, 580)
    )
    webview.start()

if __name__ == "__main__":
    main()
