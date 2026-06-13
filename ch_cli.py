#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import json
import re
import urllib.request
import urllib.parse
import uuid
import time
import argparse
import unicodedata

BASE_URL = "http://10.181.200.3"
SESSION_FILE = os.path.expanduser("~/.ch_cli_session.json")

# Colors
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_RED = "\033[31m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_BLUE = "\033[34m"
C_MAGENTA = "\033[35m"
C_CYAN = "\033[36m"
C_GREY = "\033[90m"

def log_success(msg):
    print(f"{C_GREEN}{C_BOLD}[✓] {msg}{C_RESET}")

def log_info(msg):
    print(f"{C_CYAN}[i] {msg}{C_RESET}")

def log_warn(msg):
    print(f"{C_YELLOW}[!] {msg}{C_RESET}")

def log_error(msg):
    print(f"{C_RED}{C_BOLD}[✗] {msg}{C_RESET}")

def load_session():
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}

def save_session(session):
    try:
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(session, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        log_error(f"保存会话文件失败: {e}")
        return False

def make_request(url_path, method="GET", data=None, headers=None, follow_redirects=False):
    url = f"{BASE_URL}{url_path}" if url_path.startswith("/") else url_path
    try:
        parsed = urllib.parse.urlparse(url)
        encoded_path = urllib.parse.quote(parsed.path)
        url = urllib.parse.urlunparse((
            parsed.scheme,
            parsed.netloc,
            encoded_path,
            parsed.params,
            parsed.query,
            parsed.fragment
        ))
    except Exception:
        pass
    if headers is None:
        headers = {}
    
    headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    cookies = load_session()
    cookie_items = [f"{k}={v}" for k, v in cookies.items() if v]
    if cookie_items:
        headers["Cookie"] = "; ".join(cookie_items)
        
    if method == "POST" and "csrftoken" in cookies:
        headers["X-CSRFToken"] = cookies["csrftoken"]
        headers["Referer"] = f"{BASE_URL}/"
        
    req_data = None
    if data:
        if isinstance(data, dict):
            req_data = urllib.parse.urlencode(data).encode("utf-8")
        else:
            req_data = data
            
    class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
            
    if follow_redirects:
        opener = urllib.request.build_opener()
    else:
        opener = urllib.request.build_opener(NoRedirectHandler)
        
    max_retries = 3
    for attempt in range(max_retries):
        req = urllib.request.Request(url, data=req_data, method=method)
        for k, v in headers.items():
            req.add_header(k, v)
        try:
            with opener.open(req, timeout=10) as resp:
                return resp.status, resp.read(), resp.info()
        except urllib.error.HTTPError as e:
            if e.code in (502, 504) and attempt < max_retries - 1:
                time.sleep(1.0)
                continue
            return e.code, e.read(), e.headers
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1.0)
                continue
            return 0, str(e).encode("utf-8"), {}

def get_visual_width(s):
    width = 0
    for char in s:
        if unicodedata.east_asian_width(char) in ('W', 'F', 'A'):
            width += 2
        else:
            width += 1
    return width

def pad_text(s, width, align="center"):
    vis_width = get_visual_width(s)
    pad_len = max(0, width - vis_width)
    if align == "center":
        left = pad_len // 2
        right = pad_len - left
        return " " * left + s + " " * right
    elif align == "left":
        return s + " " * pad_len
    else:
        return " " * pad_len + s

def clean_html(text):
    if not text:
        return ""
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
    
    # 替换 <a> 标签超链接为 "文本 (链接)" 格式以在终端打印
    def replace_link(match):
        href = match.group(1) or match.group(2) or ""
        anchor_text = match.group(3).strip()
        anchor_text = re.sub(r'<[^>]+>', '', anchor_text)
        href = href.strip()
        if not href or href == "#" or "javascript:" in href:
            return anchor_text
        full_url = href
        if not href.startswith("http"):
            if href.startswith("/"):
                full_url = f"{BASE_URL}{href}"
            else:
                full_url = f"{BASE_URL}/{href}"
        return f"{anchor_text} ({full_url})"

    text = re.sub(r'<a[^>]*href\s*=\s*(?:["\']([^"\']*)["\']|([^\s>]+))[^>]*>(.*?)</a>', replace_link, text, flags=re.DOTALL | re.IGNORECASE)
    
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</div>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace("&nbsp;", " ").replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    lines = [line.strip() for line in text.split('\n')]
    non_empty = []
    for line in lines:
        if line:
            non_empty.append(line)
        elif not non_empty or non_empty[-1] != "":
            non_empty.append("")
    return '\n'.join(non_empty).strip()

def extract_attachment_links(html_content):
    attachment_links = []
    links = re.findall(r'href=["\'](.*?)["\']', html_content)
    for link in links:
        link_clean = link.strip()
        if not link_clean or link_clean == "#" or "javascript:" in link_clean:
            continue
        lower_link = link_clean.lower()
        is_file = any(ext in lower_link for ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.zip', '.rar', '.png', '.jpg', '.txt', '.mp4'])
        if is_file or "/fileaccess/" in link_clean:
            if "Logo" in link_clean or "newFunc" in link_clean or "sydw" in link_clean:
                continue
            full_url = link_clean
            if not link_clean.startswith("http"):
                if link_clean.startswith("/"):
                    full_url = f"{BASE_URL}{link_clean}"
                else:
                    full_url = f"{BASE_URL}/{link_clean}"
            if full_url not in attachment_links:
                attachment_links.append(full_url)
    return attachment_links

def download_attachments(attachment_links, out_dir="."):
    if not attachment_links:
        log_warn("该详情页面中未检测到任何可供下载的附件或多媒体。")
        return
        
    log_info(f"发现 {len(attachment_links)} 个可供下载的文件，开始下载...")
    for i, att_url in enumerate(attachment_links):
        filename = att_url.split('/')[-1].split('?')[0]
        filename = urllib.parse.unquote(filename)
        if not filename:
            filename = f"attachment_{i+1}"
        
        if out_dir != ".":
            os.makedirs(out_dir, exist_ok=True)
        target_path = os.path.join(out_dir, filename)
        
        log_info(f"正在下载第 {i+1}/{len(attachment_links)} 个文件: {filename} ...")
        status_dl, body_dl, _ = make_request(att_url, method="GET")
        if status_dl == 200:
            try:
                with open(target_path, "wb") as f_dl:
                    f_dl.write(body_dl)
                log_success(f"已成功保存至: {target_path} (大小: {len(body_dl)} 字节)")
            except Exception as e_dl:
                log_error(f"保存文件 {target_path} 失败: {e_dl}")
        else:
            log_error(f"下载文件 {filename} 失败 (HTTP Code: {status_dl})")

def draw_table(headers, col_widths, rows):
    print(f"{C_BLUE}┌" + "┬".join("─" * w for w in col_widths) + f"┐{C_RESET}")
    header_padded = [pad_text(headers[i], col_widths[i]) for i in range(len(headers))]
    print(f"{C_BLUE}│{C_RESET}" + f"{C_BLUE}│{C_RESET}".join(f"{C_BOLD}{C_CYAN}{item}{C_RESET}" for item in header_padded) + f"{C_BLUE}│{C_RESET}")
    for row in rows:
        print(f"{C_BLUE}├" + "┼".join("─" * w for w in col_widths) + f"┤{C_RESET}")
        row_padded = []
        for col_idx, item in enumerate(row):
            item_str = str(item).strip()
            max_w = col_widths[col_idx]
            vis_w = get_visual_width(item_str)
            if vis_w > max_w:
                truncated = ""
                curr_w = 0
                for char in item_str:
                    char_w = 2 if unicodedata.east_asian_width(char) in ('W', 'F', 'A') else 1
                    if curr_w + char_w > max_w - 3:
                        break
                    truncated += char
                    curr_w += char_w
                item_str = truncated + "..."
            padded = pad_text(item_str, col_widths[col_idx], align="left" if col_idx == 1 else "center")
            row_padded.append(padded)
        print(f"{C_BLUE}│{C_RESET}" + f"{C_BLUE}│{C_RESET}".join(row_padded) + f"{C_BLUE}│{C_RESET}")
    print(f"{C_BLUE}└" + "┴".join("─" * w for w in col_widths) + f"┘{C_RESET}")

def draw_schedule_table(data_obj):
    col_widths = [10, 16, 16, 16, 16, 16]
    
    # Top border
    print(f"\n{C_BLUE}┌" + "┬".join("─" * w for w in col_widths) + f"┐{C_RESET}")
    
    # Header row
    header_padded = [pad_text(item, col_widths[i]) for i, item in enumerate(data_obj[0])]
    print(f"{C_BLUE}│{C_RESET}" + f"{C_BLUE}│{C_RESET}".join(f"{C_BOLD}{C_CYAN}{item}{C_RESET}" for item in header_padded) + f"{C_BLUE}│{C_RESET}")
    
    # Rows
    for row_idx, row in enumerate(data_obj[1:]):
        # Separator line
        print(f"{C_BLUE}├" + "┼".join("─" * w for w in col_widths) + f"┤{C_RESET}")
        
        row_padded = []
        for col_idx, item in enumerate(row):
            item_str = str(item).strip()
            if not item_str:
                item_str = "-"
            padded = pad_text(item_str, col_widths[col_idx])
            
            if col_idx == 0:
                row_padded.append(f"{C_BOLD}{C_GREEN}{padded}{C_RESET}")
            else:
                if "★" in item_str:
                    row_padded.append(f"{C_YELLOW}{padded}{C_RESET}")
                elif item_str == "-":
                    row_padded.append(f"{C_GREY}{padded}{C_RESET}")
                else:
                    row_padded.append(f"{padded}")
                    
        print(f"{C_BLUE}│{C_RESET}" + f"{C_BLUE}│{C_RESET}".join(row_padded) + f"{C_BLUE}│{C_RESET}")
        
    # Bottom border
    print(f"{C_BLUE}└" + "┴".join("─" * w for w in col_widths) + f"┘{C_RESET}")

def parse_teachers_and_display(html_content):
    main_manager = "未知"
    sub_manager = "未知"
    
    m1 = re.search(r'班主任：\s*([^\s<]+)', html_content)
    if m1:
        main_manager = m1.group(1).strip()
    m2 = re.search(r'副班主任：\s*([^\s<]+)', html_content)
    if m2:
        sub_manager = m2.group(1).strip()
        
    print(f"\n{C_BOLD}{C_CYAN}班级管理团队：{C_RESET}")
    print(f"  {C_BOLD}班主任：{C_RESET} {C_GREEN}{main_manager}{C_RESET}   |   {C_BOLD}副班主任：{C_RESET} {C_GREEN}{sub_manager}{C_RESET}")
    
    teacher_match = re.search(r'id="ClassSubjectTeacher"[^>]*>(.*?)</div>\s*</div>', html_content, re.DOTALL)
    if teacher_match:
        block = teacher_match.group(1)
        uls = re.findall(r'<ul>(.*?)</ul>', block, re.DOTALL)
        if uls:
            print(f"\n{C_BOLD}{C_CYAN}各科任课教师：{C_RESET}")
            teachers = []
            for ul in uls:
                clean = re.sub(r'<[^>]+>', '', ul).strip()
                clean = re.sub(r'\s+', ' ', clean)
                teachers.append(clean)
            
            for i in range(0, len(teachers), 3):
                row_items = teachers[i:i+3]
                row_str = "   |   ".join(f"{item}" for item in row_items)
                print(f"  {row_str}")

def find_class_id(grade_id, class_query):
    status, body, _ = make_request("/subjectArrangement/getClassFromGradeForSelect/", method="POST", data={"theGradeID": grade_id})
    if status != 200:
        log_error(f"无法获取班级列表。HTTP Code: {status}, Body: {body.decode('utf-8', errors='ignore')}")
        return None
    try:
        classes = json.loads(body.decode("utf-8"))
        q = str(class_query).strip()
        digits_match = re.search(r'\d+', q)
        q_num = digits_match.group(0) if digits_match else q
        
        for c in classes:
            c_name = c["CHClassName"]
            c_id = c["CHClassID"]
            c_digits = re.search(r'\d+', c_name)
            c_num = c_digits.group(0) if c_digits else c_name
            
            if q_num == c_num or q in c_name or c_name in q:
                return c_id, c_name
    except Exception as e:
        log_error(f"解析班级列表失败: {e}")
    return None

def cmd_schedule(args):
    grade_id = args.grade
    class_query = args.ch_class
    
    if not grade_id or not class_query:
        # Interactive mode
        print(f"{C_BOLD}--- 课表查询系统 ---{C_RESET}")
        print("请选择年级:")
        print("  1. 高一年级")
        print("  2. 高二年级")
        print("  3. 高三年级")
        try:
            choice = input(f"{C_CYAN}请选择 (1-3) > {C_RESET}").strip()
            if choice not in ('1', '2', '3'):
                log_error("无效的选择！")
                return
            grade_id = int(choice)
        except Exception:
            return
            
        # Fetch classes dynamically
        log_info("正在获取班级列表...")
        status, body, _ = make_request("/subjectArrangement/getClassFromGradeForSelect/", method="POST", data={"theGradeID": grade_id})
        if status != 200:
            log_error(f"获取班级列表失败 (HTTP: {status})")
            return
        try:
            classes = json.loads(body.decode("utf-8"))
            print("\n请选择班级:")
            for idx, c in enumerate(classes):
                print(f"  {idx+1:2d}. {c['CHClassName']}")
                
            choice = input(f"{C_CYAN}请选择班级序号 (1-{len(classes)}) > {C_RESET}").strip()
            idx = int(choice) - 1
            if idx < 0 or idx >= len(classes):
                log_error("无效的选择！")
                return
            class_id = classes[idx]["CHClassID"]
            class_name = classes[idx]["CHClassName"]
        except Exception as e:
            log_error(f"解析班级列表失败: {e}")
            return
    else:
        # Non-interactive mode
        if grade_id not in (1, 2, 3):
            log_error("年级参数必须在 1 到 3 之间。")
            return
        res = find_class_id(grade_id, class_query)
        if not res:
            log_error(f"在年级 {grade_id} 中未找到匹配的班级 \"{class_query}\"")
            return
        class_id, class_name = res
        
    log_info(f"正在查询 [{class_name}] 的课表安排...")
    data_post = {
        "chGradeIDForName": grade_id,
        "chClassIDForName": class_id
    }
    status, body_html, _ = make_request("/subjectArrangement/ClassClassArrangement_JustForView/", method="POST", data=data_post)
    if status != 200:
        log_error(f"查询课表失败 (HTTP: {status})")
        return
        
    html_content = body_html.decode("utf-8", errors="ignore")
    
    # Extract dataObj=[[...]]
    match = re.search(r'dataObj\s*=\s*(\[\[.*?\]\])\s*;', html_content)
    if not match:
        log_error("未能在页面中找到课表数据矩阵。")
        return
        
    try:
        data_obj = json.loads(match.group(1))
        # Draw table
        print(f"\n{C_BOLD}{C_GREEN}=== {class_name} 课表安排 ==={C_RESET}")
        draw_schedule_table(data_obj)
        # Parse teachers
        parse_teachers_and_display(html_content)
    except Exception as e:
        log_error(f"解析课表数据矩阵失败: {e}")

def cmd_messages(args):
    if args.show:
        msg_id = args.show
        log_info(f"正在查询消息详情 [ID: {msg_id}]...")
        status, body, _ = make_request(f"/sitemessage/show-Message/{msg_id}/", method="GET")
        if status != 200:
            log_error(f"获取消息详情失败 (HTTP Code: {status})")
            return
        html_content = body.decode("utf-8", errors="ignore")
        
        title = "无标题"
        title_m = re.search(r'<div class="ArticleTitle">(.*?)</div>', html_content, re.DOTALL)
        if title_m:
            title = clean_html(title_m.group(1))
            
        sender = "未知"
        sender_m = re.search(r'发送者：\s*([^\s<]+)', html_content)
        if sender_m:
            sender = sender_m.group(1).strip()
            
        send_time = "未知"
        time_m = re.search(r'发送时间：\s*([^\s<]+(?:\s+[^\s<]+)?)', html_content)
        if time_m:
            send_time = time_m.group(1).strip()
            
        content = ""
        content_m = re.search(r'<div class="ArticleContent[^>]*>(.*?)</div>\s*</div>', html_content, re.DOTALL)
        if content_m:
            content = clean_html(content_m.group(1))
        else:
            content_m = re.search(r'<div class="ArticleContent[^>]*>(.*?)</div>', html_content, re.DOTALL)
            if content_m:
                content = clean_html(content_m.group(1))
                
        recipients_all = "无"
        rec1_m = re.search(r'id="multiCollapseExample1">\s*<div class="card card-body">\s*(.*?)\s*</div>', html_content, re.DOTALL)
        if rec1_m:
            recipients_all = clean_html(rec1_m.group(1))
            
        recipients_unread = "无"
        rec2_m = re.search(r'id="multiCollapseExample2">\s*<div class="card card-body">\s*(.*?)\s*</div>', html_content, re.DOTALL)
        if rec2_m:
            recipients_unread = clean_html(rec2_m.group(1))
            
        # 提取附件超链接
        attachment_links = []
        links = re.findall(r'href=["\'](.*?)["\']', html_content)
        for link in links:
            link_clean = link.strip()
            if not link_clean or link_clean == "#" or "javascript:" in link_clean:
                continue
            lower_link = link_clean.lower()
            is_file = any(ext in lower_link for ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.zip', '.rar', '.png', '.jpg', '.txt', '.mp4'])
            if is_file or "/fileaccess/" in link_clean:
                if "Logo" in link_clean or "newFunc" in link_clean or "sydw" in link_clean:
                    continue
                full_url = link_clean
                if not link_clean.startswith("http"):
                    if link_clean.startswith("/"):
                        full_url = f"{BASE_URL}{link_clean}"
                    else:
                        full_url = f"{BASE_URL}/{link_clean}"
                if full_url not in attachment_links:
                    attachment_links.append(full_url)
            
        print(f"\n{C_BOLD}{C_GREEN}✉ 消息详情 {C_RESET}")
        print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
        print(f"{C_BOLD}标题：{C_RESET} {C_YELLOW}{title}{C_RESET}")
        print(f"{C_BOLD}发送者：{C_RESET} {C_CYAN}{sender}{C_RESET}    |    {C_BOLD}时间：{C_RESET} {C_GREY}{send_time}{C_RESET}")
        print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
        print(f"{content}")
        print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
        print(f"{C_BOLD}全体收件人：{C_RESET} {recipients_all}")
        print(f"{C_BOLD}未阅收件人：{C_RESET} {C_RED}{recipients_unread}{C_RESET}")
        print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
        
        if attachment_links:
            print(f"{C_BOLD}{C_GREEN}📎 关联附件列表：{C_RESET}")
            for i, att_url in enumerate(attachment_links):
                filename = att_url.split('/')[-1].split('?')[0]
                filename = urllib.parse.unquote(filename)
                print(f"  [{i+1}] {C_YELLOW}{filename}{C_RESET}")
                print(f"      链接: {C_CYAN}{att_url}{C_RESET}")
            print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
            
        if args.download:
            download_attachments(attachment_links, args.out)
            print()
        return

    page = args.page or 1
    log_info(f"正在获取收件箱消息列表 (第 {page} 页)...")
    url = f"/sitemessage/message-Receive-list/?page={page}"
    status, body, _ = make_request(url, method="GET")
    if status != 200:
        log_error(f"获取收件箱列表失败 (HTTP Code: {status})")
        return
        
    html_content = body.decode("utf-8", errors="ignore")
    
    tr_pattern = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL)
    trs = tr_pattern.findall(html_content)
    
    rows = []
    for tr in trs:
        if "show-Message" in tr:
            id_m = re.search(r'/sitemessage/show-Message/(\d+)/\s*', tr)
            msg_id = id_m.group(1) if id_m else ""
            if not msg_id:
                id_m = re.search(r'del_siteMessage\(this,(\d+)\)', tr)
                if id_m:
                    msg_id = id_m.group(1)
            
            tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL)
            if len(tds) >= 3:
                title = clean_html(tds[1])
                sender = clean_html(tds[2])
                date = clean_html(tds[3]) if len(tds) > 3 else ""
                rows.append([msg_id, title, sender, date])
                
    if not rows:
        log_warn("没有找到任何消息记录。")
        return
        
    print(f"\n{C_BOLD}{C_GREEN}✉ 收件箱列表 (第 {page} 页) ==={C_RESET}")
    for row in rows:
        msg_id, title, sender, date = row
        print(f"[{C_GREEN}{msg_id}{C_RESET}] {C_BOLD}{title}{C_RESET}")
        print(f"      发送人: {C_CYAN}{sender}{C_RESET}  |  时间: {C_GREY}{date}{C_RESET}")
        print(f"      {C_BLUE}┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄{C_RESET}")
    print(f"{C_GREY}提示: 使用 `python3 ch_cli.py messages --show <消息ID>` 查看消息正文详情。{C_RESET}\n")

def cmd_hygiene(args):
    if args.show:
        hygiene_id = args.show
        log_info(f"正在查询纪律卫生详情 [ID: {hygiene_id}]...")
        status, body, _ = make_request(f"/classappraise/show-Message/{hygiene_id}/", method="GET")
        if status != 200:
            log_error(f"获取纪律卫生详情失败 (HTTP Code: {status})")
            return
        html_content = body.decode("utf-8", errors="ignore")
        
        desc = "未知违纪说明"
        content_m = re.search(r'<div class="ArticleContent[^>]*>(.*?)</div>', html_content, re.DOTALL)
        if content_m:
            desc_html = content_m.group(1)
            desc = clean_html(desc_html)
            
        media_urls = []
        imgs = re.findall(r'<img[^>]+src=["\'](.*?)["\']', html_content)
        for img in imgs:
            if "Logo" not in img and "newFunc" not in img and "sydw" not in img:
                if not img.startswith("http") and img.startswith("/"):
                    media_urls.append(f"{BASE_URL}{img}")
                else:
                    media_urls.append(img)
                    
        vids = re.findall(r'<video[^>]+src=["\'](.*?)["\']', html_content)
        for vid in vids:
            if not vid.startswith("http") and vid.startswith("/"):
                media_urls.append(f"{BASE_URL}{vid}")
            else:
                media_urls.append(vid)
                
        recipients_all = "无"
        rec1_m = re.search(r'id="multiCollapseExample1">\s*<div class="card card-body">\s*(.*?)\s*</div>', html_content, re.DOTALL)
        if rec1_m:
            recipients_all = clean_html(rec1_m.group(1))
            
        recipients_unread = "无"
        rec2_m = re.search(r'id="multiCollapseExample2">\s*<div class="card card-body">\s*(.*?)\s*</div>', html_content, re.DOTALL)
        if rec2_m:
            recipients_unread = clean_html(rec2_m.group(1))
            
        print(f"\n{C_BOLD}{C_RED}⚠ 纪律卫生考评详情 {C_RESET}")
        print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
        print(f"{C_BOLD}描述：{C_RESET} {C_YELLOW}{desc}{C_RESET}")
        print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
        if media_urls:
            print(f"{C_BOLD}关联多媒体（可在浏览器中打开查看）：{C_RESET}")
            for i, m_url in enumerate(media_urls):
                print(f"  [{i+1}] {C_CYAN}{m_url}{C_RESET}")
            print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
        print(f"{C_BOLD}关联收件人：{C_RESET} {recipients_all}")
        print(f"{C_BOLD}未阅收件人：{C_RESET} {C_RED}{recipients_unread}{C_RESET}")
        print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
        
        if args.download:
            download_attachments(media_urls, args.out)
            print()
        return

    page = args.page or 1
    log_info(f"正在获取纪律卫生考评列表 (第 {page} 页)...")
    url = f"/classappraise/hygienePictures_receive_list/?page={page}"
    status, body, _ = make_request(url, method="GET")
    if status != 200:
        log_error(f"获取纪律卫生考评列表失败 (HTTP Code: {status})")
        return
        
    html_content = body.decode("utf-8", errors="ignore")
    
    tr_pattern = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL)
    trs = tr_pattern.findall(html_content)
    
    rows = []
    for tr in trs:
        if "show-Message" in tr:
            id_m = re.search(r'/classappraise/show-Message/(\d+)/\s*', tr)
            record_id = id_m.group(1) if id_m else ""
            
            tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL)
            if len(tds) >= 4:
                location = clean_html(tds[1])
                description = clean_html(tds[2])
                date = clean_html(tds[3])
                rows.append([record_id, location, description, date])
                
    if not rows:
        log_warn("没有找到任何纪律卫生考评记录。")
        return
        
    print(f"\n{C_BOLD}{C_GREEN}⚠ 纪律卫生考评记录 (第 {page} 页) ==={C_RESET}")
    for row in rows:
        record_id, location, description, date = row
        print(f"[{C_GREEN}{record_id}{C_RESET}] 地点: {C_YELLOW}{location}{C_RESET}  |  检查日期: {C_GREY}{date}{C_RESET}")
        print(f"      描述: {description}")
        print(f"      {C_BLUE}┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄{C_RESET}")
    print(f"{C_GREY}提示: 使用 `python3 ch_cli.py hygiene --show <记录ID>` 查看多媒体附件及关联收件人。{C_RESET}\n")

def cmd_duty(args):
    log_info("正在获取值周安排表...")
    status, body, _ = make_request("/classappraise/TeacherDutyWeek_JustForView/", method="GET")
    if status != 200:
        log_error(f"获取值周安排失败 (HTTP Code: {status})")
        return
        
    html_content = body.decode("utf-8", errors="ignore")
    
    blocks = re.findall(r'<ul class="list-group"\s*>(.*?)</ul>', html_content, re.DOTALL)
    if not blocks:
        log_warn("未检测到任何值周安排块。")
        return
        
    duties = []
    current_week = None
    
    for idx, block in enumerate(blocks):
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
                
        duty_info = {
            "is_current": is_current,
            "week": week_name,
            "date": date_range,
            "admin": details.get("行政值周", ""),
            "group1": details.get("第一小组", ""),
            "group2": details.get("第二小组", ""),
            "group3": details.get("第三小组", ""),
            "class": details.get("值周班级", ""),
            "talk": details.get("旗下讲话", "")
        }
        
        duties.append(duty_info)
        if is_current:
            current_week = duty_info

    if args.search:
        q = args.search.strip()
        log_info(f"正在全表中搜索与 \"{q}\" 相关的值周安排...")
        matches = []
        for d in duties:
            if q in d["week"] or q in d["admin"] or q in d["group1"] or q in d["group2"] or q in d["group3"] or q in d["class"]:
                matches.append(d)
        if not matches:
            log_warn(f"未在值周表中搜索到与 \"{q}\" 匹配的周次。")
            return
            
        print(f"\n{C_BOLD}{C_GREEN}=== 搜索到 {len(matches)} 个匹配值周安排 ==={C_RESET}")
        for d in matches:
            curr_tag = f" {C_BOLD}{C_GREEN}[当前周]{C_RESET}" if d["is_current"] else ""
            print(f"\n{C_BOLD}{C_CYAN}◆ {d['week']}{curr_tag} ({d['date']}){C_RESET}")
            print(f"  {C_BOLD}行政值周：{C_RESET} {C_YELLOW}{d['admin']}{C_RESET}")
            print(f"  {C_BOLD}第一小组：{C_RESET} {d['group1']}")
            print(f"  {C_BOLD}第二小组：{C_RESET} {d['group2']}")
            if d['group3'].replace(",", "").strip():
                print(f"  {C_BOLD}第三小组：{C_RESET} {d['group3']}")
            print(f"  {C_BOLD}值周班级：{C_RESET} {C_GREEN}{d['class']}{C_RESET}")
            if d['talk']:
                print(f"  {C_BOLD}旗下讲话：{C_RESET} {d['talk']}")
        print()
        return

    if args.all:
        print(f"\n{C_BOLD}{C_GREEN}=== 浙江省春晖中学值周排班总表 ==={C_RESET}")
        for d in duties:
            week_disp = d["week"]
            week_color = C_GREEN if d["is_current"] else C_CYAN
            curr_mark = "★ " if d["is_current"] else ""
            print(f"{C_BOLD}{week_color}{curr_mark}{week_disp}{C_RESET} ({C_GREY}{d['date']}{C_RESET})")
            print(f"  行政值周: {C_YELLOW}{d['admin']}{C_RESET}  |  值周班级: {C_GREEN}{d['class']}{C_RESET}")
            print(f"  {C_BLUE}┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄{C_RESET}")
        print(f"{C_GREY}提示: 带 ★ 的代表当前周次。使用 `python3 ch_cli.py duty --search <姓名>` 可模糊搜索。{C_RESET}\n")
        return

    if not current_week:
        log_warn("未在页面中检测到高亮标识的当前周次，默认展示全表。")
        args.all = True
        cmd_duty(args)
        return
        
    print(f"\n{C_BOLD}{C_GREEN}★ 当前值周安排 ({current_week['week']}) ★{C_RESET}")
    print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
    print(f"{C_BOLD}日期范围：{C_RESET} {C_YELLOW}{current_week['date']}{C_RESET}")
    print(f"{C_BOLD}行政值周：{C_RESET} {C_GREEN}{C_BOLD}{current_week['admin']}{C_RESET}")
    print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
    print(f"{C_BOLD}第一小组：{C_RESET} {current_week['group1']}")
    print(f"{C_BOLD}第二小组：{C_RESET} {current_week['group2']}")
    if current_week['group3'].replace(",", "").strip():
        print(f"{C_BOLD}第三小组：{C_RESET} {current_week['group3']}")
    print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
    print(f"  {C_BOLD}值周班级：{C_RESET} {C_CYAN}{C_BOLD}{current_week['class']}{C_RESET}")
    if current_week['talk']:
        print(f"  {C_BOLD}旗下讲话：{C_RESET} {current_week['talk']}")
    print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
    print(f"{C_GREY}提示: 使用 `python3 ch_cli.py duty --all` 查验整学期排班总表。{C_RESET}\n")

def encode_multipart_formdata(fields, files):
    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
    CRLF = b'\r\n'
    L = []
    for key, value in fields.items():
        L.append(f'--{boundary}'.encode('utf-8'))
        L.append(f'Content-Disposition: form-data; name="{key}"'.encode('utf-8'))
        L.append(b'')
        L.append(str(value).encode('utf-8'))
    for key, (filename, content_type, file_content) in files.items():
        L.append(f'--{boundary}'.encode('utf-8'))
        L.append(f'Content-Disposition: form-data; name="{key}"; filename="{filename}"'.encode('utf-8'))
        L.append(f'Content-Type: {content_type}'.encode('utf-8'))
        L.append(b'')
        L.append(file_content)
    L.append(f'--{boundary}--'.encode('utf-8'))
    L.append(b'')
    body = CRLF.join(L)
    content_type = f'multipart/form-data; boundary={boundary}'
    return content_type, body

def cmd_file_upload(file_path):
    if not os.path.exists(file_path):
        log_error(f"本地文件不存在: {file_path}")
        return
        
    filename = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    
    chunk_size = 50 * 1024 * 1024
    total_chunks = (file_size + chunk_size - 1) // chunk_size
    if total_chunks == 0:
        total_chunks = 1
        
    task_id = f"WU_FILE_{uuid.uuid4().hex}"
    log_info(f"正在准备分片上传文件: {filename} (大小: {file_size} 字节, 共 {total_chunks} 个分片)")
    
    try:
        with open(file_path, "rb") as f:
            for chunk_idx in range(total_chunks):
                chunk_data = f.read(chunk_size)
                
                fields = {
                    "id": "WU_FILE_0",
                    "name": filename,
                    "type": "application/octet-stream",
                    "lastModifiedDate": time.strftime("%a %b %d %Y %H:%M:%S GMT+0800"),
                    "size": str(file_size),
                    "chunks": str(total_chunks),
                    "chunk": str(chunk_idx),
                    "task_id": task_id
                }
                
                files = {
                    "file": (filename, "application/octet-stream", chunk_data)
                }
                
                content_type, body = encode_multipart_formdata(fields, files)
                
                headers = {
                    "Content-Type": content_type,
                    "Content-Length": str(len(body))
                }
                
                log_info(f"正在上传分片 {chunk_idx + 1}/{total_chunks} ({len(chunk_data)} 字节)...")
                
                status, resp_body, _ = make_request("/fileaccess/files_upload/", method="POST", data=body, headers=headers)
                if status != 200:
                    log_error(f"分片 {chunk_idx + 1} 上传失败 (HTTP Code: {status})")
                    return
    except Exception as e:
        log_error(f"读取或发送分片文件失败: {e}")
        return
                
    log_info("所有分片上传完毕，正在向服务器请求合并文件...")
    
    complete_data = {
        "task_id": task_id,
        "filename": filename
    }
    status_c, resp_c, _ = make_request("/fileaccess/upload_complete/", method="POST", data=complete_data)
    if status_c == 200:
        password = resp_c.decode("utf-8", errors="ignore").strip()
        password = clean_html(password)
        log_success(f"文件上传并合并成功！")
        print(f"\n{C_BOLD}文件提取密码：{C_RESET} {C_YELLOW}{C_BOLD}{password}{C_RESET}")
        print(f"{C_GREY}提示: 接收方可通过运行 `python3 ch_cli.py file download {password}` 来提取该文件。{C_RESET}\n")
    else:
        log_error(f"合并文件请求失败 (HTTP Code: {status_c})")

def cmd_file_download(password, out_dir="."):
    log_info(f"正在查询提取码 [{password}] 对应文件信息...")
    post_data = {
        "thePasswordTheUserEntered": password
    }
    status, body, _ = make_request("/fileaccess/get-AccessFile/", method="POST", data=post_data)
    if status != 200:
        log_error(f"查询提取码失败 (HTTP Code: {status})")
        return
        
    try:
        res_json = json.loads(body.decode("utf-8"))
        if res_json.get("error") != "0":
            err_msg = res_json.get("msg", "提取码不存在、错误或文件已过期。")
            log_error(f"提取失败: {err_msg}")
            return
            
        file_path_name = res_json.get("filePathName")
        file_name = res_json.get("fileNameForDisplay")
        
        if not file_path_name or not file_name:
            log_error("服务器返回的文件路径或文件名不完整。")
            return
            
        download_url = f"/static/fileaccess/{file_path_name}"
        
        out_path = out_dir if out_dir else "."
        if out_path != ".":
            os.makedirs(out_path, exist_ok=True)
        target_path = os.path.join(out_path, file_name)
        
        log_info(f"匹配到文件: {file_name}，正在拉取数据...")
        
        status_dl, body_dl, _ = make_request(download_url, method="GET")
        if status_dl == 200:
            with open(target_path, "wb") as f_dl:
                f_dl.write(body_dl)
            log_success(f"文件已成功保存至: {target_path} (大小: {len(body_dl)} 字节)")
        else:
            log_error(f"下载文件失败 (HTTP Code: {status_dl})")
            
    except Exception as e:
        log_error(f"解析提取结果异常: {e}")

def cmd_file(args):
    if args.action == "upload":
        cmd_file_upload(args.path)
    elif args.action == "download":
        cmd_file_download(args.password, args.out)

def cmd_news(args):
    if args.show:
        msg_id = args.show
        log_info(f"正在查询文章详情 [ID: {msg_id}]...")
        status, body, _ = make_request(f"/article/article-detail/{msg_id}/", method="GET", follow_redirects=True)
        if status != 200:
            log_error(f"获取文章详情失败 (HTTP Code: {status})")
            return
        html_content = body.decode("utf-8", errors="ignore")
        
        title = "无标题"
        title_m = re.search(r'<div class="ArticleTitle[^>]*>(.*?)</div>', html_content, re.DOTALL)
        if title_m:
            title = clean_html(title_m.group(1))
            
        source = "未知"
        source_m = re.search(r'来源：\s*([^<]+)', html_content)
        if source_m:
            source = clean_html(source_m.group(1))
            
        pub_time = "未知"
        time_m = re.search(r'发布时间：\s*([^\s<]+(?:\s+[^\s<]+)?)', html_content)
        if time_m:
            pub_time = time_m.group(1).strip()
            
        content = ""
        content_m = re.search(r'<div class="ArticleContent(?:\s+[^>]*|)\s*>(.*?)</div>', html_content, re.DOTALL)
        if content_m:
            content = clean_html(content_m.group(1))
            
        print(f"\n{C_BOLD}{C_GREEN}📄 文章详情 {C_RESET}")
        print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
        print(f"{C_BOLD}标题：{C_RESET} {C_YELLOW}{title}{C_RESET}")
        print(f"{C_BOLD}发布人：{C_RESET} {C_CYAN}{source}{C_RESET}    |    {C_BOLD}时间：{C_RESET} {C_GREY}{pub_time}{C_RESET}")
        print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
        print(f"{content}")
        print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
        
        attachment_links = extract_attachment_links(html_content)
        if attachment_links:
            print(f"{C_BOLD}{C_GREEN}📎 关联附件列表：{C_RESET}")
            for i, att_url in enumerate(attachment_links):
                filename = att_url.split('/')[-1].split('?')[0]
                filename = urllib.parse.unquote(filename)
                print(f"  [{i+1}] {C_YELLOW}{filename}{C_RESET}")
                print(f"      链接: {C_CYAN}{att_url}{C_RESET}")
            print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
            
        if args.download:
            download_attachments(attachment_links, args.out)
            print()
        return

    # 栏目映射支持
    col_mapping = {
        "news": "13",      # 新闻聚焦
        "notice": "19",    # 校内公示
        "announcement": "16", # 通知公告
        "duty": "51"       # 值周小结
    }
    col_id = col_mapping.get(args.column, args.column)
    page = args.page or 1
    
    log_info(f"正在获取栏目 [{args.column}] 文章列表 (第 {page} 页)...")
    status, body, _ = make_request(f"/article/column-detail/{col_id}/?page={page}", method="GET", follow_redirects=True)
    if status != 200:
        log_error(f"获取文章列表失败 (HTTP Code: {status})")
        return
    html_content = body.decode("utf-8", errors="ignore")
    
    items = re.findall(r'href=["\']/article/article-detail/(\d+)/["\'][^>]*>\s*(.*?)\s*</a>.*?class="[^"]*text-secondary"[^>]*>\s*(.*?)\s*</div>', html_content, re.DOTALL)
    if not items:
        log_warn("没有找到任何文章记录。")
        return
        
    rows = []
    for art_id, title, date in items:
        rows.append([art_id, clean_html(title), clean_html(date)])
        
    print(f"\n{C_BOLD}{C_GREEN}📄 文章列表 (栏目: {args.column}, 第 {page} 页) ==={C_RESET}")
    for row in rows:
        art_id, title, date = row
        print(f"[{C_GREEN}{art_id}{C_RESET}] {C_BOLD}{title}{C_RESET}")
        print(f"      发布日期: {C_GREY}{date}{C_RESET}")
        print(f"      {C_BLUE}┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄{C_RESET}")
    print(f"{C_GREY}提示: 使用 `python3 ch_cli.py news --show <文章ID>` 阅读正文内容。{C_RESET}\n")

def cmd_bedroom(args):
    if args.action == "class":
        grade = args.grade
        class_query = args.ch_class
        res = find_class_id(grade, class_query)
        if not res:
            log_error(f"未能在年级 {grade} 中找到匹配班级 \"{class_query}\"")
            return
        class_id, class_name = res
        log_info(f"正在查询 [{class_name}] 的寝室分配情况...")
        
        post_data = {
            "chGradeIDForName": grade,
            "chClassIDForName": class_id
        }
        status, body, _ = make_request("/classappraise/QueryBedroomsByClassID_JustForView/", method="POST", data=post_data)
        if status != 200:
            log_error(f"查询寝室关系失败 (HTTP Code: {status})")
            return
        html_content = body.decode("utf-8", errors="ignore")
        
        alert_m = re.search(r'class="alert alert-primary"[^>]*>\s*(.*?)\s*</div>', html_content, re.DOTALL)
        if alert_m:
            result_text = clean_html(alert_m.group(1))
            print(f"\n{C_BOLD}{C_GREEN}🏠 寝室分配查询结果 {C_RESET}")
            print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
            print(f"{C_YELLOW}{result_text}{C_RESET}")
            print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}\n")
        else:
            log_warn("未查到该班级的寝室分配数据。")
            
    elif args.action == "hygiene":
        dorm_mapping = {
            "1": "3号楼", "2": "4号楼", "3": "5号楼", "4": "6号楼", "5": "7号楼", "6": "8号楼", "7": "9号楼", "8": "10号楼", "9": "1号楼"
        }
        
        # 楼宇输入映射
        dorm_id = args.dorm
        for d_id, d_name in dorm_mapping.items():
            if d_id in args.dorm or d_name in args.dorm:
                dorm_id = d_id
                break
                
        dorm_name = dorm_mapping.get(dorm_id, f"未知楼宇(ID:{dorm_id})")
        
        # 时间范围处理
        start_date = args.start
        if not start_date:
            start_date = time.strftime("%Y-%m-%d", time.localtime(time.time() - 30 * 86400))
        end_date = args.end
        if not end_date:
            end_date = time.strftime("%Y-%m-%d")
            
        log_info(f"正在查询 [{dorm_name}] 的寝室考评记录 (日期: {start_date} 至 {end_date})...")
        
        post_data = {
            "chDormitoryForName": dorm_id,
            "theBeginDateForName": start_date,
            "theEndDateForName": end_date
        }
        status, body, _ = make_request("/classappraise/BedRoom_DisciplineHygiene_JustForView/", method="POST", data=post_data)
        if status != 200:
            log_error(f"查询宿舍考评失败 (HTTP Code: {status})")
            return
        html_content = body.decode("utf-8", errors="ignore")
        
        tr_pattern = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL)
        trs = tr_pattern.findall(html_content)
        
        rows = []
        for tr in trs:
            tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL)
            if len(tds) >= 4:
                room_name = clean_html(tds[0])
                class_name = clean_html(tds[1])
                hyg_score = clean_html(tds[2])
                disc_score = clean_html(tds[3])
                total_score = clean_html(tds[4]) if len(tds) > 4 else ""
                
                # 如果没有启用 --all，只显示合计分数非空且有扣分记录的项目
                if not args.all:
                    if not total_score or total_score.strip() == "" or total_score.strip() == "0":
                        continue
                        
                rows.append([
                    room_name,
                    class_name,
                    hyg_score or "-",
                    disc_score or "-",
                    total_score or "-"
                ])
                
        if not rows:
            log_warn("没有找到任何相关的寝室考评扣分记录。")
            return
            
        print(f"\n{C_BOLD}{C_GREEN}🧹 {dorm_name} 寝室卫生与纪律扣分考评总表 ==={C_RESET}")
        for row in rows:
            room, cls, hyg, disc, total = row
            print(f"寝室: {C_GREEN}{C_BOLD}{room}{C_RESET} ({cls})")
            print(f"  卫生扣分: {C_RED}{hyg}{C_RESET}  |  纪律扣分: {C_RED}{disc}{C_RESET}  |  合计扣分: {C_YELLOW}{total}{C_RESET}")
            print(f"  {C_BLUE}┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄{C_RESET}")
        print()

def cmd_lostfound(args):
    if args.show:
        msg_id = args.show
        log_info(f"正在查询失物招领详情 [ID: {msg_id}]...")
        status, body, _ = make_request(f"/lostAndFound/lostAndFoundDetail/{msg_id}/", method="GET", follow_redirects=True)
        if status != 200:
            log_error(f"获取失物招领详情失败 (HTTP Code: {status})")
            return
        html_content = body.decode("utf-8", errors="ignore")
        
        title = "无标题"
        title_m = re.search(r'<div class="ArticleTitle[^>]*>(.*?)</div>', html_content, re.DOTALL)
        if title_m:
            title = clean_html(title_m.group(1))
            
        reporter = "未知"
        rep_m = re.search(r'来源：\s*([^<]+)', html_content)
        if rep_m:
            reporter = clean_html(rep_m.group(1))
            
        reviewer = "未知"
        rev_m = re.search(r'审核人：\s*([^<]+)', html_content)
        if rev_m:
            reviewer = clean_html(rev_m.group(1))
            
        pub_time = "未知"
        time_m = re.search(r'发布时间：\s*([^\s<]+(?:\s+[^\s<]+)?)', html_content)
        if time_m:
            pub_time = time_m.group(1).strip()
            
        content = ""
        content_m = re.search(r'<div class="ArticleContent(?:\s+[^>]*|)\s*>(.*?)</div>', html_content, re.DOTALL)
        if content_m:
            content = clean_html(content_m.group(1))
            
        # 提取招领中关联的图片/视频等多媒体
        media_urls = []
        imgs = re.findall(r'<img[^>]+src=["\'](.*?)["\']', html_content)
        for img in imgs:
            if "Logo" not in img and "newFunc" not in img and "sydw" not in img:
                if not img.startswith("http") and img.startswith("/"):
                    media_urls.append(f"{BASE_URL}{img}")
                else:
                    media_urls.append(img)
                    
        vids = re.findall(r'<video[^>]+src=["\'](.*?)["\']', html_content)
        for vid in vids:
            if not vid.startswith("http") and vid.startswith("/"):
                media_urls.append(f"{BASE_URL}{vid}")
            else:
                media_urls.append(vid)

        attachment_links = extract_attachment_links(html_content)
        for link in attachment_links:
            if link not in media_urls:
                media_urls.append(link)

        print(f"\n{C_BOLD}{C_GREEN}🔍 失物招领详情 {C_RESET}")
        print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
        print(f"{C_BOLD}物品主题：{C_RESET} {C_YELLOW}{title}{C_RESET}")
        print(f"{C_BOLD}登记来源：{C_RESET} {C_CYAN}{reporter}{C_RESET}    |    {C_BOLD}时间：{C_RESET} {C_GREY}{pub_time}{C_RESET}")
        print(f"{C_BOLD}审 核 人：{C_RESET} {reviewer}")
        print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
        print(f"{content}")
        print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
        
        if media_urls:
            print(f"{C_BOLD}📎 关联文件或多媒体：{C_RESET}")
            for i, m_url in enumerate(media_urls):
                print(f"  [{i+1}] {C_CYAN}{m_url}{C_RESET}")
            print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
            
        if args.download:
            download_attachments(media_urls, args.out)
            print()
        return

    page = args.page or 1
    log_info(f"正在获取全校失物招领列表 (第 {page} 页)...")
    status, body, _ = make_request(f"/lostAndFound/lostAndFoundList/?page={page}", method="GET", follow_redirects=True)
    if status != 200:
        log_error(f"获取失物招领列表失败 (HTTP Code: {status})")
        return
    html_content = body.decode("utf-8", errors="ignore")
    
    tr_pattern = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL)
    trs = tr_pattern.findall(html_content)
    
    rows = []
    for tr in trs:
        tds = re.findall(r'<(?:td|th)[^>]*>(.*?)</(?:td|th)>', tr, re.DOTALL)
        if len(tds) >= 8 and "类别" not in tds[1]:
            lf_id = ""
            id_m = re.search(r'href=["\']/lostAndFound/lostAndFoundDetail/(\d+)/["\']', tds[2])
            if id_m:
                lf_id = id_m.group(1)
                
            category = clean_html(tds[1])
            title = clean_html(tds[2])
            reporter = clean_html(tds[3])
            start_date = clean_html(tds[6])
            status_text = clean_html(tds[8]) if len(tds) > 8 else ""
            
            rows.append([lf_id, category, title, reporter, start_date, status_text])
            
    if not rows:
        log_warn("没有找到任何失物招领记录。")
        return
        
    print(f"\n{C_BOLD}{C_GREEN}🔍 全校失物招领列表 (第 {page} 页) ==={C_RESET}")
    for row in rows:
        lf_id, category, title, reporter, start_date, status_text = row
        cat_color = C_YELLOW if "丢" in category else C_GREEN
        status_color = C_RED if "未" in status_text or "处理中" in status_text else C_GREY
        print(f"[{C_GREEN}{lf_id}{C_RESET}] {C_BOLD}{cat_color}[{category}]{C_RESET} {title}")
        print(f"      发布处: {C_CYAN}{reporter}{C_RESET}  |  日期: {C_GREY}{start_date}{C_RESET}  |  状态: {status_color}{status_text}{C_RESET}")
        print(f"      {C_BLUE}┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄{C_RESET}")
    print(f"{C_GREY}提示: 使用 `python3 ch_cli.py lostfound --show <ID>` 查看招领联系方式等详情。{C_RESET}\n")

def cmd_login(args):
    cookie_str = args.cookie
    if not cookie_str:
        print(f"{C_BOLD}请输入您从浏览器获取的 Cookie 字符串：{C_RESET}")
        print(f"{C_GREY}(通常可在浏览器开发者工具的 Network 面板请求头中找到。形如: sessionid=xxx; csrftoken=yyy){C_RESET}")
        cookie_str = input(f"{C_CYAN}Cookie > {C_RESET}").strip()
        
    sessionid = ""
    csrftoken = ""
    
    parts = [p.strip() for p in cookie_str.split(";")]
    for part in parts:
        if "=" in part:
            k, v = part.split("=", 1)
            k = k.strip()
            v = v.strip()
            if k == "sessionid":
                sessionid = v
            elif k == "csrftoken":
                csrftoken = v
                
    if not sessionid:
        log_warn("输入的 Cookie 中未检测到 sessionid，这可能会导致需要登录的功能无法使用。")
    if not csrftoken:
        log_warn("输入的 Cookie 中未检测到 csrftoken，这可能会导致文件上传等写操作失败。")
        
    session_data = {
        "sessionid": sessionid,
        "csrftoken": csrftoken
    }
    
    if save_session(session_data):
        log_success("Cookie 导入成功！")
        check_login_status()

def check_login_status():
    log_info("正在向服务器验证登录状态...")
    status, body, headers = make_request("/article/article-detail/37079/", method="GET")
    if status == 200:
        log_success("已成功登录！")
        return True
    elif status == 302:
        log_error("会话验证失败: 账号未登录或 Session 已失效。请重新获取 Cookie。")
    else:
        log_error(f"连接服务器失败 (HTTP Code: {status})。请检查局域网连接或服务器状态。")
    return False

def cmd_status(args):
    check_login_status()

def main():
    for idx, arg in enumerate(sys.argv):
        if arg == "?":
            sys.argv[idx] = "-h"

    parser = argparse.ArgumentParser(
        description=f"{C_BOLD}{C_CYAN}浙江省春晖中学校园网 CLI 工具 (ch_cli){C_RESET}",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # login command
    parser_login = subparsers.add_parser("login", help="通过 Cookie 进行登录")
    parser_login.add_argument("--cookie", type=str, help="直接指定 Cookie 字符串")

    # status command
    subparsers.add_parser("status", help="检查当前登录状态")

    # schedule command
    parser_sched = subparsers.add_parser("schedule", help="查询班级课表")
    parser_sched.add_argument("--grade", type=int, help="年级 (1=高一, 2=高二, 3=高三)")
    parser_sched.add_argument("--class", dest="ch_class", type=str, help="班级名称或数字 (如: 1 或 1班)")

    # messages command
    parser_msg = subparsers.add_parser("messages", help="查询个人收件箱消息")
    parser_msg.add_argument("--page", type=int, default=1, help="页码")
    parser_msg.add_argument("--show", type=int, help="要查看的消息详情 ID")
    parser_msg.add_argument("--download", "-d", action="store_true", help="是否下载该消息包含的所有附件")
    parser_msg.add_argument("--out", type=str, default=".", help="指定附件的下载保存目录")

    # hygiene command
    parser_hyg = subparsers.add_parser("hygiene", help="查询纪律卫生考评记录")
    parser_hyg.add_argument("--page", type=int, default=1, help="页码")
    parser_hyg.add_argument("--show", type=int, help="要查看的考评详情 ID")
    parser_hyg.add_argument("--download", "-d", action="store_true", help="是否下载该考评详情关联的多媒体")
    parser_hyg.add_argument("--out", type=str, default=".", help="指定多媒体文件的下载保存目录")

    # duty command
    parser_duty = subparsers.add_parser("duty", help="查询教师值周安排")
    parser_duty.add_argument("--all", action="store_true", help="展示整学期值周总表")
    parser_duty.add_argument("--search", type=str, help="模糊搜索指定值周教师或值周班级")

    # file command
    parser_file = subparsers.add_parser("file", help="学校文件存取/寄存寄取")
    file_subparsers = parser_file.add_subparsers(dest="action", help="文件操作动作")
    
    # file upload
    parser_upload = file_subparsers.add_parser("upload", help="分片上传本地文件")
    parser_upload.add_argument("path", type=str, help="要上传的本地文件路径")
    
    # file download
    parser_download = file_subparsers.add_parser("download", help="提取并下载远端文件")
    parser_download.add_argument("password", type=str, help="6 位文件提取码")
    parser_download.add_argument("--out", type=str, default=".", help="文件保存下载的本地目录")

    # news command
    parser_news = subparsers.add_parser("news", help="查询校内文章资讯与公告")
    parser_news.add_argument("--column", type=str, default="16", help="栏目ID或别名 (13=新闻聚焦, 16=通知公告, 19=校内公示, 51=值周小结)")
    parser_news.add_argument("--page", type=int, default=1, help="页码")
    parser_news.add_argument("--show", type=int, help="要阅读的文章 ID")
    parser_news.add_argument("--download", "-d", action="store_true", help="是否下载该文章包含的所有附件")
    parser_news.add_argument("--out", type=str, default=".", help="指定附件的下载保存目录")

    # bedroom command
    parser_bed = subparsers.add_parser("bedroom", help="查询班级寝室与宿舍卫生考评")
    bed_subparsers = parser_bed.add_subparsers(dest="action", help="查询动作")
    
    # bedroom class
    parser_bed_class = bed_subparsers.add_parser("class", help="查询班级使用的寝室号")
    parser_bed_class.add_argument("grade", type=int, choices=[1, 2, 3], help="年级 (1=高一, 2=高二, 3=高三)")
    parser_bed_class.add_argument("ch_class", type=str, help="班级名称或数字")
    
    # bedroom hygiene
    parser_bed_hyg = bed_subparsers.add_parser("hygiene", help="查询宿舍楼宇卫生与纪律扣分表")
    parser_bed_hyg.add_argument("dorm", type=str, help="楼宇名称或ID (如 1=3号楼, 3=5号楼等)")
    parser_bed_hyg.add_argument("--start", type=str, help="开始日期 (格式: YYYY-MM-DD)")
    parser_bed_hyg.add_argument("--end", type=str, help="结束日期 (格式: YYYY-MM-DD)")
    parser_bed_hyg.add_argument("--all", "-a", action="store_true", help="显示该楼宇全部宿舍（包括未扣分宿舍）")

    # lostfound command
    parser_lf = subparsers.add_parser("lostfound", aliases=["lf"], help="查询校园失物招领")
    parser_lf.add_argument("--page", type=int, default=1, help="页码")
    parser_lf.add_argument("--show", type=int, help="要查看的失物招领详情 ID")
    parser_lf.add_argument("--download", "-d", action="store_true", help="是否下载该失物招领关联的图片或多媒体附件")
    parser_lf.add_argument("--out", type=str, default=".", help="指定文件的下载保存目录")

    args = parser.parse_args()

    if args.command == "login":
        cmd_login(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "schedule":
        cmd_schedule(args)
    elif args.command == "messages":
        cmd_messages(args)
    elif args.command == "hygiene":
        cmd_hygiene(args)
    elif args.command == "duty":
        cmd_duty(args)
    elif args.command == "file":
        cmd_file(args)
    elif args.command == "news":
        cmd_news(args)
    elif args.command == "bedroom":
        cmd_bedroom(args)
    elif args.command == "lostfound" or args.command == "lf":
        cmd_lostfound(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()