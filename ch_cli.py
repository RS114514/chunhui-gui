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
import base64
import socket
import sqlite3
import shutil
import tempfile
import glob
import struct
import webbrowser
import datetime
import random
from html.parser import HTMLParser

BASE_URL = "http://10.181.200.3"
SESSION_FILE = os.path.expanduser("~/.ch_cli_session.json")

# 统一设置 Socket 超时为 4 秒，防止离线/无路由时系统级 TCP SYN 长时间挂起
socket.setdefaulttimeout(4)

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
    print(f"{C_GREEN}{C_BOLD}[OK] {msg}{C_RESET}")

def log_info(msg):
    print(f"{C_CYAN}[i] {msg}{C_RESET}")

def log_warn(msg):
    print(f"{C_YELLOW}[!] {msg}{C_RESET}")

def log_error(msg):
    print(f"{C_RED}{C_BOLD}[x] {msg}{C_RESET}")

def check_intranet_connection(timeout=1.5):
    """
    通过 HTTP HEAD 请求检测校园内网主站的真实连通性 (强制直连，绕过本地系统代理)
    """
    try:
        req = urllib.request.Request(f"{BASE_URL}/account/login4Stu/", method="HEAD")
        req.add_header("User-Agent", "Mozilla/5.0")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=timeout):
            return True
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False

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
        try:
            os.chmod(SESSION_FILE, 0o600)
        except Exception:
            pass
        return True
    except Exception as e:
        log_error(f"保存会话文件失败: {e}")
        return False

def clear_session():
    """
    清除本地持久化的会话认证信息
    """
    try:
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)
        return True
    except Exception as e:
        log_error(f"清除会话文件失败: {e}")
        return False

def extract_cookies_from_headers(headers_obj):
    """
    从 HTTP 响应头中提取 Set-Cookie 键值对字典
    """
    cookies = {}
    if not headers_obj:
        return cookies
    raw_list = []
    if hasattr(headers_obj, "get_all"):
        raw_list = headers_obj.get_all("Set-Cookie") or headers_obj.get_all("set-cookie") or []
    elif hasattr(headers_obj, "getlist"):
        raw_list = headers_obj.getlist("Set-Cookie") or []
    elif isinstance(headers_obj, dict):
        val = headers_obj.get("Set-Cookie") or headers_obj.get("set-cookie")
        if isinstance(val, list):
            raw_list = val
        elif val:
            raw_list = [val]
    for item in raw_list:
        parts = item.split(";")[0].strip()
        if "=" in parts:
            k, v = parts.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies

def parse_cookie_str(cookie_str):
    """
    将标准 Cookie 字符串解析为字典
    """
    cookies = {}
    if not cookie_str:
        return cookies
    for part in cookie_str.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies

def make_request(url_path, method="GET", data=None, headers=None, follow_redirects=False):
    url = f"{BASE_URL}{url_path}" if url_path.startswith("/") else url_path
    try:
        parsed = urllib.parse.urlparse(url)
        encoded_path = urllib.parse.quote(urllib.parse.unquote(parsed.path), safe='/:@&=+$,')
        encoded_query = urllib.parse.quote(urllib.parse.unquote(parsed.query), safe='/:@&=+$,?%')
        url = urllib.parse.urlunparse((
            parsed.scheme,
            parsed.netloc,
            encoded_path,
            parsed.params,
            encoded_query,
            parsed.fragment
        ))
    except Exception:
        pass
    if headers is None:
        headers = {}
    
    if "User-Agent" not in headers:
        headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    session_cookies = load_session()
    if "Cookie" not in headers:
        cookie_items = [f"{k}={v}" for k, v in session_cookies.items() if v]
        if cookie_items:
            headers["Cookie"] = "; ".join(cookie_items)
        
    if method == "POST" and "X-CSRFToken" not in headers:
        token = session_cookies.get("csrftoken")
        if not token and "Cookie" in headers:
            parsed_c = parse_cookie_str(headers["Cookie"])
            token = parsed_c.get("csrftoken")
        if token:
            headers["X-CSRFToken"] = token
            
    if method == "POST" and "Referer" not in headers:
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
            
    proxy_handler = urllib.request.ProxyHandler({})
    if follow_redirects:
        opener = urllib.request.build_opener(proxy_handler)
    else:
        opener = urllib.request.build_opener(proxy_handler, NoRedirectHandler)
        
    max_retries = 2
    for attempt in range(max_retries):
        req = urllib.request.Request(url, data=req_data, method=method)
        for k, v in headers.items():
            req.add_header(k, v)
        try:
            with opener.open(req, timeout=3) as resp:
                return resp.status, resp.read(), resp.info()
        except urllib.error.HTTPError as e:
            if e.code in (502, 504) and attempt < max_retries - 1:
                time.sleep(0.5)
                continue
            return e.code, e.read(), e.headers
        except Exception as e:
            if attempt < max_retries - 1 and "timeout" not in str(e).lower():
                time.sleep(0.5)
                continue
            return 0, str(e).encode("utf-8"), {}

def strip_ansi(s):
    if not isinstance(s, str):
        return str(s)
    return re.sub(r'\033\[[0-9;]*m', '', s)

def get_visual_width(s):
    width = 0
    clean_s = strip_ansi(s)
    for char in clean_s:
        if unicodedata.east_asian_width(char) in ('W', 'F'):
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

TUI_INNER_W = 74

def render_box_line(left, fill, right, inner_w=TUI_INNER_W):
    return f"{C_BLUE}{left}{fill * inner_w}{right}{C_RESET}"

def render_row(content, align="left", inner_w=TUI_INNER_W):
    return f"{C_BLUE}│{C_RESET} {pad_text(content, inner_w - 2, align)} {C_BLUE}│{C_RESET}"


def clean_html(text):
    if not text:
        return ""
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
    
    # 提取 <input ... value="xxx"> 中的 value 并替换
    def replace_input(match):
        return match.group(1) or ""
    text = re.sub(r'<input[^>]*value=["\']([^"\']*)["\'][^>]*>', replace_input, text, flags=re.IGNORECASE)
    
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

class HTMLToMarkdown(HTMLParser):
    def __init__(self):
        super().__init__()
        self.output = []
        self.current_line = ""
        self.ignore_data = False
        
        self.bold_depth = 0
        self.italic_depth = 0
        
        self.list_stack = []
        self.tables = []
        
        self.current_href = None
        self.current_link_text = ""

    def write_text(self, text):
        if self.tables and self.tables[-1]['current_cell'] is not None:
            self.tables[-1]['current_cell'] += text
            return
        self.current_line += text

    def ensure_newline(self):
        if self.tables and self.tables[-1]['current_cell'] is not None:
            self.tables[-1]['current_cell'] += "\n"
            return
            
        line = self.current_line.strip()
        if line:
            self.output.append(self.current_line.rstrip())
        elif self.output and self.output[-1] != "":
            self.output.append("")
        self.current_line = ""

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in ('style', 'script'):
            self.ignore_data = True
            return
        if self.ignore_data:
            return
            
        attr_dict = dict(attrs)
        
        if tag == 'table':
            self.tables.append({'rows': [], 'current_row': None, 'current_cell': None})
            return
        elif tag == 'tr':
            if self.tables:
                self.tables[-1]['current_row'] = []
            return
        elif tag in ('td', 'th'):
            if self.tables and self.tables[-1]['current_row'] is not None:
                self.tables[-1]['current_cell'] = ""
            return

        if tag in ('p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'hr'):
            self.ensure_newline()
            
        if tag == 'h1':
            self.write_text("# ")
        elif tag == 'h2':
            self.write_text("## ")
        elif tag == 'h3':
            self.write_text("### ")
        elif tag in ('h4', 'h5', 'h6'):
            self.write_text("#### ")
            
        elif tag in ('strong', 'b'):
            self.bold_depth += 1
            self.write_text("**")
        elif tag in ('em', 'i'):
            self.italic_depth += 1
            self.write_text("*")
            
        elif tag in ('ul', 'ol'):
            self.list_stack.append((tag, 0))
        elif tag == 'li':
            if self.list_stack:
                list_type, count = self.list_stack[-1]
                if list_type == 'ol':
                    count += 1
                    self.list_stack[-1] = (list_type, count)
                    prefix = "  " * (len(self.list_stack) - 1) + f"{count}. "
                else:
                    prefix = "  " * (len(self.list_stack) - 1) + "- "
                self.write_text(prefix)
                
        elif tag == 'a':
            self.current_href = attr_dict.get('href')
            self.current_link_text = ""
            self.write_text("[")
            
        elif tag == 'img':
            src = attr_dict.get('src')
            alt = attr_dict.get('alt', '图片')
            if src:
                if "Logo" not in src and "newFunc" not in src and "sydw" not in src:
                    full_url = src.strip()
                    if not full_url.startswith("http"):
                        if full_url.startswith("/"):
                            full_url = f"{BASE_URL}{full_url}"
                        else:
                            full_url = f"{BASE_URL}/{full_url}"
                    self.write_text(f"![{alt}]({full_url})")
                    
        elif tag == 'br':
            self.ensure_newline()
            
        elif tag == 'hr':
            self.ensure_newline()
            self.write_text("---")
            self.ensure_newline()

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ('style', 'script'):
            self.ignore_data = False
            return
        if self.ignore_data:
            return
            
        if tag == 'table':
            if self.tables:
                table_data = self.tables.pop()
                rendered = self.render_md_table(table_data['rows'])
                if rendered:
                    self.ensure_newline()
                    for line in rendered.split('\n'):
                        self.output.append(line)
                    self.ensure_newline()
            return
        elif tag == 'tr':
            if self.tables and self.tables[-1]['current_row'] is not None:
                row = self.tables[-1]['current_row']
                self.tables[-1]['rows'].append(row)
                self.tables[-1]['current_row'] = None
            return
        elif tag in ('td', 'th'):
            if self.tables and self.tables[-1]['current_row'] is not None:
                cell_text = self.tables[-1].get('current_cell', "")
                self.tables[-1]['current_row'].append(cell_text.strip().replace("\n", " ").replace("|", "\\|"))
                self.tables[-1]['current_cell'] = None
            return

        if tag in ('p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li'):
            self.ensure_newline()
            
        if tag in ('strong', 'b'):
            self.bold_depth = max(0, self.bold_depth - 1)
            self.write_text("**")
        elif tag in ('em', 'i'):
            self.italic_depth = max(0, self.italic_depth - 1)
            self.write_text("*")
            
        elif tag in ('ul', 'ol'):
            if self.list_stack:
                self.list_stack.pop()
            self.ensure_newline()
            
        elif tag == 'a':
            if self.current_href:
                href = self.current_href.strip()
                if href and href != "#" and "javascript:" not in href:
                    full_url = href
                    if not href.startswith("http"):
                        if href.startswith("/"):
                            full_url = f"{BASE_URL}{href}"
                        else:
                            full_url = f"{BASE_URL}/{full_url}"
                    self.write_text(f"]({full_url})")
                else:
                    self.write_text("]")
            else:
                self.write_text("]")
            self.current_href = None
            self.current_link_text = ""

    def handle_data(self, data):
        if self.ignore_data:
            return
        if self.current_href is not None:
            self.current_link_text += data
            
        data_clean = re.sub(r'\s+', ' ', data)
        
        if self.tables and self.tables[-1]['current_cell'] is not None:
            buf = self.tables[-1]['current_cell']
        else:
            buf = self.current_line
            
        if data_clean == ' ':
            if not buf or buf[-1] in (' ', '\n') or buf.endswith(' '):
                return
                
        if data_clean.startswith(' '):
            if not buf or buf[-1] in (' ', '\n') or buf.endswith(' '):
                data_clean = data_clean[1:]
                
        if data_clean:
            self.write_text(data_clean)

    def handle_entityref(self, name):
        if self.ignore_data:
            return
        entity_map = {
            'nbsp': ' ', 'lt': '<', 'gt': '>', 'amp': '&', 'quot': '"', 'apos': "'"
        }
        val = entity_map.get(name, f"&{name};")
        self.write_text(val)
        
    def handle_charref(self, name):
        if self.ignore_data:
            return
        try:
            val = chr(int(name[1:], 16)) if name.startswith('x') else chr(int(name))
            self.write_text(val)
        except:
            pass

    def get_visual_width(self, s):
        import unicodedata
        clean_s = s.replace("**", "").replace("*", "")
        width = 0
        for char in clean_s:
            if unicodedata.east_asian_width(char) in ('W', 'F'):
                width += 2
            else:
                width += 1
        return width

    def render_md_table(self, rows):
        if not rows:
            return ""
        num_cols = max(len(row) for row in rows)
        if num_cols == 0:
            return ""
            
        for row in rows:
            while len(row) < num_cols:
                row.append("")
                
        # 计算每一列的最大视觉宽度
        col_widths = []
        for c in range(num_cols):
            widths = []
            for row in rows:
                widths.append(self.get_visual_width(row[c]))
            col_widths.append(max(max(widths), 3))
            
        lines = []
        
        # 格式化一行
        def format_row(row):
            parts = []
            for c, val in enumerate(row):
                w = self.get_visual_width(val)
                pad = col_widths[c] - w
                parts.append(val + " " * pad)
            return "| " + " | ".join(parts) + " |"
            
        # 1. 渲染表头
        lines.append(format_row(rows[0]))
        
        # 2. 渲染分割线
        sep_parts = []
        for w in col_widths:
            sep_parts.append("-" * w)
        sep_line = "| " + " | ".join(sep_parts) + " |"
        lines.append(sep_line)
        
        # 3. 渲染数据行
        for row in rows[1:]:
            lines.append(format_row(row))
            
        return "\n".join(lines)

    def get_markdown(self):
        if self.current_line.strip():
            self.output.append(self.current_line.rstrip())
            
        cleaned = []
        for line in self.output:
            if line.strip() == "":
                if cleaned and cleaned[-1] != "":
                    cleaned.append("")
            else:
                cleaned.append(line)
                
        while cleaned and cleaned[0] == "":
            cleaned.pop(0)
        while cleaned and cleaned[-1] == "":
            cleaned.pop()
            
        return "\n".join(cleaned)

def render_html_to_markdown(html):
    if not html:
        return ""
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    parser = HTMLToMarkdown()
    try:
        parser.feed(html)
        return parser.get_markdown()
    except Exception as e:
        return clean_html(html)

def colorize_markdown(md_text):
    lines = []
    for line in md_text.split('\n'):
        if line.startswith('# '):
            line = f"{C_BOLD}{C_GREEN}{line}{C_RESET}"
        elif line.startswith('## '):
            line = f"{C_BOLD}{C_GREEN}{line}{C_RESET}"
        elif line.startswith('### '):
            line = f"{C_BOLD}{C_CYAN}{line}{C_RESET}"
        elif line.startswith('#### '):
            line = f"{C_BOLD}{C_CYAN}{line}{C_RESET}"
            
        line = re.sub(r'\!\[(.*?)\]\((.*?)\)', f"{C_YELLOW}[图片: \\1 - \\2]{C_RESET}", line)
        line = re.sub(r'\[(.*?)\]\((.*?)\)', f"\\1 ({C_CYAN}\\2{C_RESET})", line)
        line = re.sub(r'\*\*(.*?)\*\*', f"{C_BOLD}\\1{C_RESET}", line)
        
        if '|' in line:
            if '---' in line:
                line = f"{C_BLUE}{line}{C_RESET}"
            else:
                line = line.replace('|', f"{C_BLUE}|{C_RESET}")
                
        lines.append(line)
    return '\n'.join(lines)

def render_html_content(html):
    md_text = render_html_to_markdown(html)
    return colorize_markdown(md_text)

def clean_content_html(raw_html):
    """
    清洗并规范化详情正文 HTML，将相对图片与超链接补齐为校园内网绝对路径，
    并提取包含的所有正文图片列表。
    """
    if not raw_html:
        return "", []
        
    s = re.sub(r'<script[^>]*>.*?</script>', '', raw_html, flags=re.DOTALL | re.IGNORECASE)
    s = re.sub(r'<style[^>]*>.*?</style>', '', s, flags=re.DOTALL | re.IGNORECASE)
    
    images = []
    
    def replace_img(match):
        tag = match.group(0)
        src_m = re.search(r'src=["\'](.*?)["\']', tag, re.IGNORECASE)
        if not src_m:
            return tag
        src = src_m.group(1).strip()
        if any(k in src for k in ("Logo", "newFunc", "sydw")):
            return ""
        full_url = src
        if not full_url.startswith("http"):
            if full_url.startswith("/"):
                full_url = f"{BASE_URL}{full_url}"
            else:
                full_url = f"{BASE_URL}/{full_url}"
                
        alt_m = re.search(r'alt=["\'](.*?)["\']', tag, re.IGNORECASE)
        alt = alt_m.group(1).strip() if alt_m else ""
        fn = urllib.parse.unquote(full_url.split('/')[-1].split('?')[0])
        
        if not any(item["url"] == full_url for item in images):
            images.append({"url": full_url, "name": fn, "alt": alt or fn})
            
        svg_fallback = "data:image/svg+xml;utf8,<svg xmlns=\'http://www.w3.org/2000/svg\' width=\'320\' height=\'110\' viewBox=\'0 0 320 110\'><rect width=\'100%25\' height=\'100%25\' fill=\'%23f8fafc\' stroke=\'%23cbd5e1\' stroke-dasharray=\'4\' rx=\'8\'/><text x=\'50%25\' y=\'45%25\' dominant-baseline=\'middle\' text-anchor=\'middle\' fill=\'%2364748b\' font-size=\'13\' font-family=\'sans-serif\'>🖼️ 校园内网图片</text><text x=\'50%25\' y=\'72%25\' dominant-baseline=\'middle\' text-anchor=\'middle\' fill=\'%2394a3b8\' font-size=\'11\' font-family=\'sans-serif\'>（请连接春晖内网加载查看）</text></svg>"
        return f'<img src="{full_url}" alt="{alt}" loading="lazy" class="rich-content-img" onclick="openLightbox(\'{full_url}\', \'{alt or fn}\')" onerror="this.onerror=null; this.src=\'{svg_fallback}\';" />'
        
    s = re.sub(r'<img[^>]*>', replace_img, s, flags=re.IGNORECASE)
    
    def replace_a(match):
        tag = match.group(0)
        href_m = re.search(r'href=["\'](.*?)["\']', tag, re.IGNORECASE)
        if not href_m:
            return tag
        href = href_m.group(1).strip()
        if not href or href == "#" or "javascript:" in href:
            return tag
        if not href.startswith("http"):
            full_href = f"{BASE_URL}{href}" if href.startswith("/") else f"{BASE_URL}/{href}"
            return tag[:href_m.start(1)] + full_href + tag[href_m.end(1):]
        return tag
        
    s = re.sub(r'<a[^>]*>', replace_a, s, flags=re.IGNORECASE)
    
    return s.strip(), images

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

def sanitize_output_filename(filename, fallback):
    if filename is None:
        filename = ""
    filename = urllib.parse.unquote(str(filename)).replace("\x00", "").strip()
    filename = filename.replace("\\", "/")
    parts = [part for part in filename.split("/") if part not in ("", ".", "..")]
    safe_name = parts[-1] if parts else ""
    if not safe_name:
        safe_name = fallback
    return safe_name

def download_attachments(attachment_links, out_dir="."):
    if not attachment_links:
        log_warn("该详情页面中未检测到任何可供下载的附件或多媒体。")
        return
        
    log_info(f"发现 {len(attachment_links)} 个可供下载的文件，开始下载...")
    for i, att_url in enumerate(attachment_links):
        filename = att_url.split('/')[-1].split('?')[0]
        filename = sanitize_output_filename(filename, f"attachment_{i+1}")
        
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
                    char_w = 2 if unicodedata.east_asian_width(char) in ('W', 'F') else 1
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
    if not data_obj or not data_obj[0]:
        return
    
    num_cols = len(data_obj[0])
    col_widths = [10] + [16] * (num_cols - 1)
    
    border_line = "+" + "+".join("-" * w for w in col_widths) + "+"
    
    # Top border
    print(f"\n{C_BLUE}{border_line}{C_RESET}")
    
    # Header row
    header_padded = [pad_text(item.replace("★", ""), col_widths[i]) for i, item in enumerate(data_obj[0])]
    print(f"{C_BLUE}|{C_RESET}" + f"{C_BLUE}|{C_RESET}".join(f"{C_BOLD}{C_CYAN}{item}{C_RESET}" for item in header_padded) + f"{C_BLUE}|{C_RESET}")
    
    # Rows
    for row_idx, row in enumerate(data_obj[1:]):
        # Separator line
        print(f"{C_BLUE}{border_line}{C_RESET}")
        
        row_padded = []
        for col_idx, item in enumerate(row):
            item_str = str(item).strip()
            
            is_starred = "★" in item_str
            item_str = item_str.replace("★", "")
            
            if not item_str:
                item_str = "-"
            
            max_w = col_widths[col_idx] if col_idx < len(col_widths) else 16
            vis_w = get_visual_width(item_str)
            if vis_w > max_w:
                truncated = ""
                curr_w = 0
                for char in item_str:
                    char_w = 2 if unicodedata.east_asian_width(char) in ('W', 'F') else 1
                    if curr_w + char_w > max_w - 3:
                        break
                    truncated += char
                    curr_w += char_w
                item_str = truncated + "..."
                
            padded = pad_text(item_str, max_w)
            
            if col_idx == 0:
                row_padded.append(f"{C_BOLD}{C_GREEN}{padded}{C_RESET}")
            else:
                if is_starred:
                    row_padded.append(f"{C_YELLOW}{padded}{C_RESET}")
                elif item_str == "-":
                    row_padded.append(f"{C_GREY}{padded}{C_RESET}")
                else:
                    row_padded.append(f"{padded}")
                    
        print(f"{C_BLUE}|{C_RESET}" + f"{C_BLUE}|{C_RESET}".join(row_padded) + f"{C_BLUE}|{C_RESET}")
        
    # Bottom border
    print(f"{C_BLUE}{border_line}{C_RESET}")

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
    if class_query is None or not str(class_query).strip():
        return None
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
# ======================================================================
# 结构化数据接口 (供 CLI 终端交互与外部客户端 GUI 统一调用)
# ======================================================================

def fetch_messages(page=1):
    """获取收件箱信件列表"""
    url = f"/sitemessage/message-Receive-list/?page={page}"
    status, body, _ = make_request(url, method="GET")
    if status == 0:
        return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
    if status == 302:
        return {"success": False, "need_login": True, "error": "尚未登录或登录已失效，请先登录校园网账号"}
    if status != 200:
        return {"success": False, "error": f"获取收件箱列表失败 (HTTP {status})"}
        
    html_content = body.decode("utf-8", errors="ignore")
    if "login4Stu" in html_content and "show-Message" not in html_content:
        return {"success": False, "need_login": True, "error": "尚未登录或登录已失效，请先登录校园网账号"}
        
    tr_pattern = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL)
    trs = tr_pattern.findall(html_content)
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
            title = ""
            sender = ""
            date = ""
            title_idx = -1
            for idx, td in enumerate(tds):
                if "show-Message" in td:
                    title_idx = idx
                    title = clean_html(td)
                    break
            if title_idx != -1:
                if title_idx + 1 < len(tds):
                    sender = clean_html(tds[title_idx + 1])
                if title_idx + 2 < len(tds):
                    date = clean_html(tds[title_idx + 2])
            elif len(tds) >= 3:
                title = clean_html(tds[1])
                sender = clean_html(tds[2])
                date = clean_html(tds[3]) if len(tds) > 3 else ""
            is_unread = ("未阅" in tr or "未读" in tr or "font-weight" in tr or "red" in tr)
            rows.append({
                "id": msg_id,
                "title": title,
                "sender": sender,
                "time": date,
                "date": date,
                "unread": is_unread
            })
    return {"success": True, "data": rows, "page": page}

def fetch_message_detail(msg_id):
    """获取指定收件箱信件正文与附件"""
    status, body, _ = make_request(f"/sitemessage/show-Message/{msg_id}/", method="GET")
    if status == 0:
        return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
    if status == 302:
        return {"success": False, "need_login": True, "error": "尚未登录或登录已失效，请先登录校园网账号"}
    if status != 200:
        return {"success": False, "error": f"获取信件详情失败 (HTTP {status})"}
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
    if not content_m:
        content_m = re.search(r'<div class="ArticleContent[^>]*>(.*?)</div>', html_content, re.DOTALL)
    raw_content_html = content_m.group(1) if content_m else ""
    if raw_content_html:
        content = render_html_content(raw_content_html)
    content_html, content_images = clean_content_html(raw_content_html)
            
    recipients_all = "无"
    rec1_m = re.search(r'id="multiCollapseExample1">\s*<div class="card card-body">\s*(.*?)\s*</div>', html_content, re.DOTALL)
    if rec1_m:
        recipients_all = clean_html(rec1_m.group(1))
        
    recipients_unread = "无"
    rec2_m = re.search(r'id="multiCollapseExample2">\s*<div class="card card-body">\s*(.*?)\s*</div>', html_content, re.DOTALL)
    if rec2_m:
        recipients_unread = clean_html(rec2_m.group(1))
        
    attachment_links = extract_attachment_links(html_content)
    attachments = []
    for att_url in attachment_links:
        fname = urllib.parse.unquote(att_url.split('/')[-1].split('?')[0])
        attachments.append({"name": fname, "url": att_url})
        
    images = list(content_images)
    for att in attachments:
        att_url = att["url"]
        if any(att_url.lower().endswith(ext) for ext in ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')):
            if not any(item["url"] == att_url for item in images):
                images.append({"url": att_url, "name": att["name"], "alt": att["name"]})
        
    return {
        "success": True,
        "data": {
            "id": str(msg_id),
            "title": title,
            "sender": sender,
            "time": send_time,
            "content": content,
            "content_html": content_html,
            "images": images,
            "recipients_all": recipients_all,
            "recipients_unread": recipients_unread,
            "attachments": attachments
        }
    }

def fetch_news(column="16", page=1):
    """获取校内公告与资讯列表 (16=通知公告, 13=新闻聚焦, 19=校内公示, 51=值周小结)"""
    col_mapping = {
        "news": "13",
        "notice": "19",
        "announcement": "16",
        "duty": "51"
    }
    col_id = col_mapping.get(str(column), str(column))
    status, body, _ = make_request(f"/article/column-detail/{col_id}/?page={page}", method="GET", follow_redirects=True)
    if status == 0:
        return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
    if status != 200:
        return {"success": False, "error": f"获取资讯列表失败 (HTTP {status})"}
    html_content = body.decode("utf-8", errors="ignore")
    items = re.findall(r'href=["\']/article/article-detail/(\d+)/["\'][^>]*>\s*(.*?)\s*</a>.*?class="[^"]*text-secondary"[^>]*>\s*(.*?)\s*</div>', html_content, re.DOTALL)
    if not items:
        items = re.findall(r'<div class="ArticleTitle">\s*<a href="/article/article-detail/(\d+)/"[^>]*>(.*?)</a>\s*</div>.*?<div class="ArticleTime">(.*?)</div>', html_content, re.DOTALL)
    rows = []
    for art_id, title, date in items:
        rows.append({
            "id": art_id,
            "title": clean_html(title),
            "date": clean_html(date)
        })
    return {"success": True, "data": rows, "page": page, "column": col_id}

def fetch_news_detail(article_id):
    """获取校内资讯与文章详情正文及附件"""
    status, body, _ = make_request(f"/article/article-detail/{article_id}/", method="GET", follow_redirects=True)
    if status == 0:
        return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
    if status != 200:
        return {"success": False, "error": f"获取文章详情失败 (HTTP {status})"}
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
    raw_content_html = content_m.group(1) if content_m else ""
    if raw_content_html:
        content = render_html_content(raw_content_html)
    content_html, content_images = clean_content_html(raw_content_html)
        
    attachment_links = extract_attachment_links(html_content)
    attachments = []
    for att_url in attachment_links:
        fname = urllib.parse.unquote(att_url.split('/')[-1].split('?')[0])
        attachments.append({"name": fname, "url": att_url})
        
    images = list(content_images)
    for att in attachments:
        att_url = att["url"]
        if any(att_url.lower().endswith(ext) for ext in ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')):
            if not any(item["url"] == att_url for item in images):
                images.append({"url": att_url, "name": att["name"], "alt": att["name"]})

    return {
        "success": True,
        "data": {
            "id": str(article_id),
            "title": title,
            "source": source,
            "time": pub_time,
            "content": content,
            "content_html": content_html,
            "images": images,
            "attachments": attachments
        }
    }

def fetch_classes(grade_id):
    """根据年级ID (1=高一, 2=高二, 3=高三) 获取全部班级列表"""
    status, body, _ = make_request("/subjectArrangement/getClassFromGradeForSelect/", method="POST", data={"theGradeID": grade_id})
    if status == 0:
        return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
    if status != 200:
        return {"success": False, "error": f"获取班级列表失败 (HTTP {status})"}
    try:
        classes = json.loads(body.decode("utf-8"))
        return {"success": True, "data": classes}
    except Exception as e:
        return {"success": False, "error": f"解析班级列表异常: {e}"}

def fetch_schedule(grade_id, class_id):
    """获取指定班级的周课表矩阵和任课教师列表"""
    data_post = {
        "chGradeIDForName": grade_id,
        "chClassIDForName": class_id
    }
    status, body_html, _ = make_request("/subjectArrangement/ClassClassArrangement_JustForView/", method="POST", data=data_post)
    if status == 0:
        return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
    if status != 200:
        return {"success": False, "error": f"查询课表失败 (HTTP {status})"}
    html_content = body_html.decode("utf-8", errors="ignore")
    match = re.search(r'dataObj\s*=\s*(\[\[.*?\]\])\s*;', html_content)
    if not match:
        return {"success": False, "error": "页面中未找到课表数据矩阵 (可能未排课)"}
    try:
        data_obj = json.loads(match.group(1))
    except Exception as e:
        return {"success": False, "error": f"解析课表矩阵异常: {e}"}
        
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

def fetch_hygiene(page=1):
    """获取常规纪律卫生检查记录列表"""
    url = f"/classappraise/hygienePictures_receive_list/?page={page}"
    status, body, _ = make_request(url, method="GET")
    if status == 0:
        return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
    if status != 200:
        return {"success": False, "error": f"获取考评记录失败 (HTTP {status})"}
    html_content = body.decode("utf-8", errors="ignore")
    tr_pattern = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL)
    trs = tr_pattern.findall(html_content)
    rows = []
    for tr in trs:
        if "show-Message" in tr:
            id_m = re.search(r'/classappraise/show-Message/(\d+)/\s*', tr)
            rec_id = id_m.group(1) if id_m else ""
            tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL)
            if len(tds) >= 4:
                location = clean_html(tds[1])
                desc = clean_html(tds[2])
                date = clean_html(tds[3])
                rows.append({"id": rec_id, "location": location, "desc": desc, "date": date})
    return {"success": True, "data": rows, "page": page}

def fetch_hygiene_detail(record_id):
    """获取考评多媒体现场记录及通报情况"""
    status, body, _ = make_request(f"/classappraise/show-Message/{record_id}/", method="GET")
    if status == 0:
        return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
    if status != 200:
        return {"success": False, "error": f"获取考评详情失败 (HTTP {status})"}
    html_content = body.decode("utf-8", errors="ignore")
    desc = "未知违纪描述"
    m = re.search(r'<div class="ArticleContent[^>]*>(.*?)</div>', html_content, re.DOTALL)
    raw_content_html = m.group(1) if m else ""
    if raw_content_html:
        desc = render_html_content(raw_content_html)
    content_html, content_images = clean_content_html(raw_content_html)
    
    media_urls = []
    images = list(content_images)
    for img in re.findall(r'<img[^>]+src=["\'](.*?)["\']', html_content):
        if not any(k in img for k in ("Logo", "newFunc", "sydw")):
            full = img if img.startswith("http") else f"{BASE_URL}{img}" if img.startswith("/") else f"{BASE_URL}/{img}"
            if full not in [item["url"] for item in media_urls]:
                media_urls.append({"type": "image", "url": full})
            fn = urllib.parse.unquote(full.split('/')[-1].split('?')[0])
            if not any(item["url"] == full for item in images):
                images.append({"url": full, "name": fn, "alt": fn})
    for vid in re.findall(r'<video[^>]+src=["\'](.*?)["\']', html_content):
        full = vid if vid.startswith("http") else f"{BASE_URL}{vid}" if vid.startswith("/") else f"{BASE_URL}/{vid}"
        if full not in [item["url"] for item in media_urls]:
            media_urls.append({"type": "video", "url": full})
    recipients_all = "无"
    m = re.search(r'id="multiCollapseExample1">\s*<div class="card card-body">\s*(.*?)\s*</div>', html_content, re.DOTALL)
    if m:
        recipients_all = clean_html(m.group(1))
    recipients_unread = "无"
    m = re.search(r'id="multiCollapseExample2">\s*<div class="card card-body">\s*(.*?)\s*</div>', html_content, re.DOTALL)
    if m:
        recipients_unread = clean_html(m.group(1))
    return {
        "success": True,
        "data": {
            "id": str(record_id),
            "desc": desc,
            "content": desc,
            "content_html": content_html,
            "images": images,
            "media_urls": media_urls,
            "recipients_all": recipients_all,
            "recipients_unread": recipients_unread
        }
    }

def fetch_dorm_hygiene(dorm="1", start="", end="", show_all=False):
    """查询宿舍楼宇考评扣分总表 (dorm 1~9 对应 3号楼~11号楼)"""
    dorm_id, dorm_name = resolve_dorm(dorm)
    if not start:
        start = time.strftime("%Y-%m-%d", time.localtime(time.time() - 30 * 86400))
    if not end:
        end = time.strftime("%Y-%m-%d")
    post_data = {
        "chDormitoryForName": dorm_id,
        "theBeginDateForName": start,
        "theEndDateForName": end
    }
    status, body, _ = make_request("/classappraise/BedRoom_DisciplineHygiene_JustForView/", method="POST", data=post_data)
    if status == 0:
        return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
    if status != 200:
        return {"success": False, "error": f"查询宿舍考评失败 (HTTP {status})"}
    html_content = body.decode("utf-8", errors="ignore")
    tr_pattern = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL)
    trs = tr_pattern.findall(html_content)
    rows = []
    for tr in trs:
        tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL)
        if len(tds) >= 4:
            room = clean_html(tds[0])
            cls_name = clean_html(tds[1])
            hyg = clean_html(tds[2])
            disc = clean_html(tds[3])
            total = clean_html(tds[4]) if len(tds) > 4 else ""
            if not show_all and (not total or total.strip() in ("", "0")):
                continue
            rows.append({
                "room": room,
                "class": cls_name,
                "hygiene": hyg or "-",
                "discipline": disc or "-",
                "total": total or "-"
            })
    return {"success": True, "data": rows, "dorm": dorm_id, "dorm_name": dorm_name, "start": start, "end": end}

def fetch_dorm_class(grade_id, class_name):
    """查询班级寝室分配对应"""
    res = find_class_id(int(grade_id), class_name)
    if not res:
        return {"success": False, "error": f"在所选年级中未找到班级: {class_name}"}
    class_id, resolved_name = res
    post_data = {
        "chGradeIDForName": grade_id,
        "chClassIDForName": class_id
    }
    status, body, _ = make_request("/classappraise/QueryBedroomsByClassID_JustForView/", method="POST", data=post_data)
    if status == 0:
        return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
    if status != 200:
        return {"success": False, "error": f"查询班级寝室失败 (HTTP {status})"}
    html_content = body.decode("utf-8", errors="ignore")
    m = re.search(r'class="alert alert-primary"[^>]*>\s*(.*?)\s*</div>', html_content, re.DOTALL)
    if m:
        info = clean_html(m.group(1))
        return {"success": True, "class_name": resolved_name, "info": info}
    return {"success": True, "class_name": resolved_name, "info": "该班级暂未登记寝室分配数据"}

def fetch_duty():
    """获取教师行政值周周次排班总表"""
    status, body, _ = make_request("/classappraise/TeacherDutyWeek_JustForView/", method="GET")
    if status == 0:
        return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
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

def fetch_lostfound(page=1):
    """获取失物招领列表"""
    status, body, _ = make_request(f"/lostAndFound/lostAndFoundList/?page={page}", method="GET", follow_redirects=True)
    if status == 0:
        return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
    if status != 200:
        return {"success": False, "error": f"获取失物招领列表失败 (HTTP {status})"}
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
            title_m = re.search(r'<a[^>]*>(.*?)</a>', tds[2], re.DOTALL)
            title = clean_html(title_m.group(1) if title_m else tds[2])
            category = clean_html(tds[1])
            reporter = clean_html(tds[3])
            start_date = clean_html(tds[6])
            status_text = clean_html(tds[8]) if len(tds) > 8 else ""
            rows.append({
                "id": lf_id,
                "category": category,
                "title": title,
                "reporter": reporter,
                "date": start_date,
                "status": status_text
            })
    return {"success": True, "data": rows, "page": page}

def fetch_lostfound_detail(item_id):
    """获取失物招领详细说明与认领联系方式"""
    status, body, _ = make_request(f"/lostAndFound/lostAndFoundDetail/{item_id}/", method="GET", follow_redirects=True)
    if status == 0:
        return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
    if status != 200:
        return {"success": False, "error": f"获取招领详情失败 (HTTP {status})"}
    html_content = body.decode("utf-8", errors="ignore")
    title = "无标题"
    m = re.search(r'<div class="ArticleTitle[^>]*>(.*?)</div>', html_content, re.DOTALL)
    if m:
        title = clean_html(m.group(1))
    reporter = "未知"
    m = re.search(r'来源：\s*([^<]+)', html_content)
    if m:
        reporter = clean_html(m.group(1))
    reviewer = "未知"
    m = re.search(r'审核人：\s*([^<]+)', html_content)
    if m:
        reviewer = clean_html(m.group(1))
    pub_time = "未知"
    m = re.search(r'发布时间：\s*([^\s<]+(?:\s+[^\s<]+)?)', html_content)
    if m:
        pub_time = m.group(1).strip()
    content = ""
    m = re.search(r'<div class="ArticleContent(?:\s+[^>]*|)\s*>(.*?)</div>', html_content, re.DOTALL)
    raw_content_html = m.group(1) if m else ""
    if raw_content_html:
        content = render_html_content(raw_content_html)
    content_html, content_images = clean_content_html(raw_content_html)
    media_urls = []
    images = list(content_images)
    for img in re.findall(r'<img[^>]+src=["\'](.*?)["\']', html_content):
        if "Logo" not in img and "newFunc" not in img and "sydw" not in img:
            full = img if img.startswith("http") else f"{BASE_URL}{img}" if img.startswith("/") else f"{BASE_URL}/{img}"
            if full not in media_urls:
                media_urls.append(full)
            fn = urllib.parse.unquote(full.split('/')[-1].split('?')[0])
            if not any(item["url"] == full for item in images):
                images.append({"url": full, "name": fn, "alt": fn})
    for vid in re.findall(r'<video[^>]+src=["\'](.*?)["\']', html_content):
        full = vid if vid.startswith("http") else f"{BASE_URL}{vid}" if vid.startswith("/") else f"{BASE_URL}/{vid}"
        if full not in media_urls:
            media_urls.append(full)
    for link in extract_attachment_links(html_content):
        if link not in media_urls:
            media_urls.append(link)
    attachments = []
    for u in media_urls:
        fn = urllib.parse.unquote(u.split('/')[-1].split('?')[0])
        attachments.append({"name": fn, "url": u})
        if any(u.lower().endswith(ext) for ext in ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')):
            if not any(item["url"] == u for item in images):
                images.append({"url": u, "name": fn, "alt": fn})
    return {
        "success": True,
        "data": {
            "id": str(item_id),
            "title": title,
            "reporter": reporter,
            "reviewer": reviewer,
            "time": pub_time,
            "content": content,
            "content_html": content_html,
            "images": images,
            "media_urls": media_urls,
            "attachments": attachments
        }
    }

def upload_file_chunked(file_path, progress_callback=None):
    """100MB 逻辑分片上传并返回提取密码"""
    if not os.path.exists(file_path):
        return {"success": False, "error": f"本地文件不存在: {file_path}"}
    if not os.path.isfile(file_path):
        return {"success": False, "error": f"指定路径不是文件: {file_path}"}
    session = load_session()
    if not session.get("sessionid"):
        return {"success": False, "need_login": True, "error": "文件上传需要校园网账号认证，请先登录"}
        
    filename = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    chunk_size = 100 * 1024 * 1024
    total_chunks = (file_size + chunk_size - 1) // chunk_size
    if total_chunks == 0:
        total_chunks = 1
        
    task_id = f"WU_FILE_{uuid.uuid4().hex}"
    try:
        with open(file_path, "rb") as f:
            for chunk_idx in range(total_chunks):
                chunk_data = f.read(chunk_size)
                if progress_callback:
                    progress_callback(chunk_idx + 1, total_chunks, len(chunk_data))
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
                status, resp_body, _ = make_request("/fileaccess/files_upload/", method="POST", data=body, headers=headers)
                if status == 0:
                    return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
                if status != 200:
                    return {"success": False, "error": f"分片 {chunk_idx + 1}/{total_chunks} 上传失败 (HTTP {status})"}
    except Exception as e:
        return {"success": False, "error": f"读取或发送分片文件失败: {e}"}
        
    complete_data = {
        "task_id": task_id,
        "filename": filename
    }
    status_c, resp_c, _ = make_request("/fileaccess/upload_complete/", method="POST", data=complete_data)
    if status_c == 200:
        password = resp_c.decode("utf-8", errors="ignore").strip()
        password = clean_html(password)
        return {"success": True, "code": password, "filename": filename}
    return {"success": False, "error": f"合并文件请求失败 (HTTP {status_c})"}

def fetch_access_file(code):
    """查询 6 位提取码对应的远端文件信息"""
    code = (code or "").strip()
    if len(code) != 6 or not code.isdigit():
        return {"success": False, "error": "请输入有效的 6 位数字取件密码"}
    post_data = {"thePasswordTheUserEntered": code}
    status, body, _ = make_request("/fileaccess/get-AccessFile/", method="POST", data=post_data)
    if status == 0:
        return {"success": False, "error": "未连接到校园内网 (10.181.200.3)"}
    if status != 200:
        return {"success": False, "error": f"查询提取码失败 (HTTP {status})"}
    try:
        res_json = json.loads(body.decode("utf-8"))
        if res_json.get("error") != "0":
            return {"success": False, "error": res_json.get("msg", "提取码不存在、错误或文件已过期")}
        file_path_name = res_json.get("filePathName")
        file_name = res_json.get("fileNameForDisplay")
        if not file_path_name or not file_name:
            return {"success": False, "error": "服务端返回的文件信息不完整"}
        download_url = f"{BASE_URL}/static/fileaccess/{file_path_name}"
        return {
            "success": True,
            "filename": file_name,
            "download_url": download_url,
            "code": code
        }
    except Exception as e:
        return {"success": False, "error": f"解析提取信息异常: {e}"}

# ======================================================================
# CLI 命令实现
# ======================================================================

def cmd_messages(args):
    if args.show:
        msg_id = args.show
        log_info(f"正在查询消息详情 [ID: {msg_id}]...")
        res = fetch_message_detail(msg_id)
        if not res.get("success"):
            log_error(res.get("error"))
            return
        d = res["data"]
        print(f"\n{C_BOLD}{C_GREEN}消息详情 {C_RESET}")
        print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
        print(f"{C_BOLD}标题：{C_RESET} {C_YELLOW}{d['title']}{C_RESET}")
        print(f"{C_BOLD}发送者：{C_RESET} {C_CYAN}{d['sender']}{C_RESET}    |    {C_BOLD}时间：{C_RESET} {C_GREY}{d['time']}{C_RESET}")
        print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
        print(f"{d['content']}")
        print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
        print(f"{C_BOLD}全体收件人：{C_RESET} {d['recipients_all']}")
        print(f"{C_BOLD}未阅收件人：{C_RESET} {C_RED}{d['recipients_unread']}{C_RESET}")
        print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
        
        att_links = [a["url"] for a in d.get("attachments", [])]
        if att_links:
            print(f"{C_BOLD}{C_GREEN}关联附件列表：{C_RESET}")
            for i, a in enumerate(d["attachments"]):
                print(f"  [{i+1}] {C_YELLOW}{a['name']}{C_RESET}")
                print(f"      链接: {C_CYAN}{a['url']}{C_RESET}")
            print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
            
        if args.download:
            download_attachments(att_links, args.out)
            print()
        return

    page = args.page or 1
    log_info(f"正在获取收件箱消息列表 (第 {page} 页)...")
    res = fetch_messages(page)
    if not res.get("success"):
        log_error(res.get("error"))
        return
    rows = res.get("data", [])
    if not rows:
        log_warn("没有找到任何消息记录。")
        return
        
    print(f"\n{C_BOLD}{C_GREEN}收件箱列表 (第 {page} 页) ==={C_RESET}")
    for row in rows:
        msg_id = row["id"]
        title = row["title"]
        sender = row["sender"]
        date = row["time"]
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
            desc = render_html_content(desc_html)
            
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
            
        print(f"\n{C_BOLD}{C_RED}纪律卫生考评详情 {C_RESET}")
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
        
    print(f"\n{C_BOLD}{C_GREEN}纪律卫生考评记录 (第 {page} 页) ==={C_RESET}")
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
            print(f"\n{C_BOLD}{C_CYAN}{d['week']}{curr_tag} ({d['date']}){C_RESET}")
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
            curr_mark = "* " if d["is_current"] else ""
            print(f"{C_BOLD}{week_color}{curr_mark}{week_disp}{C_RESET} ({C_GREY}{d['date']}{C_RESET})")
            print(f"  行政值周: {C_YELLOW}{d['admin']}{C_RESET}  |  值周班级: {C_GREEN}{d['class']}{C_RESET}")
            print(f"  {C_BLUE}┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄{C_RESET}")
        print(f"{C_GREY}提示: 带 * 的代表当前周次。使用 `python3 ch_cli.py duty --search <姓名>` 可模糊搜索。{C_RESET}\n")
        return

    if not current_week:
        log_warn("未在页面中检测到高亮标识的当前周次，默认展示全表。")
        args.all = True
        cmd_duty(args)
        return
        
    print(f"\n{C_BOLD}{C_GREEN}当前值周安排 ({current_week['week']}){C_RESET}")
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
    if not os.path.isfile(file_path):
        log_error(f"指定路径不是文件: {file_path}")
        return
    filename = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    log_info(f"正在准备分片上传文件: {filename} (大小: {file_size} 字节)...")
    def on_prog(chunk_idx, total_chunks, chunk_bytes):
        log_info(f"正在上传分片 {chunk_idx}/{total_chunks} ({chunk_bytes} 字节)...")
    res = upload_file_chunked(file_path, progress_callback=on_prog)
    if not res.get("success"):
        log_error(res.get("error"))
        return
    log_success("文件上传并合并成功！")
    print(f"\n{C_BOLD}文件提取密码：{C_RESET} {C_YELLOW}{C_BOLD}{res['code']}{C_RESET}")
    print(f"{C_GREY}提示: 接收方可通过运行 `python3 ch_cli.py file download {res['code']}` 来提取该文件。{C_RESET}\n")

def cmd_file_download(password, out_dir="."):
    log_info(f"正在查询提取码 [{password}] 对应文件信息...")
    res = fetch_access_file(password)
    if not res.get("success"):
        log_error(res.get("error"))
        return
    file_name = sanitize_output_filename(res["filename"], "downloaded_file")
    out_path = out_dir if out_dir else "."
    if out_path != ".":
        os.makedirs(out_path, exist_ok=True)
    target_path = os.path.join(out_path, file_name)
    log_info(f"匹配到文件: {file_name}，正在拉取数据...")
    status_dl, body_dl, _ = make_request(res["download_url"], method="GET")
    if status_dl == 200:
        try:
            with open(target_path, "wb") as f_dl:
                f_dl.write(body_dl)
            log_success(f"文件已成功保存至: {target_path} (大小: {len(body_dl)} 字节)")
        except Exception as e_dl:
            log_error(f"保存文件 {target_path} 失败: {e_dl}")
    else:
        log_error(f"下载文件失败 (HTTP Code: {status_dl})")

def cmd_file(args):
    if args.action == "upload":
        cmd_file_upload(args.path)
    elif args.action == "download":
        cmd_file_download(args.password, args.out)

def cmd_news(args):
    if args.show:
        msg_id = args.show
        log_info(f"正在查询文章详情 [ID: {msg_id}]...")
        res = fetch_news_detail(msg_id)
        if not res.get("success"):
            log_error(res.get("error"))
            return
        d = res["data"]
        print(f"\n{C_BOLD}{C_GREEN}文章详情 {C_RESET}")
        print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
        print(f"{C_BOLD}标题：{C_RESET} {C_YELLOW}{d['title']}{C_RESET}")
        print(f"{C_BOLD}发布人：{C_RESET} {C_CYAN}{d['source']}{C_RESET}    |    {C_BOLD}时间：{C_RESET} {C_GREY}{d['time']}{C_RESET}")
        print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
        print(f"{d['content']}")
        print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
        
        att_links = [a["url"] for a in d.get("attachments", [])]
        if att_links:
            print(f"{C_BOLD}{C_GREEN}关联附件列表：{C_RESET}")
            for i, a in enumerate(d["attachments"]):
                print(f"  [{i+1}] {C_YELLOW}{a['name']}{C_RESET}")
                print(f"      链接: {C_CYAN}{a['url']}{C_RESET}")
            print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
            
        if args.download:
            download_attachments(att_links, args.out)
            print()
        return

    page = args.page or 1
    log_info(f"正在获取栏目 [{args.column}] 文章列表 (第 {page} 页)...")
    res = fetch_news(args.column, page)
    if not res.get("success"):
        log_error(res.get("error"))
        return
        
    rows = res.get("data", [])
    if not rows:
        log_warn("没有找到任何文章记录。")
        return
        
    print(f"\n{C_BOLD}{C_GREEN}文章列表 (栏目: {args.column}, 第 {page} 页) ==={C_RESET}")
    for item in rows:
        art_id = item["id"]
        title = item["title"]
        date = item["date"]
        print(f"[{C_GREEN}{art_id}{C_RESET}] {C_BOLD}{title}{C_RESET}")
        print(f"      发布日期: {C_GREY}{date}{C_RESET}")
        print(f"      {C_BLUE}┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄{C_RESET}")
    print(f"{C_GREY}提示: 使用 `python3 ch_cli.py news --show <文章ID>` 阅读正文内容。{C_RESET}\n")

DORM_MAPPING = {
    "1": "3号楼", "2": "4号楼", "3": "5号楼", "4": "6号楼",
    "5": "7号楼", "6": "8号楼", "7": "9号楼", "8": "10号楼", "9": "11号楼"
}

def resolve_dorm(dorm_input):
    s = str(dorm_input).strip() if dorm_input is not None else ""
    if not s:
        return "1", DORM_MAPPING["1"]
        
    if s in DORM_MAPPING:
        return s, DORM_MAPPING[s]
        
    for d_id, d_name in sorted(DORM_MAPPING.items(), key=lambda x: len(x[1]), reverse=True):
        if d_name in s or s in d_name:
            return d_id, d_name
            
    m = re.search(r'\d+', s)
    if m:
        num = m.group(0)
        target_building = f"{num}号楼"
        for d_id, d_name in DORM_MAPPING.items():
            if d_name == target_building:
                return d_id, d_name
        if num in DORM_MAPPING:
            return num, DORM_MAPPING[num]
            
    return s, DORM_MAPPING.get(s, f"未知楼宇(ID:{s})")

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
            print(f"\n{C_BOLD}{C_GREEN}寝室分配查询结果 {C_RESET}")
            print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
            print(f"{C_YELLOW}{result_text}{C_RESET}")
            print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}\n")
        else:
            log_warn("未查到该班级的寝室分配数据。")
            
    elif args.action == "hygiene":
        dorm_id, dorm_name = resolve_dorm(args.dorm)
        
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
            
        print(f"\n{C_BOLD}{C_GREEN}{dorm_name} 寝室卫生与纪律扣分考评总表 ==={C_RESET}")
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
        res = fetch_lostfound_detail(msg_id)
        if not res.get("success"):
            log_error(res.get("error"))
            return
        d = res["data"]
        print(f"\n{C_BOLD}{C_GREEN}失物招领详情 {C_RESET}")
        print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
        print(f"{C_BOLD}物品主题：{C_RESET} {C_YELLOW}{d['title']}{C_RESET}")
        print(f"{C_BOLD}登记来源：{C_RESET} {C_CYAN}{d['reporter']}{C_RESET}    |    {C_BOLD}时间：{C_RESET} {C_GREY}{d['time']}{C_RESET}")
        print(f"{C_BOLD}审 核 人：{C_RESET} {d['reviewer']}")
        print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
        print(f"{d['content']}")
        print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
        
        media_urls = [m["url"] for m in d.get("media", [])]
        if media_urls:
            print(f"{C_BOLD}关联文件或多媒体：{C_RESET}")
            for i, m_url in enumerate(media_urls):
                print(f"  [{i+1}] {C_CYAN}{m_url}{C_RESET}")
            print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
            
        if args.download:
            download_attachments(media_urls, args.out)
            print()
        return

    page = args.page or 1
    log_info(f"正在获取全校失物招领列表 (第 {page} 页)...")
    res = fetch_lostfound(page)
    if not res.get("success"):
        log_error(res.get("error"))
        return
        
    rows = res.get("data", [])
    if not rows:
        log_warn("没有找到任何失物招领记录。")
        return
        
    print(f"\n{C_BOLD}{C_GREEN}全校失物招领列表 (第 {page} 页) ==={C_RESET}")
    for item in rows:
        lf_id = item["id"]
        category = item["category"]
        title = item["title"]
        reporter = item["reporter"]
        start_date = item["date"]
        status_text = item["status"]
        cat_color = C_YELLOW if "丢" in category else C_GREEN
        status_color = C_RED if "未" in status_text or "处理中" in status_text else C_GREY
        print(f"[{C_GREEN}{lf_id}{C_RESET}] {C_BOLD}{cat_color}[{category}]{C_RESET} {title}")
        print(f"      发布处: {C_CYAN}{reporter}{C_RESET}  |  日期: {C_GREY}{start_date}{C_RESET}  |  状态: {status_color}{status_text}{C_RESET}")
        print(f"      {C_BLUE}┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄{C_RESET}")
    print(f"{C_GREY}提示: 使用 `python3 ch_cli.py lostfound --show <ID>` 查看招领联系方式等详情。{C_RESET}\n")

# ==============================================================================
# 模块：白马湖每日简报、课堂抽签点名与校园内网导航
# ==============================================================================

_LUNAR_TABLE = [
    0x04bd8,0x04ae0,0x0a570,0x054d5,0x0d260,0x0d950,0x16554,0x056a0,0x09ad0,0x055d2,
    0x04ae0,0x0a5b6,0x0a4d0,0x0d250,0x1d255,0x0b540,0x0d6a0,0x0ada2,0x095b0,0x14977,
    0x04970,0x0a4b0,0x0b4b5,0x06a50,0x06d40,0x1ab54,0x02b60,0x09570,0x052f2,0x04970,
    0x06566,0x0d4a0,0x0ea50,0x06e95,0x05ad0,0x02b60,0x186e3,0x092e0,0x1c8d7,0x0c950,
    0x0d4a0,0x1d8a6,0x0b550,0x056a0,0x1a5b4,0x025d0,0x092d0,0x0d2b2,0x0a950,0x0b557,
    0x06ca0,0x0b550,0x15355,0x04da0,0x0a5d0,0x14573,0x052d0,0x0a9a8,0x0e950,0x06aa0,
    0x0aea6,0x0ab50,0x04b60,0x0aae4,0x0a570,0x05260,0x0f263,0x0d950,0x05b57,0x056a0,
    0x096d0,0x04dd5,0x04ad0,0x0a4d0,0x0d4d4,0x0d250,0x0d558,0x0b540,0x0b5a0,0x195a6,
    0x095b0,0x049b0,0x0a974,0x0a4b0,0x0b27a,0x06a50,0x06d40,0x0af46,0x0ab60,0x09570,
    0x04af5,0x04970,0x064b0,0x074a3,0x0ea50,0x06b58,0x055c0,0x0ab60,0x096d5,0x092e0,
    0x0c960,0x0d954,0x0d4a0,0x0da50,0x07552,0x056a0,0x0abb7,0x025d0,0x092d0,0x0cab5,
    0x0a950,0x0b4a0,0x0baa4,0x0ad50,0x055d9,0x04ba0,0x0a5b0,0x15176,0x052b0,0x0a930,
    0x07954,0x06aa0,0x0ad50,0x05b52,0x04b60,0x0a6e6,0x0a4e0,0x0d260,0x0ea65,0x0d530,
    0x05aa0,0x076a3,0x096d0,0x04bd7,0x04ad0,0x0a4d0,0x1d0b6,0x0d250,0x0d520,0x0dd45,
    0x0b5a0,0x056d0,0x055b2,0x049b0,0x0a577,0x0a4b0,0x0aa50,0x1b255,0x06d20,0x0ada0,
    0x14b63
]

_TIANGAN = ['甲','乙','丙','丁','戊','己','庚','辛','壬','癸']
_DIZHI = ['子','丑','寅','卯','辰','巳','午','未','申','酉','戌','亥']
_SHENGXIAO = ['鼠','牛','虎','兔','龙','蛇','马','羊','猴','鸡','狗','猪']
_LUNAR_MONTHS = ['正','二','三','四','五','六','七','八','九','十','冬','腊']
_LUNAR_DAYS = [
    '初一','初二','初三','初四','初五','初六','初七','初八','初九','初十',
    '十一','十二','十三','十四','十五','十六','十七','十八','十九','二十',
    '廿一','廿二','廿三','廿四','廿五','廿六','廿七','廿八','廿九','三十'
]

def get_lunar_date_str(d=None):
    if d is None:
        d = datetime.date.today()
    elif hasattr(d, "date"):
        d = d.date()
    base_date = datetime.date(1900, 1, 31)
    offset = (d - base_date).days
    l_year = 1900
    for i in range(1900, 2050):
        code = _LUNAR_TABLE[i - 1900]
        days_in_year = 0
        for m in range(12):
            days_in_year += 30 if (code & (0x10000 >> (m + 1))) else 29
        leap_month = code & 0xf
        if leap_month > 0:
            days_in_year += 30 if (code & 0x10000) else 29
        if offset < days_in_year:
            l_year = i
            break
        offset -= days_in_year

    code = _LUNAR_TABLE[l_year - 1900]
    leap_month = code & 0xf
    is_leap = False
    l_month = 1
    for m in range(1, 13):
        days_in_month = 30 if (code & (0x10000 >> m)) else 29
        if offset < days_in_month:
            l_month = m
            break
        offset -= days_in_month
        if leap_month == m:
            leap_days = 30 if (code & 0x10000) else 29
            if offset < leap_days:
                is_leap = True
                l_month = m
                break
            offset -= leap_days
    l_day = offset + 1
    tg = _TIANGAN[(l_year - 4) % 10]
    dz = _DIZHI[(l_year - 4) % 12]
    sx = _SHENGXIAO[(l_year - 4) % 12]
    m_str = ('闰' if is_leap else '') + _LUNAR_MONTHS[l_month - 1] + '月'
    d_str = _LUNAR_DAYS[l_day - 1]
    return f"{tg}{dz}{sx}年 {m_str}{d_str}"

_FALLBACK_QUOTES = [
    {"quote": "世间好物不坚牢，彩云易散琉璃脆。", "author": "杨绛"},
    {"quote": "如果方向一致，两个命中注定要结伴同行的过客是不会擦肩而过的。", "author": "《他们最幸福》"},
    {"quote": "每一天和每个微不足道的成绩都是一种礼物。", "author": "卡夫卡"},
    {"quote": "表面看似幸福的生命可能是空虚的，而一个表面看似艰难的生活可能致力于一项伟大的事业。", "author": "阿图·葛文德"},
    {"quote": "人活着，像航海。你的恨，你的风暴；你的爱，你的云彩。", "author": "绿原"},
    {"quote": "给岁月以文明，而不是给文明以岁月。", "author": "《三体》"},
    {"quote": "纵有千古，横有八荒；前途似海，来日方长。", "author": "梁启超"},
    {"quote": "怕什么真理无穷，进一寸有进一寸的欢喜。", "author": "胡适"},
    {"quote": "追风赶月莫停留，平芜尽处是春山。", "author": "《华夏说》"},
    {"quote": "不乱于心，不困于情。不畏将来，不念过往。如此，安好。", "author": "丰子恺"},
    {"quote": "人生天地间，忽如远行客。", "author": "《古诗十九首》"},
    {"quote": "行是知之始，知是行之成。", "author": "陶行知"},
    {"quote": "岁月不饶人，我亦未曾饶过岁月。", "author": "木心"},
    {"quote": "心之所向，素履以往；生如逆旅，一苇以航。", "author": "七堇年"}
]

def load_cwu_quotes():
    """加载春戊名言库（优先读取同目录 cwu_quotes.json，缺失时使用精选内置库）"""
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "cwu_quotes.json"),
        os.path.join(os.getcwd(), "cwu_quotes.json")
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list) and len(data) > 0:
                        return data
            except Exception:
                pass
    return _FALLBACK_QUOTES

def fetch_daily_sentence():
    """获取今日名言（春戊服务端接口优先，校外或离线时采用按日轮播算法）"""
    url = "http://10.181.201.165:1908/api/pdb/sentence/today"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "chunhui-cli/1.0"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                chs = data.get("chs", "").strip()
                eng = data.get("eng", "").strip()
                prior = data.get("prior_lang", "chs")
                if prior != "chs" and eng:
                    chs, eng = eng, chs
                if chs:
                    return {
                        "source": "server",
                        "chs": chs,
                        "eng": eng,
                        "author": "春戊服务端每日推送"
                    }
    except Exception:
        pass

    # 离线轮播算法（与原版春戊客户端完全对齐）
    quotes = load_cwu_quotes()
    today = datetime.date.today()
    base_date = datetime.date(2021, 1, 1)
    days = (today - base_date).days
    offset = (7 * (days - 1)) % len(quotes)
    offset = (offset + len(quotes)) % len(quotes)
    cur = quotes[offset]
    return {
        "source": "local_rotation",
        "chs": cur.get("quote", ""),
        "eng": "",
        "author": cur.get("author", "精选名言")
    }

def fetch_daily_weather():
    """获取白马湖实时天气（内网时调取 /api/weather）"""
    url = "http://10.181.201.165:1908/api/weather"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "chunhui-cli/1.0"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                if data.get("status") == "ok" and "result" in data:
                    res = data["result"]
                    rt = res.get("realtime", {})
                    temp = round(float(rt.get("temperature", 0)))
                    app_temp = round(float(rt.get("apparent_temperature", 0)))
                    desc = res.get("forecast_keypoint", "")
                    aqi = rt.get("air_quality", {}).get("description", {}).get("chn", "")
                    d0 = res.get("daily", {})
                    d_temps = d0.get("temperature", [])
                    range_str = ""
                    if d_temps and isinstance(d_temps, list) and len(d_temps) > 0 and "min" in d_temps[0] and "max" in d_temps[0]:
                        d_max = round(float(d_temps[0].get("max", temp)))
                        d_min = round(float(d_temps[0].get("min", temp)))
                        range_str = f"{d_min}°C ~ {d_max}°C"
                    return {
                        "online": True,
                        "temp": temp,
                        "app_temp": app_temp,
                        "desc": desc,
                        "aqi": aqi,
                        "range": range_str
                    }
    except Exception:
        pass
    return {"online": False}

def get_daily_recommendations(count=3, offset=None):
    """获取原版名言推荐"""
    quotes = load_cwu_quotes()
    if not quotes:
        return []
    if offset is None:
        today = datetime.date.today()
        base_date = datetime.date(2021, 1, 1)
        days = (today - base_date).days
        offset = (7 * (days - 1)) % len(quotes)
        offset = (offset + len(quotes)) % len(quotes)
    res = []
    for i in range(count):
        idx = (offset + i) % len(quotes)
        res.append(quotes[idx])
    return res

get_cwu_quotes = get_daily_recommendations

CAMPUS_PORTAL_SERVICES = [
    {
        "id": 1,
        "name": "校园网综合门户",
        "desc": "校园办公、课表、考评、收件箱与基础数据门户",
        "url": "http://10.181.200.3/home/home4pc/",
        "icon": "🏫"
    },
    {
        "id": 2,
        "name": "云上春晖 NAS",
        "desc": "群晖文件中心，班级资料与大容量教学网盘",
        "url": "http://10.181.201.188:5000/",
        "icon": "☁️"
    },
    {
        "id": 3,
        "name": "春晖图库相册",
        "desc": "百年名校历史图库、活动掠影与校园活动素材精选",
        "url": "http://10.181.201.188/photo/",
        "icon": "🖼️"
    },
    {
        "id": 4,
        "name": "春晖视频中心",
        "desc": "校园精品公开课、电视台专题回放与视频资源库",
        "url": "http://10.181.201.185:82/",
        "icon": "🎬"
    },
    {
        "id": 5,
        "name": "云上春晖 AI",
        "desc": "校内私有化部署的大语言模型与智能辅导助手",
        "url": "http://10.181.201.181/chat/",
        "icon": "🤖"
    },
    {
        "id": 6,
        "name": "春晖电视台直播流",
        "desc": "校园大型集会、晨会与活动 RTMP 高清实时直播",
        "url": "rtmp://10.181.201.185/live/livestream",
        "icon": "📺"
    }
]

def cmd_briefing(args=None):
    """白马湖每日简报"""
    today = datetime.date.today()
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday_str = weekdays[today.weekday()]
    date_str = today.strftime("%Y年%m月%d日")
    lunar_str = get_lunar_date_str(today)
    
    print(f"\n{C_BLUE}╔════════════════════════════════════════════════════════════════════════════════╗{C_RESET}")
    print(f"{C_BLUE}║{C_RESET} {C_BOLD}{C_YELLOW}🌅 白马湖每日晨报 · CHUNHUI DAILY BRIEFING{C_RESET}")
    print(f"{C_BLUE}╠════════════════════════════════════════════════════════════════════════════════╣{C_RESET}")
    print(f"{C_BLUE}║{C_RESET} 📅 {C_BOLD}公历日期：{C_RESET}{date_str} {weekday_str}    |   🏮 {C_BOLD}农历岁次：{C_RESET}{lunar_str}")
    
    weather = fetch_daily_weather()
    if weather.get("online"):
        wt_str = f"🌡️ {weather['temp']}°C (体感 {weather['app_temp']}°C, 范围 {weather['range']}) | 空气质量: {weather['aqi']}"
        desc_str = weather.get('desc') or '天气平稳'
        print(f"{C_BLUE}║{C_RESET} ⛅ {C_BOLD}白马湖天气：{C_RESET}{wt_str}")
        print(f"{C_BLUE}║{C_RESET}    {C_CYAN}气象简评：{desc_str}{C_RESET}")
    else:
        print(f"{C_BLUE}║{C_RESET} ⛅ {C_BOLD}白马湖天气：{C_RESET}{C_GREY}离校模式 (校园内网气象站未连接){C_RESET}")
        
    print(f"{C_BLUE}╠════════════════════════════════════════════════════════════════════════════════╣{C_RESET}")
    
    sentence = fetch_daily_sentence()
    chs = sentence.get("chs", "")
    eng = sentence.get("eng", "")
    author = sentence.get("author", "")
    src_tag = "[服务端推送]" if sentence.get("source") == "server" else "[日历轮播]"
    
    print(f"{C_BLUE}║{C_RESET} {C_BOLD}{C_GREEN}💡 今日一言 {C_GREY}{src_tag}{C_RESET}")
    print(f"{C_BLUE}║{C_RESET}   {C_BOLD}“{chs}”{C_RESET}")
    if eng:
        print(f"{C_BLUE}║{C_RESET}   {C_GREY}{eng}{C_RESET}")
    if author:
        print(f"{C_BLUE}║{C_RESET}   {C_YELLOW}—— {author}{C_RESET}")
        
    print(f"{C_BLUE}╠════════════════════════════════════════════════════════════════════════════════╣{C_RESET}")
    print(f"{C_BLUE}║{C_RESET} {C_BOLD}{C_CYAN}📖 今日精选哲思推荐 (离线题库轮播){C_RESET}")
    recs = get_daily_recommendations(3)
    for i, r in enumerate(recs, 1):
        q = r.get("quote", "").strip()
        a = r.get("author", "").strip()
        a_str = f" —— {a}" if a else ""
        print(f"{C_BLUE}║{C_RESET}   {i}. {q}{C_GREY}{a_str}{C_RESET}")
        
    print(f"{C_BLUE}╚════════════════════════════════════════════════════════════════════════════════╝{C_RESET}\n")

def cmd_lottery(args=None):
    """课堂抽签点名器"""
    min_num = getattr(args, "min", 1) if args else 1
    max_num = getattr(args, "max", 50) if args else 50
    repeat = getattr(args, "repeat", False) if args else False
    
    if min_num >= max_num:
        log_error("学号区间无效：最小值必须小于最大值。")
        return

    pool = list(range(min_num, max_num + 1))
    drawn_history = []
    
    print(f"\n{C_BOLD}{C_CYAN}🎯 浙江省春晖中学 · 课堂抽签点名器 (Class Lottery){C_RESET}")
    print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
    print(f"学号范围：{C_YELLOW}{min_num} ~ {max_num}{C_RESET} 号  |  总人数：{C_GREEN}{len(pool)}{C_RESET} 人  |  抽取模式：{C_BOLD}{'允许重复' if repeat else '防重复'}{C_RESET}")
    print(f"{C_BLUE}──────────────────────────────────────────────────{C_RESET}")
    print(f"{C_GREY}操作提示：[回车/空格] 开始抽签  [r] 重置名单  [q] 退出程序{C_RESET}\n")
    
    while True:
        if not pool and not repeat:
            print(f"\n{C_YELLOW}⚠️ 本轮候选池所有学号（共 {len(drawn_history)} 人）已全部抽选完毕！{C_RESET}")
            print(f"按 [r] 重置候选名单重新开始，或按 [q] 退出...")
            k = getkey()
            if k == 'r':
                pool = list(range(min_num, max_num + 1))
                drawn_history.clear()
                print(f"{C_GREEN}已重置候选池，恢复为 {len(pool)} 人。{C_RESET}\n")
                continue
            elif k in ('q', 'esc'):
                break
            else:
                continue

        prompt_str = f"剩余候选: {len(pool)}人 | [回车] 抽选下一个 > " if not repeat else "模式: 允许重复 | [回车] 抽选下一个 > "
        sys.stdout.write(prompt_str)
        sys.stdout.flush()
        k = getkey()
        
        if k in ('q', 'esc'):
            print(f"\n{C_GREY}已退出课堂抽签。{C_RESET}\n")
            break
        elif k == 'r':
            pool = list(range(min_num, max_num + 1))
            drawn_history.clear()
            print(f"\n{C_GREEN}已手动重置候选名单 (总计 {len(pool)} 人)。{C_RESET}\n")
            continue
        elif k in ('enter', 'space', '\r', '\n'):
            all_nums = list(range(min_num, max_num + 1))
            roll_count = random.randint(18, 24)
            for step in range(roll_count):
                temp_val = random.choice(all_nums)
                delay = 0.02 + (step / roll_count) * 0.08
                sys.stdout.write(f"\r  🎲 正在摇号: {C_BOLD}{C_YELLOW}[ {temp_val:02d} 号 ]{C_RESET} ...  ")
                sys.stdout.flush()
                time.sleep(delay)
                
            if repeat:
                chosen = random.choice(all_nums)
            else:
                chosen = random.choice(pool)
                pool.remove(chosen)
            drawn_history.append(chosen)
            
            sys.stdout.write(f"\r{' ' * 45}\r")
            print(f"{C_GREEN}╔══════════════════════════════╗{C_RESET}")
            print(f"{C_GREEN}║{C_RESET}       🎯 中选中奖学号        {C_GREEN}║{C_RESET}")
            print(f"{C_GREEN}║{C_RESET}                              {C_GREEN}║{C_RESET}")
            print(f"{C_GREEN}║{C_RESET}          {C_BOLD}{C_YELLOW}【 {chosen:02d} 号 】{C_RESET}         {C_GREEN}║{C_RESET}")
            print(f"{C_GREEN}║{C_RESET}                              {C_GREEN}║{C_RESET}")
            if not repeat:
                print(f"{C_GREEN}║{C_RESET}  已抽取: {len(drawn_history):02d} 人 | 剩余: {len(pool):02d} 人   {C_GREEN}║{C_RESET}")
            else:
                print(f"{C_GREEN}║{C_RESET}  累计抽取次数: {len(drawn_history):02d} 次          {C_GREEN}║{C_RESET}")
            print(f"{C_GREEN}╚══════════════════════════════╝{C_RESET}\n")

def cmd_anydoor(args=None):
    """校园内网任意门服务聚合导航"""
    import webbrowser
    
    print(f"\n{C_BOLD}{C_CYAN}🚪 春戊校园任意门 · 校园网核心基础设施直达导航{C_RESET}")
    print(f"{C_BLUE}────────────────────────────────────────────────────────────────────────────{C_RESET}")
    print(f"{C_BOLD}{'序号':<6} {'服务名称':<18} {'节点地址 / 协议':<36} {'说明'}{C_RESET}")
    print(f"{C_BLUE}────────────────────────────────────────────────────────────────────────────{C_RESET}")
    for item in CAMPUS_PORTAL_SERVICES:
        num_tag = f"[{item['id']}]"
        print(f"{C_GREEN}{num_tag:<6}{C_RESET} {C_BOLD}{item['icon']} {item['name']:<14}{C_RESET} {C_CYAN}{item['url']:<36}{C_RESET} {C_GREY}{item['desc']}{C_RESET}")
    print(f"{C_BLUE}────────────────────────────────────────────────────────────────────────────{C_RESET}")
    print(f"{C_GREY}输入对应序号 [1-6] 直接在系统默认浏览器中打开，按 [q/Enter] 返回。{C_RESET}\n")
    
    while True:
        try:
            choice = input(f"{C_YELLOW}请选择要访问的服务 [1-6, q退出]: {C_RESET}").strip().lower()
            if not choice or choice == 'q':
                break
            if choice.isdigit() and 1 <= int(choice) <= len(CAMPUS_PORTAL_SERVICES):
                target = CAMPUS_PORTAL_SERVICES[int(choice) - 1]
                log_info(f"正在打开浏览器访问: {target['name']} ({target['url']})...")
                webbrowser.open(target['url'])
                break
            else:
                log_warn("输入无效，请输入 1 到 6 之间的数字。")
        except (KeyboardInterrupt, EOFError):
            print()
            break

def get_captcha():
    """
    获取登录验证码图片（Base64）及初始 Session Cookies。
    步骤 1: GET /account/login4Stu/ 获取初始 sessionid / csrftoken
    步骤 2: GET /account/create_code_img2/?t=... 获取验证码图片
    """
    init_cookies = {}
    try:
        status, _, resp_headers = make_request("/account/login4Stu/", method="GET", follow_redirects=False)
        if resp_headers:
            init_cookies.update(extract_cookies_from_headers(resp_headers))
            
        cookie_str = "; ".join(f"{k}={v}" for k, v in init_cookies.items())
        headers = {"Cookie": cookie_str} if cookie_str else {}
        ts = int(time.time() * 1000)
        status, img_body, img_headers = make_request(f"/account/create_code_img2/?t={ts}", method="GET", headers=headers)
        if img_headers:
            init_cookies.update(extract_cookies_from_headers(img_headers))
            
        if status == 200 and img_body:
            b64 = base64.b64encode(img_body).decode("ascii")
            return {
                "success": True,
                "image": f"data:image/png;base64,{b64}",
                "cookies": init_cookies
            }
        else:
            err_msg = f"获取验证码失败 (HTTP {status})" if status != 0 else "无法连接到校园内网 (10.181.200.3)"
            return {
                "success": False,
                "error": err_msg,
                "cookies": init_cookies
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"网络异常: {e}",
            "cookies": init_cookies
        }

def login_with_credentials(username, password, check_code, initial_cookies=None):
    """
    通过账号、密码、验证码进行登录
    """
    cookies = dict(initial_cookies) if initial_cookies else load_session()
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items() if v)
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": f"{BASE_URL}/account/login4Stu/",
        "Origin": BASE_URL,
    }
    if cookie_str:
        headers["Cookie"] = cookie_str
    if "csrftoken" in cookies:
        headers["X-CSRFToken"] = cookies["csrftoken"]
        
    post_data = {
        "username": username,
        "password": password,
        "checkCode": check_code
    }
    
    try:
        status, body, resp_headers = make_request(
            "/account/login4Stu/",
            method="POST",
            data=post_data,
            headers=headers,
            follow_redirects=False
        )
        
        if resp_headers:
            new_cookies = extract_cookies_from_headers(resp_headers)
            cookies.update(new_cookies)
            
        body_str = body.decode("utf-8", errors="ignore") if isinstance(body, bytes) else str(body)
        redirect_url = ""
        if resp_headers:
            redirect_url = resp_headers.get("Location", "")
            
        is_success = (status == 302 and ("/home/" in redirect_url or "/home/index/" in redirect_url))
        has_error = any(kw in body_str for kw in ("验证码", "密码", "错误", "失败", "id_username"))
        
        if is_success and not has_error:
            save_session(cookies)
            return {
                "success": True,
                "message": "登录成功",
                "cookies": cookies
            }
        else:
            err_msg = "登录失败，请检查账号、密码或验证码"
            match = re.search(r'(验证码[^<"\'\n\r]{0,20}|用户名[^<"\'\n\r]{0,20}|密码[^<"\'\n\r]{0,20}|错误[^<"\'\n\r]{0,20}|失败[^<"\'\n\r]{0,20})', body_str)
            if match:
                err_msg = match.group(1).strip()
            elif status == 0:
                err_msg = "连接校园内网失败 (10.181.200.3)，请检查局域网连接"
            return {
                "success": False,
                "error": err_msg,
                "need_refresh_captcha": True
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"登录异常: {e}",
            "need_refresh_captcha": True
        }

def login_with_cookie(cookie_str):
    """
    通过输入的 Cookie 字符串进行登录认证并验证
    """
    sessionid = ""
    csrftoken = ""
    for part in cookie_str.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            k = k.strip()
            v = v.strip()
            if k == "sessionid":
                sessionid = v
            elif k == "csrftoken":
                csrftoken = v
                
    if not sessionid:
        return {"success": False, "error": "Cookie 中未找到 sessionid 字段"}
        
    session_data = {
        "sessionid": sessionid,
        "csrftoken": csrftoken
    }
    if not save_session(session_data):
        return {"success": False, "error": "保存会话文件失败"}
        
    ok = check_login_status(verbose=False)
    if ok:
        return {"success": True, "message": "Cookie 导入成功且会话验证有效"}
    else:
        return {"success": True, "message": "Cookie 已保存至本地（当前网络无法直连内网验证或会话已失效）"}

def check_login_status(verbose=True):
    if verbose:
        log_info("正在向服务器验证登录状态...")
    status, body, headers = make_request("/article/article-detail/37079/", method="GET")
    if status == 200:
        if verbose:
            log_success("已成功登录！")
        return True
    elif status == 302:
        if verbose:
            log_error("会话验证失败: 账号未登录或 Session 已失效。请重新获取 Cookie。")
        return False
    else:
        if verbose:
            log_error(f"连接服务器失败 (HTTP Code: {status})。请检查局域网连接或服务器状态。")
        return False

def cmd_logout(args=None):
    clear_session()
    log_success("已退出登录，本地会话已清除。")

def extract_safari_cookies():
    """从 macOS Safari 提取春晖校园网 Cookie"""
    paths = [
        os.path.expanduser('~/Library/Containers/com.apple.Safari/Data/Library/Cookies/Cookies.binarycookies'),
        os.path.expanduser('~/Library/Cookies/Cookies.binarycookies')
    ]
    for p in paths:
        if not os.path.exists(p):
            continue
        try:
            with open(p, 'rb') as f:
                magic = f.read(4)
                if magic != b'cook':
                    continue
                num_pages = struct.unpack('>I', f.read(4))[0]
                page_sizes = [struct.unpack('>I', f.read(4))[0] for _ in range(num_pages)]
                sessionid = ''
                csrftoken = ''
                for size in page_sizes:
                    page_data = f.read(size)
                    if len(page_data) < 8:
                        continue
                    header, num_cookies = struct.unpack('<II', page_data[:8])
                    offsets = [struct.unpack('<I', page_data[8 + i*4 : 12 + i*4])[0] for i in range(num_cookies)]
                    for offset in offsets:
                        if offset >= len(page_data):
                            continue
                        cookie_data = page_data[offset:]
                        url_offset = struct.unpack('<I', cookie_data[16:20])[0]
                        name_offset = struct.unpack('<I', cookie_data[20:24])[0]
                        value_offset = struct.unpack('<I', cookie_data[28:32])[0]
                        
                        domain = cookie_data[url_offset:].split(b'\x00', 1)[0].decode('utf-8', errors='ignore')
                        name = cookie_data[name_offset:].split(b'\x00', 1)[0].decode('utf-8', errors='ignore')
                        value = cookie_data[value_offset:].split(b'\x00', 1)[0].decode('utf-8', errors='ignore')
                        
                        if '10.181.200.3' in domain or 'chunhui' in domain:
                            if name == 'sessionid':
                                sessionid = value
                            elif name == 'csrftoken':
                                csrftoken = value
                if sessionid:
                    return {'browser': 'Safari', 'sessionid': sessionid, 'csrftoken': csrftoken}
        except Exception:
            pass
    return None

def extract_firefox_cookies():
    """从 Firefox 浏览器各 Profile 中提取春晖校园网 Cookie"""
    patterns = [
        os.path.expanduser('~/Library/Application Support/Firefox/Profiles/*/cookies.sqlite'),
        os.path.expandvars(r'%APPDATA%\Mozilla\Firefox\Profiles\*\cookies.sqlite'),
        os.path.expanduser('~/.mozilla/firefox/*/cookies.sqlite')
    ]
    for pattern in patterns:
        for p in glob.glob(pattern):
            if not os.path.exists(p):
                continue
            tmp_path = None
            try:
                tmp = tempfile.NamedTemporaryFile(delete=False)
                tmp_path = tmp.name
                tmp.close()
                shutil.copy2(p, tmp_path)
                conn = sqlite3.connect(tmp_path)
                cursor = conn.cursor()
                cursor.execute("SELECT name, value FROM moz_cookies WHERE host LIKE '%10.181.200.3%' OR host LIKE '%chunhui%'")
                rows = cursor.fetchall()
                conn.close()
                sessionid = ''
                csrftoken = ''
                for name, value in rows:
                    if name == 'sessionid':
                        sessionid = value
                    elif name == 'csrftoken':
                        csrftoken = value
                if sessionid:
                    return {'browser': 'Firefox', 'sessionid': sessionid, 'csrftoken': csrftoken}
            except Exception:
                pass
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try: os.unlink(tmp_path)
                    except Exception: pass
    return None

def decrypt_windows_chromium_cookie(cookie_db_path, encrypted_value):
    """Windows 系统下对 Chromium 浏览器 Cookie 进行解密"""
    if not encrypted_value or os.name != 'nt':
        return ""
    import ctypes
    from ctypes import wintypes
    
    curr = os.path.dirname(cookie_db_path)
    local_state_path = None
    for _ in range(4):
        ls = os.path.join(curr, "Local State")
        if os.path.exists(ls):
            local_state_path = ls
            break
        curr = os.path.dirname(curr)
        
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_char))]
        
    if not local_state_path:
        pDataIn = DATA_BLOB(len(encrypted_value), ctypes.cast(ctypes.create_string_buffer(encrypted_value), ctypes.POINTER(ctypes.c_char)))
        pDataOut = DATA_BLOB()
        if ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(pDataIn), None, None, None, None, 0, ctypes.byref(pDataOut)):
            raw = ctypes.string_at(pDataOut.pbData, pDataOut.cbData)
            ctypes.windll.kernel32.LocalFree(pDataOut.pbData)
            return raw.decode('utf-8', errors='ignore')
        return ""
        
    try:
        with open(local_state_path, "r", encoding="utf-8") as f:
            local_state = json.load(f)
        enc_key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])[5:]
        
        pDataIn = DATA_BLOB(len(enc_key), ctypes.cast(ctypes.create_string_buffer(enc_key), ctypes.POINTER(ctypes.c_char)))
        pDataOut = DATA_BLOB()
        if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(pDataIn), None, None, None, None, 0, ctypes.byref(pDataOut)):
            return ""
        master_key = ctypes.string_at(pDataOut.pbData, pDataOut.cbData)
        ctypes.windll.kernel32.LocalFree(pDataOut.pbData)
        
        if encrypted_value.startswith(b'v10') or encrypted_value.startswith(b'v11'):
            nonce = encrypted_value[3:15]
            ciphertext = encrypted_value[15:-16]
            tag = encrypted_value[-16:]
            try:
                from cryptography.hazmat.primitives.ciphers.aead import AESGCM
                aesgcm = AESGCM(master_key)
                decrypted = aesgcm.decrypt(nonce, ciphertext + tag, None)
                return decrypted.decode('utf-8', errors='ignore')
            except Exception:
                pass
    except Exception:
        pass
    return ""

def extract_chromium_cookies():
    """从 Chromium 系列浏览器 (Chrome / Edge / Brave / 360 / Arc) 提取春晖校园网 Cookie"""
    patterns = [
        ('Chrome', os.path.expanduser('~/Library/Application Support/Google/Chrome/*/Cookies')),
        ('Chrome', os.path.expanduser('~/Library/Application Support/Google/Chrome/*/Network/Cookies')),
        ('Chrome', os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\User Data\*\Network\Cookies')),
        ('Chrome', os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\User Data\*\Cookies')),
        ('Chrome', os.path.expanduser('~/.config/google-chrome/*/Cookies')),
        ('Edge', os.path.expanduser('~/Library/Application Support/Microsoft Edge/*/Cookies')),
        ('Edge', os.path.expanduser('~/Library/Application Support/Microsoft Edge/*/Network/Cookies')),
        ('Edge', os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\Edge\User Data\*\Network\Cookies')),
        ('Edge', os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\Edge\User Data\*\Cookies')),
        ('Brave', os.path.expanduser('~/Library/Application Support/BraveSoftware/Brave-Browser/*/Cookies')),
        ('Brave', os.path.expandvars(r'%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data\*\Network\Cookies')),
        ('Arc', os.path.expanduser('~/Library/Application Support/Arc/User Data/*/Cookies')),
        ('360', os.path.expandvars(r'%LOCALAPPDATA%\360Chrome\Chrome\User Data\*\Network\Cookies')),
    ]
    for b_name, pattern in patterns:
        for p in glob.glob(pattern):
            if not os.path.exists(p):
                continue
            tmp_path = None
            try:
                tmp = tempfile.NamedTemporaryFile(delete=False)
                tmp_path = tmp.name
                tmp.close()
                shutil.copy2(p, tmp_path)
                conn = sqlite3.connect(tmp_path)
                cursor = conn.cursor()
                cursor.execute("SELECT name, value, encrypted_value FROM cookies WHERE host_key LIKE '%10.181.200.3%' OR host_key LIKE '%chunhui%'")
                rows = cursor.fetchall()
                conn.close()
                
                sessionid = ''
                csrftoken = ''
                for name, value, enc_val in rows:
                    cookie_val = value
                    if not cookie_val and enc_val and os.name == 'nt':
                        try:
                            cookie_val = decrypt_windows_chromium_cookie(p, enc_val)
                        except Exception:
                            pass
                    if name == 'sessionid' and cookie_val:
                        sessionid = cookie_val
                    elif name == 'csrftoken' and cookie_val:
                        csrftoken = cookie_val
                if sessionid:
                    return {'browser': b_name, 'sessionid': sessionid, 'csrftoken': csrftoken}
            except Exception:
                pass
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try: os.unlink(tmp_path)
                    except Exception: pass
    return None

def auto_get_browser_cookie():
    """
    自动按优先级扫描本机浏览器中的校园网登录凭据 (Safari -> Firefox -> Chrome/Edge)
    """
    res = extract_safari_cookies()
    if res and res.get("sessionid"):
        return res
    res = extract_firefox_cookies()
    if res and res.get("sessionid"):
        return res
    res = extract_chromium_cookies()
    if res and res.get("sessionid"):
        return res
    return None

def cmd_login_auto():
    """自动从本机浏览器获取凭据并保存"""
    log_info("正在扫描本机浏览器中的春晖校园网登录凭据...")
    res = auto_get_browser_cookie()
    if res and res.get("sessionid"):
        b_name = res.get("browser", "浏览器")
        sess_data = {
            "sessionid": res["sessionid"],
            "csrftoken": res.get("csrftoken", "")
        }
        save_session(sess_data)
        log_success(f"已自动从 {b_name} 提取到春晖校园网 Cookie (sessionid: {res['sessionid'][:6]}...)！")
        check_login_status()
        return True
    else:
        log_warn("未在本地浏览器中检索到已登录的春晖校园网会话。")
        print(f"\n{C_CYAN}提示：{C_RESET}")
        print(f"  1. 您可以先在电脑浏览器中登录校园网: {BASE_URL}/account/login4Stu/")
        print("  2. 或使用账号密码交互登录: `python3 ch_cli.py login`")
        try:
            open_br = input(f"\n是否在默认浏览器中打开登录页面？(Y/n) > ").strip().lower()
            if open_br in ('', 'y', 'yes'):
                webbrowser.open(f"{BASE_URL}/account/login4Stu/")
                print("已调起浏览器打开登录页面。请在浏览器中完成登录，完成后按回车键重新提取...")
                input()
                res2 = auto_get_browser_cookie()
                if res2 and res2.get("sessionid"):
                    b_name = res2.get("browser", "浏览器")
                    sess_data = {
                        "sessionid": res2["sessionid"],
                        "csrftoken": res2.get("csrftoken", "")
                    }
                    save_session(sess_data)
                    log_success(f"已成功从 {b_name} 自动提取并保存登录凭据！")
                    check_login_status()
                    return True
                else:
                    log_error("仍未检测到有效 Cookie，请确认是否已在浏览器中成功登录。")
        except (KeyboardInterrupt, EOFError):
            print()
        return False

def cmd_login(args):
    auto_flag = getattr(args, "auto", False)
    if auto_flag:
        cmd_login_auto()
        return

    cookie_str = getattr(args, "cookie", None)
    username = getattr(args, "username", None)
    password = getattr(args, "password", None)
    code = getattr(args, "code", None)
    
    if cookie_str:
        res = login_with_cookie(cookie_str)
        if res["success"]:
            log_success(res["message"])
        else:
            log_error(res["error"])
        return
        
    if username and password and code:
        log_info(f"正在提交登录: {username} ...")
        res = login_with_credentials(username, password, code)
        if res["success"]:
            log_success("登录成功！")
        else:
            log_error(f"登录失败: {res.get('error')}")
        return

    print(f"\n{C_BOLD}=== 春晖校园网登录 ==={C_RESET}")
    print("  1. 自动从本机浏览器提取 Cookie (推荐，免验证码)")
    print("  2. 账号密码登录 (需验证码)")
    print("  3. 导入浏览器 Cookie 字符串 (手动粘贴)")
    try:
        choice = input(f"{C_CYAN}请选择登录方式 (1-3, 默认 1) > {C_RESET}").strip() or "1"
    except (KeyboardInterrupt, EOFError):
        print()
        return
        
    if choice == "1":
        cmd_login_auto()
    elif choice == "3":
        print(f"{C_BOLD}请输入您从浏览器获取的 Cookie 字符串：{C_RESET}")
        print(f"{C_GREY}(通常可在浏览器开发者工具的 Network 面板请求头中找到。形如: sessionid=xxx; csrftoken=yyy){C_RESET}")
        try:
            c_str = input(f"{C_CYAN}Cookie > {C_RESET}").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return
        res = login_with_cookie(c_str)
        if res["success"]:
            log_success(res["message"])
        else:
            log_error(res["error"])
    else:
        log_info("正在连接校园内网获取验证码...")
        cap = get_captcha()
        if not cap["success"]:
            log_error(f"获取验证码失败: {cap.get('error')}")
            return
            
        cap_file = os.path.join(tempfile.gettempdir(), "chunhui_captcha.png")
        try:
            img_data = base64.b64decode(cap["image"].split(",", 1)[1])
            with open(cap_file, "wb") as f:
                f.write(img_data)
            log_info(f"验证码图片已保存至: {cap_file}")
            if sys.platform == "darwin":
                os.system(f"open {cap_file}")
            elif sys.platform.startswith("win"):
                os.system(f"start {cap_file}")
            elif sys.platform.startswith("linux"):
                os.system(f"xdg-open {cap_file} 2>/dev/null &")
        except Exception as e:
            log_warn(f"无法自动打开图片查看器: {e}")
            
        try:
            u_val = input(f"{C_CYAN}学号/用户名 > {C_RESET}").strip()
            import getpass
            p_val = getpass.getpass(f"{C_CYAN}密码 > {C_RESET}").strip()
            c_val = input(f"{C_CYAN}验证码 (见已打开的图片) > {C_RESET}").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return
            
        log_info("正在提交登录认证...")
        res = login_with_credentials(u_val, p_val, c_val, cap.get("cookies"))
        if res["success"]:
            log_success("登录成功！会话已写入本地凭据文件。")
            check_login_status()
        else:
            log_error(f"登录失败: {res.get('error')}")

def cmd_status(args):
    check_login_status()

class DummyArgs:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

def get_key_win():
    import msvcrt
    import time

    try:
        ch = msvcrt.getwch()
    except Exception:
        ch = msvcrt.getch()
        if isinstance(ch, bytes):
            ch = ch.decode('latin1', errors='ignore')

    # 1. 经典 Windows 控制台扩展键前缀 (0x00 或 0xE0)
    if ch in ('\x00', '\xe0', '\u0000', '\u00e0'):
        try:
            ch2 = msvcrt.getwch()
        except Exception:
            ch2 = msvcrt.getch()
            if isinstance(ch2, bytes):
                ch2 = ch2.decode('latin1', errors='ignore')
        if ch2 in ('H', 'h'): return 'up'
        if ch2 in ('P', 'p'): return 'down'
        if ch2 in ('K', 'k'): return 'left'
        if ch2 in ('M', 'm'): return 'right'
        if ch2 in ('I', 'i'): return 'pageup'
        if ch2 in ('Q', 'q'): return 'pagedown'
        return ''

    # 2. Windows Terminal / ConPTY / ANSI 转义序列 (\x1b[A, \x1b[B 等)
    if ch == '\x1b':
        time.sleep(0.02)
        if msvcrt.kbhit():
            seq = ''
            while msvcrt.kbhit():
                try:
                    c = msvcrt.getwch()
                except Exception:
                    c = msvcrt.getch()
                    if isinstance(c, bytes):
                        c = c.decode('latin1', errors='ignore')
                seq += str(c)
            if seq in ('[A', 'OA') or seq.endswith('A'):
                return 'up'
            elif seq in ('[B', 'OB') or seq.endswith('B'):
                return 'down'
            elif seq in ('[C', 'OC') or seq.endswith('C'):
                return 'right'
            elif seq in ('[D', 'OD') or seq.endswith('D'):
                return 'left'
            elif seq in ('[5~',):
                return 'pageup'
            elif seq in ('[6~',):
                return 'pagedown'
            return 'esc'
        return 'esc'

    # 3. 回车与空格
    if ch in ('\r', '\n'):
        return 'enter'
    if ch == ' ':
        return 'space'

    return ch.lower()

def get_key_unix():
    import tty
    import termios
    import select
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        ch1 = os.read(fd, 1)
        if ch1 == b'\x1b':
            r, _, _ = select.select([fd], [], [], 0.05)
            if r:
                seq = os.read(fd, 16)
                if seq in (b'[A', b'OA') or seq.endswith(b'A'):
                    return 'up'
                elif seq in (b'[B', b'OB') or seq.endswith(b'B'):
                    return 'down'
                elif seq in (b'[C', b'OC') or seq.endswith(b'C'):
                    return 'right'
                elif seq in (b'[D', b'OD') or seq.endswith(b'D'):
                    return 'left'
                elif seq == b'[5~':
                    return 'pageup'
                elif seq == b'[6~':
                    return 'pagedown'
                return 'esc'
            else:
                return 'esc'
        elif ch1 in (b'\r', b'\n'):
            return 'enter'
        elif ch1 == b' ':
            return 'space'
        try:
            return ch1.decode('utf-8', errors='ignore').lower()
        except Exception:
            return ''
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

def getkey():
    if not sys.stdin.isatty():
        try:
            line = sys.stdin.readline()
            if not line:
                return 'esc'
            val = line.strip()
            if val == '': return 'enter'
            return val
        except Exception:
            return 'esc'

    if os.name == 'nt':
        try:
            return get_key_win()
        except Exception:
            pass
    else:
        try:
            return get_key_unix()
        except Exception:
            pass
    try:
        val = input().strip()
        if val == '': return 'enter'
        return val
    except (EOFError, KeyboardInterrupt):
        return 'esc'

def fetch_messages_data(page):
    res = fetch_messages(page)
    if not res.get("success"):
        return {"items": [], "error": res.get("error", "获取信件列表失败")}
    rows = []
    for item in res.get("data", []):
        rows.append({
            "id": item.get("id", ""),
            "title": item.get("title", ""),
            "sender": item.get("sender", ""),
            "date": item.get("time", ""),
            "unread": item.get("unread", False)
        })
    return {"items": rows, "error": None}

def show_message_detail_tui(msg_id):
    if not msg_id:
        return
    os.system('cls' if os.name == 'nt' else 'clear')
    cmd_messages(DummyArgs(show=int(msg_id), download=False, out="."))
    print(f"\n{C_CYAN}{C_BOLD}[快捷操作]{C_RESET} [d] 下载全部关联附件  [b / ESC / 回车] 返回信件列表")
    k = getkey()
    if k in ('d', 'D'):
        try:
            out_dir = input("\n请输入附件保存目录 (直接回车保存在当前目录) > ").strip() or "."
            cmd_messages(DummyArgs(show=int(msg_id), download=True, out=out_dir))
            print("\n下载完成。按任意键返回信件列表...")
            getkey()
        except (KeyboardInterrupt, EOFError):
            pass

def tui_messages_paginated():
    server_page = 1
    page_size = 6
    selected_idx = 0
    subpage = 0
    cached_pages = {}
    
    while True:
        if server_page not in cached_pages:
            os.system('cls' if os.name == 'nt' else 'clear')
            print(f"\n{C_CYAN}[i] 正在获取收件箱信件 (第 {server_page} 页)...{C_RESET}")
            res_obj = fetch_messages_data(server_page)
            cached_pages[server_page] = res_obj
        else:
            res_obj = cached_pages[server_page]

        items = res_obj.get("items", [])
        err = res_obj.get("error")
            
        total_subpages = max(1, (len(items) + page_size - 1) // page_size) if items else 1
        if subpage >= total_subpages:
            subpage = max(0, total_subpages - 1)
            
        start_idx = subpage * page_size
        end_idx = min(start_idx + page_size, len(items)) if items else 0
        cur_batch = items[start_idx:end_idx] if items else []
        
        if selected_idx >= len(cur_batch):
            selected_idx = max(0, len(cur_batch) - 1)
            
        os.system('cls' if os.name == 'nt' else 'clear')
        print(render_box_line("┌", "─", "┐"))
        print(render_row(f"{C_CYAN}{C_BOLD}📨 校内个人收件箱 (Inbox Messages){C_RESET}", "center"))
        print(render_box_line("├", "─", "┤"))
        page_info = f"{C_BOLD}[当前页码]{C_RESET} 第 {server_page} 页 · 分屏 {subpage+1}/{total_subpages} (本屏 {len(cur_batch)} 条 / 共 {len(items)} 条)"
        status_disp = f"{C_GREEN}● 就绪{C_RESET}" if not err else f"{C_RED}● 异常{C_RESET}"
        print(render_row(f"{page_info}    {C_BOLD}[状态]{C_RESET} {status_disp}"))
        print(render_box_line("├", "─", "┤"))
        
        if err:
            print(render_row(f"{C_RED}⚠️ {err}{C_RESET}", "center"))
            print(render_row(f"{C_GREY}提示: 请检查校园内网连接或在主菜单按 1 重新登录{C_RESET}", "center"))
            for _ in range(8):
                print(render_row(""))
        elif not items:
            print(render_row(f"{C_YELLOW}当前收件箱第 {server_page} 页暂无更多信件记录{C_RESET}", "center"))
            for _ in range(9):
                print(render_row(""))
        else:
            for idx, msg in enumerate(cur_batch):
                num_tag = f"[{start_idx + idx + 1:02d}]"
                m_id = msg.get("id", "")
                title = msg.get("title", "无标题")
                sender = msg.get("sender", "未知")
                date = msg.get("date", "")
                unread = msg.get("unread", False)
                status_tag = f"{C_RED}[●未阅]{C_RESET}" if unread else f"{C_GREY}[○已阅]{C_RESET}"
                
                max_title_w = 40
                if get_visual_width(title) > max_title_w:
                    truncated = ""
                    w = 0
                    for ch in title:
                        cw = 2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1
                        if w + cw > max_title_w - 3:
                            break
                        truncated += ch
                        w += cw
                    title = truncated + "..."
                
                if idx == selected_idx:
                    l1 = f"{C_GREEN}{C_BOLD}▶ {num_tag} [{m_id}] {title}{C_RESET}"
                    l2 = f"        发件人: {C_CYAN}{sender}{C_RESET}    时间: {C_GREY}{date}{C_RESET}    {status_tag}"
                else:
                    l1 = f"  {C_GREY}{num_tag}{C_RESET} [{m_id}] {title}"
                    l2 = f"        发件人: {C_GREY}{sender}{C_RESET}    时间: {C_GREY}{date}{C_RESET}    {status_tag}"
                print(render_row(l1))
                print(render_row(l2))
                
            for _ in range((page_size - len(cur_batch)) * 2):
                print(render_row(""))
                
        print(render_box_line("├", "─", "┤"))
        print(render_row(f"{C_CYAN}{C_BOLD}[操作]{C_RESET} [↑/k] 上移  [↓/j] 下移  [Enter] 查看正文  [n] 下页  [p] 上页  [g] 跳页  [b] 返回", "center"))
        print(render_box_line("└", "─", "┘"))
        
        k = getkey()
        if k in ('up', 'k', 'w', '\x1b[A', '\x1bOA'):
            if selected_idx > 0:
                selected_idx -= 1
            elif subpage > 0:
                subpage -= 1
                selected_idx = page_size - 1
            elif server_page > 1:
                server_page -= 1
                subpage = 0
                selected_idx = 0
        elif k in ('down', 'j', 's', '\x1b[B', '\x1bOB'):
            if selected_idx < len(cur_batch) - 1:
                selected_idx += 1
            elif subpage < total_subpages - 1:
                subpage += 1
                selected_idx = 0
            elif cur_batch:
                server_page += 1
                subpage = 0
                selected_idx = 0
        elif k in ('n', 'right'):
            if subpage < total_subpages - 1:
                subpage += 1
                selected_idx = 0
            elif cur_batch:
                server_page += 1
                subpage = 0
                selected_idx = 0
        elif k in ('p', 'left'):
            if subpage > 0:
                subpage -= 1
                selected_idx = 0
            elif server_page > 1:
                server_page -= 1
                subpage = 0
                selected_idx = 0
        elif k in ('g',):
            os.system('cls' if os.name == 'nt' else 'clear')
            print(f"\n{C_BOLD}跳转至指定页{C_RESET}")
            try:
                g_str = input(f"请输入要跳转的页码 (当前第 {server_page} 页) > ").strip()
                if g_str.isdigit() and int(g_str) > 0:
                    server_page = int(g_str)
                    subpage = 0
                    selected_idx = 0
            except (KeyboardInterrupt, EOFError):
                pass
        elif k in ('r',):
            cached_pages.pop(server_page, None)
        elif k in ('enter', 'space', '\r', '\n'):
            if cur_batch and 0 <= selected_idx < len(cur_batch):
                target_msg = cur_batch[selected_idx]
                show_message_detail_tui(target_msg.get("id"))
        elif k in ('b', 'q', 'esc'):
            break

def show_article_detail_tui(col, article_id):
    if not article_id:
        return
    os.system('cls' if os.name == 'nt' else 'clear')
    cmd_news(DummyArgs(column=col, show=int(article_id), download=False, out="."))
    print(f"\n{C_CYAN}{C_BOLD}[快捷操作]{C_RESET} [d] 下载文章附件  [b / ESC / 回车] 返回文章列表")
    k = getkey()
    if k in ('d', 'D'):
        try:
            out_dir = input("\n请输入附件保存目录 (直接回车保存在当前目录) > ").strip() or "."
            cmd_news(DummyArgs(column=col, show=int(article_id), download=True, out=out_dir))
            print("\n下载完成。按任意键返回文章列表...")
            getkey()
        except (KeyboardInterrupt, EOFError):
            pass

def fetch_news_data(col, page):
    res = fetch_news(column=col, page=page)
    if not res.get("success"):
        return {"items": [], "error": res.get("error", "获取资讯列表失败")}
    return {"items": res.get("data", []), "error": None}

def tui_news_column_paginated(col, col_name):
    server_page = 1
    page_size = 6
    selected_idx = 0
    subpage = 0
    cached_pages = {}
    
    while True:
        if server_page not in cached_pages:
            os.system('cls' if os.name == 'nt' else 'clear')
            print(f"\n{C_CYAN}[i] 正在获取 {col_name} 文章列表 (第 {server_page} 页)...{C_RESET}")
            res_obj = fetch_news_data(col, server_page)
            cached_pages[server_page] = res_obj
        else:
            res_obj = cached_pages[server_page]
            
        items = res_obj.get("items", [])
        err = res_obj.get("error")
            
        total_subpages = max(1, (len(items) + page_size - 1) // page_size) if items else 1
        if subpage >= total_subpages:
            subpage = max(0, total_subpages - 1)
        start_idx = subpage * page_size
        end_idx = min(start_idx + page_size, len(items)) if items else 0
        cur_batch = items[start_idx:end_idx] if items else []
        if selected_idx >= len(cur_batch):
            selected_idx = max(0, len(cur_batch) - 1)
        
        os.system('cls' if os.name == 'nt' else 'clear')
        print(render_box_line("┌", "─", "┐"))
        print(render_row(f"{C_CYAN}{C_BOLD}📰 {col_name}{C_RESET}", "center"))
        print(render_box_line("├", "─", "┤"))
        page_info = f"{C_BOLD}[页码]{C_RESET} 第 {server_page} 页 · 分屏 {subpage+1}/{total_subpages} (本屏 {len(cur_batch)} 篇 / 共 {len(items)} 篇)"
        status_disp = f"{C_GREEN}● 就绪{C_RESET}" if not err else f"{C_RED}● 异常{C_RESET}"
        print(render_row(f"{page_info}    {C_BOLD}[状态]{C_RESET} {status_disp}"))
        print(render_box_line("├", "─", "┤"))
        
        if err:
            print(render_row(f"{C_RED}⚠️ {err}{C_RESET}", "center"))
            print(render_row(f"{C_GREY}提示: 请检查校园内网连接或在主菜单按 1 重新登录{C_RESET}", "center"))
            for _ in range(8):
                print(render_row(""))
        elif not items:
            print(render_row(f"{C_YELLOW}当前栏目第 {server_page} 页暂无更多文章记录{C_RESET}", "center"))
            for _ in range(9):
                print(render_row(""))
        else:
            for idx, art in enumerate(cur_batch):
                num_tag = f"[{start_idx + idx + 1:02d}]"
                a_id = art.get("id", "")
                title = art.get("title", "无标题")
                date = art.get("date", "")
                max_w = 46
                if get_visual_width(title) > max_w:
                    tr = ""
                    w = 0
                    for ch in title:
                        cw = 2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1
                        if w + cw > max_w - 3:
                            break
                        tr += ch
                        w += cw
                    title = tr + "..."
                if idx == selected_idx:
                    l1 = f"{C_GREEN}{C_BOLD}▶ {num_tag} [{a_id}] {title}{C_RESET}"
                    l2 = f"        发布时间: {C_GREY}{date}{C_RESET}"
                else:
                    l1 = f"  {C_GREY}{num_tag}{C_RESET} [{a_id}] {title}"
                    l2 = f"        发布时间: {C_GREY}{date}{C_RESET}"
                print(render_row(l1))
                print(render_row(l2))
            for _ in range((page_size - len(cur_batch)) * 2):
                print(render_row(""))
            
        print(render_box_line("├", "─", "┤"))
        print(render_row(f"{C_CYAN}{C_BOLD}[操作]{C_RESET} [↑/k] 上移  [↓/j] 下移  [Enter] 阅读正文  [n] 下页  [p] 上页  [g] 跳页  [b] 返回", "center"))
        print(render_box_line("└", "─", "┘"))
        
        k = getkey()
        if k in ('up', 'k', 'w', '\x1b[A', '\x1bOA'):
            if selected_idx > 0:
                selected_idx -= 1
            elif subpage > 0:
                subpage -= 1
                selected_idx = page_size - 1
            elif server_page > 1:
                server_page -= 1
                subpage = 0
                selected_idx = 0
        elif k in ('down', 'j', 's', '\x1b[B', '\x1bOB'):
            if selected_idx < len(cur_batch) - 1:
                selected_idx += 1
            elif subpage < total_subpages - 1:
                subpage += 1
                selected_idx = 0
            elif cur_batch:
                server_page += 1
                subpage = 0
                selected_idx = 0
        elif k in ('n', 'right'):
            if subpage < total_subpages - 1:
                subpage += 1
                selected_idx = 0
            elif cur_batch:
                server_page += 1
                subpage = 0
                selected_idx = 0
        elif k in ('p', 'left'):
            if subpage > 0:
                subpage -= 1
                selected_idx = 0
            elif server_page > 1:
                server_page -= 1
                subpage = 0
                selected_idx = 0
        elif k in ('g',):
            os.system('cls' if os.name == 'nt' else 'clear')
            try:
                g_str = input(f"请输入要跳转的页码 (当前第 {server_page} 页) > ").strip()
                if g_str.isdigit() and int(g_str) > 0:
                    server_page = int(g_str)
                    subpage = 0
                    selected_idx = 0
            except (KeyboardInterrupt, EOFError):
                pass
        elif k in ('r',):
            cached_pages.pop(server_page, None)
        elif k in ('enter', 'space', '\r', '\n'):
            if cur_batch and 0 <= selected_idx < len(cur_batch):
                show_article_detail_tui(col, cur_batch[selected_idx].get("id"))
        elif k in ('b', 'q', 'esc'):
            break

def tui_news_interactive():
    col_opts = [
        ("通知公告 (announcement)", "announcement"),
        ("新闻聚焦 (news)", "news"),
        ("校内公示 (notice)", "notice"),
        ("值周小结 (duty)", "duty"),
        ("返回主菜单", "back")
    ]
    sub_idx = 0
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print(render_box_line("┌", "─", "┐"))
        print(render_row(f"{C_CYAN}{C_BOLD}📰 校内文章资讯 (Campus News){C_RESET}", "center"))
        print(render_box_line("├", "─", "┤"))
        print(render_row("请选择要浏览的文章栏目："))
        print(render_box_line("├", "─", "┤"))
        for idx, (c_name, _) in enumerate(col_opts):
            num_tag = f"[{idx+1}]" if idx < len(col_opts) - 1 else "[0]"
            if idx == sub_idx:
                row_str = f"{C_GREEN}{C_BOLD}▶ {num_tag} {c_name}{C_RESET}"
            else:
                row_str = f"  {C_GREY}{num_tag}{C_RESET} {c_name}"
            print(render_row(row_str))
        print(render_box_line("├", "─", "┤"))
        print(render_row(f"{C_CYAN}{C_BOLD}[快捷操作]{C_RESET} [↑/k] 上移  [↓/j] 下移  [Enter] 确认  [1-4/0] 直达  [b/q] 返回", "center"))
        print(render_box_line("└", "─", "┘"))
        
        k = getkey()
        if k in ('up', 'k', 'w', '\x1b[A', '\x1bOA'):
            sub_idx = (sub_idx - 1) % len(col_opts)
        elif k in ('down', 'j', 's', '\x1b[B', '\x1bOB'):
            sub_idx = (sub_idx + 1) % len(col_opts)
        elif k in ('1', '2', '3', '4'):
            sub_idx = int(k) - 1
            tui_news_column_paginated(col_opts[sub_idx][1], col_opts[sub_idx][0])
        elif k == '0' or k in ('b', 'q', 'esc'):
            break
        elif k in ('enter', 'space', '\r', '\n'):
            if col_opts[sub_idx][1] == 'back':
                break
            tui_news_column_paginated(col_opts[sub_idx][1], col_opts[sub_idx][0])

def show_hygiene_detail_tui(h_id):
    if not h_id:
        return
    os.system('cls' if os.name == 'nt' else 'clear')
    cmd_hygiene(DummyArgs(show=int(h_id), download=False, out="."))
    print(f"\n{C_CYAN}{C_BOLD}[快捷操作]{C_RESET} [d] 下载关联多媒体附件  [b / ESC / 回车] 返回考评列表")
    k = getkey()
    if k in ('d', 'D'):
        try:
            out_dir = input("\n请输入多媒体保存目录 (直接回车保存在当前目录) > ").strip() or "."
            cmd_hygiene(DummyArgs(show=int(h_id), download=True, out=out_dir))
            print("\n下载完成。按任意键返回考评列表...")
            getkey()
        except (KeyboardInterrupt, EOFError):
            pass

def fetch_hygiene_data(page):
    res = fetch_hygiene(page=page)
    if not res.get("success"):
        return {"items": [], "error": res.get("error", "获取考评记录失败")}
    return {"items": res.get("data", []), "error": None}

def tui_hygiene_paginated():
    server_page = 1
    page_size = 6
    selected_idx = 0
    subpage = 0
    cached_pages = {}
    
    while True:
        if server_page not in cached_pages:
            os.system('cls' if os.name == 'nt' else 'clear')
            print(f"\n{C_CYAN}[i] 正在获取纪律卫生考评记录 (第 {server_page} 页)...{C_RESET}")
            res_obj = fetch_hygiene_data(server_page)
            cached_pages[server_page] = res_obj
        else:
            res_obj = cached_pages[server_page]
            
        items = res_obj.get("items", [])
        err = res_obj.get("error")
            
        total_subpages = max(1, (len(items) + page_size - 1) // page_size) if items else 1
        if subpage >= total_subpages:
            subpage = max(0, total_subpages - 1)
        start_idx = subpage * page_size
        end_idx = min(start_idx + page_size, len(items)) if items else 0
        cur_batch = items[start_idx:end_idx] if items else []
        if selected_idx >= len(cur_batch):
            selected_idx = max(0, len(cur_batch) - 1)
        
        os.system('cls' if os.name == 'nt' else 'clear')
        print(render_box_line("┌", "─", "┐"))
        print(render_row(f"{C_CYAN}{C_BOLD}🧹 纪律卫生考评记录 (Hygiene Appraisals){C_RESET}", "center"))
        print(render_box_line("├", "─", "┤"))
        page_info = f"{C_BOLD}[页码]{C_RESET} 第 {server_page} 页 · 分屏 {subpage+1}/{total_subpages} (本屏 {len(cur_batch)} 条 / 共 {len(items)} 条)"
        status_disp = f"{C_GREEN}● 就绪{C_RESET}" if not err else f"{C_RED}● 异常{C_RESET}"
        print(render_row(f"{page_info}    {C_BOLD}[状态]{C_RESET} {status_disp}"))
        print(render_box_line("├", "─", "┤"))
        
        if err:
            print(render_row(f"{C_RED}⚠️ {err}{C_RESET}", "center"))
            print(render_row(f"{C_GREY}提示: 请检查校园内网连接或在主菜单按 1 重新登录{C_RESET}", "center"))
            for _ in range(8):
                print(render_row(""))
        elif not items:
            print(render_row(f"{C_YELLOW}当前考评记录第 {server_page} 页暂无更多数据{C_RESET}", "center"))
            for _ in range(9):
                print(render_row(""))
        else:
            for idx, hg in enumerate(cur_batch):
                num_tag = f"[{start_idx + idx + 1:02d}]"
                h_id = hg.get("id", "")
                loc = hg.get("location", "")
                desc = hg.get("desc", "无说明")
                full_desc = f"[{loc}] {desc}" if loc else desc
                date = hg.get("date", "")
                max_w = 46
                if get_visual_width(full_desc) > max_w:
                    tr = ""
                    w = 0
                    for ch in full_desc:
                        cw = 2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1
                        if w + cw > max_w - 3:
                            break
                        tr += ch
                        w += cw
                    full_desc = tr + "..."
                if idx == selected_idx:
                    l1 = f"{C_GREEN}{C_BOLD}▶ {num_tag} [{h_id}] {full_desc}{C_RESET}"
                    l2 = f"        考评时间: {C_GREY}{date}{C_RESET}"
                else:
                    l1 = f"  {C_GREY}{num_tag}{C_RESET} [{h_id}] {full_desc}"
                    l2 = f"        考评时间: {C_GREY}{date}{C_RESET}"
                print(render_row(l1))
                print(render_row(l2))
            for _ in range((page_size - len(cur_batch)) * 2):
                print(render_row(""))
            
        print(render_box_line("├", "─", "┤"))
        print(render_row(f"{C_CYAN}{C_BOLD}[操作]{C_RESET} [↑/k] 上移  [↓/j] 下移  [Enter] 详情证据  [n] 下页  [p] 上页  [g] 跳页  [b] 返回", "center"))
        print(render_box_line("└", "─", "┘"))
        
        k = getkey()
        if k in ('up', 'k', 'w', '\x1b[A', '\x1bOA'):
            if selected_idx > 0:
                selected_idx -= 1
            elif subpage > 0:
                subpage -= 1
                selected_idx = page_size - 1
            elif server_page > 1:
                server_page -= 1
                subpage = 0
                selected_idx = 0
        elif k in ('down', 'j', 's', '\x1b[B', '\x1bOB'):
            if selected_idx < len(cur_batch) - 1:
                selected_idx += 1
            elif subpage < total_subpages - 1:
                subpage += 1
                selected_idx = 0
            elif cur_batch:
                server_page += 1
                subpage = 0
                selected_idx = 0
        elif k in ('n', 'right'):
            if subpage < total_subpages - 1:
                subpage += 1
                selected_idx = 0
            elif cur_batch:
                server_page += 1
                subpage = 0
                selected_idx = 0
        elif k in ('p', 'left'):
            if subpage > 0:
                subpage -= 1
                selected_idx = 0
            elif server_page > 1:
                server_page -= 1
                subpage = 0
                selected_idx = 0
        elif k in ('g',):
            os.system('cls' if os.name == 'nt' else 'clear')
            try:
                g_str = input(f"请输入要跳转的页码 (当前第 {server_page} 页) > ").strip()
                if g_str.isdigit() and int(g_str) > 0:
                    server_page = int(g_str)
                    subpage = 0
                    selected_idx = 0
            except (KeyboardInterrupt, EOFError):
                pass
        elif k in ('r',):
            cached_pages.pop(server_page, None)
        elif k in ('enter', 'space', '\r', '\n'):
            if cur_batch and 0 <= selected_idx < len(cur_batch):
                show_hygiene_detail_tui(cur_batch[selected_idx].get("id"))
        elif k in ('b', 'q', 'esc'):
            break

def show_lostfound_detail_tui(l_id):
    if not l_id:
        return
    os.system('cls' if os.name == 'nt' else 'clear')
    cmd_lostfound(DummyArgs(show=int(l_id), download=False, out="."))
    print(f"\n{C_CYAN}{C_BOLD}[快捷操作]{C_RESET} [d] 下载关联图片  [b / ESC / 回车] 返回列表")
    k = getkey()
    if k in ('d', 'D'):
        try:
            out_dir = input("\n请输入图片保存目录 (直接回车保存在当前目录) > ").strip() or "."
            cmd_lostfound(DummyArgs(show=int(l_id), download=True, out=out_dir))
            print("\n下载完成。按任意键返回列表...")
            getkey()
        except (KeyboardInterrupt, EOFError):
            pass

def fetch_lostfound_data(page):
    res = fetch_lostfound(page=page)
    if not res.get("success"):
        return {"items": [], "error": res.get("error", "获取失物招领失败")}
    return {"items": res.get("data", []), "error": None}

def tui_lostfound_paginated():
    server_page = 1
    page_size = 6
    selected_idx = 0
    subpage = 0
    cached_pages = {}
    
    while True:
        if server_page not in cached_pages:
            os.system('cls' if os.name == 'nt' else 'clear')
            print(f"\n{C_CYAN}[i] 正在获取失物招领记录 (第 {server_page} 页)...{C_RESET}")
            res_obj = fetch_lostfound_data(server_page)
            cached_pages[server_page] = res_obj
        else:
            res_obj = cached_pages[server_page]
            
        items = res_obj.get("items", [])
        err = res_obj.get("error")
            
        total_subpages = max(1, (len(items) + page_size - 1) // page_size) if items else 1
        if subpage >= total_subpages:
            subpage = max(0, total_subpages - 1)
        start_idx = subpage * page_size
        end_idx = min(start_idx + page_size, len(items)) if items else 0
        cur_batch = items[start_idx:end_idx] if items else []
        if selected_idx >= len(cur_batch):
            selected_idx = max(0, len(cur_batch) - 1)
        
        os.system('cls' if os.name == 'nt' else 'clear')
        print(render_box_line("┌", "─", "┐"))
        print(render_row(f"{C_CYAN}{C_BOLD}🔍 校园失物招领 (Lost & Found){C_RESET}", "center"))
        print(render_box_line("├", "─", "┤"))
        page_info = f"{C_BOLD}[页码]{C_RESET} 第 {server_page} 页 · 分屏 {subpage+1}/{total_subpages} (本屏 {len(cur_batch)} 条 / 共 {len(items)} 条)"
        status_disp = f"{C_GREEN}● 就绪{C_RESET}" if not err else f"{C_RED}● 异常{C_RESET}"
        print(render_row(f"{page_info}    {C_BOLD}[状态]{C_RESET} {status_disp}"))
        print(render_box_line("├", "─", "┤"))
        
        if err:
            print(render_row(f"{C_RED}⚠️ {err}{C_RESET}", "center"))
            print(render_row(f"{C_GREY}提示: 请检查校园内网连接或在主菜单按 1 重新登录{C_RESET}", "center"))
            for _ in range(8):
                print(render_row(""))
        elif not items:
            print(render_row(f"{C_YELLOW}当前失物招领第 {server_page} 页暂无更多数据{C_RESET}", "center"))
            for _ in range(9):
                print(render_row(""))
        else:
            for idx, item in enumerate(cur_batch):
                num_tag = f"[{start_idx + idx + 1:02d}]"
                l_id = item.get("id", "")
                title = item.get("title", "未命名物品")
                cat = item.get("category", "")
                reporter = item.get("reporter", "")
                date = item.get("date", "")
                status = item.get("status", "")
                cat_prefix = f"[{cat}] " if cat else ""
                disp_title = f"{cat_prefix}{title}"
                max_w = 46
                if get_visual_width(disp_title) > max_w:
                    tr = ""
                    w = 0
                    for ch in disp_title:
                        cw = 2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1
                        if w + cw > max_w - 3:
                            break
                        tr += ch
                        w += cw
                    disp_title = tr + "..."
                status_tag = f"{C_YELLOW}[{status}]{C_RESET}" if status else ""
                if idx == selected_idx:
                    l1 = f"{C_GREEN}{C_BOLD}▶ {num_tag} [{l_id}] {disp_title}{C_RESET}"
                    l2 = f"        登记人: {C_CYAN}{reporter}{C_RESET}    时间: {C_GREY}{date}{C_RESET}  {status_tag}"
                else:
                    l1 = f"  {C_GREY}{num_tag}{C_RESET} [{l_id}] {disp_title}"
                    l2 = f"        登记人: {C_GREY}{reporter}{C_RESET}    时间: {C_GREY}{date}{C_RESET}  {status_tag}"
                print(render_row(l1))
                print(render_row(l2))
            for _ in range((page_size - len(cur_batch)) * 2):
                print(render_row(""))
            
        print(render_box_line("├", "─", "┤"))
        print(render_row(f"{C_CYAN}{C_BOLD}[操作]{C_RESET} [↑/k] 上移  [↓/j] 下移  [Enter] 详情图片  [n] 下页  [p] 上页  [g] 跳页  [b] 返回", "center"))
        print(render_box_line("└", "─", "┘"))
        
        k = getkey()
        if k in ('up', 'k', 'w', '\x1b[A', '\x1bOA'):
            if selected_idx > 0:
                selected_idx -= 1
            elif subpage > 0:
                subpage -= 1
                selected_idx = page_size - 1
            elif server_page > 1:
                server_page -= 1
                subpage = 0
                selected_idx = 0
        elif k in ('down', 'j', 's', '\x1b[B', '\x1bOB'):
            if selected_idx < len(cur_batch) - 1:
                selected_idx += 1
            elif subpage < total_subpages - 1:
                subpage += 1
                selected_idx = 0
            elif cur_batch:
                server_page += 1
                subpage = 0
                selected_idx = 0
        elif k in ('n', 'right'):
            if subpage < total_subpages - 1:
                subpage += 1
                selected_idx = 0
            elif cur_batch:
                server_page += 1
                subpage = 0
                selected_idx = 0
        elif k in ('p', 'left'):
            if subpage > 0:
                subpage -= 1
                selected_idx = 0
            elif server_page > 1:
                server_page -= 1
                subpage = 0
                selected_idx = 0
        elif k in ('g',):
            os.system('cls' if os.name == 'nt' else 'clear')
            try:
                g_str = input(f"请输入要跳转的页码 (当前第 {server_page} 页) > ").strip()
                if g_str.isdigit() and int(g_str) > 0:
                    server_page = int(g_str)
                    subpage = 0
                    selected_idx = 0
            except (KeyboardInterrupt, EOFError):
                pass
        elif k in ('r',):
            cached_pages.pop(server_page, None)
        elif k in ('enter', 'space', '\r', '\n'):
            if cur_batch and 0 <= selected_idx < len(cur_batch):
                show_lostfound_detail_tui(cur_batch[selected_idx].get("id"))
        elif k in ('b', 'q', 'esc'):
            break

def tui_schedule_interactive():
    curr_grade = 1
    curr_class = "1"
    
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print(render_box_line("┌", "─", "┐"))
        print(render_row(f"{C_CYAN}{C_BOLD}📅 班级课表查询 (Class Schedule){C_RESET}", "center"))
        print(render_box_line("├", "─", "┤"))
        grade_name = {1: "高一年级", 2: "高二年级", 3: "高三年级"}.get(curr_grade, f"高{curr_grade}")
        print(render_row(f"{C_BOLD}[当前目标]{C_RESET} {C_YELLOW}{grade_name} {curr_class}班{C_RESET}"))
        print(render_box_line("├", "─", "┤"))
        print(render_row("正在从校园网拉取课表并渲染..."))
        print(render_box_line("└", "─", "┘\n"))
        
        cmd_schedule(DummyArgs(grade=curr_grade, ch_class=curr_class))
        
        print(f"\n{C_CYAN}{C_BOLD}[快捷操作]{C_RESET} [c] 切换班级  [g] 切换年级  [b / ESC / q] 返回主菜单")
        k = getkey()
        if k in ('c', 'C'):
            try:
                new_c = input(f"请输入要查询的班级 (1-12，当前: {curr_class}) > ").strip()
                if new_c:
                    curr_class = new_c
            except (KeyboardInterrupt, EOFError):
                pass
        elif k in ('g', 'G'):
            try:
                new_g = input(f"请输入年级 (1=高一, 2=高二, 3=高三，当前: {curr_grade}) > ").strip()
                if new_g in ('1', '2', '3'):
                    curr_grade = int(new_g)
            except (KeyboardInterrupt, EOFError):
                pass
        elif k in ('b', 'q', 'esc', '\x1b'):
            break

def execute_duty_action(action):
    os.system('cls' if os.name == 'nt' else 'clear')
    if action == 'current':
        cmd_duty(DummyArgs(search=None, all=False))
    elif action == 'all':
        cmd_duty(DummyArgs(search=None, all=True))
    elif action == 'search':
        try:
            q = input(f"\n请输入要搜索的教师姓名或班级名称 > ").strip()
            if q:
                cmd_duty(DummyArgs(search=q, all=False))
        except (KeyboardInterrupt, EOFError):
            pass
    print(f"\n{C_CYAN}按任意键返回值周菜单...{C_RESET}")
    getkey()

def tui_duty_interactive():
    duty_opts = [
        ("查看当前周值周安排 (Current Week)", "current"),
        ("查看整学期值周排班总表 (Full Semester)", "all"),
        ("搜索值周教师或班级姓名 (Search)", "search"),
        ("返回主菜单", "back")
    ]
    sub_idx = 0
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print(render_box_line("┌", "─", "┐"))
        print(render_row(f"{C_CYAN}{C_BOLD}📋 教师值周安排 (Teacher Duty){C_RESET}", "center"))
        print(render_box_line("├", "─", "┤"))
        print(render_row("请选择查询维度："))
        print(render_box_line("├", "─", "┤"))
        for idx, (d_name, _) in enumerate(duty_opts):
            num_tag = f"[{idx+1}]" if idx < len(duty_opts) - 1 else "[0]"
            if idx == sub_idx:
                row_str = f"{C_GREEN}{C_BOLD}▶ {num_tag} {d_name}{C_RESET}"
            else:
                row_str = f"  {C_GREY}{num_tag}{C_RESET} {d_name}"
            print(render_row(row_str))
        print(render_box_line("├", "─", "┤"))
        print(render_row(f"{C_CYAN}{C_BOLD}[快捷操作]{C_RESET} [↑/k] 上移  [↓/j] 下移  [Enter] 确认  [1-3/0] 直达  [b/q] 返回", "center"))
        print(render_box_line("└", "─", "┘"))
        
        k = getkey()
        if k in ('up', 'k', 'w', '\x1b[A', '\x1bOA'):
            sub_idx = (sub_idx - 1) % len(duty_opts)
        elif k in ('down', 'j', 's', '\x1b[B', '\x1bOB'):
            sub_idx = (sub_idx + 1) % len(duty_opts)
        elif k in ('1', '2', '3'):
            sub_idx = int(k) - 1
            execute_duty_action(duty_opts[sub_idx][1])
        elif k == '0' or k in ('b', 'q', 'esc'):
            break
        elif k in ('enter', 'space', '\r', '\n'):
            if duty_opts[sub_idx][1] == 'back':
                break
            execute_duty_action(duty_opts[sub_idx][1])

def execute_bedroom_action(action):
    os.system('cls' if os.name == 'nt' else 'clear')
    if action == 'class':
        try:
            g_str = input("请输入年级 (1=高一, 2=高二, 3=高三，默认 1) > ").strip() or "1"
            c_str = input("请输入班级 (如 1 或 1班，默认 1) > ").strip() or "1"
            if g_str in ('1', '2', '3') and c_str:
                cmd_bedroom(DummyArgs(action="class", grade=int(g_str), ch_class=c_str))
        except (KeyboardInterrupt, EOFError):
            pass
    elif action == 'hygiene':
        try:
            dorm = input("请输入宿舍楼宇名称或编号 (如 1 或 3号楼，默认 1) > ").strip() or "1"
            start = input("请输入开始日期 (YYYY-MM-DD，回车默认为30天前) > ").strip() or None
            end = input("请输入结束日期 (YYYY-MM-DD，回车默认为今天) > ").strip() or None
            all_flag = input("是否显示该楼宇全部宿舍（包括未扣分的）？(y/N) > ").strip().lower() == 'y'
            cmd_bedroom(DummyArgs(action="hygiene", dorm=dorm, start=start, end=end, all=all_flag))
        except (KeyboardInterrupt, EOFError):
            pass
    print(f"\n{C_CYAN}按任意键返回寝室菜单...{C_RESET}")
    getkey()

def tui_bedroom_interactive():
    bed_opts = [
        ("查询指定班级的寝室分配分布 (Class Bedrooms)", "class"),
        ("查询指定楼宇寝室日常考评扣分表 (Dorm Hygiene Deductions)", "hygiene"),
        ("返回主菜单", "back")
    ]
    sub_idx = 0
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print(render_box_line("┌", "─", "┐"))
        print(render_row(f"{C_CYAN}{C_BOLD}🛏️ 寝室查询与日常扣分 (Dormitory Info){C_RESET}", "center"))
        print(render_box_line("├", "─", "┤"))
        print(render_row("请选择寝室业务功能："))
        print(render_box_line("├", "─", "┤"))
        for idx, (b_name, _) in enumerate(bed_opts):
            num_tag = f"[{idx+1}]" if idx < len(bed_opts) - 1 else "[0]"
            if idx == sub_idx:
                row_str = f"{C_GREEN}{C_BOLD}▶ {num_tag} {b_name}{C_RESET}"
            else:
                row_str = f"  {C_GREY}{num_tag}{C_RESET} {b_name}"
            print(render_row(row_str))
        print(render_box_line("├", "─", "┤"))
        print(render_row(f"{C_CYAN}{C_BOLD}[快捷操作]{C_RESET} [↑/k] 上移  [↓/j] 下移  [Enter] 确认  [1-2/0] 直达  [b/q] 返回", "center"))
        print(render_box_line("└", "─", "┘"))
        
        k = getkey()
        if k in ('up', 'k', 'w', '\x1b[A', '\x1bOA'):
            sub_idx = (sub_idx - 1) % len(bed_opts)
        elif k in ('down', 'j', 's', '\x1b[B', '\x1bOB'):
            sub_idx = (sub_idx + 1) % len(bed_opts)
        elif k in ('1', '2'):
            sub_idx = int(k) - 1
            execute_bedroom_action(bed_opts[sub_idx][1])
        elif k == '0' or k in ('b', 'q', 'esc'):
            break
        elif k in ('enter', 'space', '\r', '\n'):
            if bed_opts[sub_idx][1] == 'back':
                break
            execute_bedroom_action(bed_opts[sub_idx][1])

def execute_file_action(action):
    os.system('cls' if os.name == 'nt' else 'clear')
    if action == 'upload':
        try:
            path = input("请输入要上传的本地文件完整路径 > ").strip()
            if path:
                cmd_file_upload(path)
        except (KeyboardInterrupt, EOFError):
            pass
    elif action == 'download':
        try:
            pwd = input("请输入 6 位提取码 > ").strip()
            if pwd:
                out_dir = input("请输入保存目录 (直接回车保存到当前目录) > ").strip() or "."
                cmd_file_download(pwd, out_dir)
        except (KeyboardInterrupt, EOFError):
            pass
    print(f"\n{C_CYAN}按任意键返回文件菜单...{C_RESET}")
    getkey()

def tui_file_interactive():
    file_opts = [
        ("上传本地文件 (生成 6 位安全提取码)", "upload"),
        ("提取远端文件 (输入 6 位提取码并保存)", "download"),
        ("返回主菜单", "back")
    ]
    sub_idx = 0
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print(render_box_line("┌", "─", "┐"))
        print(render_row(f"{C_CYAN}{C_BOLD}📦 学校文件寄存与提取 (File Station){C_RESET}", "center"))
        print(render_box_line("├", "─", "┤"))
        print(render_row("请选择文件存取操作："))
        print(render_box_line("├", "─", "┤"))
        for idx, (f_name, _) in enumerate(file_opts):
            num_tag = f"[{idx+1}]" if idx < len(file_opts) - 1 else "[0]"
            if idx == sub_idx:
                row_str = f"{C_GREEN}{C_BOLD}▶ {num_tag} {f_name}{C_RESET}"
            else:
                row_str = f"  {C_GREY}{num_tag}{C_RESET} {f_name}"
            print(render_row(row_str))
        print(render_box_line("├", "─", "┤"))
        print(render_row(f"{C_CYAN}{C_BOLD}[快捷操作]{C_RESET} [↑/k] 上移  [↓/j] 下移  [Enter] 确认  [1-2/0] 直达  [b/q] 返回", "center"))
        print(render_box_line("└", "─", "┘"))
        
        k = getkey()
        if k in ('up', 'k', 'w', '\x1b[A', '\x1bOA'):
            sub_idx = (sub_idx - 1) % len(file_opts)
        elif k in ('down', 'j', 's', '\x1b[B', '\x1bOB'):
            sub_idx = (sub_idx + 1) % len(file_opts)
        elif k in ('1', '2'):
            sub_idx = int(k) - 1
            execute_file_action(file_opts[sub_idx][1])
        elif k == '0' or k in ('b', 'q', 'esc'):
            break
        elif k in ('enter', 'space', '\r', '\n'):
            if file_opts[sub_idx][1] == 'back':
                break
            execute_file_action(file_opts[sub_idx][1])

def execute_login_action(action):
    os.system('cls' if os.name == 'nt' else 'clear')
    if action == 'auto':
        cmd_login_auto()
    elif action == 'cred':
        cmd_login(DummyArgs(auto=False, cookie=None, username=None, password=None, code=None))
    elif action == 'manual':
        print(f"{C_BOLD}请输入从浏览器获取的 Cookie 字符串：{C_RESET}")
        try:
            c_str = input(f"{C_CYAN}Cookie > {C_RESET}").strip()
            if c_str:
                res = login_with_cookie(c_str)
                if res["success"]:
                    log_success(res["message"])
                else:
                    log_error(res["error"])
        except (KeyboardInterrupt, EOFError):
            pass
    elif action == 'test':
        check_login_status(verbose=True)
    elif action == 'logout':
        cmd_logout()
    print(f"\n{C_CYAN}按任意键返回登录菜单...{C_RESET}")
    getkey()

def tui_login_menu():
    sub_opts = [
        ("自动从本机浏览器读取 Cookie (推荐，支持 Safari / Firefox / Chrome / Edge)", "auto"),
        ("账号密码 + 验证码登录 (自动拉取并弹出验证码，输入后直接登录)", "cred"),
        ("手动粘贴导入 Cookie 字符串", "manual"),
        ("测试与验证当前登录状态", "test"),
        ("清除本地登录凭据 (安全退出登录)", "logout"),
        ("返回主菜单", "back")
    ]
    sub_idx = 0
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        session = load_session()
        has_sess = bool(session.get("sessionid"))
        sess_str = f"{C_GREEN}● 已配置 (Session Ready){C_RESET}" if has_sess else f"{C_YELLOW}○ 未配置 (No Session){C_RESET}"
        
        print(render_box_line("┌", "─", "┐"))
        print(render_row(f"{C_CYAN}{C_BOLD}🔐 春晖校园网登录与凭据中心{C_RESET}", "center"))
        print(render_box_line("├", "─", "┤"))
        print(render_row(f"{C_BOLD}[系统节点]{C_RESET} 10.181.200.3    {C_BOLD}[当前凭据]{C_RESET} {sess_str}"))
        print(render_box_line("├", "─", "┤"))
        for idx, (opt_name, _) in enumerate(sub_opts):
            num_tag = f"[{idx+1}]" if idx < len(sub_opts) - 1 else "[0]"
            if idx == sub_idx:
                row_str = f"{C_GREEN}{C_BOLD}▶ {num_tag} {opt_name}{C_RESET}"
            else:
                row_str = f"  {C_GREY}{num_tag}{C_RESET} {opt_name}"
            print(render_row(row_str))
        print(render_box_line("├", "─", "┤"))
        print(render_row(f"{C_CYAN}{C_BOLD}[快捷操作]{C_RESET} [↑/k] 上移  [↓/j] 下移  [Enter] 确认  [1-5/0] 直达  [b/q] 返回", "center"))
        print(render_box_line("└", "─", "┘"))
        
        k = getkey()
        if k in ('up', 'k', 'w', '\x1b[A', '\x1bOA'):
            sub_idx = (sub_idx - 1) % len(sub_opts)
        elif k in ('down', 'j', 's', '\x1b[B', '\x1bOB'):
            sub_idx = (sub_idx + 1) % len(sub_opts)
        elif k in ('1', '2', '3', '4', '5'):
            sub_idx = int(k) - 1
            execute_login_action(sub_opts[sub_idx][1])
        elif k == '0' or k in ('b', 'q', 'esc'):
            break
        elif k in ('enter', 'space', '\r', '\n'):
            if sub_opts[sub_idx][1] == 'back':
                break
            execute_login_action(sub_opts[sub_idx][1])

def tui_status_card():
    os.system('cls' if os.name == 'nt' else 'clear')
    session = load_session()
    has_sess = bool(session.get("sessionid"))
    sess_str = f"{C_GREEN}● 已配置 (Session Ready){C_RESET}" if has_sess else f"{C_YELLOW}○ 未配置 (No Session){C_RESET}"
    
    print(render_box_line("┌", "─", "┐"))
    print(render_row(f"{C_CYAN}{C_BOLD}ℹ️ 登录状态与系统网络环境{C_RESET}", "center"))
    print(render_box_line("├", "─", "┤"))
    print(render_row(f"{C_BOLD}[系统节点]{C_RESET} 10.181.200.3    {C_BOLD}[凭据状态]{C_RESET} {sess_str}"))
    print(render_row(f"{C_GREY}本地会话存储: {SESSION_FILE}{C_RESET}"))
    print(render_box_line("├", "─", "┤"))
    print(render_row("正在向内网服务器发起实时心跳验证..."))
    print(render_box_line("└", "─", "┘\n"))
    
    check_login_status(verbose=True)
    
    print(f"\n{C_CYAN}按任意键返回主菜单...{C_RESET}")
    getkey()

def tui_briefing():
    os.system('cls' if os.name == 'nt' else 'clear')
    cmd_briefing()
    print(f"{C_CYAN}按任意键返回主菜单...{C_RESET}")
    getkey()

def tui_lottery():
    os.system('cls' if os.name == 'nt' else 'clear')
    cmd_lottery()
    print(f"{C_CYAN}按任意键返回主菜单...{C_RESET}")
    getkey()

def tui_anydoor():
    os.system('cls' if os.name == 'nt' else 'clear')
    cmd_anydoor()
    print(f"{C_CYAN}按任意键返回主菜单...{C_RESET}")
    getkey()

def handle_tui_action(choice):
    try:
        if choice == 0:
            tui_briefing()
        elif choice == 1:
            tui_lottery()
        elif choice == 2:
            tui_anydoor()
        elif choice == 3:
            tui_login_menu()
        elif choice == 4:
            tui_status_card()
        elif choice == 5:
            tui_schedule_interactive()
        elif choice == 6:
            tui_messages_paginated()
        elif choice == 7:
            tui_hygiene_paginated()
        elif choice == 8:
            tui_duty_interactive()
        elif choice == 9:
            tui_news_interactive()
        elif choice == 10:
            tui_bedroom_interactive()
        elif choice == 11:
            tui_lostfound_paginated()
        elif choice == 12:
            tui_file_interactive()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log_error(f"TUI 操作执行出错: {e}")
        print("\n按任意键返回主菜单...")
        getkey()

def run_tui():
    if not sys.stdin.isatty():
        print(f"{C_YELLOW}未检测到交互式终端环境，显示命令帮助：{C_RESET}")
        main_file = os.path.basename(sys.argv[0])
        cmd = f"python3 {main_file} --help" if main_file.endswith('.py') else f"{main_file} --help"
        os.system(cmd)
        return

    main_file = os.path.basename(sys.argv[0])
    if main_file.endswith('.py'):
        cmd_prefix = f"python3 {main_file}"
    else:
        cmd_prefix = main_file

    options = [
        ("白马湖每日晨报 (Daily Briefing)", f"{cmd_prefix} briefing", "今日名言、农历岁次、白马湖气象速报与哲思推荐"),
        ("课堂抽签点名器 (Class Lottery)", f"{cmd_prefix} lottery", "课堂随机抽选学号、平滑数字滚动动画、支持防重复与重置"),
        ("校园内网任意门 (AnyDoor Portal)", f"{cmd_prefix} anydoor", "一键直达校园网门户、云上春晖 NAS、图库、视频与 AI 助手"),
        ("登录系统 (Import Cookie)", f"{cmd_prefix} login", "导入浏览器获取的会话 Cookie，完成身份认证与凭据存储"),
        ("查询登录状态 (Check Status)", f"{cmd_prefix} status", "检测当前会话有效性，查看在线状态与用户基础信息"),
        ("班级课表查询 (Class Schedule)", f"{cmd_prefix} schedule", "查询高一至高三年级各班级完整课程表与任课教师团队"),
        ("收件箱消息 (Inbox Messages)", f"{cmd_prefix} messages", "浏览校内收件箱通知、查看详情并按需下载全部附件"),
        ("纪律卫生考评 (Hygiene Appraisals)", f"{cmd_prefix} hygiene", "查询班级常规评比、卫生检查扣分明细与多媒体证据"),
        ("教师值周安排 (Teacher Duty)", f"{cmd_prefix} duty", "查看本周或整学期教师值周表，支持按教师或班级模糊检索"),
        ("校内文章资讯 (Campus News)", f"{cmd_prefix} news", "浏览通知公告、新闻聚焦、校内公示与值周小结"),
        ("寝室查询与扣分 (Dormitory Info)", f"{cmd_prefix} bedroom", "查询班级宿舍分配分布与各楼宇宿舍日常考评扣分"),
        ("校园失物招领 (Lost & Found)", f"{cmd_prefix} lostfound", "浏览失物招领信息、查看详情并支持附件图片下载"),
        ("文件寄存与提取 (File Station)", f"{cmd_prefix} file", "校内文件传输，支持本地文件上传寄存与提取码下载"),
        ("退出程序 (Exit Console)", "", "安全退出春晖中学校园网控制台")
    ]

    inner_w = 74

    def render_box_line(left, fill, right):
        return f"{C_BLUE}{left}{fill * inner_w}{right}{C_RESET}"

    def render_row(content, align="left"):
        return f"{C_BLUE}│{C_RESET} {pad_text(content, inner_w - 2, align)} {C_BLUE}│{C_RESET}"

    banner = [
        r"  ____ _                  _           _        ____ _     ___ ",
        r" / ___| |__  _   _ _ __  | |__  _   _(_)      / ___| |   |_ _|",
        r"| |   | '_ \| | | | '_ \ | '_ \| | | | |_____| |   | |    | | ",
        r"| |___| | | | |_| | | | || | | | |_| | |_____| |___| |___ | | ",
        r" \____|_| |_|\__,_|_| |_||_| |_|\__,_|_|      \____|_____|___|"
    ]

    selected_idx = 0
    try:
        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            session = load_session()
            has_session = bool(session.get("sessionid"))
            session_status = f"{C_GREEN}● 已配置 (Session Ready){C_RESET}" if has_session else f"{C_YELLOW}○ 未配置 (No Session){C_RESET}"

            print(render_box_line("┌", "─", "┐"))
            for b in banner:
                print(render_row(f"{C_CYAN}{C_BOLD}{b}{C_RESET}", "center"))
            print(render_row(""))
            print(render_row(f"{C_YELLOW}{C_BOLD}浙江省春晖中学校园网控制台 · CHUNHUI HIGH SCHOOL{C_RESET}", "center"))
            print(render_box_line("├", "─", "┤"))
            print(render_row(f"{C_BOLD}[系统节点]{C_RESET} 10.181.200.3    {C_BOLD}[会话状态]{C_RESET} {session_status}"))
            print(render_row(f"{C_BOLD}[今日岁次]{C_RESET} {get_lunar_date_str()}"))
            print(render_box_line("├", "─", "┤"))

            for idx, (title, cmd, _) in enumerate(options):
                num_tag = f"[{idx+1:02d}]"
                if idx == selected_idx:
                    left_part = f"{C_GREEN}{C_BOLD}▶ {num_tag} {title}{C_RESET}"
                    right_part = f"{C_GREEN}{C_BOLD}{cmd}{C_RESET}" if cmd else ""
                else:
                    left_part = f"  {C_GREY}{num_tag}{C_RESET} {title}"
                    right_part = f"{C_GREY}{cmd}{C_RESET}" if cmd else ""

                left_padded = pad_text(left_part, 48, align="left")
                right_padded = pad_text(right_part, 20, align="right")
                print(render_row(f"{left_padded} {right_padded}"))

            print(render_box_line("├", "─", "┤"))
            cur_title, _, cur_desc = options[selected_idx]
            print(render_row(f"{C_YELLOW}{C_BOLD}[当前功能]{C_RESET} {C_BOLD}{cur_title}{C_RESET}"))
            print(render_row(f"{C_GREY}详细说明: {cur_desc}{C_RESET}"))
            print(render_box_line("├", "─", "┤"))
            print(render_row(f"{C_CYAN}{C_BOLD}[快捷操作]{C_RESET} [↑/k/w] 上移  [↓/j/s] 下移  [1-9/0] 直达  [Enter] 确认  [q] 退出", "center"))
            print(render_box_line("└", "─", "┘"))

            key = getkey()
            if key in ('up', 'k', 'w', '\x1b[A', '\x1bOA'):
                selected_idx = (selected_idx - 1) % len(options)
            elif key in ('down', 'j', 's', '\x1b[B', '\x1bOB'):
                selected_idx = (selected_idx + 1) % len(options)
            elif key in ('pageup',):
                selected_idx = (selected_idx - 5) % len(options)
            elif key in ('pagedown',):
                selected_idx = (selected_idx + 5) % len(options)
            elif key in ('enter', 'space', '\r', '\n'):
                if selected_idx == len(options) - 1:
                    break
                else:
                    handle_tui_action(selected_idx)
            elif key in ('1', '2', '3', '4', '5', '6', '7', '8', '9'):
                target = int(key) - 1
                if 0 <= target < len(options) - 1:
                    selected_idx = target
                    handle_tui_action(selected_idx)
            elif key == '0':
                selected_idx = 9
                handle_tui_action(selected_idx)
            elif key in ('q', 'esc'):
                break
    except KeyboardInterrupt:
        pass
    print("\n已退出控制台。")

def main():
    if len(sys.argv) == 1:
        run_tui()
        sys.exit(0)
    for idx, arg in enumerate(sys.argv):
        if arg == "?":
            sys.argv[idx] = "-h"

    parser = argparse.ArgumentParser(
        description=f"{C_BOLD}{C_CYAN}浙江省春晖中学校园网 CLI 工具 (ch_cli){C_RESET}",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # login command
    parser_login = subparsers.add_parser("login", help="校园网账号密码或 Cookie 登录")
    parser_login.add_argument("--auto", action="store_true", help="自动从本机浏览器获取并同步 Cookie")
    parser_login.add_argument("--cookie", type=str, help="直接指定 Cookie 字符串")
    parser_login.add_argument("-u", "--username", type=str, help="登录用户名/学号")
    parser_login.add_argument("-p", "--password", type=str, help="登录密码")
    parser_login.add_argument("-c", "--code", type=str, help="验证码")

    # logout command
    subparsers.add_parser("logout", help="退出当前登录并清除本地会话")

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

    # briefing command
    subparsers.add_parser("briefing", aliases=["morning", "daily"], help="白马湖每日晨报 (今日名言、农历天气与哲思推荐)")

    # lottery command
    parser_lottery = subparsers.add_parser("lottery", aliases=["roll"], help="课堂抽签点名器 (随机抽选学号、平滑数字滚动动画)")
    parser_lottery.add_argument("--min", type=int, default=1, help="学号最小值 (默认: 1)")
    parser_lottery.add_argument("--max", type=int, default=50, help="学号最大值 (默认: 50)")
    parser_lottery.add_argument("--repeat", action="store_true", help="允许重复抽取同一学号 (默认防重复)")

    # anydoor / portal command
    subparsers.add_parser("anydoor", aliases=["portal"], help="校园内网任意门服务聚合导航 (一键直达校园基础设施)")

    args = parser.parse_args()

    if args.command == "bedroom" and not getattr(args, "action", None):
        parser_bed.print_help()
        sys.exit(0)
    elif args.command == "file" and not getattr(args, "action", None):
        parser_file.print_help()
        sys.exit(0)

    if args.command in ("briefing", "morning", "daily"):
        cmd_briefing(args)
    elif args.command in ("lottery", "roll"):
        cmd_lottery(args)
    elif args.command in ("anydoor", "portal"):
        cmd_anydoor(args)
    elif args.command == "login":
        cmd_login(args)
    elif args.command == "logout":
        cmd_logout(args)
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