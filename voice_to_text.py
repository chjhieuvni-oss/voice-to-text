# -*- coding: utf-8 -*-
"""
Voice-To-Text Toolbar (Upgraded Version)
Features:
1. Single Mic button (🎤/●): listens, recognizes speech, normalizes Vietnamese text, copies to clipboard only.
2. Always-on-top: root.attributes('-topmost', True) + Windows API SetWindowPos(HWND_TOPMOST) periodic re-assertion.
3. Buttons: [Mic] [■ Stop] [A] [C] [V] [↵] [▲] [▼] [Status]
   - A: focuses target window, presses Ctrl+A (select all)
   - C: focuses target window, presses Ctrl+C (copy)
   - V: focuses target window, presses Ctrl+V (paste)
   - ↵: focuses target window, presses Enter (send message / submit input)
   - ▲: lăn chuột lên (scroll wheel up, cuộn trang/chat lên)
   - ▼: lăn chuột xuống (scroll wheel down, cuộn trang/chat xuống)
   - UI Scale: cấu hình kích thước giao diện tùy biến (x1, x2.5, x5.0 gấp đôi, x7.5 gấp ba) trong Settings.
4. Global Hotkeys (Phím tắt toàn hệ thống):
   - Ctrl+L: Bật / Tắt Mic thu âm (tự động nhận diện và copy vào clipboard)
   - Ctrl+S: Dừng / Hủy thu âm hoặc dừng task (Shift+F5 / Ctrl+F5)
5. Fast & Accurate Voice-to-Text:
   - Non-blocking initial calibration (calibrates in background, zero delay on mic click)
   - Snappy silence cut-off: pause_threshold=0.75s (instead of 2.0s)
   - Rich Vietnamese speech normalization (punctuation, coding & prompt keywords)
6. Click-to-Finish & Auto Paste + Enter:
   - Khi đang nói/ghi âm, click chuột trái vào đâu sẽ lập tức dừng thu, chuyển sang text, dán và nhấn Enter cách nhau 0.3s.
"""

import ctypes
from ctypes import wintypes
import json
import os
import re
import subprocess
import sys

# High-DPI Awareness for crisp rendering on 125%, 150%, 200% displays
def init_windows_dpi():
    if sys.platform != 'win32':
        return 1.0
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return max(1.0, dpi / 96.0)
    except Exception:
        return 1.0

DPI_SCALE = init_windows_dpi()

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

# Prevent crash under pythonw and log unhandled exceptions
LOG_ERR_PATH = os.path.join(get_base_dir(), "app_stderr.log")
if sys.stdout is None:
    sys.stdout = open(LOG_ERR_PATH, 'a', encoding='utf-8')
if sys.stderr is None:
    sys.stderr = open(LOG_ERR_PATH, 'a', encoding='utf-8')

import threading
import time
import tkinter as tk
from tkinter import messagebox
import urllib.request
import urllib.parse
import urllib.error
import webbrowser

import pyautogui
import pyperclip
import speech_recognition as sr
from PIL import Image, ImageDraw, ImageTk
import winsound

try:
    import numpy as np
except ImportError:
    np = None

try:
    import sounddevice as sd
except ImportError:
    sd = None

try:
    import sherpa_onnx
except ImportError:
    sherpa_onnx = None


def get_sherpa_model_paths():
    candidates = []
    if hasattr(sys, '_MEIPASS'):
        candidates.append(os.path.join(sys._MEIPASS, "models", "sherpa-onnx-zipformer-vi-30M-int8-2026-02-09"))
    candidates.append(os.path.join(get_base_dir(), "models", "sherpa-onnx-zipformer-vi-30M-int8-2026-02-09"))
    candidates.append(r"D:\Setup\voice to text\models\sherpa-onnx-zipformer-vi-30M-int8-2026-02-09")

    for model_dir in candidates:
        encoder = os.path.join(model_dir, "encoder.int8.onnx")
        decoder = os.path.join(model_dir, "decoder.onnx")
        joiner = os.path.join(model_dir, "joiner.int8.onnx")
        tokens = os.path.join(model_dir, "tokens.txt")
        if os.path.exists(encoder) and os.path.exists(tokens):
            return {
                "encoder": encoder,
                "decoder": decoder,
                "joiner": joiner,
                "tokens": tokens,
            }
    return None



# Constants
APP_VERSION = "2.1.4"
GITHUB_REPO = "chjhieuvni-oss/voice-to-text"
DEFAULT_UPDATE_MANIFEST_URL = ""
DEFAULT_GEMINI_API_KEY = "AIzaSyAUeSFBzrFz0EUPFLZXLNW5IL6VJ26Zfnk"
CLICK_X = 1066
CLICK_Y = 1012
DEFAULT_WINDOW_X = 1501
DEFAULT_WINDOW_Y = 1128
LANG = "vi-VN"
ICON_FILE = r"icons\voice_to_text.ico"
APP_USER_MODEL_ID = "AutomationFaire.VoiceToText"
UI_SCALE = 2.5  # Phóng to x2.5 kích thước toàn bộ thanh công cụ

MIC_IDLE_ICON = "🎤"
MIC_ACTIVE_ICON = "●"
STOP_ICON = "■"

VI_DIACRITICS = re.compile(r'[àáảãạăắằẳẵặâấầẩẫậđèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵ]', re.IGNORECASE)

COMMON_VI_WORDS = {
    'và', 'là', 'của', 'cho', 'các', 'những', 'có', 'không', 'được', 'trong',
    'với', 'người', 'một', 'hai', 'ba', 'bốn', 'này', 'đó', 'tôi', 'bạn',
    'anh', 'em', 'chị', 'làm', 'xem', 'hộ', 'giúp', 'tạo', 'viết', 'kiểm',
    'tra', 'thử', 'áo', 'quần', 'hình', 'ảnh', 'màu', 'sắc', 'vào', 'ra',
    'đến', 'ở', 'thì', 'mà', 'đã', 'sẽ', 'đang', 'nhé', 'nha', 'chút',
    'cái', 'thế', 'nào', 'gì', 'sao', 'mẫu', 'chọn', 'bật', 'tắt', 'thun',
    'lại', 'về', 'này', 'đây', 'đó', 'kia', 'rồi', 'chưa', 'hãy', 'đang'
}

VN_SPEECH_REPLACEMENTS = (
    # Punctuation & Symbols
    (' dấu chấm hỏi ', ' ? '),
    (' dấu chấm than ', ' ! '),
    (' dấu chấm phẩy ', ' ; '),
    (' dấu hai chấm ', ' : '),
    (' dấu chấm ', ' . '),
    (' dấu phẩy ', ' , '),
    (' dấu bằng ', ' = '),
    (' dấu cộng ', ' + '),
    (' dấu trừ ', ' - '),
    (' dấu nhân ', ' * '),
    (' dấu chia ', ' / '),
    (' chấm hỏi ', ' ? '),
    (' chấm than ', ' ! '),
    (' chấm phẩy ', ' ; '),
    (' hai chấm ', ' : '),
    (' chấm ', ' . '),
    (' phẩy ', ' , '),
    (' xuống dòng ', ' \n '),
    (' dòng mới ', ' \n '),
    (' khoảng trắng ', ' '),
    (' mở ngoặc tròn ', ' ( '),
    (' đóng ngoặc tròn ', ' ) '),
    (' mở ngoặc vuông ', ' [ '),
    (' đóng ngoặc vuông ', ' ] '),
    (' mở ngoặc nhọn ', ' { '),
    (' đóng ngoặc nhọn ', ' } '),
    (' mở ngoặc ', ' ( '),
    (' đóng ngoặc ', ' ) '),
    (' ngoặc kép ', ' " '),
    (' gạch dưới ', '_'),
    (' gạch ngang ', '-'),

    # POD / Design / Apparel / Graphics
    (' móc úp ', ' mockup '),
    (' mốc úp ', ' mockup '),
    (' móc cúp ', ' mockup '),
    (' móp cúp ', ' mockup '),
    (' mác cúp ', ' mockup '),
    (' mắc cúp ', ' mockup '),
    (' mốc cúp ', ' mockup '),
    (' móp úp ', ' mockup '),
    (' mock up ', ' mockup '),
    (' mock-up ', ' mockup '),
    (' đi dai ', ' design '),
    (' đì zai ', ' design '),
    (' đi sai ', ' design '),
    (' đì sai ', ' design '),
    (' đi day ', ' design '),
    (' de sign ', ' design '),
    (' pờ rôm phờ ', ' prompt '),
    (' pờ rôm ', ' prompt '),
    (' promp ', ' prompt '),
    (' bờ rôm ', ' prompt '),
    (' vin tít ', ' vintage '),
    (' vin tịt ', ' vintage '),
    (' văn tít ', ' vintage '),
    (' văn tịt ', ' vintage '),
    (' vin tết ', ' vintage '),
    (' bút lếch ', ' bootleg '),
    (' bút lết ', ' bootleg '),
    (' bút léc ', ' bootleg '),
    (' bút lếg ', ' bootleg '),
    (' boot leg ', ' bootleg '),
    (' ti sớt ', ' t-shirt '),
    (' ti shirt ', ' t-shirt '),
    (' t shirt ', ' t-shirt '),
    (' tee shirt ', ' t-shirt '),
    (' ráp ti ', ' rap tee '),
    (' hu đi ', ' hoodie '),
    (' hu đy ', ' hoodie '),
    (' xoét tơ ', ' sweater '),
    (' xoét sớt ', ' sweatshirt '),
    (' véc tơ ', ' vector '),
    (' vét tơ ', ' vector '),
    (' ben nơ ', ' banner '),
    (' ban nơ ', ' banner '),
    (' lây ơ ', ' layer '),
    (' lay ơ ', ' layer '),
    (' ren đơ ', ' render '),
    (' ren đờ ', ' render '),
    (' xì tai ', ' style '),
    (' xì tay ', ' style '),
    (' cờ rốp ', ' crop '),
    (' cờ ráp ', ' crop '),
    (' xờ keo ', ' scale '),
    (' sờ keo ', ' scale '),
    (' phông chữ ', ' font '),
    (' phông ', ' font '),
    (' phoong ', ' font '),
    (' lô gô ', ' logo '),
    (' ai con ', ' icon '),
    (' com bo ', ' combo '),
    (' côm bô ', ' combo '),
    (' bờ ríp ', ' brief '),
    (' háp tôn ', ' halftone '),
    (' xờ cơ rin prin ', ' screenprint '),
    (' xờ cơ rin ', ' screen '),
    (' mô nô crôm ', ' monochrome '),
    (' gờ ray xờ keo ', ' grayscale '),
    (' gờ rây xờ keo ', ' grayscale '),
    (' bách đờ ráp ', ' backdrop '),
    (' bách ráp ', ' backdrop '),
    (' bách grao ', ' background '),
    (' bách ground ', ' background '),
    (' bác ground ', ' background '),
    (' mô đen ', ' model '),
    (' mô đần ', ' model '),
    (' sa đâu ', ' shadow '),
    (' lai tinh ', ' lighting '),
    (' co lo ', ' color '),
    (' co lơ ', ' color '),
    (' bờ lách ', ' black '),
    (' pích xeo ', ' pixel '),
    (' pích seo ', ' pixel '),
    (' đi teo ', ' detail '),
    (' đi theo ', ' detail '),
    (' tếch chờ ', ' texture '),
    (' con trát ', ' contrast '),

    # Platforms & Commerce
    (' ét xi ', ' Etsy '),
    (' et si ', ' Etsy '),
    (' ét ti ', ' Etsy '),
    (' éc si ', ' Etsy '),
    (' pi ô đi ', ' POD '),
    (' pót ', ' POD '),
    (' en ép eo ', ' NFL '),
    (' en ef el ', ' NFL '),
    (' en nét eo ', ' NFL '),
    (' sóp pi phai ', ' Shopify '),
    (' xốp pi phai ', ' Shopify '),
    (' lít ting ', ' listing '),
    (' lít tinh ', ' listing '),
    (' ki guốc ', ' keyword '),
    (' ki uốc ', ' keyword '),
    (' ki wọt ', ' keyword '),
    (' nít ', ' niche '),
    (' ních ', ' niche '),
    (' tren đinh ', ' trending '),
    (' tren ', ' trend '),
    (' chen ', ' trend '),
    (' sêu ', ' sales '),
    (' seo ', ' sales '),
    (' ranh ', ' rank '),
    (' renk ', ' rank '),
    (' ri viu ', ' review '),
    (' phít bách ', ' feedback '),

    # Programming & Tech terms
    (' phăng sần ', ' function '),
    (' phăng son ', ' function '),
    (' phăng xơn ', ' function '),
    (' phăng xần ', ' function '),
    (' ríp tơn ', ' return '),
    (' ríp tớn ', ' return '),
    (' rít tơn ', ' return '),
    (' rí tơn ', ' return '),
    (' im pót ', ' import '),
    (' im port ', ' import '),
    (' in pót ', ' import '),
    (' phờ rom ', ' from '),
    (' phờ rôm ', ' from '),
    (' xờ tring ', ' string '),
    (' xờ chinh ', ' string '),
    (' cờ lát ', ' class '),
    (' cờ lass ', ' class '),
    (' ô bê chờ ', ' object '),
    (' prin tờ ', ' print '),
    (' ai đi ', ' ID '),
    (' u rờ eo ', ' URL '),
    (' i pi y ', ' API '),
    (' ây pi ai ', ' API '),
    (' jay sần ', ' JSON '),
    (' jay son ', ' JSON '),
    (' tru ', ' True '),
    (' phôn ', ' False '),
    (' non ', ' None '),
    (' gít ', ' git '),
    (' phích ', ' fix '),
    (' phai ', ' file '),
    (' phôn đờ ', ' folder '),
    (' cốt ', ' code '),
    (' co pi ', ' copy '),
    (' cóp bi ', ' copy '),
    (' pết ', ' paste '),
    (' pét ', ' paste '),
    (' cờ lích ', ' click '),
    (' clích ', ' click '),
    (' tun ', ' tool '),
    (' sét úp ', ' setup '),
    (' xét úp ', ' setup '),
    (' chếch ', ' check '),
    (' sếch ', ' check '),
    (' tét ', ' test '),
    (' bắc ', ' bug '),
    (' bấc ', ' bug '),
    (' linh ', ' link '),
    (' guốc phơ lâu ', ' workflow '),
    (' úp đết ', ' update '),
    (' áp đết ', ' update '),
    (' can xèo ', ' cancel '),
    (' đì lít ', ' delete '),
    (' ê đít ', ' edit '),
    (' xờ cờ ríp ', ' script '),
    (' xờ ríp ', ' script '),
    (' ây ai ', ' AI '),
    (' chát gpt ', ' ChatGPT '),
    (' chát gi pi ti ', ' ChatGPT '),
    (' mít giơ ni ', ' Midjourney '),
    (' mít zơ ni ', ' Midjourney '),
    (' cờ loát ', ' Claude '),
    (' dê mi ni ', ' Gemini '),
    (' gem mi ni ', ' Gemini '),

    # Sports
    (' dơ sì ', ' jersey '),
    (' giơ si ', ' jersey '),
    (' pờ lây ơ ', ' player '),
    (' quắt tơ bách ', ' quarterback '),
    (' rút ki ', ' rookie '),
    (' su pơ bôn ', ' Super Bowl '),
    (' su pơ bâu ', ' Super Bowl '),
)

# Lenient Phonetic & Fuzzy Patterns for English loanwords & speech corrections
FUZZY_ENGLISH_PATTERNS = [
    # Mockup & Design & Prompt & Vintage
    (r'\b(m[oóòỏõọôốồổỗộ][ck]\s*(?:[uúùủũụ]p|[aáàảãạ]p|c[aáàảãạ]p)|m[oóò]c-?up)\b', 'mockup'),
    (r'\b([dđ][iìíỉĩịêếềểễệ]\s*[zds][aàáảãạ]i(?:\s*n[oơờớởỡợ]?)?|de[- ]?sign)\b', 'design'),
    (r'\b(v[iìíỉĩị]n\s*t[iìíỉĩịeèéẻẽẹ][cttsh]?|văn\s*t[iíì]t)\b', 'vintage'),
    (r'\b([pfp][hờơớ]?[ \-]?[rld]?[oóòỏõọôốồổỗộơớờởỡợ]m(?:\s*t[eèé]?|p)?|pro?mp?t?)\b', 'prompt'),
    (r'\b([xs][iìíỉĩịờơ]?\s*t[aàáảãạ]i)\b', 'style'),
    (r'\b(t[iìí]\s*[sx][oơớờ]t|t[- ]shirt|tee[- ]shirt)\b', 't-shirt'),
    (r'\b(h[uúù][td]\s*[dđ][iìí]|hoo?die)\b', 'hoodie'),
    (r'\b(r[aáà]p\s*t[iìí]|rap\s*tee)\b', 'rap tee'),
    (r'\b(x[oôó]ét\s*t[oơớ][r]?|sweat[eè]r)\b', 'sweater'),
    (r'\b(x[oôó]ét\s*[sx][oơớ]t|sweat\s*shirt)\b', 'sweatshirt'),
    (r'\b(c[oôó]r?[oôó]p\s*t[oôó]p)\b', 'crop top'),
    (r'\b(c[aáà]t\s*a[uúù]t)\b', 'cutout'),

    # Commerce & Platforms
    (r'\b([eéè][tcxs]\s*[sxct][iìí]|ét\s*ti)\b', 'Etsy'),
    (r'\b([pb][iìí]\s*[oôó]\s*[dđ][iìí]|p[oóò]t)\b', 'POD'),
    (r'\b(en\s*[eéè]?[fn]\s*[eéè]?l|en\s*n[eéè]t\s*eo|en\s*ép\s*eo)\b', 'NFL'),
    (r'\b(c[oôó][m]\s*b[oôó])\b', 'combo'),
    (r'\b(l[iíì]t\s*t[iìí]n[gh]?)\b', 'listing'),
    (r'\b(k[iìí]\s*[gwvw]?[uùúủũụưứừửữự][oóòỏõọôốồổỗộơớờởỡợ]?[ctcksh]?)\b', 'keyword'),
    (r'\b(n[iíì][tcsh]+)\b', 'niche'),
    (r'\b(b[uúù]t\s*l[eèé][ckts]?|boot[- ]leg)\b', 'bootleg'),
    (r'\b([tc]h?r?[eèé]n(?:\s*d[iìí]n[gh]?)?)\b', 'trending'),

    # Graphics & Art
    (r'\b(g?ờ?\s*r[aàá]\s*p[h]?í[cksh]?|graph[- ]?ic)\b', 'graphic'),
    (r'\b(v[eéè][ck]\s*t[oơớ][r]?|vec[- ]?tor)\b', 'vector'),
    (r'\b(l[eêâa]y\s*[oơớ][r]?|lay[- ]?er)\b', 'layer'),
    (r'\b(t[eéè][ck]\s*c?h?[oơớ][r]?|tex[- ]?ture)\b', 'texture'),
    (r'\b(c[oô][nm]g?\s*t[r]?á[ts]?|con[- ]?trast)\b', 'contrast'),
    (r'\b(c[oô][l][oơớ][r]?|col[- ]?or)\b', 'color'),
    (r'\b(h[aáà][fp]\s*t[oôô][nm]|half[- ]?tone)\b', 'halftone'),
    (r'\b(x?ờ?\s*c?ờ?\s*r[iíì]n\s*p?ờ?\s*r[iíì]n|screen[- ]?print)\b', 'screenprint'),
    (r'\b(m[oô][nm][oô]\s*c?ờ?\s*r[oô][nm]|mono[- ]?chrome)\b', 'monochrome'),
    (r'\b(g?ờ?\s*r[eê][y|i]\s*x?ờ?\s*k[eê]o|gray[- ]?scale)\b', 'grayscale'),
    (r'\b(b[aá][ck]\s*d?ờ?\s*r[aá]p|back[- ]?drop)\b', 'backdrop'),
    (r'\b(b[aá][ck]\s*g?ờ?\s*r[aá][uù]n[d]?|back[- ]?ground)\b', 'background'),

    # Tech & AI
    (r'\b(c[oôố]t|co[- ]?de)\b', 'code'),
    (r'\b(x?ờ?\s*c?ờ?\s*r[iíì]p|sc[- ]?ript)\b', 'script'),
    (r'\b(t[uúù]n|to[- ]?ol)\b', 'tool'),
    (r'\b(t[eéè][ts]+)\b', 'test'),
    (r'\b(c?h?[eéè][ckts]+)\b', 'check'),
    (r'\b(p?h[iíì][ckts]+)\b', 'fix'),
    (r'\b(b[aắăâ]?[cấk]+)\b', 'bug'),
    (r'\b([uúá][p]\s*đ[eế]t|up[- ]?date)\b', 'update'),
    (r'\b(ch[aá]t\s*g?i?\s*p?i?\s*t[ií]|chat\s*gpt)\b', 'ChatGPT'),
    (r'\b(m[iíì]t\s*[gz][iíơ][oơ]?\s*n[ií]|mid[- ]?journey)\b', 'Midjourney'),
    (r'\b(c?ờ?\s*l[oô][aá]t|clau?de)\b', 'Claude'),
    (r'\b(d[eê]\s*m[ií]\s*n[ií]|gem[- ]?mi[- ]?ni)\b', 'Gemini'),

    # Contextual speech corrections
    (r'\bkẹo\s*mút\s*tóc\b', 'kẹo mút thay thuốc'),
    (r'\bkẹo\s*mút\s*hút\s*thuốc\b', 'kẹo mút thay thuốc'),
]


def normalize_vietnamese_speech(text: str) -> str:
    """Normalize Vietnamese speech text with smart punctuation, fuzzy English matching & keywords."""
    if not text:
        return text

    padded = f" {text.lower()} "
    padded = padded.replace('\n', ' \n ')

    # 1. Tách khoảng trắng quanh dấu câu để các từ cạnh dấu câu luôn khớp chính xác
    padded = re.sub(r'([,.;:!?\(\)\[\]\{\}\"\'\/])', r' \1 ', padded)

    # 2. Thay thế từ điển chuỗi cơ bản
    for _ in range(2):
        for src, dst in VN_SPEECH_REPLACEMENTS:
            padded = padded.replace(src, dst)

    # 3. Thay thế Regex bắt lỏng (Fuzzy / Phonetic Patterns) cho mọi biến thể tiếng Anh
    for pat, repl in FUZZY_ENGLISH_PATTERNS:
        padded = re.sub(pat, repl, padded, flags=re.IGNORECASE)

    # 4. Clean whitespace & restore proper punctuation tightness
    padded = re.sub(r'[ \t]+', ' ', padded)
    padded = re.sub(r' +([,.;:!?\)\]\}])', r'\1', padded)
    padded = re.sub(r'([\(\[\{]) +', r'\1', padded)
    padded = re.sub(r' *\n *', '\n', padded)
    res = padded.strip()

    # Capitalize first letter of sentences
    if res:
        sentences = re.split(r'([.!?\n]\s*)', res)
        capitalized = []
        cap_next = True
        for part in sentences:
            if cap_next and part and part[0].isalpha():
                part = part[0].upper() + part[1:]
                cap_next = False
            if re.search(r'[.!?\n]', part):
                cap_next = True
            capitalized.append(part)
        res = "".join(capitalized)

    return res


def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_config_candidates(base_dir):
    candidates = [
        os.path.join(base_dir, 'voice_to_text_config.json'),
        r'D:\Setup\voice to text\voice_to_text_config.json',
        r'D:\Setup\voice_to_text_config.json'
    ]
    seen = set()
    result = []
    for c in candidates:
        norm = os.path.normpath(c).lower()
        if norm not in seen:
            seen.add(norm)
            result.append(c)
    return result


def focus_vscode():
    """Focus VS Code window."""
    try:
        subprocess.run(
            ['powershell', '-Command', "$w=New-Object -ComObject wscript.shell;$w.AppActivate('Visual Studio Code')"],
            capture_output=True, timeout=2
        )
    except Exception:
        pass


def send_key_event(vk, is_up=False):
    """Sends a keyboard event with both VirtualKey and hardware ScanCode via keybd_event."""
    user32 = ctypes.windll.user32
    scan = user32.MapVirtualKeyW(vk, 0)
    flags = 0x0002 if is_up else 0  # KEYEVENTF_KEYUP
    user32.keybd_event(vk, scan, flags, 0)


def is_remote_desktop_window(hwnd):
    """Detects whether target window is a remote desktop client (RustDesk, AnyDesk, TeamViewer, RDP, etc.)."""
    if not hwnd or not ctypes.windll.user32.IsWindow(hwnd):
        return False
    user32 = ctypes.windll.user32
    cls = ctypes.create_unicode_buffer(512)
    user32.GetClassNameW(hwnd, cls, 512)
    title = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, title, 512)
    c_lower = cls.value.lower()
    t_lower = title.value.lower()
    remote_sigs = ['rustdesk', 'flutterview', 'flutter', 'anydesk', 'teamviewer', 'mstsc', 'remote desktop', 'vmware', 'virtualbox', 'ultraviewer']
    if any(sig in c_lower or sig in t_lower for sig in remote_sigs):
        return True
    try:
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value:
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            h_proc = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
            if h_proc:
                buf = ctypes.create_unicode_buffer(1024)
                size = ctypes.c_ulong(1024)
                if ctypes.windll.kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size)):
                    p_lower = buf.value.lower()
                    ctypes.windll.kernel32.CloseHandle(h_proc)
                    return any(sig in p_lower for sig in remote_sigs)
                ctypes.windll.kernel32.CloseHandle(h_proc)
    except Exception:
        pass
    return False


def force_foreground_window(hwnd):
    """Brings the target window to foreground reliably without losing or stealing input focus."""
    if not hwnd or not ctypes.windll.user32.IsWindow(hwnd):
        return False
    user32 = ctypes.windll.user32
    curr_fg = user32.GetForegroundWindow()
    # CRITICAL: If target is already the active foreground window, DO NOT touch or reset focus!
    if curr_fg == hwnd:
        return True

    my_tid = ctypes.windll.kernel32.GetCurrentThreadId()
    fg_tid = user32.GetWindowThreadProcessId(curr_fg, None) if curr_fg else 0
    target_tid = user32.GetWindowThreadProcessId(hwnd, None)

    try:
        if fg_tid and fg_tid != my_tid:
            user32.AttachThreadInput(my_tid, fg_tid, True)
        if target_tid and target_tid != my_tid:
            user32.AttachThreadInput(my_tid, target_tid, True)

        user32.BringWindowToTop(hwnd)
        user32.ShowWindow(hwnd, 5)  # SW_SHOW
        res = user32.SetForegroundWindow(hwnd)

        # For RustDesk: if child FLUTTERVIEW exists, set focus to it
        if is_remote_desktop_window(hwnd):
            child = user32.FindWindowExW(hwnd, None, "FLUTTERVIEW", None)
            if child and user32.IsWindow(child):
                user32.SetFocus(child)

        if fg_tid and fg_tid != my_tid:
            user32.AttachThreadInput(my_tid, fg_tid, False)
        if target_tid and target_tid != my_tid:
            user32.AttachThreadInput(my_tid, target_tid, False)
        return bool(res)
    except Exception:
        return False


def send_paste():
    """Simulates Ctrl+V with hardware scancodes and proper hold timings for all apps including RustDesk."""
    VK_CONTROL = 0x11
    VK_V = 0x56
    send_key_event(VK_CONTROL, is_up=False)
    time.sleep(0.02)
    send_key_event(VK_V, is_up=False)
    time.sleep(0.035)
    send_key_event(VK_V, is_up=True)
    time.sleep(0.02)
    send_key_event(VK_CONTROL, is_up=True)


def send_select_all():
    """Simulates Ctrl+A with hardware scancodes and proper hold timings for all apps including RustDesk."""
    VK_CONTROL = 0x11
    VK_A = 0x41
    send_key_event(VK_CONTROL, is_up=False)
    time.sleep(0.02)
    send_key_event(VK_A, is_up=False)
    time.sleep(0.035)
    send_key_event(VK_A, is_up=True)
    time.sleep(0.02)
    send_key_event(VK_CONTROL, is_up=True)


def send_copy():
    """Simulates Ctrl+C with hardware scancodes and proper hold timings for all apps including RustDesk."""
    VK_CONTROL = 0x11
    VK_C = 0x43
    send_key_event(VK_CONTROL, is_up=False)
    time.sleep(0.02)
    send_key_event(VK_C, is_up=False)
    time.sleep(0.035)
    send_key_event(VK_C, is_up=True)
    time.sleep(0.02)
    send_key_event(VK_CONTROL, is_up=True)


def send_enter():
    """Simulates Enter key with hardware scancode and proper hold timing for all apps including RustDesk."""
    VK_RETURN = 0x0D
    send_key_event(VK_RETURN, is_up=False)
    time.sleep(0.035)
    send_key_event(VK_RETURN, is_up=True)


def send_scroll(delta=360, target_hwnd=None, target_x=None, target_y=None):
    """Simulates authentic mouse wheel scrolling (MOUSEEVENTF_WHEEL + WM_MOUSEWHEEL)
    with cursor positioning inside target window (essential for RustDesk and Remote Desktop),
    and seamlessly restores the cursor to its previous position so toolbar buttons stay clickable."""
    user32 = ctypes.windll.user32
    MOUSEEVENTF_WHEEL = 0x0800
    WM_MOUSEWHEEL = 0x020A

    class POINT(ctypes.Structure):
        _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]

    class RECT(ctypes.Structure):
        _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long),
                    ('right', ctypes.c_long), ('bottom', ctypes.c_long)]

    # 1. Save current cursor position (over the toolbar button)
    pt_orig = POINT()
    user32.GetCursorPos(ctypes.byref(pt_orig))
    orig_x, orig_y = pt_orig.x, pt_orig.y

    # 2. Resolve target HWND
    if not target_hwnd or not user32.IsWindow(target_hwnd):
        target_hwnd = user32.GetForegroundWindow()

    # 3. Focus target window if specified
    if target_hwnd and user32.IsWindow(target_hwnd):
        force_foreground_window(target_hwnd)
        is_remote = is_remote_desktop_window(target_hwnd)
        time.sleep(0.12 if is_remote else 0.04)

    # 4. Resolve target coordinate inside target window
    if target_x is None or target_y is None:
        if target_hwnd and user32.IsWindow(target_hwnd):
            rect = RECT()
            if user32.GetWindowRect(target_hwnd, ctypes.byref(rect)):
                target_x = (rect.left + rect.right) // 2
                target_y = (rect.top + rect.bottom) // 2
            else:
                target_x, target_y = 800, 500
        else:
            target_x, target_y = 800, 500

    target_x = int(target_x)
    target_y = int(target_y)

    # 5. CRITICAL FOR RUSTDESK: Move cursor inside the remote desktop window
    # RustDesk only captures and forwards mouse wheel events when cursor is inside its canvas!
    user32.SetCursorPos(target_x, target_y)
    time.sleep(0.02)

    # 6. Fire authentic OS-level mouse wheel event via mouse_event
    # Send 3 distinct wheel notches (delta 120 each, total 360) for natural, fluid scrolling
    step = 120 if delta > 0 else -120
    notches = max(1, abs(int(delta)) // 120)
    for _ in range(notches):
        user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, step, 0)
        time.sleep(0.015)

    # 7. Dual fallback: also PostMessage WM_MOUSEWHEEL to the target / child window
    try:
        pt = POINT(target_x, target_y)
        child = user32.WindowFromPoint(pt)
        wParam = (int(delta) << 16) & 0xFFFFFFFF
        lParam = ((target_y & 0xFFFF) << 16) | (target_x & 0xFFFF)
        if child and user32.IsWindow(child):
            user32.PostMessageW(child, WM_MOUSEWHEEL, wParam, lParam)
        if target_hwnd and user32.IsWindow(target_hwnd) and target_hwnd != child:
            user32.PostMessageW(target_hwnd, WM_MOUSEWHEEL, wParam, lParam)
    except Exception:
        pass

    # 8. Restore cursor position back to the toolbar button
    # This allows the user to click repeatedly (nhấp liên tục để cuộn nhiều) without losing mouse aim!
    time.sleep(0.02)
    user32.SetCursorPos(orig_x, orig_y)


def send_up():
    """Simulates Up arrow key instantaneously without moving the mouse pointer."""
    VK_UP = 0x26
    KEYEVENTF_KEYUP = 0x0002
    user32 = ctypes.windll.user32
    user32.keybd_event(VK_UP, 0, 0, 0)
    time.sleep(0.02)
    user32.keybd_event(VK_UP, 0, KEYEVENTF_KEYUP, 0)


def send_down():
    """Simulates Down arrow key instantaneously without moving the mouse pointer."""
    VK_DOWN = 0x28
    KEYEVENTF_KEYUP = 0x0002
    user32 = ctypes.windll.user32
    user32.keybd_event(VK_DOWN, 0, 0, 0)
    time.sleep(0.02)
    user32.keybd_event(VK_DOWN, 0, KEYEVENTF_KEYUP, 0)


# ==========================================
# AUTO-UPDATE VIA GITHUB RELEASES
# ==========================================

def parse_semver(v_str: str):
    """Parses version strings like 'v2.0.1', '2.0.0', 'v2.1' into tuple (major, minor, patch)."""
    if not v_str:
        return (0, 0, 0)
    clean = str(v_str).strip().lstrip('vV').split('-')[0].split('+')[0]
    nums = []
    for part in clean.split('.'):
        try:
            nums.append(int(re.sub(r'\D', '', part) or '0'))
        except Exception:
            nums.append(0)
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums[:3])


def check_github_update(repo: str = GITHUB_REPO, current_ver: str = APP_VERSION, timeout: float = 6.0) -> dict:
    """Queries GitHub API for latest release in public repo."""
    url = f"https://api.github.com/repos/{repo.strip()}/releases/latest"
    headers = {
        "User-Agent": f"VoiceToText-App/{current_ver}",
        "Accept": "application/vnd.github.v3+json"
    }
    try:
        req = urllib.request.Request(url, headers=headers, method='GET')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode('utf-8'))
                tag = data.get("tag_name", "").strip()
                rel_name = data.get("name", tag) or tag
                body = data.get("body", "").strip()
                html_url = data.get("html_url", f"https://github.com/{repo}/releases")

                asset_url = None
                asset_name = None
                asset_size = 0
                for a in data.get("assets", []):
                    aname = a.get("name", "")
                    if aname.lower().endswith(".exe"):
                        asset_url = a.get("browser_download_url")
                        asset_name = aname
                        asset_size = a.get("size", 0)
                        break

                if not asset_url and data.get("assets"):
                    first_a = data["assets"][0]
                    asset_url = first_a.get("browser_download_url")
                    asset_name = first_a.get("name")
                    asset_size = first_a.get("size", 0)

                has_update = parse_semver(tag) > parse_semver(current_ver)
                return {
                    "has_update": has_update,
                    "latest_ver": tag,
                    "current_ver": current_ver,
                    "release_name": rel_name,
                    "body": body,
                    "html_url": html_url,
                    "download_url": asset_url,
                    "asset_name": asset_name or "voice_to_text.exe",
                    "asset_size": asset_size,
                    "error": None
                }
    except urllib.error.HTTPError as he:
        if he.code == 404:
            return {
                "has_update": False,
                "latest_ver": current_ver,
                "current_ver": current_ver,
                "release_name": "",
                "body": "",
                "html_url": f"https://github.com/{repo}/releases",
                "download_url": None,
                "asset_name": "voice_to_text.exe",
                "asset_size": 0,
                "error": None,
                "no_releases": True
            }
        return {"has_update": False, "latest_ver": current_ver, "error": f"HTTP {he.code}: {he.reason}"}
    except Exception as e:
        return {"has_update": False, "latest_ver": current_ver, "error": str(e)}


def download_update_file(url: str, dest_path: str, progress_callback=None, timeout: float = 60.0) -> bool:
    """Downloads file with chunked streaming and progress callback."""
    tmp_path = dest_path + ".tmp"
    headers = {"User-Agent": f"VoiceToText-App/{APP_VERSION}"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            total_size = int(resp.headers.get('content-length', 0))
            downloaded = 0
            block_size = 64 * 1024
            with open(tmp_path, 'wb') as out_f:
                while True:
                    chunk = resp.read(block_size)
                    if not chunk:
                        break
                    out_f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        pct = int((downloaded / total_size) * 100) if total_size > 0 else 0
                        progress_callback(downloaded, total_size, pct)
        if os.path.exists(dest_path):
            try:
                os.remove(dest_path)
            except Exception:
                pass
        os.rename(tmp_path, dest_path)
        return True
    except Exception as e:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        raise e


def launch_updater_and_restart(new_file_path: str, target_exe_path: str = None) -> bool:
    """Creates and executes detached _apply_update.bat to replace the exe and relaunch seamlessly."""
    base_dir = get_base_dir()
    if not target_exe_path:
        if getattr(sys, 'frozen', False):
            target_exe_path = sys.executable
        else:
            target_exe_path = os.path.join(base_dir, "voice_to_text.exe")

    target_exe_path = os.path.abspath(target_exe_path)
    new_file_path = os.path.abspath(new_file_path)
    backup_exe_path = os.path.abspath(os.path.join(base_dir, "voice_to_text_backup.exe"))
    bat_path = os.path.abspath(os.path.join(base_dir, "_apply_update.bat"))
    current_pid = os.getpid()

    bat_content = f"""@echo off
chcp 65001 >nul
set PID={current_pid}
set RETRIES=0

:WAIT_PID
tasklist /FI "PID eq %PID%" 2>nul | find /I "%PID%" >nul
if "%ERRORLEVEL%"=="0" (
    timeout /t 1 /nobreak >nul
    set /a RETRIES+=1
    if %RETRIES% LSS 10 goto WAIT_PID
    taskkill /F /PID %PID% >nul 2>&1
)
timeout /t 1 /nobreak >nul

if exist "{target_exe_path}" (
    copy /Y "{target_exe_path}" "{backup_exe_path}" >nul 2>&1
)

move /Y "{new_file_path}" "{target_exe_path}" >nul 2>&1
if errorlevel 1 (
    copy /Y "{new_file_path}" "{target_exe_path}" >nul 2>&1
    del /f /q "{new_file_path}" >nul 2>&1
)

start "" "{target_exe_path}"
(goto) 2>nul & del "%~f0"
"""

    with open(bat_path, 'w', encoding='utf-8') as f:
        f.write(bat_content)

    DETACHED_PROCESS = 0x00000008
    CREATE_NO_WINDOW = 0x08000000
    subprocess.Popen(
        ["cmd.exe", "/c", bat_path],
        creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
        close_fds=True,
        shell=False
    )
    return True




class CancellableStream:
    """Wraps PyAudio stream so listen() breaks immediately when stop condition is met."""
    def __init__(self, raw_stream, stop_check_fn):
        self._stream = raw_stream
        self._stop_check = stop_check_fn

    def read(self, size):
        if self._stop_check and self._stop_check():
            return b""
        return self._stream.read(size)

    def __getattr__(self, name):
        return getattr(self._stream, name)


GEMINI_SYSTEM_PROMPT = """Bạn là trợ lý AI hiệu đính tiếng Việt và tiếng Anh siêu thông minh cho phần mềm Voice-To-Text.
Người dùng đang nói bằng giọng nói tự nhiên, có thể nói tiếng Việt, tiếng Anh, hoặc chêm từ tiếng Anh (code-switching).
Bộ nhận diện âm thanh thường phiên âm từ tiếng Anh thành âm tiếng Việt hoặc nghe nhầm các từ công nghệ, lập trình, kinh doanh, POD, thương mại điện tử (Etsy, Shopify, Amazon), văn phòng.

Nhiệm vụ:
1. Nhận diện các từ tiếng Anh bị phiên âm sai hoặc nghe nhầm và khôi phục về tiếng Anh chuẩn (Ví dụ: 'phích bấc' -> 'feedback', 'chép meo' / 'chếch meo' -> 'check mail', 'cốt' -> 'code', 'sét úp' -> 'setup', 'móp cúp' -> 'mockup', 'dê mi ni' -> 'Gemini', 'ét si' -> 'Etsy', 'bút lếch' -> 'bootleg', 'ti sớt' -> 't-shirt', 'ráp ti' -> 'rap tee', 'pờ rôm' -> 'prompt').
2. Nếu người dùng nói hoàn toàn bằng tiếng Anh hoặc một cụm từ tiếng Anh, hãy sửa thành tiếng Anh chuẩn chính tả.
3. Nếu người dùng nói tiếng Việt kết hợp tiếng Anh, giữ câu văn tự nhiên, mượt mà, đúng ngữ pháp, thêm dấu câu (chấm, phẩy, hỏi) hợp lý.
4. TUYỆT ĐỐI CHỈ XUẤT RA DUY NHẤT CÂU VĂN ĐÃ SỬA. KHÔNG giải thích, KHÔNG thêm lời dẫn, KHÔNG để trong dấu ngoặc kép."""


def refine_text_with_gemini(raw_text: str, api_key: str, model: str = "gemini-2.5-flash", timeout: float = 3.5, raise_exceptions: bool = False) -> str:
    """Uses Google Gemini Flash to infer contextual meaning and correct speech errors."""
    if not api_key or not raw_text or not raw_text.strip():
        return raw_text

    clean = raw_text.strip()
    # Skip AI call for ultra-short single syllables to preserve instantaneous speed
    if len(clean.split()) <= 1 and len(clean) <= 4:
        return raw_text

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key.strip()}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": f"{GEMINI_SYSTEM_PROMPT}\n\nVăn bản cần hiệu đính:\n\"{clean}\""
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 1000,
            "thinkingConfig": {
                "thinkingBudget": 0
            }
        }
    }

    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                result = json.loads(resp.read().decode('utf-8'))
                candidates = result.get('candidates', [])
                if candidates:
                    parts = candidates[0].get('content', {}).get('parts', [])
                    if parts:
                        refined = parts[0].get('text', '').strip()
                        if (refined.startswith('"') and refined.endswith('"')) or (refined.startswith("'") and refined.endswith("'")):
                            refined = refined[1:-1].strip()
                        if refined:
                            return refined
    except Exception as e:
        if raise_exceptions:
            raise e
        pass
    return raw_text


def check_gemini_api_status(api_key: str, model: str = "gemini-2.5-flash", timeout: float = 3.5) -> bool:
    """Fast non-blocking check to verify if Gemini API key and model are active and valid."""
    if not api_key or not api_key.strip():
        return False
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model.strip()}?key={api_key.strip()}"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def set_windows_app_id():
    if sys.platform != 'win32':
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.ui_scale = UI_SCALE
        self.base_dir = get_base_dir()
        self.config_candidates = get_config_candidates(self.base_dir)
        self.config_path = self.config_candidates[0]
        self.log_path = os.path.join(self.base_dir, 'voice_to_text_mic.log')

        # Colors
        self.bg = '#1f1f1f'
        self.bg2 = '#2a2a2a'
        self.white = '#ffffff'
        self.yellow = '#FFD700'
        self.green = '#2ecc71'
        self.red = '#ff4d4d'
        self.txt = '#eaeaea'
        self.muted = '#bdbdbd'

        # State
        self.listening = False
        self.silence_timeout = 0.75  # Snappy default
        self.click_x = CLICK_X
        self.click_y = CLICK_Y
        self.window_x = DEFAULT_WINDOW_X
        self.window_y = DEFAULT_WINDOW_Y
        self.mic_index = None
        self.app_running = True
        self.last_text = ""

        # Speech Recognizer with audited performance parameters
        self.rec = sr.Recognizer()
        self.rec.energy_threshold = 280  # Nhạy hơn, bắt nhẹ nhàng không nuốt âm
        self.rec.dynamic_energy_threshold = True
        self.rec.dynamic_energy_adjustment_damping = 0.15
        self.rec.dynamic_energy_ratio = 1.3  # Bắt lỏng hơn đối với âm nhẹ/lướt
        self.rec.pause_threshold = 0.85  # Cho phép dừng nhẹ khi nói tiếng Anh
        self.rec.non_speaking_duration = 0.4
        self.rec.phrase_threshold = 0.2
        self._mic_calibrated = False

        self._speech_popup = None
        self.settings_win = None
        self.coord_var = None
        self.silence_var = None
        self._photo_cache = {}
        self.lang_mode = 'auto'
        self.use_fixed_coord = False
        self.auto_paste_enter_on_click = True
        self.paste_enter_delay = 0.3
        self.last_external_hwnd = None
        self.last_external_cursor_pos = None
        self._stop_requested = False
        self._auto_paste_enter_on_finish = False
        self._click_target_hwnd = None
        self.gemini_enabled = True
        self.gemini_api_key = DEFAULT_GEMINI_API_KEY
        self.gemini_model = "gemini-2.5-flash"
        self.dpi_scale = DPI_SCALE
        self.auto_check_update = True
        self.github_repo = GITHUB_REPO

        # Sherpa-ONNX Zipformer Vietnamese streaming engine
        self._sherpa_rec = None
        threading.Thread(target=self._init_sherpa, daemon=True).start()

        # Load persisted config
        self.load_config()

        # Window settings
        self.root.title("Voice To Text")
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', 0.8)

        self.outer = None
        self.frm = None
        self.status = None
        self.menu = None
        self._ib_state = {}
        self._current_border_color = self.yellow
        self.rebuild_toolbar()

        # Hover transparency: 80% opacity idle (hơi mờ), 95% on hover
        def _on_root_enter(e):
            try:
                self.root.attributes('-alpha', 0.95)
            except Exception:
                pass

        def _on_root_leave(e):
            try:
                px, py = self.root.winfo_pointerxy()
                rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
                rw, rh = self.root.winfo_width(), self.root.winfo_height()
                if not (rx <= px <= rx + rw and ry <= py <= ry + rh):
                    self.root.attributes('-alpha', 0.8)
            except Exception:
                pass

        self.root.bind('<Enter>', _on_root_enter)
        self.root.bind('<Leave>', _on_root_leave)

        self.root.bind('<Escape>', self.close_app)
        self.root.protocol('WM_DELETE_WINDOW', self.close_app)

        # Periodically enforce Always-On-Top
        self._keep_on_top()

        # Track external foreground window so A, C, V paste into the active window (e.g. Facebook)
        self.root.after(300, self._setup_no_activate)
        self.root.after(400, self._track_foreground_window)

        # Background calibrate mic ambient noise once (non-blocking)
        threading.Thread(target=self._initial_calibrate, daemon=True).start()

        # System-wide Global Hotkeys: Ctrl+L (Mic) and Ctrl+S (Stop)
        self._hotkey_tid = None
        self._start_global_hotkeys()

        # Check Gemini API status & set border color (Green = OK, Yellow = Disconnected/No Key)
        self.root.after(150, self.update_gemini_border_status)

        # Background check for updates via GitHub Releases
        self.root.after(3500, self._start_background_update_check)

    def rebuild_toolbar(self):
        """Constructs or reconstructs the toolbar with current self.ui_scale and all buttons."""
        self._photo_cache.clear()
        self._ib_state = {}

        if hasattr(self, 'outer') and self.outer:
            try:
                self.outer.destroy()
            except Exception:
                pass
            self.outer = None
            self.frm = None
            self.status = None

        s = self._s
        BW = s(24)
        BH = s(24)
        BR = s(5)  # Bo tròn viền góc nút
        btn_pad_y = max(2, s(1))
        outer_pad = max(1, s(1))
        H = BH + 2 * btn_pad_y + 2 * outer_pad
        BY = btn_pad_y

        btn_gap = max(2, s(1))
        x_mic = 2
        x_stop = x_mic + BW + btn_gap
        x_a = x_stop + BW + btn_gap
        x_c = x_a + BW + btn_gap
        x_v = x_c + BW + btn_gap
        x_enter = x_v + BW + btn_gap
        x_up = x_enter + BW + btn_gap
        x_down = x_up + BW + btn_gap
        status_x = x_down + BW + btn_gap + 2
        status_w = s(46)
        W = status_x + status_w + outer_pad * 2 + 2

        # Đảm bảo cửa sổ không bị tràn ra ngoài cạnh màn hình khi phóng to
        try:
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            if self.window_x + W > screen_w:
                self.window_x = max(10, screen_w - W - 20)
            if self.window_y + H > screen_h - 40:
                self.window_y = max(10, screen_h - H - 55)
        except Exception:
            pass

        self.geometry_str = f"{W}x{H}+{self.window_x}+{self.window_y}"
        self.root.geometry(self.geometry_str)

        # Outer border (giữ nguyên màu viền đang có hoặc vàng mặc định)
        border_color = getattr(self, '_current_border_color', self.yellow)
        self.outer = tk.Frame(self.root, bg=border_color)
        self.outer.pack(fill='both', expand=True)

        # Inner container with snug padding
        self.frm = tk.Frame(self.outer, bg=self.bg)
        self.frm.pack(fill='both', expand=True, padx=outer_pad, pady=outer_pad)

        border_w = max(2, s(1))  # Độ dày viền rõ nét trên nền đen

        def _make_tb_btn(tag, icon, fnt, fg, x, cmd, bg=self.bg2, hbg='#383838', border='#6e6e6e', hborder='#ffd700', hfg=None):
            self._ib_state[tag] = {
                'bg': bg, 'hbg': hbg, 'border': border, 'hborder': hborder,
                'icon': icon, 'fg': fg, 'hfg': hfg or fg, 'hover': False, 'font': fnt
            }
            c = tk.Canvas(self.frm, width=BW, height=BH, bg=self.bg, highlightthickness=0, cursor='hand2')
            c.place(x=x, y=BY)

            def redraw():
                if tag not in self._ib_state:
                    return
                st = self._ib_state[tag]
                bg_c = st['hbg'] if st['hover'] else st['bg']
                border_c = st['hborder'] if st['hover'] else st['border']
                fg_c = st['hfg'] if st['hover'] else st['fg']

                photo = self._get_btn_photo(BW, BH, BR, bg_c, border_c, border_w)
                c.delete('all')
                c.create_image(0, 0, image=photo, anchor='nw')
                c.img_ref = photo
                c.create_text(BW // 2, BH // 2, text=st['icon'], fill=fg_c, font=st['font'])

            def _enter(e):
                if tag in self._ib_state:
                    self._ib_state[tag]['hover'] = True
                    redraw()

            def _leave(e):
                if tag in self._ib_state:
                    self._ib_state[tag]['hover'] = False
                    redraw()

            def _click(e):
                cmd()

            redraw()
            c.bind('<Enter>', _enter)
            c.bind('<Leave>', _leave)
            c.bind('<Button-1>', _click)
            return redraw

        mf = self._font('Segoe UI Emoji', 9)
        sf = self._font('Segoe UI', 9, 'bold')

        # 1. Single Mic button (copies text only) - Viền xanh lá công nghệ
        self._rdraw_mic = _make_tb_btn(
            'tb_mic', MIC_IDLE_ICON, mf, self.green, x_mic, self.toggle_mic,
            bg='#223026', hbg='#2c3f32', border=self.green, hborder='#40ff88', hfg='#40ff88'
        )

        # 2. Stop button (stops recording or task) - Viền đỏ cảnh báo
        self._rdraw_stop = _make_tb_btn(
            'tb_stop', '■', sf, self.red, x_stop, self.stop_action,
            bg='#302222', hbg='#422b2b', border='#e74c3c', hborder='#ff6666', hfg='#ff6666'
        )

        # 3. 'A' button (Select All in prompt) - Viền bạc sáng rõ trên nền đen
        self._rdraw_a = _make_tb_btn(
            'tb_a', 'A', sf, self.white, x_a, self.press_a,
            bg=self.bg2, hbg='#383838', border='#6e6e6e', hborder=self.yellow, hfg=self.yellow
        )

        # 4. 'C' button (Copy) - Viền bạc sáng rõ trên nền đen
        self._rdraw_c = _make_tb_btn(
            'tb_c', 'C', sf, self.white, x_c, self.press_c,
            bg=self.bg2, hbg='#383838', border='#6e6e6e', hborder=self.yellow, hfg=self.yellow
        )

        # 5. 'V' button (Paste) - Viền bạc sáng rõ trên nền đen
        self._rdraw_v = _make_tb_btn(
            'tb_v', 'V', sf, self.white, x_v, self.press_v,
            bg=self.bg2, hbg='#383838', border='#6e6e6e', hborder=self.yellow, hfg=self.yellow
        )

        # 6. '↵' button (Enter) - Viền bạc sáng rõ trên nền đen
        self._rdraw_enter = _make_tb_btn(
            'tb_enter', '↵', sf, self.white, x_enter, self.press_enter,
            bg=self.bg2, hbg='#383838', border='#6e6e6e', hborder=self.yellow, hfg=self.yellow
        )

        # 7. '▲' button (Up arrow) - Nút Lên
        self._rdraw_up = _make_tb_btn(
            'tb_up', '▲', sf, self.white, x_up, self.press_up,
            bg=self.bg2, hbg='#383838', border='#6e6e6e', hborder=self.yellow, hfg=self.yellow
        )

        # 8. '▼' button (Down arrow) - Nút Xuống
        self._rdraw_down = _make_tb_btn(
            'tb_down', '▼', sf, self.white, x_down, self.press_down,
            bg=self.bg2, hbg='#383838', border='#6e6e6e', hborder=self.yellow, hfg=self.yellow
        )

        # 9. Status label
        status_font = self._font('Segoe UI', 10, 'bold')
        self.status = tk.Label(
            self.frm, text='Ready', font=status_font,
            bg=self.bg, fg=self.muted, anchor='center'
        )
        self.status.place(x=status_x, y=0, width=status_w, height=BH + 2 * btn_pad_y)

        # Dragging events & Context menu
        for widget in (self.root, self.outer, self.frm, self.status):
            widget.bind('<ButtonPress-1>', self._drag_start)
            widget.bind('<B1-Motion>', self._drag_move)
            widget.bind('<ButtonRelease-1>', self._drag_end)
            widget.bind('<Button-3>', self.show_context_menu)

        # Restore mic UI state if listening
        if getattr(self, 'listening', False):
            self.set_ui(True)

    def _set_border_color(self, color):
        self._current_border_color = color
        try:
            if hasattr(self, 'outer') and self.outer:
                self.outer.config(bg=color)
        except Exception:
            pass


    def update_gemini_border_status(self):
        """Asynchronously checks Gemini API health and updates outer border color:
           - Green (#2ecc71) if Gemini API is active & valid.
           - Yellow (#FFD700) if disconnected, disabled, or invalid key.
        """
        if not getattr(self, 'gemini_enabled', True) or not getattr(self, 'gemini_api_key', '').strip():
            self._set_border_color(self.yellow)
            return

        def _worker():
            key = getattr(self, 'gemini_api_key', '').strip()
            model = getattr(self, 'gemini_model', 'gemini-2.5-flash').strip()
            is_ok = check_gemini_api_status(key, model=model)
            color = self.green if is_ok else self.yellow
            try:
                self.root.after(0, lambda: self._set_border_color(color))
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def _start_global_hotkeys(self):
        """Registers system-wide global hotkeys: Ctrl+L (Mic) and Ctrl+S (Stop)."""
        def _hotkey_worker():
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            self._hotkey_tid = kernel32.GetCurrentThreadId()

            MOD_CONTROL = 0x0002
            MOD_NOREPEAT = 0x4000
            VK_L = 0x4C
            VK_S = 0x53
            HOTKEY_ID_MIC = 101
            HOTKEY_ID_STOP = 102
            WM_HOTKEY = 0x0312

            # Register Ctrl+L (Mic)
            r_mic = user32.RegisterHotKey(None, HOTKEY_ID_MIC, MOD_CONTROL | MOD_NOREPEAT, VK_L)
            if not r_mic:
                user32.RegisterHotKey(None, HOTKEY_ID_MIC, MOD_CONTROL, VK_L)

            # Register Ctrl+S (Stop)
            r_stop = user32.RegisterHotKey(None, HOTKEY_ID_STOP, MOD_CONTROL | MOD_NOREPEAT, VK_S)
            if not r_stop:
                user32.RegisterHotKey(None, HOTKEY_ID_STOP, MOD_CONTROL, VK_S)

            msg = wintypes.MSG()
            while self.app_running:
                ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret <= 0:
                    break
                if msg.message == WM_HOTKEY:
                    hk_id = msg.wParam
                    if hk_id == HOTKEY_ID_MIC:
                        self.root.after(0, self.toggle_mic)
                    elif hk_id == HOTKEY_ID_STOP:
                        self.root.after(0, self.stop_action)
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

            try:
                user32.UnregisterHotKey(None, HOTKEY_ID_MIC)
                user32.UnregisterHotKey(None, HOTKEY_ID_STOP)
            except Exception:
                pass

        t = threading.Thread(target=_hotkey_worker, daemon=True)
        t.start()

    def _s(self, px):
        return int(round(px * self.ui_scale))

    def _font(self, family, size, weight='normal'):
        scaled_size = max(8, int(round(size * self.ui_scale)))
        return (family, scaled_size, weight)

    def _keep_on_top(self):
        """Enforces topmost on Windows so the widget never gets hidden."""
        if not self.app_running:
            return
        try:
            self.root.attributes('-topmost', True)
            hwnd = self.root.winfo_id()
            ctypes.windll.user32.SetWindowPos(
                hwnd, -1, 0, 0, 0, 0,
                0x0001 | 0x0002 | 0x0040  # SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW
            )
        except Exception:
            pass
        self.root.after(1000, self._keep_on_top)

    def _setup_no_activate(self):
        if sys.platform != 'win32':
            return
        try:
            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            old_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, old_style | WS_EX_NOACTIVATE)
        except Exception:
            pass

    def _track_foreground_window(self):
        if not self.app_running:
            return
        try:
            fg = ctypes.windll.user32.GetForegroundWindow()
            if fg and ctypes.windll.user32.IsWindow(fg):
                my_hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
                if fg != my_hwnd and not self._is_own_window(fg):
                    self.last_external_hwnd = fg
            # Track mouse position when hovering over target/external window
            class POINT(ctypes.Structure):
                _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]
            pt = POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            my_hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            cur_hwnd = ctypes.windll.user32.WindowFromPoint(pt)
            if cur_hwnd != my_hwnd and not self._is_own_window(cur_hwnd):
                self.last_external_cursor_pos = (pt.x, pt.y)
        except Exception:
            pass
        self.root.after(100, self._track_foreground_window)

    def _is_own_window(self, hwnd):
        try:
            if self.settings_win and self.settings_win.winfo_exists():
                sw_hwnd = ctypes.windll.user32.GetParent(self.settings_win.winfo_id()) or self.settings_win.winfo_id()
                if hwnd == sw_hwnd:
                    return True
        except Exception:
            pass
        return False

    def _drag_start(self, e):
        self._drag_x = e.x_root - self.root.winfo_x()
        self._drag_y = e.y_root - self.root.winfo_y()

    def _drag_move(self, e):
        x = e.x_root - self._drag_x
        y = e.y_root - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    def _drag_end(self, e):
        self._remember_window_position()
        self.save_config()
        self._keep_on_top()

    def _close_ctx(self, e=None):
        if self.menu:
            try:
                self.menu.destroy()
            except Exception:
                pass
            self.menu = None

    def show_context_menu(self, e):
        self._close_ctx()
        menu = tk.Menu(self.root, tearoff=0, bg=self.bg2, fg=self.txt, activebackground='#3d3d3d', activeforeground=self.yellow)
        menu.add_command(label="🎤 Bật / Tắt Mic (Ctrl+L)", command=self.toggle_mic)
        menu.add_command(label="⏹ Dừng lại (Ctrl+S)", command=self.stop_action)
        menu.add_separator()
        menu.add_command(label="Cài đặt tọa độ Click (Settings)", command=self.open_settings)
        menu.add_command(label="Thử click tọa độ (Test Click)", command=self._test_click_coord)
        menu.add_separator()
        menu.add_command(
            label=f"{'✓ ' if self.lang_mode == 'auto' else '    '}🌐 Ngôn ngữ: Tự động (Song ngữ VI + EN)",
            command=lambda: self.set_lang_mode('auto')
        )
        menu.add_command(
            label=f"{'✓ ' if self.lang_mode == 'vi' else '    '}🇻🇳 Ưu tiên Tiếng Việt (Vietnamese)",
            command=lambda: self.set_lang_mode('vi')
        )
        menu.add_command(
            label=f"{'✓ ' if self.lang_mode == 'en' else '    '}🇺🇸 Chỉ Tiếng Anh (English Only)",
            command=lambda: self.set_lang_mode('en')
        )
        menu.add_separator()
        menu.add_command(label="Thử âm thanh (Test Beep)", command=lambda: winsound.Beep(1800, 150))
        menu.add_separator()
        menu.add_command(label=f"🔄 Kiểm tra cập nhật (v{APP_VERSION})", command=self.check_updates_interactive)
        menu.add_separator()
        menu.add_command(label="Thoát (Exit)", command=self.close_app)
        menu.post(e.x_root, e.y_root)
        self.menu = menu

    def set_lang_mode(self, mode):
        self.lang_mode = mode
        self.save_config()
        labels = {'auto': 'Tự động (VI + EN)', 'vi': 'Tiếng Việt', 'en': 'English'}
        self.show_temp_status(f"Lang: {labels.get(mode, mode)}", self.green, 2000)

    def _remember_window_position(self):
        try:
            self.window_x = int(self.root.winfo_x())
            self.window_y = int(self.root.winfo_y())
        except Exception:
            pass

    def load_config(self):
        for path in self.config_candidates:
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    self.click_x = int(data.get('click_x', self.click_x))
                    self.click_y = int(data.get('click_y', self.click_y))
                    self.window_x = int(data.get('window_x', self.window_x))
                    self.window_y = int(data.get('window_y', self.window_y))
                    self.silence_timeout = float(data.get('silence_timeout', self.silence_timeout))
                    self.rec.pause_threshold = self.silence_timeout
                    self.lang_mode = data.get('lang_mode', 'auto')
                    self.use_fixed_coord = bool(data.get('use_fixed_coord', False))
                    self.auto_paste_enter_on_click = bool(data.get('auto_paste_enter_on_click', True))
                    self.paste_enter_delay = float(data.get('paste_enter_delay', 0.3))
                    self.ui_scale = float(data.get('ui_scale', getattr(self, 'ui_scale', UI_SCALE)))
                    self.gemini_enabled = bool(data.get('gemini_enabled', True))
                    raw_key = str(data.get('gemini_api_key', '')).strip()
                    if not raw_key:
                        raw_key = DEFAULT_GEMINI_API_KEY
                    self.gemini_api_key = raw_key
                    m = str(data.get('gemini_model', 'gemini-2.5-flash'))
                    if m in ('gemini-1.5-flash', 'gemini-1.5-pro'):
                        m = 'gemini-2.5-flash'
                    self.gemini_model = m
                    self.auto_check_update = bool(data.get('auto_check_update', True))
                    self.github_repo = str(data.get('github_repo', GITHUB_REPO))
                    self.config_path = path
                    break
                except Exception as ex:
                    self._log_error(f"load_config error: {ex}")

    def save_config(self):
        self._remember_window_position()
        data = {
            "click_x": self.click_x,
            "click_y": self.click_y,
            "window_x": self.window_x,
            "window_y": self.window_y,
            "silence_timeout": round(self.silence_timeout, 2),
            "ui_scale": round(float(getattr(self, 'ui_scale', UI_SCALE)), 2),
            "lang_mode": getattr(self, 'lang_mode', 'auto'),
            "use_fixed_coord": getattr(self, 'use_fixed_coord', False),
            "auto_paste_enter_on_click": getattr(self, 'auto_paste_enter_on_click', True),
            "paste_enter_delay": round(getattr(self, 'paste_enter_delay', 0.3), 2),
            "gemini_enabled": getattr(self, 'gemini_enabled', True),
            "gemini_api_key": getattr(self, 'gemini_api_key', ''),
            "gemini_model": getattr(self, 'gemini_model', 'gemini-2.5-flash'),
            "auto_check_update": getattr(self, 'auto_check_update', True),
            "github_repo": getattr(self, 'github_repo', GITHUB_REPO)
        }
        for path in self.config_candidates:
            try:
                os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
            except Exception:
                pass

    def _log_error(self, msg):
        try:
            with open(self.log_path, 'a', encoding='utf-8') as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | error | {msg}\n")
        except Exception:
            pass

    def show_temp_status(self, text, color=None, duration=2200):
        if not color:
            color = self.yellow
        self.status.config(text=text, fg=color)
        self.root.after(duration, lambda: self.status.config(text='Ready', fg=self.muted))

    def _show_speech_popup(self, raw_text, final_text, is_live=False):
        """Show floating preview of recognized voice text (supports smooth live streaming)."""
        if not raw_text and not final_text:
            return

        display_text = final_text or raw_text
        if len(display_text) > 130:
            display_text = display_text[:127] + "..."

        # If live and popup already exists, update text smoothly without flickering
        if is_live and getattr(self, '_speech_popup', None) and self._speech_popup.winfo_exists():
            try:
                if hasattr(self, '_speech_popup_lbl') and self._speech_popup_lbl.winfo_exists():
                    self._speech_popup_lbl.config(text=f"🎙️ {display_text}", fg=self.yellow)
                    return
            except Exception:
                pass

        try:
            if getattr(self, '_speech_popup', None) and self._speech_popup.winfo_exists():
                self._speech_popup.destroy()
        except Exception:
            pass

        popup = tk.Toplevel(self.root)
        popup.overrideredirect(True)
        popup.attributes('-topmost', True)
        popup.config(bg='#00b4d8' if is_live else self.yellow)

        inner = tk.Frame(popup, bg=self.bg2, padx=10, pady=5)
        inner.pack(fill='both', expand=True, padx=1, pady=1)

        is_ai_refined = bool(final_text and raw_text and final_text.strip().lower() != raw_text.strip().lower())
        if is_live:
            prefix = "🎙️ "
            lbl_fg = self.yellow
        else:
            prefix = "✨ " if is_ai_refined else "📋 "
            lbl_fg = '#00e676' if is_ai_refined else self.green

        lbl = tk.Label(
            inner, text=f"{prefix}{display_text}", font=('Segoe UI', 10),
            bg=self.bg2, fg=lbl_fg, wraplength=440, justify='left'
        )
        lbl.pack(anchor='w')
        self._speech_popup_lbl = lbl

        if not is_live and is_ai_refined:
            raw_disp = raw_text if len(raw_text) <= 75 else raw_text[:72] + "..."
            lbl_raw = tk.Label(
                inner, text=f"Gốc: {raw_disp}", font=('Segoe UI', 8),
                bg=self.bg2, fg='#888888', wraplength=440, justify='left'
            )
            lbl_raw.pack(anchor='w', pady=(2, 0))

        # Position above toolbar with accurate geometry
        popup.update_idletasks()
        pw = popup.winfo_reqwidth()
        ph = popup.winfo_reqheight()
        px = max(10, self.window_x)
        py = max(10, self.window_y - ph - 8)
        popup.geometry(f"+{px}+{py}")

        self._speech_popup = popup
        if not is_live:
            popup.after(3800, lambda: popup.destroy() if popup.winfo_exists() else None)

    def set_ui(self, listening: bool):
        st = self._ib_state.get('tb_mic')
        if st:
            if listening:
                st['icon'] = MIC_ACTIVE_ICON
                st['fg'] = self.red
                st['hfg'] = '#ff6666'
                st['border'] = self.red
                st['hborder'] = '#ff6666'
                st['bg'] = '#3a1e1e'
                st['hbg'] = '#4a2626'
                self.status.config(text="Listening...", fg=self.red)
            else:
                st['icon'] = MIC_IDLE_ICON
                st['fg'] = self.green
                st['hfg'] = '#40ff88'
                st['border'] = self.green
                st['hborder'] = '#40ff88'
                st['bg'] = '#223026'
                st['hbg'] = '#2c3f32'
                self.status.config(text="Ready", fg=self.muted)
            self._rdraw_mic()

    def _init_sherpa(self):
        """Asynchronously loads Sherpa-ONNX Zipformer Vietnamese model for instantaneous streaming ASR."""
        paths = get_sherpa_model_paths()
        if paths and sherpa_onnx is not None:
            try:
                self._sherpa_rec = sherpa_onnx.OfflineRecognizer.from_transducer(
                    tokens=paths["tokens"],
                    encoder=paths["encoder"],
                    decoder=paths["decoder"],
                    joiner=paths["joiner"],
                    num_threads=2,
                    sample_rate=16000,
                    feature_dim=80,
                )
            except Exception as e:
                self._log_error(f"Failed to load Sherpa-ONNX model: {e}")
                self._sherpa_rec = None

    def _initial_calibrate(self):
        """Initial background calibration of mic without blocking UI."""
        try:
            mic_idx, mic_name = self._resolve_mic_source(self.mic_index)
            with sr.Microphone(device_index=mic_idx) as source:
                self.rec.adjust_for_ambient_noise(source, duration=0.2)
            self._mic_calibrated = True
        except Exception:
            pass

    def _resolve_mic_source(self, idx):
        if idx is not None:
            return idx, f"Microphone #{idx}"
        return None, "Default Microphone"

    def toggle_mic(self):
        """Combined single mic (Ctrl+L): toggles speech-to-text, copies to clipboard only."""
        if self.listening:
            self.listening = False
            self._stop_requested = True
            self.set_ui(False)
            try:
                winsound.Beep(1200, 60)
            except Exception:
                pass
        else:
            self.listening = True
            self._stop_requested = False
            self._auto_paste_enter_on_finish = False
            self._click_target_hwnd = None
            self.set_ui(True)
            try:
                winsound.Beep(1800, 70)
            except Exception:
                pass
            threading.Thread(target=self.worker, daemon=True).start()
            if getattr(self, 'auto_paste_enter_on_click', True):
                threading.Thread(target=self._watch_click_to_finish, daemon=True).start()

    def stop_action(self):
        """Action for Stop (Ctrl+S): Cancels active recording or stops active task."""
        if self.listening:
            self.listening = False
            self._stop_requested = True
            self._auto_paste_enter_on_finish = False
            self.set_ui(False)
            self.show_temp_status("Stopped", self.red, 1200)
            try:
                winsound.Beep(1100, 90)
            except Exception:
                pass
        else:
            self.stop_vscode()

    def _watch_click_to_finish(self):
        """Monitors for left-click anywhere while recording to immediately finish & paste+enter."""
        user32 = ctypes.windll.user32
        user32.GetAsyncKeyState.restype = ctypes.c_short
        user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        VK_LBUTTON = 0x01

        # Grace period: if left button is currently pressed down (e.g. from clicking Mic), wait until released
        if user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000:
            while self.listening and (user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000):
                time.sleep(0.01)
            time.sleep(0.04)
        else:
            time.sleep(0.05)

        while self.listening and not getattr(self, '_stop_requested', False):
            state = user32.GetAsyncKeyState(VK_LBUTTON)
            if (state & 0x8000) or (state & 0x0001):
                # Check if click is on toolbar
                try:
                    px, py = pyautogui.position()
                    wx = self.root.winfo_rootx()
                    wy = self.root.winfo_rooty()
                    ww = self.root.winfo_width()
                    wh = self.root.winfo_height()
                    if wx <= px <= wx + ww and wy <= py <= wy + wh:
                        # Click on toolbar -> ignore in watcher
                        time.sleep(0.05)
                        continue
                except Exception:
                    pass

                # Click is OUTSIDE toolbar!
                # Wait for mouse release so the target window receives the click event cleanly
                while user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000:
                    time.sleep(0.01)
                time.sleep(0.04)

                # Determine the exact window clicked
                try:
                    point = wintypes.POINT(int(px), int(py))
                    wnd_under_cursor = user32.WindowFromPoint(point)
                    GA_ROOT = 2
                    root_wnd = user32.GetAncestor(wnd_under_cursor, GA_ROOT) if wnd_under_cursor else 0
                    fg_wnd = user32.GetForegroundWindow()
                    target = root_wnd or wnd_under_cursor or fg_wnd
                    if not target or target == self.root.winfo_id() or self._is_own_window(target):
                        target = getattr(self, 'last_external_hwnd', None)
                except Exception:
                    target = user32.GetForegroundWindow()

                self._click_target_hwnd = target
                self._auto_paste_enter_on_finish = True
                self._stop_requested = True
                self.root.after(0, lambda: self.status.config(text="Transcribing...", fg=self.yellow))
                break

            time.sleep(0.008)

    def recognize_bilingual(self, audio):
        """Intelligently recognizes speech with single-pass FLAC encoding and early return."""
        mode = getattr(self, 'lang_mode', 'auto')
        if mode == 'en':
            return self.rec.recognize_google(audio, language="en-US").strip()
        if mode == 'vi':
            return self.rec.recognize_google(audio, language="vi-VN").strip()

        # Pre-cache FLAC data on this AudioData instance so flac.exe runs only once
        orig_get_flac = audio.get_flac_data
        _flac_cache = None
        def _cached_flac(*args, **kwargs):
            nonlocal _flac_cache
            if _flac_cache is None:
                _flac_cache = orig_get_flac(*args, **kwargs)
            return _flac_cache
        audio.get_flac_data = _cached_flac

        # Auto Bilingual Mode: Concurrently query vi-VN and en-US
        res_vi, res_en = None, None
        early_vi_done = threading.Event()

        def _rec_vi():
            nonlocal res_vi
            try:
                res_vi = self.rec.recognize_google(audio, language="vi-VN").strip()
                if res_vi and VI_DIACRITICS.search(res_vi):
                    # Authentic Vietnamese with diacritics identified - fast exit!
                    early_vi_done.set()
            except Exception:
                res_vi = None

        def _rec_en():
            nonlocal res_en
            try:
                res_en = self.rec.recognize_google(audio, language="en-US").strip()
            except Exception:
                res_en = None

        t_vi = threading.Thread(target=_rec_vi, daemon=True)
        t_en = threading.Thread(target=_rec_en, daemon=True)
        t_vi.start()
        t_en.start()

        # Responsive wait loop: exit immediately as soon as Vietnamese is confirmed
        t0 = time.time()
        while time.time() - t0 < 8.0:
            if early_vi_done.is_set():
                break
            if not t_vi.is_alive() and not t_en.is_alive():
                break
            time.sleep(0.02)

        if res_vi and not res_en:
            return res_vi
        if res_en and not res_vi:
            return res_en
        if not res_vi and not res_en:
            raise sr.UnknownValueError()

        # Check whether user spoke authentic Vietnamese or pure English
        words_vi = re.findall(r'\w+', res_vi.lower())
        vi_word_count = sum(1 for w in words_vi if w in COMMON_VI_WORDS)
        vi_diacritic_count = sum(1 for w in words_vi if VI_DIACRITICS.search(w))

        # Must have authentic Vietnamese structural words AND diacritics
        if vi_word_count >= 1 and vi_diacritic_count >= 1:
            return res_vi
        else:
            return res_en

    def _worker_sherpa_streaming(self):
        """Real-time streaming speech recognition using sounddevice + Sherpa-ONNX Zipformer Vi."""
        temp_status = None
        try:
            sample_rate = 16000
            block_size = 1600  # 100ms
            audio_buffer = []
            audio_queue = []
            has_spoken = False
            last_speech_time = None
            last_preview_time = 0
            min_speech_energy = 0.004

            self.root.after(0, lambda: self.status.config(text="Speak now...", fg=self.yellow))

            def _audio_callback(indata, frames, time_info, status):
                audio_queue.append(indata.copy())

            stream_kwargs = {
                'samplerate': sample_rate,
                'channels': 1,
                'dtype': 'float32',
                'blocksize': block_size,
                'callback': _audio_callback,
            }
            if self.mic_index is not None:
                try:
                    stream_kwargs['device'] = self.mic_index
                except Exception:
                    pass

            with sd.InputStream(**stream_kwargs):
                t_start = time.time()
                while self.listening and not getattr(self, '_stop_requested', False):
                    time.sleep(0.03)

                    # Drain audio queue
                    while audio_queue:
                        chunk = audio_queue.pop(0).flatten()
                        audio_buffer.extend(chunk)

                        energy = np.sqrt(np.mean(chunk**2)) if len(chunk) > 0 else 0
                        if energy > min_speech_energy:
                            last_speech_time = time.time()
                            has_spoken = True

                    now = time.time()

                    # Live preview every 220ms once user starts speaking
                    if has_spoken and (now - last_preview_time >= 0.22) and len(audio_buffer) >= 3200:
                        last_preview_time = now
                        try:
                            s = self._sherpa_rec.create_stream()
                            s.accept_waveform(sample_rate, np.array(audio_buffer, dtype=np.float32))
                            self._sherpa_rec.decode_stream(s)
                            partial = s.result.text.strip()
                            if partial:
                                disp = partial.lower().capitalize()
                                self.root.after(0, lambda t=disp: self._show_speech_popup(t, "", is_live=True))
                                self.root.after(0, lambda: self.status.config(text="● Đang nghe...", fg=self.yellow))
                        except Exception:
                            pass

                    # Silence cut-off
                    if has_spoken and last_speech_time and (now - last_speech_time > self.silence_timeout):
                        break

                    # Maximum phrase limit: 45s
                    if now - t_start > 45:
                        break

            if not self.listening and not getattr(self, '_auto_paste_enter_on_finish', False):
                return

            self.root.after(0, lambda: self.status.config(text="Transcribing...", fg=self.yellow))

            if not has_spoken or len(audio_buffer) < 3200:
                temp_status = ("NoSpeech", self.muted)
                return

            # Final decode on full buffer
            s = self._sherpa_rec.create_stream()
            s.accept_waveform(sample_rate, np.array(audio_buffer, dtype=np.float32))
            self._sherpa_rec.decode_stream(s)
            raw_text = s.result.text.strip()

            if raw_text:
                text = raw_text.lower().capitalize()
                text = normalize_vietnamese_speech(text)

                # Optional AI Refinement with Gemini Flash (Toggleable)
                if getattr(self, 'gemini_enabled', False) and getattr(self, 'gemini_api_key', '').strip():
                    self.root.after(0, lambda: self.status.config(text="AI...", fg='#00d2ff'))
                    try:
                        refined = refine_text_with_gemini(
                            text,
                            api_key=self.gemini_api_key.strip(),
                            model=getattr(self, 'gemini_model', 'gemini-2.5-flash'),
                            timeout=3.0
                        )
                        if refined and refined.strip():
                            text = refined.strip()
                    except Exception as ai_ex:
                        self._log_error(f"Gemini error (using Sherpa text): {ai_ex}")

                self.last_text = text
                pyperclip.copy(text)

                try:
                    winsound.Beep(1800, 70)
                except Exception:
                    pass

                temp_status = ("Copied", self.green)
                self.root.after(0, lambda r=raw_text, t=text: self._show_speech_popup(r, t, is_live=False))

                # Auto Paste & Enter on Left-Click / Finish
                if getattr(self, '_auto_paste_enter_on_finish', False):
                    self._auto_paste_enter_on_finish = False
                    target = getattr(self, '_click_target_hwnd', None) or getattr(self, 'last_external_hwnd', None)
                    is_remote = is_remote_desktop_window(target)
                    if target and ctypes.windll.user32.IsWindow(target):
                        curr_fg = ctypes.windll.user32.GetForegroundWindow()
                        if curr_fg != target:
                            force_foreground_window(target)
                        time.sleep(0.25 if is_remote else 0.06)
                    else:
                        time.sleep(0.06)

                    send_paste()
                    temp_status = ("Pasted", self.green)

                    delay = getattr(self, 'paste_enter_delay', 0.3)
                    if is_remote and delay < 0.35:
                        delay = 0.35
                    time.sleep(delay)

                    send_enter()
                    temp_status = ("Sent", self.yellow)
            else:
                temp_status = ("NoSpeech", self.muted)

        except Exception as ex:
            self._log_error(f"Sherpa streaming worker error: {ex}")
            temp_status = ("Error", self.red)
        finally:
            self.listening = False
            self._stop_requested = False
            self.root.after(0, lambda: self.set_ui(False))
            if temp_status:
                self.root.after(0, lambda ts=temp_status: self.show_temp_status(ts[0], ts[1]))

    def worker(self):
        """Dispatches to Sherpa-ONNX streaming engine (primary) or Google Speech (fallback)."""
        if getattr(self, '_sherpa_rec', None) is not None and sd is not None and np is not None:
            self._worker_sherpa_streaming()
        else:
            self._worker_google_fallback()

    def _worker_google_fallback(self):
        """Listens, transcribes via Google Speech, and copies text to clipboard."""
        temp_status = None
        try:
            mic_idx, mic_name = self._resolve_mic_source(self.mic_index)
            with sr.Microphone(device_index=mic_idx) as source:
                if not self._mic_calibrated:
                    self.rec.adjust_for_ambient_noise(source, duration=0.2)
                    self._mic_calibrated = True

                self.root.after(0, lambda: self.status.config(text="Speak now...", fg=self.yellow))

                # Wrap source.stream with CancellableStream so left-click breaks immediately
                orig_stream = source.stream
                source.stream = CancellableStream(orig_stream, lambda: getattr(self, '_stop_requested', False))

                # Listen for speech
                audio = self.rec.listen(source, timeout=25, phrase_time_limit=45)

            if not self.listening and not getattr(self, '_auto_paste_enter_on_finish', False):
                return

            self.root.after(0, lambda: self.status.config(text="Transcribing...", fg=self.yellow))

            # Recognize speech (Bilingual Vietnamese + English)
            raw_text = self.recognize_bilingual(audio)

            if raw_text:
                text = normalize_vietnamese_speech(raw_text)

                # Context-aware AI error correction using Google Gemini Flash
                if getattr(self, 'gemini_enabled', True) and getattr(self, 'gemini_api_key', '').strip():
                    self.root.after(0, lambda: self.status.config(text="AI...", fg='#00d2ff'))
                    try:
                        refined = refine_text_with_gemini(
                            text,
                            api_key=self.gemini_api_key.strip(),
                            model=getattr(self, 'gemini_model', 'gemini-2.5-flash'),
                            timeout=3.5
                        )
                        if refined and refined.strip():
                            text = refined.strip()
                    except Exception as ai_ex:
                        self._log_error(f"Gemini refine error: {ai_ex}")

                self.last_text = text

                # Copy to clipboard
                pyperclip.copy(text)

                # Audio chime
                try:
                    winsound.Beep(1800, 70)
                except Exception:
                    pass

                # Status and preview popup
                temp_status = ("Copied", self.green)
                self.root.after(0, lambda r=raw_text, t=text: self._show_speech_popup(r, t))

                # Auto Paste & Enter on Left-Click
                if getattr(self, '_auto_paste_enter_on_finish', False):
                    self._auto_paste_enter_on_finish = False
                    target = getattr(self, '_click_target_hwnd', None) or getattr(self, 'last_external_hwnd', None)
                    is_remote = is_remote_desktop_window(target)
                    if target and ctypes.windll.user32.IsWindow(target):
                        curr_fg = ctypes.windll.user32.GetForegroundWindow()
                        if curr_fg != target:
                            force_foreground_window(target)
                        time.sleep(0.25 if is_remote else 0.06)
                    else:
                        time.sleep(0.06)

                    send_paste()
                    temp_status = ("Pasted", self.green)

                    # Delay between paste and enter (minimum 0.35s for remote desktop)
                    delay = getattr(self, 'paste_enter_delay', 0.3)
                    if is_remote and delay < 0.35:
                        delay = 0.35
                    time.sleep(delay)

                    send_enter()
                    temp_status = ("Sent", self.yellow)
            else:
                temp_status = ("NoSpeech", self.muted)

        except sr.WaitTimeoutError:
            temp_status = ("Timeout", self.muted)
        except sr.UnknownValueError:
            temp_status = ("NoSpeech", self.muted)
        except Exception as ex:
            self._log_error(f"worker error: {ex}")
            temp_status = ("Error", self.red)
        finally:
            self.listening = False
            self._stop_requested = False
            self.root.after(0, lambda: self.set_ui(False))
            if temp_status:
                self.root.after(0, lambda ts=temp_status: self.show_temp_status(ts[0], ts[1]))

    # Toolbar Button Actions
    def press_a(self):
        """Button 'A': Selects all in active window without losing mouse or focus."""
        self.show_temp_status("Select All", self.yellow, 1200)
        def _task():
            try:
                orig_x, orig_y = pyautogui.position()
                if getattr(self, 'use_fixed_coord', False):
                    pyautogui.hotkey('alt', 'tab')
                    time.sleep(0.12)
                    pyautogui.click(self.click_x, self.click_y)
                    time.sleep(0.06)
                    send_select_all()
                    return

                target = getattr(self, 'last_external_hwnd', None)
                if target and ctypes.windll.user32.IsWindow(target):
                    force_foreground_window(target)
                    is_remote = is_remote_desktop_window(target)
                    time.sleep(0.12 if is_remote else 0.05)

                send_select_all()

                now_x, now_y = pyautogui.position()
                if (now_x, now_y) != (orig_x, orig_y):
                    pyautogui.moveTo(orig_x, orig_y)
            except Exception as e:
                self._log_error(f"press_a: {e}")
        threading.Thread(target=_task, daemon=True).start()

    def press_c(self):
        """Button 'C': Copies from active window without losing mouse or focus."""
        self.show_temp_status("Copied", self.green, 1500)
        def _task():
            try:
                orig_x, orig_y = pyautogui.position()
                target = getattr(self, 'last_external_hwnd', None)
                if target and ctypes.windll.user32.IsWindow(target):
                    force_foreground_window(target)
                    is_remote = is_remote_desktop_window(target)
                    time.sleep(0.12 if is_remote else 0.05)

                send_copy()

                now_x, now_y = pyautogui.position()
                if (now_x, now_y) != (orig_x, orig_y):
                    pyautogui.moveTo(orig_x, orig_y)
            except Exception as e:
                self._log_error(f"press_c: {e}")
        threading.Thread(target=_task, daemon=True).start()

    def press_v(self):
        """Button 'V': Pastes into active window without losing mouse or focus."""
        self.show_temp_status("Pasted", self.green, 1500)
        def _task():
            try:
                orig_x, orig_y = pyautogui.position()
                if getattr(self, 'use_fixed_coord', False):
                    pyautogui.hotkey('alt', 'tab')
                    time.sleep(0.12)
                    pyautogui.click(self.click_x, self.click_y)
                    time.sleep(0.06)
                    send_paste()
                    return

                target = getattr(self, 'last_external_hwnd', None)
                if target and ctypes.windll.user32.IsWindow(target):
                    force_foreground_window(target)
                    is_remote = is_remote_desktop_window(target)
                    time.sleep(0.15 if is_remote else 0.05)

                send_paste()

                now_x, now_y = pyautogui.position()
                if (now_x, now_y) != (orig_x, orig_y):
                    pyautogui.moveTo(orig_x, orig_y)
            except Exception as e:
                self._log_error(f"press_v: {e}")
        threading.Thread(target=_task, daemon=True).start()

    def press_enter(self):
        """Button 'Enter' (↵): Presses Enter in active window without losing mouse or focus."""
        self.show_temp_status("Enter", self.yellow, 1200)
        def _task():
            try:
                orig_x, orig_y = pyautogui.position()
                if getattr(self, 'use_fixed_coord', False):
                    pyautogui.hotkey('alt', 'tab')
                    time.sleep(0.12)
                    pyautogui.click(self.click_x, self.click_y)
                    time.sleep(0.06)
                    send_enter()
                    return

                target = getattr(self, 'last_external_hwnd', None)
                if target and ctypes.windll.user32.IsWindow(target):
                    force_foreground_window(target)
                    is_remote = is_remote_desktop_window(target)
                    time.sleep(0.12 if is_remote else 0.05)

                send_enter()

                now_x, now_y = pyautogui.position()
                if (now_x, now_y) != (orig_x, orig_y):
                    pyautogui.moveTo(orig_x, orig_y)
            except Exception as e:
                self._log_error(f"press_enter: {e}")
        threading.Thread(target=_task, daemon=True).start()

    def _get_scroll_target_coords(self):
        """Calculates screen coordinates of the active content area to receive scroll wheel events."""
        if getattr(self, 'use_fixed_coord', False):
            return self.click_x, self.click_y

        target = getattr(self, 'last_external_hwnd', None)
        if target and ctypes.windll.user32.IsWindow(target):
            class RECT(ctypes.Structure):
                _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long),
                            ('right', ctypes.c_long), ('bottom', ctypes.c_long)]
            rect = RECT()
            if ctypes.windll.user32.GetWindowRect(target, ctypes.byref(rect)):
                # If user recently had cursor inside this window, use that exact spot!
                last_pos = getattr(self, 'last_external_cursor_pos', None)
                if last_pos and len(last_pos) == 2:
                    lx, ly = last_pos
                    if rect.left <= lx <= rect.right and rect.top <= ly <= rect.bottom:
                        return lx, ly

                w = rect.right - rect.left
                h = rect.bottom - rect.top
                if w > 80 and h > 80:
                    return rect.left + w // 2, rect.top + h // 2

        try:
            return self.root.winfo_screenwidth() // 2, self.root.winfo_screenheight() // 2
        except Exception:
            return 800, 500

    def press_up(self):
        """Button 'Up' (▲): Scrolls window up like rolling the mouse wheel up."""
        self.show_temp_status("Cuộn Lên", self.yellow, 800)
        def _task():
            try:
                if getattr(self, 'use_fixed_coord', False):
                    pyautogui.hotkey('alt', 'tab')
                    time.sleep(0.12)
                    send_scroll(360, target_x=self.click_x, target_y=self.click_y)
                    return

                target = getattr(self, 'last_external_hwnd', None)
                if target and ctypes.windll.user32.IsWindow(target):
                    force_foreground_window(target)
                    time.sleep(0.04)

                tx, ty = self._get_scroll_target_coords()
                send_scroll(360, target_hwnd=target, target_x=tx, target_y=ty)
            except Exception as e:
                self._log_error(f"press_up scroll: {e}")
        threading.Thread(target=_task, daemon=True).start()

    def press_down(self):
        """Button 'Down' (▼): Scrolls window down like rolling the mouse wheel down."""
        self.show_temp_status("Cuộn Xuống", self.yellow, 800)
        def _task():
            try:
                if getattr(self, 'use_fixed_coord', False):
                    pyautogui.hotkey('alt', 'tab')
                    time.sleep(0.12)
                    send_scroll(-360, target_x=self.click_x, target_y=self.click_y)
                    return

                target = getattr(self, 'last_external_hwnd', None)
                if target and ctypes.windll.user32.IsWindow(target):
                    force_foreground_window(target)
                    time.sleep(0.04)

                tx, ty = self._get_scroll_target_coords()
                send_scroll(-360, target_hwnd=target, target_x=tx, target_y=ty)
            except Exception as e:
                self._log_error(f"press_down scroll: {e}")
        threading.Thread(target=_task, daemon=True).start()

    def stop_vscode(self):
        """Button 'Stop': Stops active task in VS Code (Shift+F5 / Ctrl+F5)."""
        self.show_temp_status("Stopped", self.red, 1500)
        def _task():
            try:
                focus_vscode()
                pyautogui.hotkey('shift', 'f5')
                time.sleep(0.15)
                pyautogui.hotkey('ctrl', 'f5')
                time.sleep(0.08)
                pyautogui.press('space')
            except Exception as e:
                self._log_error(f"stop_vscode: {e}")
        threading.Thread(target=_task, daemon=True).start()

    def _get_btn_photo(self, w, h, r, bg, border, border_w):
        key = (w, h, r, bg, border, border_w)
        if key not in self._photo_cache:
            factor = 3
            fw, fh = w * factor, h * factor
            fr = r * factor
            fbw = border_w * factor
            img = Image.new('RGBA', (fw, fh), (31, 31, 31, 255))
            d = ImageDraw.Draw(img)
            offset = fbw // 2
            d.rounded_rectangle(
                (offset, offset, fw - 1 - offset, fh - 1 - offset),
                radius=fr, fill=bg, outline=border, width=fbw
            )
            resized = img.resize((w, h), Image.Resampling.LANCZOS)
            self._photo_cache[key] = ImageTk.PhotoImage(resized)
        return self._photo_cache[key]

    # Rounded rectangle canvas helper
    def _rr_canvas(self, cv, x1, y1, x2, y2, r, color, tag):
        r = max(1, r)
        cv.create_arc(x1, y1, x1 + 2 * r, y1 + 2 * r, start=90, extent=90, fill=color, outline=color, tags=tag)
        cv.create_arc(x2 - 2 * r, y1, x2, y1 + 2 * r, start=0, extent=90, fill=color, outline=color, tags=tag)
        cv.create_arc(x1, y2 - 2 * r, x1 + 2 * r, y2, start=180, extent=90, fill=color, outline=color, tags=tag)
        cv.create_arc(x2 - 2 * r, y2 - 2 * r, x2, y2, start=270, extent=90, fill=color, outline=color, tags=tag)
        cv.create_rectangle(x1 + r, y1, x2 - r, y2, fill=color, outline=color, tags=tag)
        cv.create_rectangle(x1, y1 + r, x2, y2 - r, fill=color, outline=color, tags=tag)

    def _test_gemini_api_key(self):
        key = self.gemini_key_var.get().strip() if hasattr(self, 'gemini_key_var') else getattr(self, 'gemini_api_key', '').strip()
        if not key:
            messagebox.showwarning("Gemini AI", "Vui lòng nhập API Key trước khi thử!\n\nNhấn nút 'Lấy API Key miễn phí' nếu bạn chưa có key.")
            return

        model = self.gemini_model_var.get().strip() if hasattr(self, 'gemini_model_var') else getattr(self, 'gemini_model', 'gemini-2.5-flash')
        sample = "cá hợp lý rồi sau khi tôi yêu xong"
        self.show_temp_status("Testing AI...", '#00d2ff', 4000)

        def _test():
            try:
                res = refine_text_with_gemini(sample, key, model=model, timeout=6.0, raise_exceptions=True)
                msg = f"🎉 Kết nối Google Gemini Flash thành công!\n\nModel: {model}\n\nCâu thử nghiệm:\n\"{sample}\"\n\nGemini đã sửa thành:\n\"{res}\""
                self.root.after(0, lambda: messagebox.showinfo("Gemini AI Test - Thành công", msg))
                self.root.after(0, lambda: self.show_temp_status("AI OK", self.green, 2000))
                self.root.after(0, lambda: self._set_border_color(self.green))
            except urllib.error.HTTPError as he:
                err_body = ""
                try:
                    err_body = he.read().decode('utf-8')
                except Exception:
                    pass
                msg = f"❌ Lỗi xác thực từ Google AI (HTTP {he.code}):\n{he.reason}\n\nChi tiết:\n{err_body[:200]}"
                self.root.after(0, lambda: messagebox.showerror("Gemini AI Test - Thất bại", msg))
                self.root.after(0, lambda: self.show_temp_status("AI Error", self.red, 2000))
                self.root.after(0, lambda: self._set_border_color(self.yellow))
            except Exception as e:
                msg = f"❌ Không thể kết nối tới Google Gemini:\n{e}\n\nVui lòng kiểm tra lại kết nối mạng hoặc API Key."
                self.root.after(0, lambda: messagebox.showerror("Gemini AI Test - Thất bại", msg))
                self.root.after(0, lambda: self.show_temp_status("AI Error", self.red, 2000))
                self.root.after(0, lambda: self._set_border_color(self.yellow))

        threading.Thread(target=_test, daemon=True).start()

    # Settings Dialog
    def open_settings(self):
        if self.settings_win and self.settings_win.winfo_exists():
            self.settings_win.lift()
            self.settings_win.focus_force()
            return

        win = tk.Toplevel(self.root)
        win.title("Cài đặt Voice-To-Text")
        win.configure(bg=self.bg)
        win.attributes('-topmost', True)
        self.settings_win = win

        # Responsive sizing according to display DPI & resolution
        dpi = getattr(self, 'dpi_scale', DPI_SCALE)
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        ww = max(540, int(540 * min(1.8, max(1.0, dpi))))
        wh = max(720, int(720 * min(1.8, max(1.0, dpi))))
        wh = min(wh, sh - 60)
        ww = min(ww, sw - 60)
        wx = max(30, (sw - ww) // 2)
        wy = max(30, (sh - wh) // 2)
        win.geometry(f"{ww}x{wh}+{wx}+{wy}")
        win.minsize(500, 480)
        win.resizable(True, True)

        fnt_title = ('Segoe UI', 12, 'bold')
        fnt_sec = ('Segoe UI', 9, 'bold')
        fnt_body = ('Segoe UI', 9)
        fnt_sub = ('Segoe UI', 8)

        # Pinned Bottom Action Buttons
        btn_row = tk.Frame(win, bg='#222222', padx=18, pady=10, highlightthickness=1, highlightbackground='#333333')
        btn_row.pack(fill='x', side='bottom')
        tk.Button(btn_row, text="💾 Lưu Cài Đặt", font=fnt_sec, bg=self.green, fg='#000000', padx=14, relief='flat', cursor='hand2', command=self.save_settings).pack(side='right', padx=(8, 0), ipady=4)
        tk.Button(btn_row, text="Đóng", font=fnt_body, bg='#383838', fg='#bbbbbb', padx=12, relief='flat', cursor='hand2', command=win.destroy).pack(side='right', ipady=4)

        # Scrollable Canvas
        canvas = tk.Canvas(win, bg=self.bg, highlightthickness=0)
        v_scroll = tk.Scrollbar(win, orient="vertical", command=canvas.yview)
        pad = tk.Frame(canvas, bg=self.bg, padx=14, pady=10)

        def _on_frame_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))

        pad.bind("<Configure>", _on_frame_configure)
        canvas_window = canvas.create_window((0, 0), window=pad, anchor="nw", width=ww - 20)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_window, width=max(460, e.width - 24)))
        canvas.configure(yscrollcommand=v_scroll.set)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _on_win_destroy(event):
            if event.widget == win:
                canvas.unbind_all("<MouseWheel>")

        win.bind("<Destroy>", _on_win_destroy)

        canvas.pack(side="left", fill="both", expand=True)
        v_scroll.pack(side="right", fill="y")

        # Header
        tk.Label(pad, text="⚙️ CÀI ĐẶT VOICE-TO-TEXT", font=fnt_title, bg=self.bg, fg=self.yellow).pack(anchor='w')
        tk.Label(pad, text="Tùy chỉnh AI ngữ cảnh Gemini, phím tắt, tọa độ click và micro", font=fnt_sub, bg=self.bg, fg='#888888').pack(anchor='w', pady=(2, 8))

        # Card 0: Google Gemini Flash Context Corrector
        card_ai = tk.Frame(pad, bg='#18232c', padx=12, pady=10, highlightthickness=1, highlightbackground='#00b4d8')
        card_ai.pack(fill='x', pady=(0, 8))

        tk.Label(card_ai, text="✨ AI NGỮ CẢNH THÔNG MINH (GOOGLE GEMINI FLASH):", font=fnt_sec, bg='#18232c', fg='#00d2ff').pack(anchor='w', pady=(0, 4))

        self.gemini_enabled_var = tk.BooleanVar(value=getattr(self, 'gemini_enabled', True))
        cb_ai = tk.Checkbutton(
            card_ai, text="Bật AI tự động đoán & sửa từ nghe nhầm theo ngữ cảnh câu",
            variable=self.gemini_enabled_var, font=fnt_body, bg='#18232c', fg='#ffffff',
            selectcolor='#101920', activebackground='#18232c', activeforeground='#00d2ff', cursor='hand2'
        )
        cb_ai.pack(anchor='w', pady=(1, 6))

        # API Key Row
        row_key = tk.Frame(card_ai, bg='#18232c')
        row_key.pack(fill='x', pady=(2, 4))
        tk.Label(row_key, text="Gemini API Key:", font=fnt_sec, bg='#18232c', fg='#dddddd').pack(side='left', padx=(0, 6))

        self.gemini_key_var = tk.StringVar(value=getattr(self, 'gemini_api_key', ''))
        self._key_entry = tk.Entry(row_key, textvariable=self.gemini_key_var, show="•", font=fnt_body, bg='#101920', fg=self.yellow, insertbackground=self.white)
        self._key_entry.pack(side='left', fill='x', expand=True, padx=(0, 6), ipady=2)

        self._show_key = False
        def _toggle_key_vis():
            self._show_key = not self._show_key
            self._key_entry.config(show="" if self._show_key else "•")
            btn_eye.config(text="🙈" if self._show_key else "👁️")

        btn_eye = tk.Button(row_key, text="👁️", font=fnt_body, bg='#253440', fg='#ffffff', relief='flat', cursor='hand2', width=3, command=_toggle_key_vis)
        btn_eye.pack(side='left', ipady=1)

        # Buttons Row: Test Key + Get Free Key Link
        row_key_btns = tk.Frame(card_ai, bg='#18232c')
        row_key_btns.pack(fill='x', pady=(3, 4))

        tk.Button(
            row_key_btns, text="⚡ Thử Key", font=fnt_sec, bg='#0077b6', fg=self.white,
            relief='flat', cursor='hand2', padx=8, command=self._test_gemini_api_key
        ).pack(side='left', padx=(0, 8), ipady=2)

        def _open_ai_studio():
            webbrowser.open("https://aistudio.google.com/apikey")

        tk.Button(
            row_key_btns, text="🌐 Lấy API Key miễn phí (Google AI Studio)", font=fnt_sub, bg='#203342', fg='#48cae4',
            relief='flat', cursor='hand2', padx=8, command=_open_ai_studio
        ).pack(side='left', ipady=2)

        # Model selection row
        row_model = tk.Frame(card_ai, bg='#18232c')
        row_model.pack(fill='x', pady=(3, 2))
        tk.Label(row_model, text="Model:", font=fnt_sub, bg='#18232c', fg='#999999').pack(side='left', padx=(0, 6))
        self.gemini_model_var = tk.StringVar(value=getattr(self, 'gemini_model', 'gemini-2.5-flash'))
        for m_val, m_label in [('gemini-2.5-flash', 'Gemini 2.5 Flash (Khuyên dùng - Nhanh nhất)'), ('gemini-flash-latest', 'Gemini Flash Latest')]:
            tk.Radiobutton(
                row_model, text=m_label, variable=self.gemini_model_var, value=m_val,
                font=fnt_sub, bg='#18232c', fg='#cccccc', selectcolor='#101920',
                activebackground='#18232c', activeforeground='#00d2ff', cursor='hand2'
            ).pack(side='left', padx=(0, 10))

        tk.Label(card_ai, text="* AI tự động hiểu ngữ cảnh để sửa chính xác: \"cá hợp lý\" ➔ \"Khá hợp lý\", \"tôi yêu\" ➔ \"tối ưu\", \"móp cúp\" ➔ \"mockup\".", font=fnt_sub, bg='#18232c', fg='#7a9aa8', wraplength=440, justify='left').pack(anchor='w', pady=(3, 0))
        tk.Label(card_ai, text="⚡ MẸO: Có thể dùng hoặc không! Khi TẮT Gemini, phần mềm chạy 100% Offline siêu tốc (<50ms) bằng mô hình Sherpa-ONNX Zipformer Vi (0đ, không cần Internet). BẬT khi bạn có key mới.", font=fnt_sub, bg='#18232c', fg='#00d2ff', wraplength=440, justify='left').pack(anchor='w', pady=(3, 0))

        # Card UI Scale: Kích thước giao diện (Phóng to x2, x3)
        card_scale = tk.Frame(pad, bg='#262626', padx=12, pady=10, highlightthickness=1, highlightbackground='#3a3a3a')
        card_scale.pack(fill='x', pady=(0, 8))
        tk.Label(card_scale, text="📏 KÍCH THƯỚC GIAO DIỆN (UI SCALE):", font=fnt_sec, bg='#262626', fg=self.yellow).pack(anchor='w', pady=(0, 4))
        tk.Label(card_scale, text="Tùy chỉnh độ lớn thanh công cụ (phóng to x2, x3) để dễ nhìn & bấm trên mọi màn hình:", font=fnt_sub, bg='#262626', fg='#aaaaaa').pack(anchor='w', pady=(0, 6))

        current_scale = round(float(getattr(self, 'ui_scale', UI_SCALE)), 2)
        self.scale_var = tk.DoubleVar(value=current_scale)

        def _get_scale_desc(val):
            val = round(float(val), 2)
            if abs(val - 2.5) < 0.05:
                return f"Hiện tại: {val:.1f}x (Mặc định chuẩn - 100%)"
            elif abs(val - 5.0) < 0.05:
                return f"Hiện tại: {val:.1f}x (Gấp 2 lần giao diện chuẩn - 200% 🔥)"
            elif abs(val - 7.5) < 0.05:
                return f"Hiện tại: {val:.1f}x (Gấp 3 lần giao diện chuẩn - 300% 🔥)"
            elif abs(val - 1.0) < 0.05:
                return f"Hiện tại: {val:.1f}x (Gốc nhỏ gọn)"
            else:
                ratio = round((val / 2.5) * 100)
                return f"Hiện tại: {val:.2f}x ({ratio}% so với chuẩn)"

        lbl_scale_info = tk.Label(card_scale, text=_get_scale_desc(current_scale), font=fnt_sec, bg='#181818', fg='#00e676', padx=10, pady=4)
        lbl_scale_info.pack(anchor='w', pady=(0, 6), fill='x')

        def _on_slider_change(val):
            try:
                lbl_scale_info.config(text=_get_scale_desc(float(val)))
            except Exception:
                pass

        # Preset Buttons Row
        row_presets = tk.Frame(card_scale, bg='#262626')
        row_presets.pack(fill='x', pady=(0, 6))

        def _set_scale(v):
            self.scale_var.set(v)
            _on_slider_change(v)

        presets = [
            ("1.0x Nhỏ", 1.0, '#383838'),
            ("2.5x Hiện tại", 2.5, '#2980b9'),
            ("5.0x (Gấp 2 lần)", 5.0, '#d35400'),
            ("7.5x (Gấp 3 lần)", 7.5, '#c0392b')
        ]
        for p_label, p_val, p_bg in presets:
            btn_p = tk.Button(
                row_presets, text=p_label, font=fnt_sub, bg=p_bg, fg=self.white,
                relief='flat', cursor='hand2', padx=8, pady=3,
                command=lambda v=p_val: _set_scale(v)
            )
            btn_p.pack(side='left', padx=(0, 6))

        # Slider for fine-tuning
        row_slider = tk.Frame(card_scale, bg='#262626')
        row_slider.pack(fill='x', pady=(2, 0))
        scale_slider = tk.Scale(
            row_slider, from_=1.0, to=7.5, resolution=0.25, orient='horizontal',
            variable=self.scale_var, command=_on_slider_change,
            bg='#262626', fg=self.yellow, activebackground=self.yellow,
            troughcolor='#181818', highlightthickness=0, showvalue=False
        )
        scale_slider.pack(fill='x', expand=True, side='left')

        tk.Label(card_scale, text="* Tự động co giãn thanh công cụ ngay lập tức khi bấm '💾 Lưu Cài Đặt'.", font=fnt_sub, bg='#262626', fg='#888888').pack(anchor='w', pady=(4, 0))

        # Card 1: Coordinate
        card1 = tk.Frame(pad, bg='#262626', padx=12, pady=10, highlightthickness=1, highlightbackground='#3a3a3a')
        card1.pack(fill='x', pady=(0, 8))
        tk.Label(card1, text="🎯 Tọa độ Click Ô Chat (X, Y):", font=fnt_sec, bg='#262626', fg=self.white).pack(anchor='w', pady=(0, 5))
        row1 = tk.Frame(card1, bg='#262626')
        row1.pack(fill='x')
        self.coord_var = tk.StringVar(value=f"{self.click_x}, {self.click_y}")
        e_coord = tk.Entry(row1, textvariable=self.coord_var, font=fnt_body, bg='#181818', fg=self.yellow, insertbackground=self.white, width=15)
        e_coord.pack(side='left', padx=(0, 8), ipady=3)
        tk.Button(row1, text="🎯 Bắt tọa độ (3s)", font=fnt_sec, bg='#2980b9', fg=self.white, relief='flat', cursor='hand2', command=self._start_record_coord).pack(side='left', padx=(0, 6), ipady=2)
        tk.Button(row1, text="⚡ Thử Click", font=fnt_body, bg='#383838', fg='#dddddd', relief='flat', cursor='hand2', command=self._test_click_coord).pack(side='left', ipady=2)

        self.use_fixed_coord_var = tk.BooleanVar(value=getattr(self, 'use_fixed_coord', False))
        cb_fixed = tk.Checkbutton(
            card1, text="Tự động click chuột vào tọa độ này khi ấn V / A",
            variable=self.use_fixed_coord_var, font=fnt_body, bg='#262626', fg='#e0e0e0',
            selectcolor='#181818', activebackground='#262626', activeforeground=self.yellow, cursor='hand2'
        )
        cb_fixed.pack(anchor='w', pady=(6, 0))
        tk.Label(card1, text="* Mặc định TẮT: Dán trực tiếp vào ô chat đang gõ (Facebook, Web...) không bao giờ mất chuột.", font=fnt_sub, bg='#262626', fg='#888888').pack(anchor='w', pady=(2, 0))

        # Card 2: Click to Finish & Paste + Enter
        card_click = tk.Frame(pad, bg='#262626', padx=12, pady=10, highlightthickness=1, highlightbackground='#3a3a3a')
        card_click.pack(fill='x', pady=(0, 8))
        tk.Label(card_click, text="🖱️ Click Chuột Trái để Ngắt & Gửi (Paste + Enter):", font=fnt_sec, bg='#262626', fg=self.white).pack(anchor='w', pady=(0, 4))
        self.auto_paste_enter_var = tk.BooleanVar(value=getattr(self, 'auto_paste_enter_on_click', True))
        cb_click = tk.Checkbutton(
            card_click, text="Đang nói click chuột trái vào đâu sẽ dừng ngay và tự động Paste + Enter",
            variable=self.auto_paste_enter_var, font=fnt_body, bg='#262626', fg='#e0e0e0',
            selectcolor='#181818', activebackground='#262626', activeforeground=self.yellow, cursor='hand2'
        )
        cb_click.pack(anchor='w', pady=(2, 4))

        row_delay = tk.Frame(card_click, bg='#262626')
        row_delay.pack(fill='x', pady=(2, 0))
        tk.Label(row_delay, text="Độ trễ giữa Paste và Enter (giây):", font=fnt_sub, bg='#262626', fg='#aaaaaa').pack(side='left', padx=(0, 6))
        self.paste_delay_var = tk.StringVar(value=str(getattr(self, 'paste_enter_delay', 0.3)))
        e_delay = tk.Entry(row_delay, textvariable=self.paste_delay_var, font=fnt_body, bg='#181818', fg=self.yellow, insertbackground=self.white, width=6)
        e_delay.pack(side='left', ipady=1)
        tk.Label(row_delay, text="s (Mặc định: 0.3 giây)", font=fnt_sub, bg='#262626', fg='#777777').pack(side='left', padx=(6, 0))

        # Card 3: Silence Timeout
        card2 = tk.Frame(pad, bg='#262626', padx=12, pady=10, highlightthickness=1, highlightbackground='#3a3a3a')
        card2.pack(fill='x', pady=(0, 8))
        tk.Label(card2, text="⏱️ Độ trễ ngắt câu khi im lặng (giây):", font=fnt_sec, bg='#262626', fg=self.white).pack(anchor='w', pady=(0, 5))
        self.silence_var = tk.StringVar(value=str(self.silence_timeout))
        e_silence = tk.Entry(card2, textvariable=self.silence_var, font=fnt_body, bg='#181818', fg=self.yellow, insertbackground=self.white, width=12)
        e_silence.pack(anchor='w', ipady=3)
        tk.Label(card2, text="* Thời gian im lặng trước khi dứt câu (Mặc định: 0.75s).", font=fnt_sub, bg='#262626', fg='#777777').pack(anchor='w', pady=(6, 0))

        # Card 4: Language Mode
        card3 = tk.Frame(pad, bg='#262626', padx=12, pady=10, highlightthickness=1, highlightbackground='#3a3a3a')
        card3.pack(fill='x', pady=(0, 8))
        tk.Label(card3, text="🌐 Chế độ Ngôn ngữ nhận diện:", font=fnt_sec, bg='#262626', fg=self.white).pack(anchor='w', pady=(0, 6))
        self.lang_mode_var = tk.StringVar(value=getattr(self, 'lang_mode', 'auto'))
        for val, text in [
            ('auto', '🌐 Tự động (Song ngữ VI + EN)'),
            ('vi', '🇻🇳 Ưu tiên Tiếng Việt'),
            ('en', '🇺🇸 Chỉ Tiếng Anh (English Only)')
        ]:
            tk.Radiobutton(
                card3, text=text, variable=self.lang_mode_var, value=val,
                font=fnt_body, bg='#262626', fg='#e0e0e0', selectcolor='#181818',
                activebackground='#262626', activeforeground=self.yellow, cursor='hand2'
            ).pack(anchor='w', pady=1)

        # Card 5: Global Hotkeys
        card4 = tk.Frame(pad, bg='#262626', padx=12, pady=10, highlightthickness=1, highlightbackground='#3a3a3a')
        card4.pack(fill='x', pady=(0, 10))
        tk.Label(card4, text="⌨️ Phím tắt toàn hệ thống (Global Hotkeys):", font=fnt_sec, bg='#262626', fg=self.white).pack(anchor='w', pady=(0, 5))
        tk.Label(card4, text="• Ctrl + L : Bật / Tắt Mic thu âm giọng nói", font=fnt_body, bg='#262626', fg='#40ff88').pack(anchor='w', pady=1)
        tk.Label(card4, text="• Ctrl + S : Dừng / Hủy thu âm hoặc dừng task", font=fnt_body, bg='#262626', fg='#ff6666').pack(anchor='w', pady=1)

        # Card 6: Auto-Update (GitHub Releases)
        card_update = tk.Frame(pad, bg='#1c252d', padx=12, pady=10, highlightthickness=1, highlightbackground='#2a485e')
        card_update.pack(fill='x', pady=(0, 10))
        tk.Label(card_update, text="🚀 CẬP NHẬT PHẦN MỀM (AUTO-UPDATE GITHUB):", font=fnt_sec, bg='#1c252d', fg='#48cae4').pack(anchor='w', pady=(0, 4))

        row_ver = tk.Frame(card_update, bg='#1c252d')
        row_ver.pack(fill='x', pady=(2, 4))
        tk.Label(row_ver, text=f"Phiên bản hiện tại: v{APP_VERSION} (Streaming ASR)", font=fnt_sec, bg='#1c252d', fg='#48cae4').pack(side='left')
        tk.Button(
            row_ver, text="🔄 Kiểm tra cập nhật ngay", font=fnt_sub, bg='#0077b6', fg=self.white,
            relief='flat', cursor='hand2', padx=10, command=self.check_updates_interactive
        ).pack(side='right', ipady=2)

        self.auto_update_var = tk.BooleanVar(value=getattr(self, 'auto_check_update', True))
        cb_update = tk.Checkbutton(
            card_update, text="Tự động kiểm tra bản mới nhất từ GitHub khi khởi động",
            variable=self.auto_update_var, font=fnt_body, bg='#1c252d', fg='#dddddd',
            selectcolor='#101920', activebackground='#1c252d', activeforeground='#48cae4', cursor='hand2'
        )
        cb_update.pack(anchor='w', pady=(2, 3))

        tk.Label(card_update, text=f"• GitHub: https://github.com/{getattr(self, 'github_repo', GITHUB_REPO)}", font=fnt_sub, bg='#1c252d', fg='#7d9bb0').pack(anchor='w')

    def _start_record_coord(self):
        self.show_temp_status("Click mục tiêu!", self.yellow, 4000)
        def _rec():
            time.sleep(2.5)
            pt = pyautogui.position()
            self.click_x = pt.x
            self.click_y = pt.y
            if self.coord_var:
                self.coord_var.set(f"{pt.x}, {pt.y}")
            self.save_config()
            try:
                winsound.Beep(2000, 100)
            except Exception:
                pass
            self.show_temp_status(f"Ghi: {pt.x},{pt.y}", self.green)
        threading.Thread(target=_rec, daemon=True).start()

    def _test_click_coord(self):
        self.show_temp_status("Testing...", self.yellow)
        def _test():
            time.sleep(0.5)
            pyautogui.click(self.click_x, self.click_y)
            self.show_temp_status("Clicked!", self.green)
        threading.Thread(target=_test, daemon=True).start()

    def save_settings(self):
        try:
            parts = [p.strip() for p in self.coord_var.get().split(',')]
            self.click_x = int(parts[0])
            self.click_y = int(parts[1])
            self.silence_timeout = float(self.silence_var.get())
            self.rec.pause_threshold = self.silence_timeout
            if hasattr(self, 'lang_mode_var') and self.lang_mode_var:
                self.lang_mode = self.lang_mode_var.get()
            if hasattr(self, 'use_fixed_coord_var') and self.use_fixed_coord_var:
                self.use_fixed_coord = bool(self.use_fixed_coord_var.get())
            if hasattr(self, 'auto_paste_enter_var') and self.auto_paste_enter_var:
                self.auto_paste_enter_on_click = bool(self.auto_paste_enter_var.get())
            if hasattr(self, 'paste_delay_var') and self.paste_delay_var:
                try:
                    self.paste_enter_delay = max(0.05, float(self.paste_delay_var.get()))
                except Exception:
                    self.paste_enter_delay = 0.3
            if hasattr(self, 'gemini_enabled_var') and self.gemini_enabled_var:
                self.gemini_enabled = bool(self.gemini_enabled_var.get())
            if hasattr(self, 'gemini_key_var') and self.gemini_key_var:
                self.gemini_api_key = self.gemini_key_var.get().strip()
            if hasattr(self, 'gemini_model_var') and self.gemini_model_var:
                self.gemini_model = self.gemini_model_var.get().strip() or 'gemini-2.5-flash'
            if hasattr(self, 'scale_var') and self.scale_var:
                try:
                    new_scale = round(float(self.scale_var.get()), 2)
                    if new_scale > 0 and abs(new_scale - getattr(self, 'ui_scale', UI_SCALE)) > 0.01:
                        self.ui_scale = new_scale
                        self.rebuild_toolbar()
                except Exception as ex:
                    self._log_error(f"save_settings ui_scale: {ex}")
            if hasattr(self, 'auto_update_var') and self.auto_update_var:
                self.auto_check_update = bool(self.auto_update_var.get())
            self.save_config()
            self.update_gemini_border_status()
            if self.settings_win:
                self.settings_win.destroy()
            self.show_temp_status("Đã lưu!", self.green)
        except Exception as e:
            messagebox.showerror("Lỗi", f"Giá trị không hợp lệ: {e}")

    def _start_background_update_check(self):
        """Silently checks for updates in background on startup."""
        if not getattr(self, 'auto_check_update', True):
            return

        def _worker():
            repo = getattr(self, 'github_repo', GITHUB_REPO)
            info = check_github_update(repo=repo, current_ver=APP_VERSION, timeout=8.0)
            if info.get('has_update'):
                try:
                    self.root.after(0, lambda: self._prompt_update_dialog(info))
                except Exception:
                    pass

        threading.Thread(target=_worker, daemon=True).start()

    def check_updates_interactive(self):
        """Manual check triggered from context menu or settings button."""
        self.show_temp_status("Checking...", self.yellow, 3000)

        def _worker():
            repo = getattr(self, 'github_repo', GITHUB_REPO)
            info = check_github_update(repo=repo, current_ver=APP_VERSION, timeout=8.0)
            try:
                if info.get('has_update'):
                    self.root.after(0, lambda: self._prompt_update_dialog(info))
                elif info.get('error'):
                    self.root.after(0, lambda: messagebox.showwarning(
                        "Kiểm tra cập nhật",
                        f"Không thể kiểm tra cập nhật:\n{info['error']}\n\nVui lòng kiểm tra lại kết nối mạng hoặc thử lại sau."
                    ))
                else:
                    self.root.after(0, lambda: messagebox.showinfo(
                        "Cập nhật phần mềm",
                        f"Bạn đang sử dụng phiên bản mới nhất (v{APP_VERSION})!\nKhông có bản cập nhật mới nào."
                    ))
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def _prompt_update_dialog(self, info):
        """Displays a clean modal dialog when a new release is detected."""
        latest_ver = info.get('latest_ver', 'Mới')
        release_name = info.get('release_name') or f"Phiên bản {latest_ver}"
        body = info.get('body', '').strip()
        asset_size = info.get('asset_size', 0)
        size_str = f" • Dung lượng: {asset_size / (1024 * 1024):.1f} MB" if asset_size > 0 else ""

        dlg = tk.Toplevel(self.root)
        dlg.title(f"Cập nhật mới: {latest_ver}")
        dlg.configure(bg='#1e1e1e')
        dlg.attributes('-topmost', True)
        dlg.resizable(True, True)

        # Responsive sizing according to display DPI & resolution (prevents cramped shrunken window)
        dpi = getattr(self, 'dpi_scale', DPI_SCALE)
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        dw = max(580, int(580 * min(1.8, max(1.0, dpi))))
        dh = max(460, int(460 * min(1.8, max(1.0, dpi))))
        dw = min(dw, sw - 60)
        dh = min(dh, sh - 60)
        dx = max(30, (sw - dw) // 2)
        dy = max(30, (sh - dh) // 2)
        dlg.geometry(f"{dw}x{dh}+{dx}+{dy}")
        dlg.minsize(520, 380)

        fnt_h = ('Segoe UI', 11, 'bold')
        fnt_sub = ('Segoe UI', 9)
        fnt_btn = ('Segoe UI', 9, 'bold')

        def _do_update():
            dlg.destroy()
            self._start_download_and_apply(info)

        def _do_browser():
            if info.get('html_url'):
                webbrowser.open(info['html_url'])

        # CRITICAL FIX: Pack Action Button bar (bf) FIRST at side='bottom'
        # This guarantees buttons are NEVER clipped or pushed off-screen regardless of window size!
        bf = tk.Frame(dlg, bg='#181818', padx=16, pady=12, highlightthickness=1, highlightbackground='#2c2c2c')
        bf.pack(fill='x', side='bottom')

        btn_up = tk.Button(bf, text="⚡ Cập Nhật Tự Động Ngay", font=fnt_btn, bg=self.green, fg='#000000', padx=16, relief='flat', cursor='hand2', command=_do_update)
        btn_up.pack(side='right', padx=(10, 0), ipady=6)

        btn_gh = tk.Button(bf, text="🌐 GitHub", font=fnt_sub, bg='#0077b6', fg='#ffffff', padx=12, relief='flat', cursor='hand2', command=_do_browser)
        btn_gh.pack(side='right', padx=(8, 0), ipady=6)

        btn_skip = tk.Button(bf, text="Để Sau", font=fnt_sub, bg='#383838', fg='#bbbbbb', padx=12, relief='flat', cursor='hand2', command=dlg.destroy)
        btn_skip.pack(side='right', ipady=6)

        # Header frame
        hf = tk.Frame(dlg, bg='#14222d', padx=16, pady=12, highlightthickness=1, highlightbackground='#00b4d8')
        hf.pack(fill='x', side='top')
        tk.Label(hf, text=f"🚀 Phát Hiện Phiên Bản Mới: {latest_ver}", font=fnt_h, bg='#14222d', fg='#00e5ff').pack(anchor='w')
        tk.Label(hf, text=f"Phiên bản hiện tại: v{APP_VERSION}{size_str}", font=fnt_sub, bg='#14222d', fg='#90b4ce').pack(anchor='w', pady=(2, 0))

        # Content frame (Release notes)
        cf = tk.Frame(dlg, bg='#1e1e1e', padx=16, pady=8)
        cf.pack(fill='both', expand=True)

        tk.Label(cf, text=f"Nội dung cập nhật ({release_name}):", font=fnt_btn, bg='#1e1e1e', fg='#ffffff').pack(anchor='w', pady=(2, 4))

        txt_frame = tk.Frame(cf, bg='#252526', highlightthickness=1, highlightbackground='#3a3a3a')
        txt_frame.pack(fill='both', expand=True)

        scroll = tk.Scrollbar(txt_frame)
        txt = tk.Text(txt_frame, wrap='word', font=('Segoe UI', 9), bg='#252526', fg='#cccccc', yscrollcommand=scroll.set, bd=0, padx=10, pady=8)
        scroll.config(command=txt.yview)
        scroll.pack(side='right', fill='y')
        txt.pack(side='left', fill='both', expand=True)

        if body:
            txt.insert('1.0', body)
        else:
            txt.insert('1.0', f"Bản cập nhật {latest_ver} với các cải tiến và sửa lỗi mới nhất từ GitHub Releases.")
        txt.config(state='disabled')

        # Keyboard shortcuts and default focus for quick update
        btn_up.focus_set()
        dlg.bind('<Return>', lambda e: _do_update())
        dlg.bind('<KP_Enter>', lambda e: _do_update())
        dlg.bind('<Escape>', lambda e: dlg.destroy())

    def _start_download_and_apply(self, info):
        """Downloads the new release exe in a background thread with toolbar progress and triggers restart."""
        download_url = info.get('download_url')
        if not download_url:
            if info.get('html_url'):
                webbrowser.open(info['html_url'])
            messagebox.showinfo("Cập nhật", "Không tìm thấy file thực thi trực tiếp (.exe) trên Release.\nĐã mở trang GitHub để bạn tải thủ công.")
            return

        base_dir = get_base_dir()
        temp_exe = os.path.join(base_dir, "voice_to_text_update.tmp")

        self.show_temp_status("Tải: 0%", self.green, 60000)

        def _worker():
            def _progress(down, total, pct):
                pct_str = f"Tải: {pct}%" if pct > 0 else "Tải..."
                try:
                    self.root.after(0, lambda: self.status.config(text=pct_str, fg=self.green))
                except Exception:
                    pass

            try:
                # 1. Download updated exe
                download_update_file(download_url, temp_exe, progress_callback=_progress, timeout=120.0)

                # 2. Also sync voice_to_text.py if python source file exists
                py_file = os.path.join(base_dir, "voice_to_text.py")
                if os.path.exists(py_file):
                    repo = getattr(self, 'github_repo', GITHUB_REPO)
                    raw_py_url = f"https://raw.githubusercontent.com/{repo}/main/voice_to_text.py"
                    try:
                        raw_req = urllib.request.Request(raw_py_url, headers={"User-Agent": f"VoiceToText-App/{APP_VERSION}"})
                        with urllib.request.urlopen(raw_req, timeout=10.0) as raw_resp:
                            if raw_resp.status == 200:
                                py_content = raw_resp.read()
                                if len(py_content) > 1000:
                                    with open(py_file, 'wb') as pf:
                                        pf.write(py_content)
                    except Exception:
                        pass

                # 3. Inform user and launch updater
                try:
                    self.root.after(0, lambda: self.status.config(text="Khởi động...", fg=self.yellow))
                except Exception:
                    pass

                time.sleep(0.5)
                launch_updater_and_restart(temp_exe)

                # Close current app to release locks
                self.root.after(100, lambda: self.close_app())
            except Exception as e:
                err_msg = str(e)
                try:
                    self.root.after(0, lambda: self.show_temp_status("Lỗi tải!", self.red, 3000))
                    self.root.after(0, lambda: messagebox.showerror("Lỗi Cập Nhật", f"Không thể tải bản cập nhật:\n{err_msg}"))
                except Exception:
                    pass

        threading.Thread(target=_worker, daemon=True).start()

    def close_app(self, e=None):
        self._log_error(f"close_app was triggered with event: {e}")
        self.app_running = False
        if hasattr(self, '_hotkey_tid') and self._hotkey_tid:
            try:
                ctypes.windll.user32.PostThreadMessageW(self._hotkey_tid, 0x0012, 0, 0)
            except Exception:
                pass
        self._remember_window_position()
        self.save_config()
        self.root.destroy()
        sys.exit(0)


def attach_to_default_desktop():
    if sys.platform != 'win32':
        return
    try:
        user32 = ctypes.windll.user32
        h_desk = user32.OpenDesktopW("default", 0, False, 0x01FF)
        if h_desk:
            user32.SetThreadDesktop(h_desk)
    except Exception:
        pass


def main():
    try:
        attach_to_default_desktop()
        set_windows_app_id()
        root = tk.Tk()
        app = App(root)
        root.mainloop()
    except Exception as e:
        import traceback
        with open(os.path.join(get_base_dir(), 'app_crash.log'), 'w', encoding='utf-8') as f:
            f.write(traceback.format_exc())


if __name__ == '__main__':
    main()
