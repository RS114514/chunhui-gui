#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
from html.parser import HTMLParser
import customtkinter as ctk

BASE_URL = "http://10.181.200.3"

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
            self.current_line = ""
        elif self.current_line == "":
            if self.output and self.output[-1] != "":
                self.output.append("")

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
            if unicodedata.east_asian_width(char) in ('W', 'F', 'A'):
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
        return str(e)

def display_markdown_in_textbox(widget, md_text):
    widget.configure(state="normal")
    widget.delete("0.0", "end")
    
    family = "Courier"
    textbox_core = getattr(widget, "_textbox", widget)
    
    # 重新配置所有 Tag 属性
    textbox_core.tag_config("h1", font=(family, 20, "bold"), foreground="#4caf50")
    textbox_core.tag_config("h2", font=(family, 17, "bold"), foreground="#4caf50")
    textbox_core.tag_config("h3", font=(family, 15, "bold"), foreground="#00adb5")
    textbox_core.tag_config("h4", font=(family, 14, "bold"), foreground="#00adb5")
    textbox_core.tag_config("bold", font=(family, 14, "bold"))
    textbox_core.tag_config("link", font=(family, 14, "underline"), foreground="#00adb5")
    textbox_core.tag_config("table_sep", font=(family, 14), foreground="#56b6c2")
    textbox_core.tag_config("table_header", font=(family, 14, "bold"), foreground="#00adb5")
    textbox_core.tag_config("img", font=(family, 14, "bold"), foreground="#d19a66")
    
    lines = md_text.split('\n')
    is_table_header = True
    
    for line in lines:
        if line.startswith('# '):
            widget.insert("end", line[2:] + "\n", "h1")
            continue
        elif line.startswith('## '):
            widget.insert("end", line[3:] + "\n", "h2")
            continue
        elif line.startswith('### '):
            widget.insert("end", line[4:] + "\n", "h3")
            continue
        elif line.startswith('#### '):
            widget.insert("end", line[5:] + "\n", "h4")
            continue
            
        if '|' in line and '---' in line:
            widget.insert("end", line + "\n", "table_sep")
            is_table_header = False
            continue
            
        if '|' in line:
            parts = line.split('|')
            widget.insert("end", "|", "table_sep")
            for part in parts[1:-1]:
                tag = "table_header" if is_table_header else "bold" if "**" in part else ""
                clean_part = part.replace("**", "")
                widget.insert("end", clean_part, tag)
                widget.insert("end", "|", "table_sep")
            widget.insert("end", "\n")
            continue
            
        is_table_header = True
        
        ptr = 0
        while ptr < len(line):
            img_match = re.match(r'\!\[(.*?)\]\((.*?)\)', line[ptr:])
            if img_match:
                alt = img_match.group(1) or "图片"
                widget.insert("end", f" [📷 图片: {alt}] ", "img")
                ptr += img_match.end()
                continue
                
            link_match = re.match(r'\[(.*?)\]\((.*?)\)', line[ptr:])
            if link_match:
                text = link_match.group(1)
                widget.insert("end", text, "link")
                ptr += link_match.end()
                continue
                
            bold_match = re.match(r'\*\*(.*?)\*\*', line[ptr:])
            if bold_match:
                text = bold_match.group(1)
                widget.insert("end", text, "bold")
                ptr += bold_match.end()
                continue
                
            widget.insert("end", line[ptr])
            ptr += 1
            
        widget.insert("end", "\n")
        
    widget.configure(state="disabled")

# 默认测试 HTML
DEFAULT_HTML = """<div>
  <h1>校内公示：关于端午节值周与考评的通知</h1>
  <p>各位班主任、老师和同学：</p>
  <p>为切实做好假期前后的安全与纪律工作，现将下周<strong>值周小组</strong>及考评标准公布如下。请各部门严格对照执行：</p>
  
  <h3>1. 值周与检查小组分工</h3>
  <ul>
    <li>行政总值周：<strong>章老师</strong> (负责全校统筹)</li>
    <li>第一值周组：负责教学区及连廊纪律检查</li>
    <li>第二值周组：负责寝室卫生与午休考评</li>
  </ul>
  
  <h3>2. 各宿舍楼卫生扣分重点项目</h3>
  <p>请各宿舍管理员严格对照下表进行打分和登记：</p>
  
  <table border="1">
    <tr>
      <th>考评项 (指标)</th>
      <th>扣分分值</th>
      <th>说明与备注</th>
    </tr>
    <tr>
      <td>垃圾未带下楼</td>
      <td>每处扣 <strong>1.5 分</strong></td>
      <td>需在早上 7:30 前清理完毕</td>
    </tr>
    <tr>
      <td>违规使用电器</td>
      <td>每处扣 <strong>5.0 分</strong></td>
      <td>一经查实，当季评优一票否决</td>
    </tr>
    <tr>
      <td>被子未叠放整齐</td>
      <td>每处扣 <strong>0.5 分</strong></td>
      <td>以整洁美观为考核基准</td>
    </tr>
  </table>
  
  <p>如有疑问，请点击 <a href="/department/hygiene">联系德育处</a> 咨询相关负责人。</p>
  <p>以下是往期扣分现场整改流程图，供大家查阅：</p>
  <img src="/static/media/flowchart.png" alt="整改规范图示" />
  
  <p>顺祝端午安康！</p>
</div>"""

class TestApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("春晖中学校园网 GUI Markdown 渲染测试")
        self.geometry("960x640")
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        self.top_lbl = ctk.CTkLabel(
            self, 
            text="春晖校园网 GUI Markdown 展示引擎测试 (Tkinter 免联线版)", 
            font=ctk.CTkFont(size=18, weight="bold")
        )
        self.top_lbl.grid(row=0, column=0, columnspan=2, padx=20, pady=15, sticky="w")

        self.left_frame = ctk.CTkFrame(self)
        self.left_frame.grid(row=1, column=0, padx=(20, 10), pady=10, sticky="nsew")
        self.left_frame.grid_columnconfigure(0, weight=1)
        self.left_frame.grid_rowconfigure(1, weight=1)

        self.html_lbl = ctk.CTkLabel(self.left_frame, text="网页 HTML 原始数据 (可在此修改测试)：", font=ctk.CTkFont(size=13, weight="bold"))
        self.html_lbl.grid(row=0, column=0, padx=15, pady=(10, 5), sticky="w")

        self.html_text = ctk.CTkTextbox(self.left_frame, font=ctk.CTkFont(size=12))
        self.html_text.grid(row=1, column=0, padx=15, pady=(5, 10), sticky="nsew")
        self.html_text.insert("0.0", DEFAULT_HTML)

        self.right_frame = ctk.CTkFrame(self)
        self.right_frame.grid(row=1, column=1, padx=(10, 20), pady=10, sticky="nsew")
        self.right_frame.grid_columnconfigure(0, weight=1)
        self.right_frame.grid_rowconfigure(1, weight=1)

        self.md_lbl = ctk.CTkLabel(self.right_frame, text="CTkTextbox 中渲染的 Markdown (等宽富文本效果)：", font=ctk.CTkFont(size=13, weight="bold"))
        self.md_lbl.grid(row=0, column=0, padx=15, pady=(10, 5), sticky="w")

        self.md_text = ctk.CTkTextbox(self.right_frame, font=ctk.CTkFont(family="Courier", size=14))
        self.md_text.grid(row=1, column=0, padx=15, pady=(5, 10), sticky="nsew")

        self.control_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.control_frame.grid(row=2, column=0, columnspan=2, padx=20, pady=15, sticky="ew")
        
        self.convert_btn = ctk.CTkButton(
            self.control_frame, 
            text="开始测试渲染 ⚡", 
            fg_color="#00adb5",
            hover_color="#00888d",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.run_conversion
        )
        self.convert_btn.pack(side="right", padx=10)

        self.reset_btn = ctk.CTkButton(
            self.control_frame, 
            text="恢复默认模板", 
            width=100, 
            fg_color="transparent", 
            border_width=1,
            command=self.reset_template
        )
        self.reset_btn.pack(side="right", padx=10)

        self.run_conversion()

    def run_conversion(self):
        html = self.html_text.get("0.0", "end").strip()
        md = render_html_to_markdown(html)
        
        # 使用自定义的富文本渲染器
        display_markdown_in_textbox(self.md_text, md)

    def reset_template(self):
        self.html_text.delete("0.0", "end")
        self.html_text.insert("0.0", DEFAULT_HTML)
        self.run_conversion()

if __name__ == "__main__":
    app = TestApp()
    app.mainloop()
