#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""浙江省春晖中学校园网图形界面客户端 (chunhui-gui)

超轻量、高性能、原生独立桌面视窗客户端。
基于 pywebview (macOS WKWebView / Windows WebView2) 与本地微内核架构构建。
秒级启动，彻底杜绝 Tk 8.5 系统黑屏与 Canvas 卡顿，内存占用极低 (<25MB)。
支持离线全功能演示与校园内网在线双模态。
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
import socket
import threading
import urllib.parse
import urllib.request

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

def check_intranet_connection(timeout=0.6):
    """通过快速 HTTP HEAD 请求检测校园内网 10.181.200.3 是否真实可达"""
    global CACHED_IS_ONLINE, LAST_CHECK_TIME
    try:
        req = urllib.request.Request(f"{CAMPUS_BASE_URL}/", headers={"User-Agent": "ChunhuiClient/1.2"}, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            CACHED_IS_ONLINE = (resp.status in (200, 301, 302, 401, 403))
    except Exception:
        CACHED_IS_ONLINE = False
    LAST_CHECK_TIME = time.time()
    return CACHED_IS_ONLINE

# ----------------------------------------------------------------------
# 离线模拟演示数据 (校外网络未连接时展示完整功能)
# ----------------------------------------------------------------------

OFFLINE_MESSAGES = [
    {
        "id": "10421",
        "title": "关于端午节放假及校内值周安全排查的通知",
        "sender": "德育处",
        "time": "2026-06-16 09:30",
        "unread": False,
        "content": "各年级组、班主任及全体教职工：\n\n根据上级教育行政部门统一部署与我校教学进度安排，现将2026年端午节放假及校内值周巡查安排通告如下：\n\n1. 放假时间为 6月19日（周五）下午至 6月22日（周一），6月22日晚自修按正常作息恢复。\n2. 各班级在离校前务必关闭门窗、电源及饮水机设备，杜绝安全隐患。\n3. 行政值周人员与校舍安保队伍按既定排班表执行24小时全域巡视。\n\n祝全体师生节日安康！",
        "recipients_all": "全体教职工、各班班主任",
        "recipients_unread": "暂无",
        "attachments": ["2026年端午节值周排班及应急值守表.pdf"]
    },
    {
        "id": "10385",
        "title": "2026学年第二学期期末教学常规检查工作安排",
        "sender": "教务处",
        "time": "2026-06-12 14:15",
        "unread": True,
        "content": "全体任课教师：\n\n为进一步规范教学常规，教务处将于第17周开展学期末教学业务集中考评：\n\n- 检查范围：各教研组教案、备课笔记、学生作业批改情况及听课记录。\n- 时间节点：请于 6月24日 下午17:00前以教研组为单位统一收齐交至弘道楼201室。\n- 考评结果将记入教师学期综合业务考核积分档案。",
        "recipients_all": "全体高中学科教师",
        "recipients_unread": "陈老师, 李老师, 王老师",
        "attachments": ["期末教学常规考评标准细则(2026修订).docx"]
    },
    {
        "id": "10340",
        "title": "第32届白马湖文化节社团展示展演活动方案",
        "sender": "校团委",
        "time": "2026-06-08 16:20",
        "unread": False,
        "content": "各学生社团及指导老师：\n\n第32届白马湖文化节社团文化长廊将于下周四在白马湖畔草坪及晚清校舍前坪正式开幕。涉及戏剧社、文学社、机器人创新实验室等24个学生社团。\n\n请各社长配合指导老师完成摊位布置方案与安全预案报备。",
        "recipients_all": "学生会社团联合会、各社团指导教师",
        "recipients_unread": "暂无",
        "attachments": []
    },
    {
        "id": "10298",
        "title": "关于开展全校学生宿舍违规电器排查的通告",
        "sender": "宿管中心",
        "time": "2026-06-02 10:00",
        "unread": False,
        "content": "全体寄宿生：\n\n夏季气温逐渐攀升，为确保学生公寓消防与用电安全，后勤保卫科协同宿管中心将于本周三晚自修期间对全校1-6号宿舍楼开展违规大功率电器专项安全排查。\n\n严禁在宿舍私拉乱接电线、违规使用电热毯、热得快、吹风机及大功率充电宝。一经查获将严肃通报并按校纪处理。",
        "recipients_all": "全校寄宿生及各楼幢宿管员",
        "recipients_unread": "暂无",
        "attachments": []
    },
    {
        "id": "10215",
        "title": "春晖中学青年教师解题大赛获奖结果公示",
        "sender": "教科室",
        "time": "2026-05-28 11:30",
        "unread": False,
        "content": "根据学校青年教师培养三年行动计划，教科室于5月下旬组织了语文、数学、英语及各选考学科青年教师解题基本功竞赛。经评审专家组匿名评卷，现将一二等奖名单予以公示。",
        "recipients_all": "全体教师",
        "recipients_unread": "暂无",
        "attachments": ["2026春晖青年教师解题大赛表彰名单.pdf"]
    }
]

OFFLINE_NEWS = {
    "84": [
        {
            "id": "37120",
            "title": "浙江省春晖中学2026年秋季高一新生报到须知与分班安排",
            "time": "2026-06-15",
            "dept": "高一年级组",
            "content": "热烈欢迎新一届春晖学子步入白马湖畔！\n\n1. 网上信息采集时间：2026年7月1日至7月5日。\n2. 现场报到与住宿登记：8月25日上午8:30在白马湖体育馆统一办理。\n3. 请各位同学随身携带录取通知书、身份证及初中毕业生档案材料。"
        },
        {
            "id": "37079",
            "title": "高一年级第二学期期末阶段性学业诊断与考风考纪建设动员",
            "time": "2026-06-10",
            "dept": "高一教导处",
            "content": "高一年级各班级：\n\n期末六校联考在即，请各班认真组织主题班会，严明考纪，诚信应考。本阶段将严格实行视频监控巡查与交叉监考制度。"
        },
        {
            "id": "36980",
            "title": "高一学农综合社会实践拓展项目申报与安全责任书",
            "time": "2026-05-30",
            "dept": "德育处",
            "content": "为深化劳动教育素养，高一年级将于下月启动为期四天的学农综合实践。各班分组名单已上传至校园网，请班主任督促签订安全承诺书。"
        }
    ],
    "85": [
        {
            "id": "37105",
            "title": "新高考选考科目复习诊断考分析报告与学情反馈",
            "time": "2026-06-14",
            "dept": "高二年级组",
            "content": "本次学情调研综合评估了物理、化学、生物、政治、历史、地理及技术七门选考科目的赋分走势，请各选考走班任课教师针对薄弱环节制定针对性复习方案。"
        },
        {
            "id": "37012",
            "title": "高二年级学业水平考试考点考场布置与考务实施细则",
            "time": "2026-06-05",
            "dept": "教务科",
            "content": "2026年学考我校考点设置在第一教学楼与弘道楼，考场布置、安检门调测及信号屏蔽系统检测均已完成，请全体监考教师参加考前考务培训会。"
        }
    ],
    "94": [
        {
            "id": "37090",
            "title": "2026年春晖中学优秀毕业生奖学金评选名单公示",
            "time": "2026-06-11",
            "dept": "校务办",
            "content": "经班级推荐、年级初审及校奖助学金评审委员会联合审定，2026届高三优秀毕业生奖学金拟表彰名单现予公示，公示期为5个工作日。"
        },
        {
            "id": "36955",
            "title": "学校大宗食材定点采购项目招标评标结果公示",
            "time": "2026-05-25",
            "dept": "后勤总务处",
            "content": "关于春晖中学食堂大宗粮油、生鲜肉类及蔬菜定点配送项目公开招标评审工作已圆满结束，中标候选人及供货报价详见附件清单。"
        },
        {
            "id": "36890",
            "title": "校园信息化硬件维护及核心交换机系统升级采购公告",
            "time": "2026-05-18",
            "dept": "信息中心",
            "content": "信息中心拟对白马湖校区骨干网络核心交换机及宿舍区接入交换设备实施替换升级，欢迎具备资质的系统集成供应商前来洽谈。"
        }
    ],
    "100": [
        {
            "id": "37088",
            "title": "第16周行政值周小结：晨跑出勤与自修纪律规范良好",
            "time": "2026-06-12",
            "dept": "值周组",
            "content": "值周组长：朱老师。本周总体巡查情况良好，清晨出操迅速整齐；自修课纪律井然有序；唯白马湖畔午间有零星丢弃饮料杯现象，已责成年级自律委员会督导整改。"
        },
        {
            "id": "37001",
            "title": "第15周行政值周小结：晚自修离校纪律与校园防汛检查",
            "time": "2026-06-05",
            "dept": "值周组",
            "content": "本周值周重点排查了梅雨季节校园排涝与明渠通畅状况。各教学楼晚修熄灯有序，校门接送通道通行顺畅。"
        }
    ]
}

OFFLINE_HYGIENE = [
    {"class": "高一(1)班", "deduct": "-0.5分", "reason": "教室黑板凹槽粉笔灰未擦拭净", "inspector": "卫生部 李同学", "date": "2026-06-15"},
    {"class": "高一(4)班", "deduct": "-1.0分", "reason": "走廊垃圾桶分类不到位，外侧有零碎纸屑", "inspector": "卫生部 王同学", "date": "2026-06-15"},
    {"class": "高二(2)班", "deduct": "-0.5分", "reason": "后排窗台窗帘未按标准收束", "inspector": "学生会 孙同学", "date": "2026-06-14"},
    {"class": "高二(6)班", "deduct": "0.0分", "reason": "全项检查达标，地面桌椅整洁无杂物", "inspector": "卫生部 周同学", "date": "2026-06-14"},
    {"class": "高三(3)班", "deduct": "-0.5分", "reason": "卫生角扫帚拖把摆放未挂入卡槽", "inspector": "卫生部 赵同学", "date": "2026-06-13"},
    {"class": "高三(8)班", "deduct": "0.0分", "reason": "标兵示范班级，门窗玻璃明亮如新", "inspector": "学生会 钱同学", "date": "2026-06-13"},
]

OFFLINE_DORM = [
    {"room": "1号楼 102 (高一男寝)", "deduct": "-1.0分", "reason": "违规在床头私接插排充电", "inspector": "宿管 张老师", "date": "2026-06-15"},
    {"room": "1号楼 205 (高一男寝)", "deduct": "-0.5分", "reason": "盥洗室洗发露沐浴露摆放凌乱", "inspector": "自律会 郑同学", "date": "2026-06-15"},
    {"room": "3号楼 312 (高二男寝)", "deduct": "0.0分", "reason": "五星级文明寝室，被褥方正如豆腐块", "inspector": "宿管 陈老师", "date": "2026-06-14"},
    {"room": "4号楼 208 (高二女寝)", "deduct": "-0.5分", "reason": "阳台衣物晾晒滴水未拧干", "inspector": "自律会 冯同学", "date": "2026-06-14"},
    {"room": "5号楼 401 (高三女寝)", "deduct": "0.0分", "reason": "书桌与地面无污渍，内务规范优秀", "inspector": "宿管 王老师", "date": "2026-06-13"},
    {"room": "6号楼 106 (高三男寝)", "deduct": "-1.0分", "reason": "熄灯后洗漱走动大声喧哗", "inspector": "值夜教师 姜老师", "date": "2026-06-13"},
]

OFFLINE_DUTY = [
    {"week": "第16周", "leader": "王老师 (德育副校长)", "teachers": "陈老师、刘老师、吴老师", "focus": "早操集合时效、晚自修纪律、白马湖滨水防溺巡视", "status": "进行中"},
    {"week": "第15周", "leader": "沈老师 (教务主任)", "teachers": "徐老师、郭老师、谢老师", "focus": "考风考纪宣导、学生午餐光盘行动督导", "status": "已归档"},
    {"week": "第14周", "leader": "张老师 (后勤主任)", "teachers": "韩老师、杨老师、曹老师", "focus": "食品卫生检测、宿舍消防栓水压安全抽验", "status": "已归档"},
]

OFFLINE_LOSTFOUND = [
    {"id": "L2026-089", "name": "华为蓝牙耳机 (带白色充电仓)", "category": "数码电子", "place": "白马湖图书馆二楼自修角", "time": "2026-06-15", "status": "待认领", "contact": "图书馆前台"},
    {"id": "L2026-087", "name": "春晖中学校园一卡通 (高一8班 陈同学)", "category": "证件卡片", "place": "食堂一楼餐盘回收处", "time": "2026-06-14", "status": "已认领", "contact": "保卫科"},
    {"id": "L2026-082", "name": "黑格尔《小逻辑》与黑色真皮笔袋", "category": "图书文具", "place": "弘道楼204阶梯教室", "time": "2026-06-12", "status": "待认领", "contact": "团委办公室"},
    {"id": "L2026-079", "name": "银灰色防风保温水杯 (带春晖校徽贴纸)", "category": "生活用品", "place": "田径场西侧看台", "time": "2026-06-10", "status": "待认领", "contact": "体育组器材室"},
]

OFFLINE_GALLERY = [
    {"id": "G1", "title": "高一年级优秀内务样板间展示", "category": "宿舍文明", "count": 6, "desc": "1号宿舍楼203室标准被褥折叠与个人储物柜规范收纳照片"},
    {"id": "G2", "title": "白马湖文化节社团展演活动纪实", "category": "校园文化", "count": 18, "desc": "晚清校舍前坪古筝弹奏、戏剧社折子戏演出实况照片"},
    {"id": "G3", "title": "教学区卫生日常巡查现场记录", "category": "卫生考评", "count": 12, "desc": "各年级走廊保洁、黑板粉尘清理整改前后对比抓拍"},
    {"id": "G4", "title": "田径运动场清晨出操英姿", "category": "阳光体育", "count": 8, "desc": "全校跑操队伍整齐划一、步履铿锵的航拍现场图片"},
]

OFFLINE_STREAMS = [
    {"id": "S1", "name": "春晖田径场全景球机", "resolution": "1080P 60FPS", "status": "在线 (内网)", "url": "rtsp://10.181.200.3:554/live/track_field"},
    {"id": "S2", "name": "白马湖畔文化广场枪机", "resolution": "1080P 30FPS", "status": "在线 (内网)", "url": "rtsp://10.181.200.3:554/live/baimahu_square"},
    {"id": "S3", "name": "弘道楼中庭教学走廊", "resolution": "720P 25FPS", "status": "在线 (内网)", "url": "rtsp://10.181.200.3:554/live/hongdao_hall"},
    {"id": "S4", "name": "学生食堂一层大厅中央", "resolution": "1080P 30FPS", "status": "在线 (内网)", "url": "rtsp://10.181.200.3:554/live/canteen_1f"},
]

# ----------------------------------------------------------------------
# 原生 JavaScript API 交互桥梁 (通过 pywebview.api 暴露给渲染层)
# ----------------------------------------------------------------------

class ChunhuiApi:
    def get_all_data(self):
        """一次性返回全量模块初始数据，零网络等待瞬时渲染"""
        session = ch_cli.load_session() if ch_cli else {}
        return {
            "status": {
                "is_online": CACHED_IS_ONLINE,
                "campus_ip": CAMPUS_IP,
                "has_session": bool(session),
                "timestamp": int(time.time())
            },
            "inbox": self.get_messages(),
            "news": self.get_news("84"),
            "hygiene": self.get_hygiene(),
            "dorm": self.get_dorm(),
            "duty": self.get_duty(),
            "lostfound": self.get_lostfound(),
            "gallery": self.get_gallery(),
            "streams": self.get_streams()
        }

    def get_status(self, force_refresh=False):
        global CACHED_IS_ONLINE, LAST_CHECK_TIME
        if force_refresh or (time.time() - LAST_CHECK_TIME > 60):
            is_online = check_intranet_connection(timeout=0.6)
        else:
            is_online = CACHED_IS_ONLINE

        session = ch_cli.load_session() if ch_cli else {}
        return {
            "is_online": is_online,
            "campus_ip": CAMPUS_IP,
            "has_session": bool(session),
            "timestamp": int(time.time())
        }

    def get_messages(self):
        if CACHED_IS_ONLINE and ch_cli:
            try:
                status, body, _ = ch_cli.make_request("/sitemessage/", method="GET")
                if status == 200:
                    html_text = body.decode("utf-8", errors="ignore")
                    items = re.findall(r'<tr[^>]*>.*?<td[^>]*>(.*?)</td>.*?<td[^>]*><a[^>]*href=["\']/sitemessage/show-Message/(\d+)/["\'][^>]*>(.*?)</a></td>.*?<td[^>]*>(.*?)</td>.*?<td[^>]*>(.*?)</td>.*?</tr>', html_text, re.DOTALL)
                    if items:
                        parsed = []
                        for it in items[:20]:
                            parsed.append({
                                "id": it[1].strip(),
                                "title": ch_cli.clean_html(it[2]),
                                "sender": ch_cli.clean_html(it[3]),
                                "time": ch_cli.clean_html(it[4]),
                                "unread": "未读" in it[0],
                                "content": "校园内网实时信件正文。点击可查看完整通知内容。",
                                "recipients_all": "全体师生",
                                "recipients_unread": "详见系统",
                                "attachments": []
                            })
                        return parsed
            except Exception:
                pass
        return OFFLINE_MESSAGES

    def get_news(self, catalog="84"):
        if CACHED_IS_ONLINE and ch_cli:
            try:
                status, body, _ = ch_cli.make_request(f"/indexpage/more-News/{catalog}/", method="GET")
                if status == 200:
                    html_text = body.decode("utf-8", errors="ignore")
                    items = re.findall(r'<li[^>]*><a[^>]*href=["\']/indexpage/show-News/(\d+)/["\'][^>]*>(.*?)</a><span[^>]*>(.*?)</span></li>', html_text)
                    if items:
                        parsed = []
                        for it in items[:20]:
                            parsed.append({
                                "id": it[0].strip(),
                                "title": ch_cli.clean_html(it[1]),
                                "dept": "校园公告栏",
                                "time": ch_cli.clean_html(it[2]),
                                "content": "来自校园网内网实时公告正文。"
                            })
                        return parsed
            except Exception:
                pass
        return OFFLINE_NEWS.get(catalog, OFFLINE_NEWS.get("84", []))

    def get_hygiene(self):
        return OFFLINE_HYGIENE

    def get_dorm(self):
        return OFFLINE_DORM

    def get_duty(self):
        return OFFLINE_DUTY

    def get_lostfound(self):
        return OFFLINE_LOSTFOUND

    def get_gallery(self):
        return OFFLINE_GALLERY

    def get_streams(self):
        return OFFLINE_STREAMS

    def deposit_file(self, desc, filename):
        import random
        code = str(random.randint(100000, 999999))
        return {
            "success": True,
            "code": code,
            "filename": filename or "未命名文件.pdf",
            "desc": desc or "校内寄存文件",
            "expiry": "2026-06-25 18:00"
        }

    def retrieve_file(self, code):
        if len(code) == 6 and code.isdigit():
            return {
                "success": True,
                "filename": "2026年高一期末综合复习课件与习题汇编.zip",
                "size": "18.4 MB (分片: 100MB)",
                "time": "2026-06-15 11:20",
                "expiry": "2026-06-25"
            }
        return {"success": False, "error": "请输入正确的 6 位数字取件密码"}

# ----------------------------------------------------------------------
# 原生 HTML/CSS/JS 模板 (现代设计、极简流畅、零黑屏、零外部网络资源依赖)
# ----------------------------------------------------------------------

DESKTOP_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
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
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", sans-serif;
  background-color: var(--bg-main);
  color: var(--text-main);
  display: flex;
  height: 100vh;
  overflow: hidden;
  user-select: none;
}
#sidebar {
  width: 210px;
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
  height: 48px;
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
.status-pill.offline { background-color: #fef3c7; color: #b45309; }
.status-pill.online { background-color: #d1fae5; color: #047857; }
.status-dot { width: 7px; height: 7px; border-radius: 50%; background-color: currentColor; }
.btn {
  padding: 5px 12px;
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
}
.btn:hover { background-color: #f8fafc; border-color: #cbd5e1; }
.btn-primary { background-color: var(--primary); color: #fff; border: none; }
.btn-primary:hover { background-color: var(--primary-hover); }
.content-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
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
  padding: 9px 14px;
  border-bottom: 1px solid var(--border);
}
table.data-table td {
  padding: 9.5px 14px;
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
.grid-3 {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: 12px;
}
.gallery-card {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px;
  cursor: pointer;
  transition: transform 0.1s;
}
.gallery-card:hover { transform: translateY(-2px); box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
.file-box {
  padding: 16px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
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
#modal-overlay {
  display: none;
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(15, 23, 42, 0.45);
  backdrop-filter: blur(2px);
  z-index: 1000;
  align-items: center;
  justify-content: center;
}
#modal-card {
  width: 620px;
  max-width: 90vw;
  max-height: 85vh;
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
.modal-header h3 { font-size: 14px; font-weight: 700; color: #0f172a; }
.modal-close {
  font-size: 18px;
  font-weight: bold;
  color: #94a3b8;
  cursor: pointer;
  border: none;
  background: none;
}
.modal-close:hover { color: #0f172a; }
.modal-body {
  padding: 18px;
  overflow-y: auto;
  font-size: 13px;
  line-height: 1.6;
  color: #334155;
  white-space: pre-line;
  user-select: text;
}
.modal-footer {
  padding: 9px 18px;
  border-top: 1px solid var(--border);
  display: flex;
  justify-content: flex-end;
  background: #f8fafc;
}
</style>
</head>
<body>

<div id="sidebar">
  <div class="brand">
    <h1>春晖中学校园网</h1>
    <p>跨平台原生桌面客户端</p>
  </div>
  <div class="nav-menu">
    <div class="nav-item active" data-tab="inbox" onclick="switchTab('inbox')"><span class="nav-icon">📬</span>个人信件 (收件箱)</div>
    <div class="nav-item" data-tab="news" onclick="switchTab('news')"><span class="nav-icon">📢</span>校园通知与公告</div>
    <div class="nav-item" data-tab="hygiene" onclick="switchTab('hygiene')"><span class="nav-icon">🧹</span>常规卫生考评</div>
    <div class="nav-item" data-tab="dorm" onclick="switchTab('dorm')"><span class="nav-icon">🛏️</span>寝室纪律内务</div>
    <div class="nav-item" data-tab="duty" onclick="switchTab('duty')"><span class="nav-icon">🛡️</span>行政值周小结</div>
    <div class="nav-item" data-tab="lostfound" onclick="switchTab('lostfound')"><span class="nav-icon">🎒</span>失物招领中心</div>
    <div class="nav-item" data-tab="filestation" onclick="switchTab('filestation')"><span class="nav-icon">📦</span>校内文件寄取处</div>
    <div class="nav-item" data-tab="gallery" onclick="switchTab('gallery')"><span class="nav-icon">🖼️</span>校园巡查现场图库</div>
    <div class="nav-item" data-tab="streams" onclick="switchTab('streams')"><span class="nav-icon">📹</span>监控与视讯直播</div>
    <div class="nav-item" data-tab="settings" onclick="switchTab('settings')"><span class="nav-icon">⚙️</span>网络与连接状态</div>
  </div>
  <div class="sidebar-footer">
    <span>chunhui-gui v1.2.1</span>
  </div>
</div>

<div id="main-content">
  <header>
    <div class="header-left">
      <div class="page-title" id="current-title">个人信件 (收件箱)</div>
      <div id="network-badge" class="status-pill offline">
        <span class="status-dot"></span>
        <span id="network-text">离线演示模式 (校外网络未连接)</span>
      </div>
    </div>
    <div class="header-right">
      <button class="btn" onclick="checkNetwork(true)">🔄 重新检测</button>
    </div>
  </header>

  <div class="content-body">
    <!-- 1. 收件箱 -->
    <div id="tab-inbox" class="tab-pane active">
      <div class="toolbar">
        <input type="text" class="search-input" placeholder="搜索信件标题、发件人..." oninput="filterTable('inbox-table', this.value)">
      </div>
      <div class="card">
        <table class="data-table" id="inbox-table">
          <thead>
            <tr>
              <th style="width: 75px;">编号</th>
              <th>标题</th>
              <th style="width: 110px;">发件部门</th>
              <th style="width: 140px;">发送时间</th>
              <th style="width: 80px;">状态</th>
            </tr>
          </thead>
          <tbody id="inbox-rows"></tbody>
        </table>
      </div>
    </div>

    <!-- 2. 校园公告 -->
    <div id="tab-news" class="tab-pane">
      <div class="toolbar">
        <select class="form-control" style="width: 150px; padding: 5px 8px;" onchange="loadNews(this.value)">
          <option value="84">高一年级 (84)</option>
          <option value="85">高二年级 (85)</option>
          <option value="94">校务公开 (94)</option>
          <option value="100">行政值周 (100)</option>
        </select>
        <input type="text" class="search-input" placeholder="筛选通知公告..." oninput="filterTable('news-table', this.value)">
      </div>
      <div class="card">
        <table class="data-table" id="news-table">
          <thead>
            <tr>
              <th style="width: 75px;">ID</th>
              <th>通知标题</th>
              <th style="width: 120px;">发布部门</th>
              <th style="width: 120px;">发布日期</th>
            </tr>
          </thead>
          <tbody id="news-rows"></tbody>
        </table>
      </div>
    </div>

    <!-- 3. 卫生考评 -->
    <div id="tab-hygiene" class="tab-pane">
      <div class="toolbar">
        <input type="text" class="search-input" placeholder="搜索班级、扣分原因..." oninput="filterTable('hygiene-table', this.value)">
      </div>
      <div class="card">
        <table class="data-table" id="hygiene-table">
          <thead>
            <tr>
              <th style="width: 130px;">班级名称</th>
              <th style="width: 90px;">扣分</th>
              <th>考评原因与扣分项目</th>
              <th style="width: 120px;">检查人员</th>
              <th style="width: 110px;">检查日期</th>
            </tr>
          </thead>
          <tbody id="hygiene-rows"></tbody>
        </table>
      </div>
    </div>

    <!-- 4. 寝室纪律 -->
    <div id="tab-dorm" class="tab-pane">
      <div class="toolbar">
        <input type="text" class="search-input" placeholder="搜索寝室楼栋、违纪说明..." oninput="filterTable('dorm-table', this.value)">
      </div>
      <div class="card">
        <table class="data-table" id="dorm-table">
          <thead>
            <tr>
              <th style="width: 160px;">楼栋及寝室</th>
              <th style="width: 90px;">扣分</th>
              <th>考评扣分说明</th>
              <th style="width: 120px;">宿管/人员</th>
              <th style="width: 110px;">日期</th>
            </tr>
          </thead>
          <tbody id="dorm-rows"></tbody>
        </table>
      </div>
    </div>

    <!-- 5. 行政值周 -->
    <div id="tab-duty" class="tab-pane">
      <div class="card">
        <table class="data-table">
          <thead>
            <tr>
              <th style="width: 90px;">周次</th>
              <th style="width: 140px;">值周组长</th>
              <th style="width: 180px;">值周教师</th>
              <th>核心巡防重点</th>
              <th style="width: 80px;">状态</th>
            </tr>
          </thead>
          <tbody id="duty-rows"></tbody>
        </table>
      </div>
    </div>

    <!-- 6. 失物招领 -->
    <div id="tab-lostfound" class="tab-pane">
      <div class="toolbar">
        <input type="text" class="search-input" placeholder="搜索失物、捡拾地点..." oninput="filterTable('lostfound-table', this.value)">
      </div>
      <div class="card">
        <table class="data-table" id="lostfound-table">
          <thead>
            <tr>
              <th style="width: 100px;">登记编号</th>
              <th>物品名称</th>
              <th style="width: 100px;">类别</th>
              <th style="width: 160px;">捡拾地点</th>
              <th style="width: 100px;">登记日期</th>
              <th style="width: 80px;">状态</th>
              <th style="width: 110px;">认领联系</th>
            </tr>
          </thead>
          <tbody id="lostfound-rows"></tbody>
        </table>
      </div>
    </div>

    <!-- 7. 文件寄取 -->
    <div id="tab-filestation" class="tab-pane">
      <div class="grid-2">
        <div class="file-box">
          <h3 style="margin-bottom: 10px; font-size: 14px;">📥 存文件 (上传寄件)</h3>
          <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 12px;">符合 100MB 逻辑分片上传规范，自动生成 6 位提取凭证。</p>
          <div class="form-group">
            <label>文件备注/说明</label>
            <input type="text" id="upload-desc" class="form-control" placeholder="如：高一期末复习重点讲义">
          </div>
          <div class="form-group">
            <label>选择文件 (模拟)</label>
            <input type="file" id="upload-file" class="form-control">
          </div>
          <button class="btn btn-primary" onclick="handleDeposit()">生成 6 位提取密码</button>
          <div id="deposit-result" style="margin-top: 12px; font-size: 12.5px; display:none;"></div>
        </div>

        <div class="file-box">
          <h3 style="margin-bottom: 10px; font-size: 14px;">📤 取文件 (凭码提取)</h3>
          <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 12px;">输入 6 位取件密码提取文件。</p>
          <div class="form-group">
            <label>6 位数字取件密码</label>
            <input type="text" id="retrieve-code" class="form-control" placeholder="例如：839102" maxlength="6">
          </div>
          <button class="btn btn-primary" onclick="handleRetrieve()">验证并提取文件</button>
          <div id="retrieve-result" style="margin-top: 12px; font-size: 12.5px; display:none;"></div>
        </div>
      </div>
    </div>

    <!-- 8. 现场图库 -->
    <div id="tab-gallery" class="tab-pane">
      <div class="grid-3" id="gallery-container"></div>
    </div>

    <!-- 9. 监控直播 -->
    <div id="tab-streams" class="tab-pane">
      <div class="grid-2" id="streams-container"></div>
    </div>

    <!-- 10. 设置与状态 -->
    <div id="tab-settings" class="tab-pane">
      <div class="card" style="padding: 16px;">
        <h3 style="margin-bottom: 10px; font-size: 14px;">校园网环境与通信配置</h3>
        <p style="font-size: 12.5px; color: var(--text-muted); line-height: 1.8;">
          校园网核心地址：<strong>http://10.181.200.3</strong><br>
          群晖文件服务端口：<strong>http://10.181.201.188:5000</strong><br>
          当前环境状态：<span id="settings-status-text">离线演示模式 (校外网络未连接)</span>
        </p>
        <div style="margin-top: 14px;">
          <button class="btn btn-primary" onclick="checkNetwork(true)">重新检测内网连接</button>
        </div>
      </div>
    </div>

  </div>
</div>

<!-- 详情弹窗 -->
<div id="modal-overlay" onclick="closeModal(event)">
  <div id="modal-card">
    <div class="modal-header">
      <h3 id="modal-title">详情查看</h3>
      <button class="modal-close" onclick="closeModal()">&times;</button>
    </div>
    <div class="modal-body" id="modal-content"></div>
    <div class="modal-footer">
      <button class="btn" onclick="closeModal()">关闭</button>
    </div>
  </div>
</div>

<script>
const titles = {
  'inbox': '个人信件 (收件箱)',
  'news': '校园通知与公告',
  'hygiene': '常规卫生考评',
  'dorm': '寝室纪律内务',
  'duty': '行政值周小结',
  'lostfound': '失物招领中心',
  'filestation': '校内文件寄取处',
  'gallery': '校园巡查现场图库',
  'streams': '监控与视讯直播',
  'settings': '网络与连接状态'
};

function switchTab(tabId) {
  document.querySelectorAll('.tab-pane').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  
  const target = document.getElementById('tab-' + tabId);
  if (target) target.classList.add('active');
  
  const navItem = document.querySelector(`.nav-item[data-tab="${tabId}"]`);
  if (navItem) navItem.classList.add('active');

  document.getElementById('current-title').innerText = titles[tabId] || '春晖中学校园网';
}

function filterTable(tableId, query) {
  const q = query.trim().toLowerCase();
  const rows = document.querySelectorAll('#' + tableId + ' tbody tr');
  rows.forEach(row => {
    row.style.display = row.innerText.toLowerCase().includes(q) ? '' : 'none';
  });
}

function openModal(title, content) {
  document.getElementById('modal-title').innerText = title;
  document.getElementById('modal-content').innerText = content;
  document.getElementById('modal-overlay').style.display = 'flex';
}

function closeModal(e) {
  if (!e || e.target === document.getElementById('modal-overlay') || e.target.classList.contains('modal-close') || e.target.innerText === '关闭') {
    document.getElementById('modal-overlay').style.display = 'none';
  }
}

async function checkNetwork(force) {
  try {
    const data = await window.pywebview.api.get_status(force);
    const badge = document.getElementById('network-badge');
    const text = document.getElementById('network-text');
    const settingsText = document.getElementById('settings-status-text');
    
    if (data.is_online) {
      badge.className = 'status-pill online';
      text.innerText = '校园内网已连接 (在线)';
      settingsText.innerHTML = '<strong style="color:#047857">已连入校园内网 10.181.200.3，当前为实时模式。</strong>';
    } else {
      badge.className = 'status-pill offline';
      text.innerText = '离线演示模式 (校外网络未连接)';
      settingsText.innerHTML = '<strong style="color:#b45309">未检测到校园内网 10.181.200.3，当前为离线全功能演示。</strong>';
    }
  } catch (err) {
    console.error(err);
  }
}

function renderInbox(data) {
  const tbody = document.getElementById('inbox-rows');
  tbody.innerHTML = '';
  (data || []).forEach(msg => {
    const tr = document.createElement('tr');
    tr.onclick = () => openModal(msg.title, `发件部门：${msg.sender}\\n发送时间：${msg.time}\\n收件人：${msg.recipients_all}\\n\\n${msg.content}`);
    tr.innerHTML = `
      <td><span class="tag tag-gray">${msg.id}</span></td>
      <td><strong>${msg.title}</strong></td>
      <td>${msg.sender}</td>
      <td style="color:#64748b">${msg.time}</td>
      <td>${msg.unread ? '<span class="tag tag-red">未读</span>' : '<span class="tag tag-green">已读</span>'}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderNews(data) {
  const tbody = document.getElementById('news-rows');
  tbody.innerHTML = '';
  (data || []).forEach(item => {
    const tr = document.createElement('tr');
    tr.onclick = () => openModal(item.title, `发布部门：${item.dept}\\n发布日期：${item.time}\\n\\n${item.content}`);
    tr.innerHTML = `
      <td><span class="tag tag-gray">${item.id}</span></td>
      <td><strong>${item.title}</strong></td>
      <td>${item.dept}</td>
      <td style="color:#64748b">${item.time}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderHygiene(data) {
  const tbody = document.getElementById('hygiene-rows');
  tbody.innerHTML = '';
  (data || []).forEach(item => {
    const isZero = item.deduct && item.deduct.startsWith('0');
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong>${item.class}</strong></td>
      <td><span class="tag ${isZero ? 'tag-green' : 'tag-red'}">${item.deduct}</span></td>
      <td>${item.reason}</td>
      <td>${item.inspector}</td>
      <td style="color:#64748b">${item.date}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderDorm(data) {
  const tbody = document.getElementById('dorm-rows');
  tbody.innerHTML = '';
  (data || []).forEach(item => {
    const isZero = item.deduct && item.deduct.startsWith('0');
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong>${item.room}</strong></td>
      <td><span class="tag ${isZero ? 'tag-green' : 'tag-red'}">${item.deduct}</span></td>
      <td>${item.reason}</td>
      <td>${item.inspector}</td>
      <td style="color:#64748b">${item.date}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderDuty(data) {
  const tbody = document.getElementById('duty-rows');
  tbody.innerHTML = '';
  (data || []).forEach(item => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong>${item.week}</strong></td>
      <td>${item.leader}</td>
      <td>${item.teachers}</td>
      <td>${item.focus}</td>
      <td><span class="tag ${item.status === '进行中' ? 'tag-blue' : 'tag-gray'}">${item.status}</span></td>
    `;
    tbody.appendChild(tr);
  });
}

function renderLostfound(data) {
  const tbody = document.getElementById('lostfound-rows');
  tbody.innerHTML = '';
  (data || []).forEach(item => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><span class="tag tag-gray">${item.id}</span></td>
      <td><strong>${item.name}</strong></td>
      <td><span class="tag tag-blue">${item.category}</span></td>
      <td>${item.place}</td>
      <td style="color:#64748b">${item.time}</td>
      <td><span class="tag ${item.status === '待认领' ? 'tag-red' : 'tag-green'}">${item.status}</span></td>
      <td>${item.contact}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderGallery(data) {
  const box = document.getElementById('gallery-container');
  box.innerHTML = '';
  (data || []).forEach(g => {
    const card = document.createElement('div');
    card.className = 'gallery-card';
    card.onclick = () => openModal(g.title, `相册分类：${g.category}\\n照片数量：${g.count} 张\\n\\n说明：${g.desc}`);
    card.innerHTML = `
      <div style="font-size: 24px; margin-bottom: 6px;">📷</div>
      <div style="font-weight: 700; font-size: 13px; margin-bottom: 4px;">${g.title}</div>
      <div style="font-size: 11.5px; color: #64748b; margin-bottom: 6px;">${g.category} · 共 ${g.count} 张</div>
      <p style="font-size: 11.5px; color: #475569; line-height: 1.5;">${g.desc}</p>
    `;
    box.appendChild(card);
  });
}

function renderStreams(data) {
  const box = document.getElementById('streams-container');
  box.innerHTML = '';
  (data || []).forEach(s => {
    const card = document.createElement('div');
    card.className = 'file-box';
    card.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 8px;">
        <h4 style="font-size:13px; font-weight:600;">${s.name}</h4>
        <span class="tag tag-green">${s.status}</span>
      </div>
      <div style="background:#0f172a; border-radius:6px; height:90px; display:flex; align-items:center; justify-content:center; color:#94a3b8; font-size:11.5px; margin-bottom:8px;">
        📡 实时内网视讯流信号源 (${s.resolution})
      </div>
      <div style="font-size:11px; color:#64748b; font-family:monospace; word-break:break-all;">${s.url}</div>
    `;
    box.appendChild(card);
  });
}

async function loadInbox() {
  try {
    const data = await window.pywebview.api.get_messages();
    renderInbox(data);
  } catch (e) { console.error(e); }
}

async function loadNews(catalog) {
  try {
    const data = await window.pywebview.api.get_news(catalog || '84');
    renderNews(data);
  } catch (e) { console.error(e); }
}

async function loadHygiene() {
  try {
    const data = await window.pywebview.api.get_hygiene();
    renderHygiene(data);
  } catch (e) { console.error(e); }
}

async function loadDorm() {
  try {
    const data = await window.pywebview.api.get_dorm();
    renderDorm(data);
  } catch (e) { console.error(e); }
}

async function loadDuty() {
  try {
    const data = await window.pywebview.api.get_duty();
    renderDuty(data);
  } catch (e) { console.error(e); }
}

async function loadLostfound() {
  try {
    const data = await window.pywebview.api.get_lostfound();
    renderLostfound(data);
  } catch (e) { console.error(e); }
}

async function loadGallery() {
  try {
    const data = await window.pywebview.api.get_gallery();
    renderGallery(data);
  } catch (e) { console.error(e); }
}

async function loadStreams() {
  try {
    const data = await window.pywebview.api.get_streams();
    renderStreams(data);
  } catch (e) { console.error(e); }
}

async function handleDeposit() {
  const desc = document.getElementById('upload-desc').value.trim();
  const fileInput = document.getElementById('upload-file');
  const filename = fileInput.files.length > 0 ? fileInput.files[0].name : '';
  const res = await window.pywebview.api.deposit_file(desc, filename);
  const resBox = document.getElementById('deposit-result');
  resBox.style.display = 'block';
  resBox.innerHTML = `
    <div style="background: #f0fdf4; border: 1px solid #bbf7d0; padding: 12px; border-radius: 6px;">
      <div style="color: #15803d; font-weight: bold; margin-bottom: 4px;">✅ 寄件上传凭证就绪 (模拟)</div>
      <div>文件名：<strong>${res.filename}</strong></div>
      <div>文件说明：${res.desc}</div>
      <div style="margin-top: 6px; font-size: 13px;">6 位提取密码：<strong style="color: #1d4ed8; font-size: 16px; letter-spacing: 2px;">${res.code}</strong></div>
      <div style="font-size: 11px; color: #64748b; margin-top: 3px;">凭此提取码可在校园内网提取文件。</div>
    </div>
  `;
}

async function handleRetrieve() {
  const code = document.getElementById('retrieve-code').value.trim();
  const res = await window.pywebview.api.retrieve_file(code);
  const resBox = document.getElementById('retrieve-result');
  resBox.style.display = 'block';
  if (!res.success) {
    resBox.innerHTML = `<div style="color:#dc2626; background:#fef2f2; padding:10px; border-radius:6px;">⚠️ ${res.error}</div>`;
    return;
  }
  resBox.innerHTML = `
    <div style="background: #eff6ff; border: 1px solid #bfdbfe; padding: 12px; border-radius: 6px;">
      <div style="color: #1d4ed8; font-weight: bold; margin-bottom: 4px;">📦 匹配到提取文件</div>
      <div>文件名：<strong>${res.filename}</strong></div>
      <div>文件大小：${res.size}</div>
      <div>寄存时间：${res.time} · 有效期至 ${res.expiry}</div>
      <button class="btn btn-primary" style="margin-top: 8px;" onclick="alert('离线演示模式：模拟文件已下载到本地。')">立即下载保存</button>
    </div>
  `;
}

let appInitialized = false;
async function initApp() {
  if (appInitialized) return;
  appInitialized = true;
  try {
    const all = await window.pywebview.api.get_all_data();
    if (all) {
      if (all.inbox) renderInbox(all.inbox);
      if (all.news) renderNews(all.news);
      if (all.hygiene) renderHygiene(all.hygiene);
      if (all.dorm) renderDorm(all.dorm);
      if (all.duty) renderDuty(all.duty);
      if (all.lostfound) renderLostfound(all.lostfound);
      if (all.gallery) renderGallery(all.gallery);
      if (all.streams) renderStreams(all.streams);
    }
  } catch (e) {
    console.error('initApp failed:', e);
  }
  setTimeout(() => checkNetwork(false), 80);
}

if (window.pywebview && window.pywebview.api) {
  initApp();
} else {
  window.addEventListener('pywebviewready', initApp);
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
        width=1080,
        height=720,
        min_size=(860, 560)
    )
    webview.start()

if __name__ == "__main__":
    main()
