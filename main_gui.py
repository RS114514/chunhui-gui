#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import time
import json
import threading
import urllib.parse
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image, ImageTk

# 引入我们刚才重命名并更新后的底层逻辑客户端
import ch_cli

# 配置 CustomTkinter 全局主题与外观
ctk.set_appearance_mode("System")  # System, Dark, Light
ctk.set_default_color_theme("blue")  # blue, green, dark-blue

def get_theme_colors():
    is_dark = (ctk.get_appearance_mode() == "Dark")
    return {
        "card_bg": "#2b2b2b" if is_dark else "#dbdbdb",
        "text_primary": "#ffffff" if is_dark else "#000000",
        "text_secondary": "#aaaaaa" if is_dark else "#555555"
    }

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        # 设置窗口基本属性
        self.title("春晖中学校园网 GUI 客户端 (chunhui-gui)")
        self.geometry("1100x750")
        self.minsize(1000, 700)

        # 设置精美的应用图标
        try:
            self.iconbitmap("app.ico")
        except Exception:
            try:
                # 适配 macOS 平台
                self.icon_photo = ImageTk.PhotoImage(file="app.png")
                self.wm_iconphoto(True, self.icon_photo)
            except Exception:
                pass


        # 布局：1行 x 2列 (左侧导航, 右侧多面板展示区)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # 初始化左侧边栏
        self.init_sidebar()

        # 初始化右侧各个功能面板框架
        self.frames = {}
        self.init_all_frames()

        # 默认选中第一页：收件箱
        self.select_frame("messages")
        
        # 异步验证一次登录连接状态
        self.check_login_status_async()

    def init_sidebar(self):
        # 侧边栏 Frame
        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(9, weight=1)

        # 应用大标题
        self.title_label = ctk.CTkLabel(self.sidebar, text="浙江省春晖中学", font=ctk.CTkFont(size=20, weight="bold"))
        self.title_label.grid(row=0, column=0, padx=20, pady=(25, 2))
        self.subtitle_label = ctk.CTkLabel(self.sidebar, text="校园网客户端 (chunhui-gui)", text_color="grey50", font=ctk.CTkFont(size=12))
        self.subtitle_label.grid(row=1, column=0, padx=20, pady=(0, 20))

        # 导航按钮定义
        self.nav_buttons = {}
        menu_items = [
            ("messages", "✉  个人收件箱", 2),
            ("news", "📄  校内资讯公告", 3),
            ("hygiene", "🧹  纪律卫生考评", 4),
            ("bedroom", "🏠  寝室分配考评", 5),
            ("duty", "📅  教师值周排班", 6),
            ("lostfound", "🔍  全校失物招领", 7),
            ("file", "📁  学校文件寄取", 8)
        ]

        for code, label, row_idx in menu_items:
            btn = ctk.CTkButton(
                self.sidebar, 
                text=label, 
                fg_color="transparent", 
                text_color=("gray10", "gray90"),
                hover_color=("gray70", "gray30"),
                anchor="w",
                height=40,
                font=ctk.CTkFont(size=14),
                command=lambda c=code: self.select_frame(c)
            )
            btn.grid(row=row_idx, column=0, padx=15, pady=4, sticky="ew")
            self.nav_buttons[code] = btn

        # 底部账号状态与导入面板
        self.status_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.status_frame.grid(row=10, column=0, padx=15, pady=20, sticky="ew")
        
        self.status_indicator = ctk.CTkLabel(
            self.status_frame, 
            text="●  连线状态未知", 
            text_color="#ff9800",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.status_indicator.pack(pady=4, fill="x")

        self.login_btn = ctk.CTkButton(
            self.status_frame, 
            text="🔑 导入 Cookie 登录", 
            height=30,
            font=ctk.CTkFont(size=12),
            command=self.open_login_dialog
        )
        self.login_btn.pack(pady=5, fill="x")

    def init_all_frames(self):
        # 所有功能页面存放的容器 Frame
        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.grid(row=0, column=1, sticky="nsew", padx=15, pady=15)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        # 实例化各个面板
        self.frames["messages"] = MessagesFrame(self.container, self)
        self.frames["news"] = NewsFrame(self.container, self)
        self.frames["hygiene"] = HygieneFrame(self.container, self)
        self.frames["bedroom"] = BedroomFrame(self.container, self)
        self.frames["duty"] = DutyFrame(self.container, self)
        self.frames["lostfound"] = LostFoundFrame(self.container, self)
        self.frames["file"] = FileFrame(self.container, self)

        for name, frame in self.frames.items():
            frame.grid(row=0, column=0, sticky="nsew")

    def select_frame(self, name):
        # 高亮选中的导航按钮，恢复其余按钮
        for code, btn in self.nav_buttons.items():
            if code == name:
                btn.configure(fg_color=("gray80", "gray20"), text_color="#1088ff" if ctk.get_appearance_mode() == "Light" else "#00adb5")
            else:
                btn.configure(fg_color="transparent", text_color=("gray10", "gray90"))

        # 提升目标页面到最前显示
        self.frames[name].tkraise()
        # 切换页面时，若有刷新方法则刷新
        if hasattr(self.frames[name], "on_show"):
            self.frames[name].on_show()

    def open_login_dialog(self):
        dialog = CookieLoginDialog(self)
        self.wait_window(dialog)

    def check_login_status_async(self):
        def worker():
            cookies = ch_cli.load_session()
            if not cookies.get("sessionid"):
                self.set_login_status(False, "未登录")
                return
            
            # 向服务器请求验证状态
            status, _, _ = ch_cli.make_request("/article/article-detail/37079/", method="GET")
            if status == 200:
                self.set_login_status(True, "登录有效")
            else:
                self.set_login_status(False, "会话失效")
                
        threading.Thread(target=worker, daemon=True).start()

    def set_login_status(self, is_valid, msg):
        def update():
            if is_valid:
                self.status_indicator.configure(text=f"●  已连接 ({msg})", text_color="#4caf50")
            else:
                self.status_indicator.configure(text=f"●  未连接 ({msg})", text_color="#f44336")
        self.after(0, update)

    def run_async(self, func, *args, callback=None):
        def worker():
            try:
                res = func(*args)
                if callback:
                    self.after(0, callback, res)
            except Exception as e:
                if callback:
                    self.after(0, callback, (False, str(e)))
        threading.Thread(target=worker, daemon=True).start()


class CookieLoginDialog(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("导入 Cookie 进行连接")
        self.geometry("520x340")
        self.resizable(False, False)
        
        # 弹窗置顶
        self.transient(parent)
        self.wait_visibility()
        self.grab_set()

        self.grid_columnconfigure(0, weight=1)
        
        title = ctk.CTkLabel(self, text="🔑 导入浏览器 Cookie 会话", font=ctk.CTkFont(size=18, weight="bold"))
        title.grid(row=0, column=0, padx=20, pady=(20, 5), sticky="w")

        desc = ctk.CTkLabel(
            self, 
            text="通常可在浏览器 F12 的网络(Network)面板请求头中找到。请复制并粘贴以下格式的字符串：\n形如: sessionid=xxxxxx; csrftoken=yyyyyy", 
            text_color="grey60",
            font=ctk.CTkFont(size=12),
            justify="left"
        )
        desc.grid(row=1, column=0, padx=20, pady=5, sticky="w")

        self.cookie_text = ctk.CTkTextbox(self, height=120, border_width=1)
        self.cookie_text.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        
        # 预填充现有的 Cookie
        curr = ch_cli.load_session()
        if curr.get("sessionid"):
            pre_val = f"sessionid={curr['sessionid']}"
            if curr.get("csrftoken"):
                pre_val += f"; csrftoken={curr['csrftoken']}"
            self.cookie_text.insert("0.0", pre_val)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=3, column=0, padx=20, pady=15, sticky="e")

        self.cancel_btn = ctk.CTkButton(btn_frame, text="取消", width=90, fg_color="transparent", border_width=1, command=self.destroy)
        self.cancel_btn.pack(side="left", padx=5)

        self.ok_btn = ctk.CTkButton(btn_frame, text="导入并检测", width=110, command=self.save_and_test)
        self.ok_btn.pack(side="left", padx=5)

    def save_and_test(self):
        cookie_str = self.cookie_text.get("0.0", "end").strip()
        if not cookie_str:
            messagebox.showerror("错误", "请输入 Cookie 字符串！")
            return
            
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
            messagebox.showwarning("警告", "输入的 Cookie 中未检测到 sessionid，连接可能会失败。")

        session_data = {
            "sessionid": sessionid,
            "csrftoken": csrftoken
        }
        
        if not ch_cli.save_session(session_data):
            messagebox.showerror("错误", "无法保存会话文件，请检查目录权限！")
            return
        
        # 异步做一次网络连线检测
        self.ok_btn.configure(state="disabled", text="正在校验...")
        
        def check_task():
            status, _, _ = ch_cli.make_request("/article/article-detail/37079/", method="GET")
            if not self.winfo_exists():
                return
            if status == 200:
                self.parent.set_login_status(True, "导入成功")
                self.parent.after(0, lambda: messagebox.showinfo("成功", "Cookie 校验通过，登录成功！") if self.winfo_exists() else None)
                self.parent.after(0, lambda: self.destroy() if self.winfo_exists() else None)
            else:
                self.parent.set_login_status(False, f"HTTP {status} 校验失败")
                self.parent.after(0, lambda: messagebox.showerror("失败", f"Cookie 连线校验失败 (HTTP: {status})，请重新获取。") if self.winfo_exists() else None)
                self.parent.after(0, lambda: self.ok_btn.configure(state="normal", text="导入并检测") if self.winfo_exists() else None)

        threading.Thread(target=check_task, daemon=True).start()


class MessagesFrame(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color="transparent")
        self.controller = controller
        
        self.page = 1
        
        # 头部控制栏
        self.header = ctk.CTkFrame(self, fg_color="transparent")
        self.header.pack(fill="x", pady=(5, 10))
        
        self.title = ctk.CTkLabel(self.header, text="✉ 个人收件箱通知列表", font=ctk.CTkFont(size=18, weight="bold"))
        self.title.pack(side="left", padx=5)

        self.refresh_btn = ctk.CTkButton(self.header, text="🔄 刷新列表", width=100, command=self.load_list)
        self.refresh_btn.pack(side="right", padx=5)

        self.prev_btn = ctk.CTkButton(self.header, text="◀ 上一页", width=80, command=lambda: self.change_page(-1))
        self.prev_btn.pack(side="right", padx=5)
        
        self.page_label = ctk.CTkLabel(self.header, text="第 1 页", font=ctk.CTkFont(size=13))
        self.page_label.pack(side="right", padx=10)

        self.next_btn = ctk.CTkButton(self.header, text="下一页 ▶", width=80, command=lambda: self.change_page(1))
        self.next_btn.pack(side="right", padx=5)

        # 列表滑动容器
        self.scroll = ctk.CTkScrollableFrame(self)
        self.scroll.pack(fill="both", expand=True)

        self.loaded = False

    def on_show(self):
        if not self.loaded:
            self.load_list()

    def change_page(self, delta):
        if self.page + delta < 1:
            return
        self.page += delta
        self.page_label.configure(text=f"第 {self.page} 页")
        self.load_list()

    def load_list(self):
        self.refresh_btn.configure(state="disabled", text="正在拉取...")
        self.prev_btn.configure(state="disabled")
        self.next_btn.configure(state="disabled")
        for child in self.scroll.winfo_children():
            child.destroy()
            
        loading = ctk.CTkLabel(self.scroll, text="正在读取校园网数据，请稍候...", font=ctk.CTkFont(size=14))
        loading.pack(pady=40)

        def query_messages():
            url = f"/sitemessage/message-Receive-list/?page={self.page}"
            status, body, _ = ch_cli.make_request(url, method="GET")
            if status != 200:
                return False, f"HTTP Error: {status}"
                
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
                        title = ch_cli.clean_html(tds[1])
                        sender = ch_cli.clean_html(tds[2])
                        date = ch_cli.clean_html(tds[3]) if len(tds) > 3 else ""
                        rows.append((msg_id, title, sender, date))
            return True, rows

        def callback(res):
            self.refresh_btn.configure(state="normal", text="🔄 刷新列表")
            self.prev_btn.configure(state="normal" if self.page > 1 else "disabled")
            self.next_btn.configure(state="normal")
            for child in self.scroll.winfo_children():
                child.destroy()
                
            success, data = res
            if not success:
                err = ctk.CTkLabel(self.scroll, text=f"加载数据失败: {data}\n请确认您的 Cookie 是否有效并已联网。", text_color="red")
                err.pack(pady=40)
                return
                
            if not data:
                empty = ctk.CTkLabel(self.scroll, text="收件箱暂无消息通知。")
                empty.pack(pady=40)
                return
                
            self.loaded = True
            colors = get_theme_colors()
            for msg_id, title, sender, date in data:
                card = ctk.CTkFrame(self.scroll, corner_radius=6)
                card.pack(fill="x", padx=5, pady=5)
                
                # 双列：左侧文字，右侧按钮
                card.columnconfigure(0, weight=1)
                
                t_lbl = tk.Label(card, text=title, font=("Helvetica", 11, "bold"), fg=colors["text_primary"], bg=colors["card_bg"], anchor="w", justify="left")
                t_lbl.grid(row=0, column=0, padx=15, pady=(10, 2), sticky="w")
                
                info_lbl = tk.Label(card, text=f"发送人: {sender}   |   日期: {date}   |   ID: {msg_id}", fg=colors["text_secondary"], bg=colors["card_bg"], font=("Helvetica", 9), anchor="w", justify="left")
                info_lbl.grid(row=1, column=0, padx=15, pady=(0, 10), sticky="w")
                
                btn = ctk.CTkButton(card, text="阅读正文", width=90, command=lambda m=msg_id: self.show_detail(m))
                btn.grid(row=0, column=1, rowspan=2, padx=15, pady=10)

        self.controller.run_async(query_messages, callback=callback)

    def show_detail(self, msg_id):
        # 弹窗展示正文详情
        detail_win = MessageDetailWindow(self.controller, msg_id)
        self.controller.wait_window(detail_win)


class MessageDetailWindow(ctk.CTkToplevel):
    def __init__(self, parent, msg_id):
        super().__init__(parent)
        self.parent = parent
        self.msg_id = msg_id
        self.title("通知消息正文")
        self.geometry("720x540")
        
        self.transient(parent)
        self.wait_visibility()
        self.grab_set()

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # 头部面板
        self.meta_frame = ctk.CTkFrame(self, corner_radius=0)
        self.meta_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 5))
        self.meta_frame.columnconfigure(0, weight=1)

        self.title_lbl = ctk.CTkLabel(self.meta_frame, text="正在装载...", font=ctk.CTkFont(size=16, weight="bold"), justify="left")
        self.title_lbl.grid(row=0, column=0, padx=15, pady=(10, 5), sticky="w")

        self.info_lbl = ctk.CTkLabel(self.meta_frame, text="", text_color="grey60", font=ctk.CTkFont(size=12))
        self.info_lbl.grid(row=1, column=0, padx=15, pady=(0, 10), sticky="w")

        # 正文文本框
        self.textbox = ctk.CTkTextbox(self, font=ctk.CTkFont(size=14))
        self.textbox.grid(row=2, column=0, sticky="nsew", padx=15, pady=5)
        
        # 附件栏
        self.attachment_frame = ctk.CTkFrame(self, height=70)
        self.attachment_frame.grid(row=3, column=0, sticky="ew", padx=15, pady=(5, 15))
        self.attachment_frame.columnconfigure(0, weight=1)
        
        self.att_lbl = ctk.CTkLabel(self.attachment_frame, text="📎 附件加载中...", text_color="grey60", font=ctk.CTkFont(size=12))
        self.att_lbl.grid(row=0, column=0, padx=15, pady=10, sticky="w")

        self.download_btn = ctk.CTkButton(self.attachment_frame, text="📥 下载全部附件", state="disabled", width=120, command=self.download_all)
        self.download_btn.grid(row=0, column=1, padx=15, pady=10)

        self.attachment_links = []
        self.load_detail()

    def load_detail(self):
        def worker():
            status, body, _ = ch_cli.make_request(f"/sitemessage/show-Message/{self.msg_id}/", method="GET")
            if status != 200:
                return False, f"获取详情失败 (HTTP Code: {status})"
            
            html_content = body.decode("utf-8", errors="ignore")
            
            # 提取标题
            title = "无标题"
            title_m = re.search(r'<div class="ArticleTitle">(.*?)</div>', html_content, re.DOTALL)
            if title_m:
                title = ch_cli.clean_html(title_m.group(1))
                
            # 发送人
            sender = "未知"
            sender_m = re.search(r'发送者：\s*([^\s<]+)', html_content)
            if sender_m:
                sender = sender_m.group(1).strip()
                
            # 时间
            send_time = "未知"
            time_m = re.search(r'发送时间：\s*([^\s<]+(?:\s+[^\s<]+)?)', html_content)
            if time_m:
                send_time = time_m.group(1).strip()
                
            # 内容
            content = ""
            content_m = re.search(r'<div class="ArticleContent[^>]*>(.*?)</div>\s*</div>', html_content, re.DOTALL)
            if not content_m:
                content_m = re.search(r'<div class="ArticleContent[^>]*>(.*?)</div>', html_content, re.DOTALL)
            if content_m:
                content = ch_cli.clean_html(content_m.group(1))
                
            # 附件
            links = ch_cli.extract_attachment_links(html_content)
            return True, (title, sender, send_time, content, links)

        def callback(res):
            if not self.winfo_exists():
                return
            success, data = res
            if not success:
                self.title_lbl.configure(text="加载失败")
                self.textbox.insert("0.0", data)
                self.att_lbl.configure(text="📎 无法加载附件列表")
                return
                
            title, sender, send_time, content, links = data
            self.title_lbl.configure(text=title)
            self.info_lbl.configure(text=f"发送者: {sender}   |   发送时间: {send_time}")
            self.textbox.insert("0.0", content)
            
            self.attachment_links = links
            if links:
                self.att_lbl.configure(text=f"📎 发现 {len(links)} 个关联的文档或附件", text_color="#1088ff" if ctk.get_appearance_mode() == "Light" else "#00adb5")
                self.download_btn.configure(state="normal")
            else:
                self.att_lbl.configure(text="📎 本条消息未附带任何附件")

        self.parent.run_async(worker, callback=callback)

    def download_all(self):
        if not self.attachment_links:
            return
        # 选择下载保存目录
        out_dir = filedialog.askdirectory(title="选择下载附件的保存位置")
        if not out_dir:
            return
            
        self.download_btn.configure(state="disabled", text="正在下载...")
        
        def task():
            ch_cli.download_attachments(self.attachment_links, out_dir)
            return True

        def callback(res):
            if not self.winfo_exists():
                return
            self.download_btn.configure(state="normal", text="📥 下载全部附件")
            messagebox.showinfo("成功", f"所有附件已下载并成功保存至:\n{out_dir}")

        self.parent.run_async(task, callback=callback)


class NewsFrame(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color="transparent")
        self.controller = controller
        
        self.page = 1
        
        self.header = ctk.CTkFrame(self, fg_color="transparent")
        self.header.pack(fill="x", pady=(5, 10))

        self.title = ctk.CTkLabel(self.header, text="📄 校内文章公告栏目", font=ctk.CTkFont(size=18, weight="bold"))
        self.title.pack(side="left", padx=5)

        # 栏目下拉选择菜单
        self.col_options = {
            "通知公告 (默认)": "16",
            "校内公示": "19",
            "新闻聚焦": "13",
            "值周小结": "51"
        }
        self.col_select = ctk.CTkOptionMenu(
            self.header, 
            values=list(self.col_options.keys()), 
            width=150, 
            command=self.on_column_change
        )
        self.col_select.pack(side="left", padx=15)

        self.refresh_btn = ctk.CTkButton(self.header, text="🔄 刷新", width=80, command=self.load_list)
        self.refresh_btn.pack(side="right", padx=5)

        self.prev_btn = ctk.CTkButton(self.header, text="◀ 上一页", width=80, command=lambda: self.change_page(-1))
        self.prev_btn.pack(side="right", padx=5)
        
        self.page_label = ctk.CTkLabel(self.header, text="第 1 页", font=ctk.CTkFont(size=13))
        self.page_label.pack(side="right", padx=10)

        self.next_btn = ctk.CTkButton(self.header, text="下一页 ▶", width=80, command=lambda: self.change_page(1))
        self.next_btn.pack(side="right", padx=5)

        self.scroll = ctk.CTkScrollableFrame(self)
        self.scroll.pack(fill="both", expand=True)

        self.loaded = False

    def on_show(self):
        if not self.loaded:
            self.load_list()

    def on_column_change(self, choice):
        self.page = 1
        self.page_label.configure(text="第 1 页")
        self.load_list()

    def change_page(self, delta):
        if self.page + delta < 1:
            return
        self.page += delta
        self.page_label.configure(text=f"第 {self.page} 页")
        self.load_list()

    def load_list(self):
        self.refresh_btn.configure(state="disabled", text="加载中...")
        self.prev_btn.configure(state="disabled")
        self.next_btn.configure(state="disabled")
        for child in self.scroll.winfo_children():
            child.destroy()
            
        loading = ctk.CTkLabel(self.scroll, text="正在读取栏目文章列表...", font=ctk.CTkFont(size=14))
        loading.pack(pady=40)

        col_name = self.col_select.get()
        col_id = self.col_options.get(col_name, "16")

        def query_news():
            status, body, _ = ch_cli.make_request(f"/article/column-detail/{col_id}/?page={self.page}", method="GET", follow_redirects=True)
            if status != 200:
                return False, f"HTTP Error: {status}"
            
            html_content = body.decode("utf-8", errors="ignore")
            items = re.findall(r'href=["\']/article/article-detail/(\d+)/["\'][^>]*>\s*(.*?)\s*</a>.*?class="[^"]*text-secondary"[^>]*>\s*(.*?)\s*</div>', html_content, re.DOTALL)
            
            rows = []
            for art_id, title, date in items:
                rows.append((art_id, ch_cli.clean_html(title), ch_cli.clean_html(date)))
            return True, rows

        def callback(res):
            self.refresh_btn.configure(state="normal", text="🔄 刷新")
            self.prev_btn.configure(state="normal" if self.page > 1 else "disabled")
            self.next_btn.configure(state="normal")
            for child in self.scroll.winfo_children():
                child.destroy()
                
            success, data = res
            if not success:
                err = ctk.CTkLabel(self.scroll, text=f"加载失败: {data}\n请确认 Cookie 是否有效。", text_color="red")
                err.pack(pady=40)
                return
                
            if not data:
                empty = ctk.CTkLabel(self.scroll, text="此栏目本页无文章记录。")
                empty.pack(pady=40)
                return
                
            self.loaded = True
            colors = get_theme_colors()
            for art_id, title, date in data:
                card = ctk.CTkFrame(self.scroll, corner_radius=6)
                card.pack(fill="x", padx=5, pady=5)
                
                card.columnconfigure(0, weight=1)
                
                t_lbl = tk.Label(card, text=title, font=("Helvetica", 11, "bold"), fg=colors["text_primary"], bg=colors["card_bg"], anchor="w", justify="left")
                t_lbl.grid(row=0, column=0, padx=15, pady=(10, 2), sticky="w")
                
                info_lbl = tk.Label(card, text=f"发布日期: {date}   |   文章 ID: {art_id}", fg=colors["text_secondary"], bg=colors["card_bg"], font=("Helvetica", 9), anchor="w", justify="left")
                info_lbl.grid(row=1, column=0, padx=15, pady=(0, 10), sticky="w")
                
                btn = ctk.CTkButton(card, text="查看详情", width=90, command=lambda a=art_id: self.show_detail(a))
                btn.grid(row=0, column=1, rowspan=2, padx=15, pady=10)

        self.controller.run_async(query_news, callback=callback)

    def show_detail(self, art_id):
        detail_win = NewsDetailWindow(self.controller, art_id)
        self.controller.wait_window(detail_win)


class NewsDetailWindow(ctk.CTkToplevel):
    def __init__(self, parent, art_id):
        super().__init__(parent)
        self.parent = parent
        self.art_id = art_id
        self.title("文章详情内容")
        self.geometry("740x560")
        
        self.transient(parent)
        self.wait_visibility()
        self.grab_set()

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.meta_frame = ctk.CTkFrame(self, corner_radius=0)
        self.meta_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 5))
        self.meta_frame.columnconfigure(0, weight=1)

        self.title_lbl = ctk.CTkLabel(self.meta_frame, text="读取文章中...", font=ctk.CTkFont(size=16, weight="bold"), justify="left")
        self.title_lbl.grid(row=0, column=0, padx=15, pady=(10, 5), sticky="w")

        self.info_lbl = ctk.CTkLabel(self.meta_frame, text="", text_color="grey60", font=ctk.CTkFont(size=12))
        self.info_lbl.grid(row=1, column=0, padx=15, pady=(0, 10), sticky="w")

        self.textbox = ctk.CTkTextbox(self, font=ctk.CTkFont(size=14))
        self.textbox.grid(row=2, column=0, sticky="nsew", padx=15, pady=5)
        
        self.attachment_frame = ctk.CTkFrame(self, height=70)
        self.attachment_frame.grid(row=3, column=0, sticky="ew", padx=15, pady=(5, 15))
        self.attachment_frame.columnconfigure(0, weight=1)
        
        self.att_lbl = ctk.CTkLabel(self.attachment_frame, text="📎 正在提取内嵌附件...", text_color="grey60", font=ctk.CTkFont(size=12))
        self.att_lbl.grid(row=0, column=0, padx=15, pady=10, sticky="w")

        self.download_btn = ctk.CTkButton(self.attachment_frame, text="📥 下载关联文件", state="disabled", width=120, command=self.download_all)
        self.download_btn.grid(row=0, column=1, padx=15, pady=10)

        self.attachment_links = []
        self.load_detail()

    def load_detail(self):
        def worker():
            status, body, _ = ch_cli.make_request(f"/article/article-detail/{self.art_id}/", method="GET", follow_redirects=True)
            if status != 200:
                return False, f"获取详情失败 (HTTP Code: {status})"
            
            html_content = body.decode("utf-8", errors="ignore")
            
            title = "无标题"
            title_m = re.search(r'<div class="ArticleTitle[^>]*>(.*?)</div>', html_content, re.DOTALL)
            if title_m:
                title = ch_cli.clean_html(title_m.group(1))
                
            source = "未知"
            source_m = re.search(r'来源：\s*([^<]+)', html_content)
            if source_m:
                source = ch_cli.clean_html(source_m.group(1))
                
            pub_time = "未知"
            time_m = re.search(r'发布时间：\s*([^\s<]+(?:\s+[^\s<]+)?)', html_content)
            if time_m:
                pub_time = time_m.group(1).strip()
                
            content = ""
            content_m = re.search(r'<div class="ArticleContent(?:\s+[^>]*|)\s*>(.*?)</div>', html_content, re.DOTALL)
            if content_m:
                content = ch_cli.clean_html(content_m.group(1))
                
            links = ch_cli.extract_attachment_links(html_content)
            return True, (title, source, pub_time, content, links)

        def callback(res):
            if not self.winfo_exists():
                return
            success, data = res
            if not success:
                self.title_lbl.configure(text="读取失败")
                self.textbox.insert("0.0", data)
                self.att_lbl.configure(text="📎 无法加载附件")
                return
                
            title, source, pub_time, content, links = data
            self.title_lbl.configure(text=title)
            self.info_lbl.configure(text=f"来源部门/人: {source}   |   发布时间: {pub_time}")
            self.textbox.insert("0.0", content)
            
            self.attachment_links = links
            if links:
                self.att_lbl.configure(text=f"📎 发现该公告内嵌了 {len(links)} 个可供下载的文件附件", text_color="#1088ff" if ctk.get_appearance_mode() == "Light" else "#00adb5")
                self.download_btn.configure(state="normal")
            else:
                self.att_lbl.configure(text="📎 本篇文章未检测到独立文件附件")

        self.parent.run_async(worker, callback=callback)

    def download_all(self):
        if not self.attachment_links:
            return
        out_dir = filedialog.askdirectory(title="选择下载文件保存目录")
        if not out_dir:
            return
            
        self.download_btn.configure(state="disabled", text="正在下载...")
        
        def task():
            ch_cli.download_attachments(self.attachment_links, out_dir)
            return True

        def callback(res):
            if not self.winfo_exists():
                return
            self.download_btn.configure(state="normal", text="📥 下载关联文件")
            messagebox.showinfo("成功", f"文件附件下载成功，已保存至:\n{out_dir}")

        self.parent.run_async(task, callback=callback)


class HygieneFrame(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color="transparent")
        self.controller = controller
        
        self.page = 1

        self.header = ctk.CTkFrame(self, fg_color="transparent")
        self.header.pack(fill="x", pady=(5, 10))

        self.title = ctk.CTkLabel(self.header, text="🧹 全校纪律卫生考评记录", font=ctk.CTkFont(size=18, weight="bold"))
        self.title.pack(side="left", padx=5)

        self.refresh_btn = ctk.CTkButton(self.header, text="🔄 刷新", width=80, command=self.load_list)
        self.refresh_btn.pack(side="right", padx=5)

        self.prev_btn = ctk.CTkButton(self.header, text="◀ 上一页", width=80, command=lambda: self.change_page(-1))
        self.prev_btn.pack(side="right", padx=5)
        
        self.page_label = ctk.CTkLabel(self.header, text="第 1 页", font=ctk.CTkFont(size=13))
        self.page_label.pack(side="right", padx=10)

        self.next_btn = ctk.CTkButton(self.header, text="下一页 ▶", width=80, command=lambda: self.change_page(1))
        self.next_btn.pack(side="right", padx=5)

        self.scroll = ctk.CTkScrollableFrame(self)
        self.scroll.pack(fill="both", expand=True)

        self.loaded = False

    def on_show(self):
        if not self.loaded:
            self.load_list()

    def change_page(self, delta):
        if self.page + delta < 1:
            return
        self.page += delta
        self.page_label.configure(text=f"第 {self.page} 页")
        self.load_list()

    def load_list(self):
        self.refresh_btn.configure(state="disabled", text="加载中...")
        self.prev_btn.configure(state="disabled")
        self.next_btn.configure(state="disabled")
        for child in self.scroll.winfo_children():
            child.destroy()
            
        loading = ctk.CTkLabel(self.scroll, text="正在读取纪律卫生考评记录...", font=ctk.CTkFont(size=14))
        loading.pack(pady=40)

        def query_hygiene():
            status, body, _ = ch_cli.make_request(f"/classappraise/hygienePictures_receive_list/?page={self.page}", method="GET")
            if status != 200:
                return False, f"HTTP Error: {status}"
            
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
                        location = ch_cli.clean_html(tds[1])
                        description = ch_cli.clean_html(tds[2])
                        date = ch_cli.clean_html(tds[3])
                        rows.append((record_id, location, description, date))
            return True, rows

        def callback(res):
            self.refresh_btn.configure(state="normal", text="🔄 刷新")
            self.prev_btn.configure(state="normal" if self.page > 1 else "disabled")
            self.next_btn.configure(state="normal")
            for child in self.scroll.winfo_children():
                child.destroy()
                
            success, data = res
            if not success:
                err = ctk.CTkLabel(self.scroll, text=f"加载失败: {data}\n请确认 Cookie 连接是否有效。", text_color="red")
                err.pack(pady=40)
                return
                
            if not data:
                empty = ctk.CTkLabel(self.scroll, text="本页暂无扣分考评违纪记录。")
                empty.pack(pady=40)
                return
                
            self.loaded = True
            colors = get_theme_colors()
            for record_id, location, description, date in data:
                card = ctk.CTkFrame(self.scroll, corner_radius=6)
                card.pack(fill="x", padx=5, pady=5)
                
                card.columnconfigure(0, weight=1)
                
                loc_lbl = tk.Label(card, text=f"📍 检查地点: {location}   |   检查日期: {date}", font=("Helvetica", 11, "bold"), fg=colors["text_primary"], bg=colors["card_bg"], anchor="w", justify="left")
                loc_lbl.grid(row=0, column=0, padx=15, pady=(10, 2), sticky="w")
                
                desc_lbl = tk.Label(card, text=f"违纪描述: {description}", fg=colors["text_secondary"], bg=colors["card_bg"], font=("Helvetica", 9), anchor="w", justify="left")
                desc_lbl.grid(row=1, column=0, padx=15, pady=(0, 10), sticky="w")
                
                btn = ctk.CTkButton(card, text="多媒体详情", width=95, command=lambda r=record_id: self.show_detail(r))
                btn.grid(row=0, column=1, rowspan=2, padx=15, pady=10)

        self.controller.run_async(query_hygiene, callback=callback)

    def show_detail(self, record_id):
        detail_win = HygieneDetailWindow(self.controller, record_id)
        self.controller.wait_window(detail_win)


class HygieneDetailWindow(ctk.CTkToplevel):
    def __init__(self, parent, record_id):
        super().__init__(parent)
        self.parent = parent
        self.record_id = record_id
        self.title("纪律卫生违纪考评明细")
        self.geometry("700x520")
        
        self.transient(parent)
        self.wait_visibility()
        self.grab_set()

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.meta_frame = ctk.CTkFrame(self, corner_radius=0)
        self.meta_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 5))
        self.meta_frame.columnconfigure(0, weight=1)

        self.title_lbl = ctk.CTkLabel(self.meta_frame, text="读取违纪考评信息...", font=ctk.CTkFont(size=15, weight="bold"), justify="left")
        self.title_lbl.grid(row=0, column=0, padx=15, pady=(10, 5), sticky="w")

        self.info_lbl = ctk.CTkLabel(self.meta_frame, text="", text_color="grey60", font=ctk.CTkFont(size=12))
        self.info_lbl.grid(row=1, column=0, padx=15, pady=(0, 10), sticky="w")

        # 描述与多媒体列表显示区
        self.textbox = ctk.CTkTextbox(self, font=ctk.CTkFont(size=14))
        self.textbox.grid(row=2, column=0, sticky="nsew", padx=15, pady=5)
        
        # 违纪配图/视频多媒体下载条
        self.attachment_frame = ctk.CTkFrame(self, height=70)
        self.attachment_frame.grid(row=3, column=0, sticky="ew", padx=15, pady=(5, 15))
        self.attachment_frame.columnconfigure(0, weight=1)
        
        self.att_lbl = ctk.CTkLabel(self.attachment_frame, text="📷 正在获取现场图片/视频...", text_color="grey60", font=ctk.CTkFont(size=12))
        self.att_lbl.grid(row=0, column=0, padx=15, pady=10, sticky="w")

        self.download_btn = ctk.CTkButton(self.attachment_frame, text="📥 下载现场照片", state="disabled", width=120, command=self.download_all)
        self.download_btn.grid(row=0, column=1, padx=15, pady=10)

        self.media_urls = []
        self.load_detail()

    def load_detail(self):
        def worker():
            status, body, _ = ch_cli.make_request(f"/classappraise/show-Message/{self.record_id}/", method="GET")
            if status != 200:
                return False, f"获取详情失败 (HTTP Code: {status})"
            
            html_content = body.decode("utf-8", errors="ignore")
            
            desc = "未知违纪说明"
            content_m = re.search(r'<div class="ArticleContent[^>]*>(.*?)</div>', html_content, re.DOTALL)
            if content_m:
                desc = ch_cli.clean_html(content_m.group(1))
                
            recipients_all = "无"
            rec1_m = re.search(r'id="multiCollapseExample1">\s*<div class="card card-body">\s*(.*?)\s*</div>', html_content, re.DOTALL)
            if rec1_m:
                recipients_all = ch_cli.clean_html(rec1_m.group(1))
                
            # 提取多媒体链接
            media_urls = []
            imgs = re.findall(r'<img[^>]+src=["\'](.*?)["\']', html_content)
            for img in imgs:
                if "Logo" not in img and "newFunc" not in img and "sydw" not in img:
                    if not img.startswith("http") and img.startswith("/"):
                        media_urls.append(f"{ch_cli.BASE_URL}{img}")
                    else:
                        media_urls.append(img)
                        
            vids = re.findall(r'<video[^>]+src=["\'](.*?)["\']', html_content)
            for vid in vids:
                if not vid.startswith("http") and vid.startswith("/"):
                    media_urls.append(f"{ch_cli.BASE_URL}{vid}")
                else:
                    media_urls.append(vid)
                    
            return True, (desc, recipients_all, media_urls)

        def callback(res):
            if not self.winfo_exists():
                return
            success, data = res
            if not success:
                self.title_lbl.configure(text="加载详情失败")
                self.textbox.insert("0.0", data)
                self.att_lbl.configure(text="📷 无法加载多媒体现场照片")
                return
                
            desc, recipients_all, media_urls = data
            self.title_lbl.configure(text="🚨 违纪考评项明细记录")
            self.info_lbl.configure(text=f"关联收件人(班主任等): {recipients_all}")
            
            full_txt = f"违纪说明:\n{desc}\n\n现场连线文件链接:\n"
            if media_urls:
                for u in media_urls:
                    full_txt += f"- {u}\n"
            else:
                full_txt += "无\n"
            self.textbox.insert("0.0", full_txt)
            
            self.media_urls = media_urls
            if media_urls:
                self.att_lbl.configure(text=f"📷 发现 {len(media_urls)} 张违纪现场图片/视频文件", text_color="#1088ff" if ctk.get_appearance_mode() == "Light" else "#00adb5")
                self.download_btn.configure(state="normal")
            else:
                self.att_lbl.configure(text="📷 本记录未关联现场多媒体附件")

        self.parent.run_async(worker, callback=callback)

    def download_all(self):
        if not self.media_urls:
            return
        out_dir = filedialog.askdirectory(title="选择图片保存目录")
        if not out_dir:
            return
            
        self.download_btn.configure(state="disabled", text="正在保存...")
        
        def task():
            ch_cli.download_attachments(self.media_urls, out_dir)
            return True

        def callback(res):
            if not self.winfo_exists():
                return
            self.download_btn.configure(state="normal", text="📥 下载现场照片")
            messagebox.showinfo("成功", f"照片已下载并成功保存至:\n{out_dir}")

        self.parent.run_async(task, callback=callback)


class BedroomFrame(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color="transparent")
        self.controller = controller

        # 头部 Title
        self.header = ctk.CTkFrame(self, fg_color="transparent")
        self.header.pack(fill="x", pady=(5, 10))

        self.title = ctk.CTkLabel(self.header, text="🏠 寝室分配与楼宇卫生扣分考评", font=ctk.CTkFont(size=18, weight="bold"))
        self.title.pack(side="left", padx=5)

        # Tab 选项卡分流
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True)

        self.tab_class = self.tabview.add("按班级查寝室分配")
        self.tab_hygiene = self.tabview.add("按楼宇查扣分记录")

        self.init_class_tab()
        self.init_hygiene_tab()

    def init_class_tab(self):
        # 班级分配面板布局
        self.tab_class.columnconfigure(2, weight=1)
        
        lbl_grade = ctk.CTkLabel(self.tab_class, text="年级选择:")
        lbl_grade.grid(row=0, column=0, padx=15, pady=15, sticky="w")
        
        self.grade_combo = ctk.CTkOptionMenu(self.tab_class, values=["高一", "高二", "高三"], width=120)
        self.grade_combo.grid(row=0, column=1, padx=5, pady=15, sticky="w")

        lbl_cls = ctk.CTkLabel(self.tab_class, text="班级名字/数字:")
        lbl_cls.grid(row=0, column=2, padx=15, pady=15, sticky="w")

        self.cls_entry = ctk.CTkEntry(self.tab_class, placeholder_text="如: 10班 或 10", width=120)
        self.cls_entry.grid(row=0, column=3, padx=5, pady=15, sticky="w")

        self.query_cls_btn = ctk.CTkButton(self.tab_class, text="🔍 查询寝室分配", width=130, command=self.query_class_bedroom)
        self.query_cls_btn.grid(row=0, column=4, padx=15, pady=15, sticky="e")

        self.cls_result = ctk.CTkTextbox(self.tab_class, font=ctk.CTkFont(size=14))
        self.cls_result.grid(row=1, column=0, columnspan=5, sticky="nsew", padx=15, pady=(5, 15))
        self.tab_class.rowconfigure(1, weight=1)

    def init_hygiene_tab(self):
        # 楼宇扣分查询面板布局
        self.tab_hygiene.columnconfigure(3, weight=1)

        lbl_dorm = ctk.CTkLabel(self.tab_hygiene, text="宿舍楼宇:")
        lbl_dorm.grid(row=0, column=0, padx=10, pady=10, sticky="w")
        
        self.dorm_mapping = {
            "3号楼 (1)": "1", "4号楼 (2)": "2", "5号楼 (3)": "3", "6号楼 (4)": "4",
            "7号楼 (5)": "5", "8号楼 (6)": "6", "9号楼 (7)": "7", "10号楼 (8)": "8", "1号楼 (9)": "9"
        }
        self.dorm_combo = ctk.CTkOptionMenu(self.tab_hygiene, values=list(self.dorm_mapping.keys()), width=120)
        self.dorm_combo.grid(row=0, column=1, padx=5, pady=10, sticky="w")

        lbl_days = ctk.CTkLabel(self.tab_hygiene, text="查询天数:")
        lbl_days.grid(row=0, column=2, padx=10, pady=10, sticky="w")

        self.days_combo = ctk.CTkOptionMenu(self.tab_hygiene, values=["最近30天", "最近60天", "最近7天"], width=100)
        self.days_combo.grid(row=0, column=3, padx=5, pady=10, sticky="w")

        self.show_all_var = ctk.BooleanVar(value=False)
        self.show_all_cb = ctk.CTkCheckBox(self.tab_hygiene, text="显示无扣分寝室", variable=self.show_all_var)
        self.show_all_cb.grid(row=0, column=4, padx=10, pady=10, sticky="w")

        self.query_hyg_btn = ctk.CTkButton(self.tab_hygiene, text="🔍 查询卫生扣分", width=120, command=self.query_dorm_hygiene)
        self.query_hyg_btn.grid(row=0, column=5, padx=10, pady=10, sticky="e")

        self.hyg_scroll = ctk.CTkScrollableFrame(self.tab_hygiene)
        self.hyg_scroll.grid(row=1, column=0, columnspan=6, sticky="nsew", padx=10, pady=10)
        self.tab_hygiene.rowconfigure(1, weight=1)

    def query_class_bedroom(self):
        grade_str = self.grade_combo.get()
        grade_map = {"高一": 1, "高二": 2, "高三": 3}
        grade_id = grade_map[grade_str]
        
        class_query = self.cls_entry.get().strip()
        if not class_query:
            messagebox.showerror("错误", "请输入班级！")
            return
            
        self.query_cls_btn.configure(state="disabled", text="查询中...")
        self.cls_result.delete("0.0", "end")

        def query_task():
            res = ch_cli.find_class_id(grade_id, class_query)
            if not res:
                return False, f"未能在{grade_str}中找到匹配班级 \"{class_query}\""
            class_id, class_name = res
            
            post_data = {
                "chGradeIDForName": grade_id,
                "chClassIDForName": class_id
            }
            status, body, _ = ch_cli.make_request("/classappraise/QueryBedroomsByClassID_JustForView/", method="POST", data=post_data)
            if status != 200:
                return False, f"网络请求失败 (HTTP: {status})"
                
            html = body.decode("utf-8", errors="ignore")
            alert_m = re.search(r'class="alert alert-primary"[^>]*>\s*(.*?)\s*</div>', html, re.DOTALL)
            if alert_m:
                return True, (class_name, ch_cli.clean_html(alert_m.group(1)))
            return False, "未查到该班级的寝室分配数据。"

        def callback(res):
            self.query_cls_btn.configure(state="normal", text="🔍 查询寝室分配")
            success, val = res
            if not success:
                self.cls_result.insert("0.0", f"查询失败: {val}")
            else:
                c_name, result_text = val
                self.cls_result.insert("0.0", f"班级：{c_name}\n\n{result_text}")

        self.controller.run_async(query_task, callback=callback)

    def query_dorm_hygiene(self):
        dorm_choice = self.dorm_combo.get()
        dorm_id = self.dorm_mapping[dorm_choice]
        
        days_choice = self.days_combo.get()
        days_map = {"最近7天": 7, "最近30天": 30, "最近60天": 60}
        days = days_map[days_choice]
        
        # 计算起止日期
        end_date = time.strftime("%Y-%m-%d")
        start_date = time.strftime("%Y-%m-%d", time.localtime(time.time() - days * 86400))
        
        show_all = self.show_all_var.get()
        
        self.query_hyg_btn.configure(state="disabled", text="查询中...")
        for child in self.hyg_scroll.winfo_children():
            child.destroy()
            
        loading = ctk.CTkLabel(self.hyg_scroll, text="正在向校园网检索宿舍评分数据，请稍候...", font=ctk.CTkFont(size=14))
        loading.pack(pady=40)

        def query_task():
            post_data = {
                "chDormitoryForName": dorm_id,
                "theBeginDateForName": start_date,
                "theEndDateForName": end_date
            }
            status, body, _ = ch_cli.make_request("/classappraise/BedRoom_DisciplineHygiene_JustForView/", method="POST", data=post_data)
            if status != 200:
                return False, f"HTTP Error: {status}"
                
            html = body.decode("utf-8", errors="ignore")
            tr_pattern = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL)
            trs = tr_pattern.findall(html)
            
            rows = []
            for tr in trs:
                tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL)
                if len(tds) >= 4:
                    room = ch_cli.clean_html(tds[0])
                    cls_name = ch_cli.clean_html(tds[1])
                    hyg = ch_cli.clean_html(tds[2]) or "0"
                    disc = ch_cli.clean_html(tds[3]) or "0"
                    total = ch_cli.clean_html(tds[4]) if len(tds) > 4 else "0"
                    
                    if not show_all:
                        # 过滤无扣分项
                        if not total or total.strip() == "" or total.strip() == "0":
                            continue
                    rows.append((room, cls_name, hyg, disc, total))
            return True, rows

        def callback(res):
            self.query_hyg_btn.configure(state="normal", text="🔍 查询卫生扣分")
            for child in self.hyg_scroll.winfo_children():
                child.destroy()
                
            success, data = res
            if not success:
                err = ctk.CTkLabel(self.hyg_scroll, text=f"加载失败: {data}\n请确认 Cookie 连接是否有效。", text_color="red")
                err.pack(pady=40)
                return
                
            if not data:
                empty = ctk.CTkLabel(self.hyg_scroll, text="此日期范围内该宿舍楼宇没有找到任何扣分记录。")
                empty.pack(pady=40)
                return
                
            colors = get_theme_colors()
            for room, cls_name, hyg, disc, total in data:
                card = ctk.CTkFrame(self.hyg_scroll, corner_radius=6)
                card.pack(fill="x", padx=5, pady=4)
                
                card.columnconfigure(0, weight=1)
                
                title_lbl = tk.Label(card, text=f"🏠 寝室: {room}   ({cls_name})", font=("Helvetica", 11, "bold"), fg=colors["text_primary"], bg=colors["card_bg"], anchor="w", justify="left")
                title_lbl.grid(row=0, column=0, padx=15, pady=(10, 2), sticky="w")
                
                score_color = "#ff5722" if total != "0" else colors["text_secondary"]
                score_lbl = tk.Label(
                    card, 
                    text=f"卫生扣分: {hyg}   |   纪律扣分: {disc}   |   合计扣分: {total}", 
                    fg=score_color, 
                    bg=colors["card_bg"],
                    font=("Helvetica", 9),
                    anchor="w",
                    justify="left"
                )
                score_lbl.grid(row=1, column=0, padx=15, pady=(0, 10), sticky="w")

        self.controller.run_async(query_task, callback=callback)


class DutyFrame(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color="transparent")
        self.controller = controller

        self.header = ctk.CTkFrame(self, fg_color="transparent")
        self.header.pack(fill="x", pady=(5, 10))

        self.title = ctk.CTkLabel(self.header, text="📅 校园教师值周排班安排", font=ctk.CTkFont(size=18, weight="bold"))
        self.title.pack(side="left", padx=5)

        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True)

        self.tab_current = self.tabview.add("当前星期安排")
        self.tab_all = self.tabview.add("学期排班总表")

        self.init_current_tab()
        self.init_all_tab()
        
        self.loaded = False

    def on_show(self):
        if not self.loaded:
            self.load_current_duty()

    def init_current_tab(self):
        self.tab_current.columnconfigure(0, weight=1)
        
        self.current_scroll = ctk.CTkScrollableFrame(self.tab_current)
        self.current_scroll.grid(row=0, column=0, sticky="nsew", padx=15, pady=15)
        self.tab_current.rowconfigure(0, weight=1)

        self.refresh_cur_btn = ctk.CTkButton(self.tab_current, text="🔄 刷新值周安排", command=self.load_current_duty)
        self.refresh_cur_btn.grid(row=1, column=0, pady=(0, 15))

    def init_all_tab(self):
        # 值周总表布局，支持搜索
        self.tab_all.columnconfigure(0, weight=1)
        
        search_frame = ctk.CTkFrame(self.tab_all, fg_color="transparent")
        search_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=10)
        search_frame.columnconfigure(0, weight=1)
        
        self.search_entry = ctk.CTkEntry(search_frame, placeholder_text="输入教师名字或值周班级（如: 创新01班）模糊搜索")
        self.search_entry.grid(row=0, column=0, padx=(0, 10), sticky="ew")

        self.search_btn = ctk.CTkButton(search_frame, text="🔍 搜索", width=90, command=self.search_duty)
        self.search_btn.grid(row=0, column=1)

        self.all_scroll = ctk.CTkScrollableFrame(self.tab_all)
        self.all_scroll.grid(row=1, column=0, sticky="nsew", padx=15, pady=(5, 15))
        self.tab_all.rowconfigure(1, weight=1)

        self.duties_cache = []

    def load_current_duty(self):
        for child in self.current_scroll.winfo_children():
            child.destroy()
        loading = ctk.CTkLabel(self.current_scroll, text="正在读取当前星期值周安排...")
        loading.pack(pady=40)

        def query_task():
            status, body, _ = ch_cli.make_request("/classappraise/TeacherDutyWeek_JustForView/", method="GET")
            if status != 200:
                return False, f"HTTP Error: {status}"
                
            html = body.decode("utf-8", errors="ignore")
            blocks = re.findall(r'<ul class="list-group"\s*>(.*?)</ul>', html, re.DOTALL)
            
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
                        
                info = {
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
                duties.append(info)
                if is_current:
                    current_week = info
            return True, (current_week, duties)

        def callback(res):
            for child in self.current_scroll.winfo_children():
                child.destroy()
            success, data = res
            if not success:
                err = ctk.CTkLabel(self.current_scroll, text=f"加载失败: {data}", text_color="red")
                err.pack(pady=40)
                return
                
            current_week, duties = data
            self.duties_cache = duties
            self.loaded = True
            
            # 渲染当前周次
            if not current_week:
                empty = ctk.CTkLabel(self.current_scroll, text="未能在值周排班中检测到标记为当前周次的条目。")
                empty.pack(pady=40)
            else:
                card = ctk.CTkFrame(self.current_scroll, border_width=1, border_color="#00adb5")
                card.pack(fill="x", padx=10, pady=10)
                
                title = ctk.CTkLabel(card, text=f"★ 当前值周次: {current_week['week']} ★", font=ctk.CTkFont(size=16, weight="bold"), text_color="#00adb5")
                title.pack(pady=(15, 5))
                
                dates = ctk.CTkLabel(card, text=f"时间范围: {current_week['date']}", text_color="grey60", font=ctk.CTkFont(size=12))
                dates.pack(pady=(0, 15))
                
                lbl_admin = ctk.CTkLabel(card, text=f"行政值周教师: {current_week['admin']}", font=ctk.CTkFont(size=14, weight="bold"))
                lbl_admin.pack(pady=5)
                
                lbl_class = ctk.CTkLabel(card, text=f"值周班级: {current_week['class']}", font=ctk.CTkFont(size=14, weight="bold"))
                lbl_class.pack(pady=5)

                lbl_group1 = ctk.CTkLabel(card, text=f"第一小组: {current_week['group1']}", justify="left")
                lbl_group1.pack(pady=5)

                lbl_group2 = ctk.CTkLabel(card, text=f"第二小组: {current_week['group2']}", justify="left")
                lbl_group2.pack(pady=5)

                if current_week['group3'].replace(",", "").strip():
                    lbl_group3 = ctk.CTkLabel(card, text=f"第三小组: {current_week['group3']}", justify="left")
                    lbl_group3.pack(pady=5)

                if current_week['talk']:
                    lbl_talk = ctk.CTkLabel(card, text=f"旗下讲话主题: {current_week['talk']}", text_color="gold", font=ctk.CTkFont(size=13))
                    lbl_talk.pack(pady=(10, 15))
                    
            # 同时刷新总表页面内容
            self.refresh_all_tab(duties)

        self.controller.run_async(query_task, callback=callback)

    def refresh_all_tab(self, duties):
        for child in self.all_scroll.winfo_children():
            child.destroy()
            
        colors = get_theme_colors()
        for d in duties:
            card = ctk.CTkFrame(self.all_scroll, corner_radius=6, border_width=1 if d["is_current"] else 0, border_color="#00adb5")
            card.pack(fill="x", padx=5, pady=4)
            
            card.columnconfigure(0, weight=1)
            
            title_text = f"📅 {d['week']}"
            if d["is_current"]:
                title_text += "  [当前值周]"
                
            t_color = "#00adb5" if d["is_current"] else colors["text_primary"]
            title_lbl = tk.Label(card, text=title_text, font=("Helvetica", 11, "bold"), fg=t_color, bg=colors["card_bg"], anchor="w", justify="left")
            title_lbl.grid(row=0, column=0, padx=15, pady=(10, 2), sticky="w")
            
            det_text = f"行政值周: {d['admin']}   |   值周班级: {d['class']}   |   时间: {d['date']}"
            det_lbl = tk.Label(card, text=det_text, fg=colors["text_secondary"], bg=colors["card_bg"], font=("Helvetica", 9), anchor="w", justify="left")
            det_lbl.grid(row=1, column=0, padx=15, pady=(0, 10), sticky="w")

    def search_duty(self):
        q = self.search_entry.get().strip()
        if not q:
            # 输入为空，恢复全表显示
            if self.duties_cache:
                self.refresh_all_tab(self.duties_cache)
            return
            
        matches = []
        for d in self.duties_cache:
            if q in d["week"] or q in d["admin"] or q in d["group1"] or q in d["group2"] or q in d["group3"] or q in d["class"]:
                matches.append(d)
                
        for child in self.all_scroll.winfo_children():
            child.destroy()
            
        if not matches:
            empty = ctk.CTkLabel(self.all_scroll, text="没有搜索到任何匹配的值周排班周次。")
            empty.pack(pady=40)
        else:
            self.refresh_all_tab(matches)


class LostFoundFrame(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color="transparent")
        self.controller = controller
        
        self.page = 1

        self.header = ctk.CTkFrame(self, fg_color="transparent")
        self.header.pack(fill="x", pady=(5, 10))

        self.title = ctk.CTkLabel(self.header, text="🔍 全校失物招领登记", font=ctk.CTkFont(size=18, weight="bold"))
        self.title.pack(side="left", padx=5)

        self.refresh_btn = ctk.CTkButton(self.header, text="🔄 刷新", width=80, command=self.load_list)
        self.refresh_btn.pack(side="right", padx=5)

        self.prev_btn = ctk.CTkButton(self.header, text="◀ 上一页", width=80, command=lambda: self.change_page(-1))
        self.prev_btn.pack(side="right", padx=5)
        
        self.page_label = ctk.CTkLabel(self.header, text="第 1 页", font=ctk.CTkFont(size=13))
        self.page_label.pack(side="right", padx=10)

        self.next_btn = ctk.CTkButton(self.header, text="下一页 ▶", width=80, command=lambda: self.change_page(1))
        self.next_btn.pack(side="right", padx=5)

        self.scroll = ctk.CTkScrollableFrame(self)
        self.scroll.pack(fill="both", expand=True)

        self.loaded = False

    def on_show(self):
        if not self.loaded:
            self.load_list()

    def change_page(self, delta):
        if self.page + delta < 1:
            return
        self.page += delta
        self.page_label.configure(text=f"第 {self.page} 页")
        self.load_list()

    def load_list(self):
        self.refresh_btn.configure(state="disabled", text="加载中...")
        self.prev_btn.configure(state="disabled")
        self.next_btn.configure(state="disabled")
        for child in self.scroll.winfo_children():
            child.destroy()
            
        loading = ctk.CTkLabel(self.scroll, text="正在读取校园失物招领，请稍候...", font=ctk.CTkFont(size=14))
        loading.pack(pady=40)

        def query_lf():
            status, body, _ = ch_cli.make_request(f"/lostAndFound/lostAndFoundList/?page={self.page}", method="GET", follow_redirects=True)
            if status != 200:
                return False, f"HTTP Error: {status}"
                
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
                        
                    category = ch_cli.clean_html(tds[1])
                    title = ch_cli.clean_html(tds[2])
                    reporter = ch_cli.clean_html(tds[3])
                    start_date = ch_cli.clean_html(tds[6])
                    status_text = ch_cli.clean_html(tds[8]) if len(tds) > 8 else ""
                    
                    rows.append((lf_id, category, title, reporter, start_date, status_text))
            return True, rows

        def callback(res):
            self.refresh_btn.configure(state="normal", text="🔄 刷新")
            self.prev_btn.configure(state="normal" if self.page > 1 else "disabled")
            self.next_btn.configure(state="normal")
            for child in self.scroll.winfo_children():
                child.destroy()
                
            success, data = res
            if not success:
                err = ctk.CTkLabel(self.scroll, text=f"加载失败: {data}", text_color="red")
                err.pack(pady=40)
                return
                
            if not data:
                empty = ctk.CTkLabel(self.scroll, text="本页暂无失物招领登记。")
                empty.pack(pady=40)
                return
                
            self.loaded = True
            colors = get_theme_colors()
            for lf_id, category, title, reporter, start_date, status_text in data:
                card = ctk.CTkFrame(self.scroll, corner_radius=6)
                card.pack(fill="x", padx=5, pady=4)
                
                card.columnconfigure(0, weight=1)
                
                # 状态高亮
                tag_color = "#f44336" if "丢" in category else "#4caf50"
                stat_color = "#f44336" if "等待" in status_text else colors["text_secondary"]
                
                title_lbl = tk.Label(card, text=f"[{category}]  {title}", font=("Helvetica", 11, "bold"), fg=tag_color, bg=colors["card_bg"], anchor="w", justify="left")
                title_lbl.grid(row=0, column=0, padx=15, pady=(10, 2), sticky="w")
                
                info_text = f"发布处: {reporter}   |   发布日期: {start_date}   |   状态: {status_text}"
                info_lbl = tk.Label(card, text=info_text, fg=stat_color, bg=colors["card_bg"], font=("Helvetica", 9), anchor="w", justify="left")
                info_lbl.grid(row=1, column=0, padx=15, pady=(0, 10), sticky="w")
                
                btn = ctk.CTkButton(card, text="查看招领", width=90, command=lambda l=lf_id: self.show_detail(l))
                btn.grid(row=0, column=1, rowspan=2, padx=15, pady=10)

        self.controller.run_async(query_lf, callback=callback)

    def show_detail(self, lf_id):
        detail_win = LostFoundDetailWindow(self.controller, lf_id)
        self.controller.wait_window(detail_win)


class LostFoundDetailWindow(ctk.CTkToplevel):
    def __init__(self, parent, lf_id):
        super().__init__(parent)
        self.parent = parent
        self.lf_id = lf_id
        self.title("物品招领/丢失信息明细")
        self.geometry("700x520")
        
        self.transient(parent)
        self.wait_visibility()
        self.grab_set()

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.meta_frame = ctk.CTkFrame(self, corner_radius=0)
        self.meta_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 5))
        self.meta_frame.columnconfigure(0, weight=1)

        self.title_lbl = ctk.CTkLabel(self.meta_frame, text="正在读取招领信息详情...", font=ctk.CTkFont(size=15, weight="bold"), justify="left")
        self.title_lbl.grid(row=0, column=0, padx=15, pady=(10, 5), sticky="w")

        self.info_lbl = ctk.CTkLabel(self.meta_frame, text="", text_color="grey60", font=ctk.CTkFont(size=12))
        self.info_lbl.grid(row=1, column=0, padx=15, pady=(0, 10), sticky="w")

        self.textbox = ctk.CTkTextbox(self, font=ctk.CTkFont(size=14))
        self.textbox.grid(row=2, column=0, sticky="nsew", padx=15, pady=5)
        
        # 配图多媒体
        self.attachment_frame = ctk.CTkFrame(self, height=70)
        self.attachment_frame.grid(row=3, column=0, sticky="ew", padx=15, pady=(5, 15))
        self.attachment_frame.columnconfigure(0, weight=1)
        
        self.att_lbl = ctk.CTkLabel(self.attachment_frame, text="📎 正在提取关联附件...", text_color="grey60", font=ctk.CTkFont(size=12))
        self.att_lbl.grid(row=0, column=0, padx=15, pady=10, sticky="w")

        self.download_btn = ctk.CTkButton(self.attachment_frame, text="📥 下载全部文件", state="disabled", width=120, command=self.download_all)
        self.download_btn.grid(row=0, column=1, padx=15, pady=10)

        self.media_urls = []
        self.load_detail()

    def load_detail(self):
        def worker():
            status, body, _ = ch_cli.make_request(f"/lostAndFound/lostAndFoundDetail/{self.lf_id}/", method="GET", follow_redirects=True)
            if status != 200:
                return False, f"获取详情失败 (HTTP Code: {status})"
            
            html_content = body.decode("utf-8", errors="ignore")
            
            title = "无标题"
            title_m = re.search(r'<div class="ArticleTitle[^>]*>(.*?)</div>', html_content, re.DOTALL)
            if title_m:
                title = ch_cli.clean_html(title_m.group(1))
                
            reporter = "未知"
            rep_m = re.search(r'来源：\s*([^<]+)', html_content)
            if rep_m:
                reporter = ch_cli.clean_html(rep_m.group(1))
                
            reviewer = "未知"
            rev_m = re.search(r'审核人：\s*([^<]+)', html_content)
            if rev_m:
                reviewer = ch_cli.clean_html(rev_m.group(1))
                
            pub_time = "未知"
            time_m = re.search(r'发布时间：\s*([^\s<]+(?:\s+[^\s<]+)?)', html_content)
            if time_m:
                pub_time = time_m.group(1).strip()
                
            content = ""
            content_m = re.search(r'<div class="ArticleContent(?:\s+[^>]*|)\s*>(.*?)</div>', html_content, re.DOTALL)
            if content_m:
                content = ch_cli.clean_html(content_m.group(1))
                
            # 提取多媒体
            media_urls = []
            imgs = re.findall(r'<img[^>]+src=["\'](.*?)["\']', html_content)
            for img in imgs:
                if "Logo" not in img and "newFunc" not in img and "sydw" not in img:
                    if not img.startswith("http") and img.startswith("/"):
                        media_urls.append(f"{ch_cli.BASE_URL}{img}")
                    else:
                        media_urls.append(img)
                        
            vids = re.findall(r'<video[^>]+src=["\'](.*?)["\']', html_content)
            for vid in vids:
                if not vid.startswith("http") and vid.startswith("/"):
                    media_urls.append(f"{ch_cli.BASE_URL}{vid}")
                else:
                    media_urls.append(vid)

            attachment_links = ch_cli.extract_attachment_links(html_content)
            for link in attachment_links:
                if link not in media_urls:
                    media_urls.append(link)
            return True, (title, reporter, reviewer, pub_time, content, media_urls)

        def callback(res):
            if not self.winfo_exists():
                return
            success, data = res
            if not success:
                self.title_lbl.configure(text="加载详情失败")
                self.textbox.insert("0.0", data)
                self.att_lbl.configure(text="📎 无法加载招领配图/附件")
                return
                
            title, reporter, reviewer, pub_time, content, media_urls = data
            self.title_lbl.configure(text=f"🔍 物品招领：{title}")
            self.info_lbl.configure(text=f"登记处: {reporter}   |   审核人: {reviewer}   |   时间: {pub_time}")
            self.textbox.insert("0.0", content)
            
            self.media_urls = media_urls
            if media_urls:
                self.att_lbl.configure(text=f"📎 发现该失物招领关联了 {len(media_urls)} 个多媒体文件或附件", text_color="#1088ff" if ctk.get_appearance_mode() == "Light" else "#00adb5")
                self.download_btn.configure(state="normal")
            else:
                self.att_lbl.configure(text="📎 本招领未检测到多媒体附件或关联文件")

        self.parent.run_async(worker, callback=callback)

    def download_all(self):
        if not self.media_urls:
            return
        out_dir = filedialog.askdirectory(title="选择照片保存位置")
        if not out_dir:
            return
            
        self.download_btn.configure(state="disabled", text="正在保存...")
        
        def task():
            ch_cli.download_attachments(self.media_urls, out_dir)
            return True

        def callback(res):
            if not self.winfo_exists():
                return
            self.download_btn.configure(state="normal", text="📥 下载全部文件")
            messagebox.showinfo("成功", f"文件附件下载成功，已保存至:\n{out_dir}")

        self.parent.run_async(task, callback=callback)


class FileFrame(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color="transparent")
        self.controller = controller

        self.header = ctk.CTkFrame(self, fg_color="transparent")
        self.header.pack(fill="x", pady=(5, 10))

        self.title = ctk.CTkLabel(self.header, text="📁 学校文件临时寄存与安全寄取提取", font=ctk.CTkFont(size=18, weight="bold"))
        self.title.pack(side="left", padx=5)

        # 左右双分流面板
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True)
        self.body.columnconfigure(0, weight=1)
        self.body.columnconfigure(1, weight=1)

        self.init_upload_panel()
        self.init_download_panel()

    def init_upload_panel(self):
        # 左侧：上传面板
        self.upload_panel = ctk.CTkFrame(self.body)
        self.upload_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=10)
        self.upload_panel.columnconfigure(0, weight=1)

        lbl = ctk.CTkLabel(self.upload_panel, text="📤 寄存文件上传", font=ctk.CTkFont(size=15, weight="bold"))
        lbl.grid(row=0, column=0, padx=15, pady=(15, 10), sticky="w")

        desc = ctk.CTkLabel(self.upload_panel, text="选择本地任意文件，客户端将自动执行\n50MB 大小逻辑分片上传，合并后生成六位提取密码。", text_color="grey60", font=ctk.CTkFont(size=12), justify="left")
        desc.grid(row=1, column=0, padx=15, pady=5, sticky="w")

        # 选择文件展示
        self.sel_file_lbl = ctk.CTkLabel(self.upload_panel, text="尚未选择任何文件", text_color="grey50", font=ctk.CTkFont(size=13))
        self.sel_file_lbl.grid(row=2, column=0, padx=15, pady=10, sticky="w")

        self.choose_btn = ctk.CTkButton(self.upload_panel, text="📁 选择本地文件", command=self.choose_file)
        self.choose_btn.grid(row=3, column=0, padx=15, pady=5, sticky="w")

        # 进度条
        self.progress_bar = ctk.CTkProgressBar(self.upload_panel, width=240)
        self.progress_bar.grid(row=4, column=0, padx=15, pady=15, sticky="w")
        self.progress_bar.set(0)

        self.progress_lbl = ctk.CTkLabel(self.upload_panel, text="进度: 0%", font=ctk.CTkFont(size=12))
        self.progress_lbl.grid(row=4, column=0, padx=(270, 15), pady=15, sticky="w")

        self.upload_btn = ctk.CTkButton(self.upload_panel, text="🚀 开始分片上传", state="disabled", command=self.start_upload)
        self.upload_btn.grid(row=5, column=0, padx=15, pady=10, sticky="w")

        # 上传生成的密码显示
        self.pwd_result_frame = ctk.CTkFrame(self.upload_panel, fg_color="transparent")
        self.pwd_result_frame.grid(row=6, column=0, padx=15, pady=15, sticky="ew")

        self.pwd_lbl = ctk.CTkLabel(self.pwd_result_frame, text="", font=ctk.CTkFont(size=22, weight="bold"), text_color="#4caf50")
        self.pwd_lbl.pack(side="left", padx=5)

        self.copy_btn = ctk.CTkButton(self.pwd_result_frame, text="📋 复制密码", width=80, state="disabled", command=self.copy_password)
        self.copy_btn.pack(side="left", padx=10)

        self.selected_file_path = None
        self.generated_pwd = ""

    def init_download_panel(self):
        # 右侧：下载提取面板
        self.download_panel = ctk.CTkFrame(self.body)
        self.download_panel.grid(row=0, column=1, sticky="nsew", padx=(10, 0), pady=10)
        self.download_panel.columnconfigure(0, weight=1)

        lbl = ctk.CTkLabel(self.download_panel, text="📥 提取下载文件", font=ctk.CTkFont(size=15, weight="bold"))
        lbl.grid(row=0, column=0, padx=15, pady=(15, 10), sticky="w")

        desc = ctk.CTkLabel(self.download_panel, text="输入发送方生成的六位数文件提取密码，\n即可高速下载合并好的寄存文件至本地指定位置。", text_color="grey60", font=ctk.CTkFont(size=12), justify="left")
        desc.grid(row=1, column=0, padx=15, pady=5, sticky="w")

        # 密码输入
        lbl_pwd = ctk.CTkLabel(self.download_panel, text="输入 6 位提取密码:")
        lbl_pwd.grid(row=2, column=0, padx=15, pady=(15, 5), sticky="w")

        self.pwd_entry = ctk.CTkEntry(self.download_panel, placeholder_text="如: 123456", font=ctk.CTkFont(size=14), width=180)
        self.pwd_entry.grid(row=3, column=0, padx=15, pady=5, sticky="w")

        # 目标路径
        self.dest_lbl = ctk.CTkLabel(self.download_panel, text="默认保存至: 系统下载目录/当前目录", text_color="grey50", font=ctk.CTkFont(size=12))
        self.dest_lbl.grid(row=4, column=0, padx=15, pady=10, sticky="w")

        self.dest_btn = ctk.CTkButton(self.download_panel, text="📂 选择保存目录", command=self.choose_dest)
        self.dest_btn.grid(row=5, column=0, padx=15, pady=5, sticky="w")

        self.download_btn = ctk.CTkButton(self.download_panel, text="📥 提取拉取文件", command=self.start_download)
        self.download_btn.grid(row=6, column=0, padx=15, pady=20, sticky="w")

        self.selected_dest_dir = "."

    def choose_file(self):
        file_path = filedialog.askopenfilename(title="选择要寄存上传的文件")
        if file_path:
            self.selected_file_path = file_path
            filename = os.path.basename(file_path)
            size = os.path.getsize(file_path)
            self.sel_file_lbl.configure(text=f"已选: {filename}\n大小: {size} 字节", text_color=("gray10", "gray90"))
            self.upload_btn.configure(state="normal")
            
            # 重置进度与密码
            self.progress_bar.set(0)
            self.progress_lbl.configure(text="进度: 0%")
            self.pwd_lbl.configure(text="")
            self.copy_btn.configure(state="disabled")

    def start_upload(self):
        if not self.selected_file_path or not os.path.exists(self.selected_file_path):
            return
            
        self.upload_btn.configure(state="disabled", text="正在分片...")
        self.choose_btn.configure(state="disabled")
        
        file_path = self.selected_file_path
        filename = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        
        # 50MB 逻辑分片
        chunk_size = 50 * 1024 * 1024
        total_chunks = (file_size + chunk_size - 1) // chunk_size
        if total_chunks == 0:
            total_chunks = 1
            
        task_id = f"WU_FILE_{urllib.parse.quote(filename)}_{int(time.time())}"

        def upload_task():
            try:
                with open(file_path, "rb") as f:
                    for chunk_idx in range(total_chunks):
                        # 更新UI进度条
                        progress = (chunk_idx) / total_chunks
                        self.after(0, lambda p=progress, i=chunk_idx: self.update_progress(p, f"正在发送分片 {i+1}/{total_chunks}..."))
                        
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
                        
                        content_type, body = ch_cli.encode_multipart_formdata(fields, files)
                        headers = {
                            "Content-Type": content_type,
                            "Content-Length": str(len(body))
                        }
                        
                        status, _, _ = ch_cli.make_request("/fileaccess/files_upload/", method="POST", data=body, headers=headers)
                        if status != 200:
                            return False, f"分片 {chunk_idx + 1} 上传失败 (HTTP: {status})"
                            
                # 所有分片上传完，请求合并
                self.after(0, lambda: self.update_progress(0.95, "所有分片已完工，正在进行服务器合并..."))
                complete_data = {
                    "task_id": task_id,
                    "filename": filename
                }
                status_c, resp_c, _ = ch_cli.make_request("/fileaccess/upload_complete/", method="POST", data=complete_data)
                if status_c == 200:
                    password = resp_c.decode("utf-8", errors="ignore").strip()
                    password = ch_cli.clean_html(password)
                    return True, password
                else:
                    return False, f"合并失败 (HTTP Code: {status_c})"
            except Exception as e:
                return False, str(e)

        def callback(res):
            self.choose_btn.configure(state="normal")
            self.upload_btn.configure(state="normal", text="🚀 开始分片上传")
            success, val = res
            if not success:
                self.update_progress(0, "进度: 0%")
                messagebox.showerror("失败", f"上传文件失败:\n{val}")
            else:
                self.update_progress(1.0, "进度: 100% (完成)")
                self.generated_pwd = val
                self.pwd_lbl.configure(text=f"🔑 提取密码：{val}")
                self.copy_btn.configure(state="normal")
                messagebox.showinfo("成功", f"文件寄存并分片上传成功！\n文件提取密码为: {val}")

        self.controller.run_async(upload_task, callback=callback)

    def update_progress(self, val, text):
        self.progress_bar.set(val)
        self.progress_lbl.configure(text=text)

    def copy_password(self):
        if self.generated_pwd:
            self.clipboard_clear()
            self.clipboard_append(self.generated_pwd)
            messagebox.showinfo("复制", f"密码 {self.generated_pwd} 已成功复制至剪贴板。")

    def choose_dest(self):
        dest = filedialog.askdirectory(title="选择文件保存目录")
        if dest:
            self.selected_dest_dir = dest
            self.dest_lbl.configure(text=f"保存至: {dest}", text_color=("gray10", "gray90"))

    def start_download(self):
        pwd = self.pwd_entry.get().strip()
        if not pwd or len(pwd) != 6:
            messagebox.showerror("错误", "请输入有效的 6 位数提取密码！")
            return
            
        self.download_btn.configure(state="disabled", text="正在拉取...")
        
        def task():
            post_data = {
                "thePasswordTheUserEntered": pwd
            }
            status, body, _ = ch_cli.make_request("/fileaccess/get-AccessFile/", method="POST", data=post_data)
            if status != 200:
                return False, f"请求失败 (HTTP: {status})"
                
            try:
                res_json = json.loads(body.decode("utf-8"))
                if res_json.get("error") != "0":
                    return False, res_json.get("msg", "提取码不存在或文件已过期。")
                    
                file_path_name = res_json.get("filePathName")
                file_name = res_json.get("fileNameForDisplay")
                if not file_path_name or not file_name:
                    return False, "服务器返回的文件元数据不完整。"
                    
                download_url = f"/static/fileaccess/{file_path_name}"
                target_path = os.path.join(self.selected_dest_dir, file_name)
                
                # 开始下载大文件
                status_dl, body_dl, _ = ch_cli.make_request(download_url, method="GET")
                if status_dl == 200:
                    with open(target_path, "wb") as f_dl:
                        f_dl.write(body_dl)
                    return True, target_path
                else:
                    return False, f"下载数据流失败 (HTTP: {status_dl})"
            except Exception as e:
                return False, str(e)

        def callback(res):
            self.download_btn.configure(state="normal", text="📥 提取拉取文件")
            success, val = res
            if not success:
                messagebox.showerror("错误", f"提取寄存文件失败:\n{val}")
            else:
                messagebox.showinfo("成功", f"文件已成功安全提取并下载！\n已保存至:\n{val}")

        self.controller.run_async(task, callback=callback)


if __name__ == "__main__":
    app = App()
    app.mainloop()
