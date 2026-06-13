"""
keyboard_typing.py
读取纯文本文件，通过模拟按键操作将其内容输入到目标窗口。
适用场景：环境禁止复制粘贴，需通过键盘模拟方式将文本内容同步到目标文件。

依赖安装：
    pip install keyboard

使用方式：
    以管理员权限运行本脚本：
        python keyboard_typing.py
    运行后有 10 秒倒计时，请在倒计时结束前切换到目标编辑器窗口。
    倒计时结束后脚本将自动开始模拟键盘输入。

    紧急停止：
        按 Esc 键可随时中止输入。

两种工作模式：
    A. 逐字模拟输入 (USE_CLIPBOARD = False，默认)
       通过模拟键盘逐字输入，可跨越远程桌面/虚拟机等剪贴板隔离环境。
       速度受目标窗口吞吐限制，用 WRITE_DELAY 调节“速度 vs 准确”。
    B. 剪贴板模式 (USE_CLIPBOARD = True)
       一次 Ctrl+V 粘贴，瞬时且零错误，但【仅在本机与目标窗口
       共享剪贴板时可用】。远程桌面/虚拟机等隔离环境无法使用。

速度与准确的权衡（仅逐字模式）：
    隔离/远程窗口带宽有限，WRITE_DELAY 太小会丢字、错位、重复。
    丢字就调大 WRITE_DELAY 或 LINE_PAUSE；稳定后可逐步调小提速。

注意：
    1. 运行前将输入法切换为英文。
    2. 记事本(Notepad)用默认配置即可。
    3. 逐字模式下若用 VSCode 等智能编辑器，需将
       EDITOR_AUTO_INDENT / DISMISS_SUGGESTIONS 设为 True，
       并在 VSCode settings.json 中关闭自动补全 / 自动闭合等功能。
"""

import ctypes
import os
import sys
import time
from ctypes import wintypes

try:
    import keyboard
except ImportError:
    print("缺少依赖: keyboard")
    print("请运行: pip install keyboard")
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_NAME = os.path.basename(__file__)
CANDIDATE_EXTENSIONS = (
    ".json",
    ".txt",
    ".csv",
    ".xml",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
    ".log",
    ".md",
    ".py",
)
COUNTDOWN_SECONDS = 10
TYPING_DELAY = 0.03
ENTER_DELAY = 0.03
EXTRA_DELAY = 0.05
ESC_CHECK_INTERVAL = 50

# 剪贴板模式：把整个文件放入剪贴板后一次 Ctrl+V 粘贴，瞬时且零错误。
# 仅在【本机与目标窗口共享剪贴板】时可用。
# 若目标是远程桌面/虚拟机/沙箱等剪贴板隔离环境，必须设为 False。
USE_CLIPBOARD = False

# ↓↓↓ 以下为逐字模拟输入参数（USE_CLIPBOARD = False 时生效）↓↓↓

# 整行一次性写入（仍按 WRITE_DELAY 控制字符间隔），代码开销比纯逐字循环小。
FAST_WRITE = True

# 每个字符之间的间隔(秒)，是“速度 vs 准确”的核心旋钮：
#   远程桌面/虚拟机等隔离窗口带宽有限，发太快会丢字/错位/重复。
#   - 本地记事本：可试 0.002~0.004
#   - 远程桌面/虚拟机：建议 0.006~0.012，丢字就再调大
# 6000 行(约 24 万字符)耗时 ≈ 字符数 × WRITE_DELAY，请据此权衡。
WRITE_DELAY = 0.008

# 每行写完、换行前的额外停顿(秒)，给远程窗口一点缓冲消化时间。
LINE_PAUSE = 0.0

# 目标编辑器是否会在换行时自动复制上一行缩进。
# 记事本(Notepad)不会，设为 False 直接逐字输入整行；
# VSCode 等会自动缩进，设为 True 启用缩进补偿。
EDITOR_AUTO_INDENT = False

# 换行前按 Esc 关闭编辑器的自动补全弹窗（VSCode 等需要）。
# 记事本无补全弹窗，应设为 False。
DISMISS_SUGGESTIONS = False
DISMISS_DELAY = 0.03

# XML/HTML 等敏感字符，编辑器可能拦截或自动改写，需额外等待
SENSITIVE_CHARS = frozenset("/<>\"'=")


def split_leading_whitespace(line):
    index = 0
    while index < len(line) and line[index] in " \t":
        index += 1
    return line[:index], line[index:]


def common_prefix_length(a, b):
    length = min(len(a), len(b))
    for index in range(length):
        if a[index] != b[index]:
            return index
    return length


def press_key(key):
    keyboard.press_and_release(key)
    time.sleep(TYPING_DELAY)


def type_character(ch):
    # 空格单独按键，避免批量 write 时偶发丢字符
    if ch == " ":
        press_key("space")
        return
    if ch == "\t":
        press_key("tab")
        return

    # 统一用 write 处理可打印字符（含 < > 等需 Shift 的符号），
    # 比手动 press/release shift 更可靠，也兼容不同键盘布局
    try:
        keyboard.write(ch)
    except ValueError:
        keyboard.press_and_release(ch)

    time.sleep(TYPING_DELAY)
    if ch in SENSITIVE_CHARS:
        time.sleep(EXTRA_DELAY)


def check_esc(char_count):
    if char_count > 0 and char_count % ESC_CHECK_INTERVAL == 0:
        if keyboard.is_pressed("esc"):
            print("\n检测到 Esc，输入已中止。")
            return False
        time.sleep(0.01)
    return True


def type_string(text):
    char_count = 0
    for ch in text:
        type_character(ch)
        char_count += 1
        if not check_esc(char_count):
            return False
    return True


def type_line_fast(line):
    # 整行一次性写入，速度远快于逐字符。适用于记事本等无干扰编辑器。
    if keyboard.is_pressed("esc"):
        print("\n检测到 Esc，输入已中止。")
        return False
    if line:
        keyboard.write(line, delay=WRITE_DELAY)
    return True


def apply_line_prefix(prev_prefix, target_prefix):
    common = common_prefix_length(prev_prefix, target_prefix)

    for _ in range(len(prev_prefix) - common):
        press_key("backspace")

    if target_prefix[common:]:
        if not type_string(target_prefix[common:]):
            return False

    return True


def dismiss_suggestions():
    # 关闭可能弹出的自动补全/提示窗口，使随后的 Enter 产生真正的换行。
    if not DISMISS_SUGGESTIONS:
        return
    keyboard.press_and_release("esc")
    time.sleep(DISMISS_DELAY)


def press_enter():
    dismiss_suggestions()
    keyboard.press_and_release("enter")
    time.sleep(ENTER_DELAY)


def set_clipboard_text(text):
    """通过 Windows 原生 API 把文本写入剪贴板（CF_UNICODETEXT）。

    不创建任何窗口，因此不会抢走目标编辑器(记事本)的焦点。
    """
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.OpenClipboard.argtypes = [wintypes.HWND]

    data = text.encode("utf-16-le") + b"\x00\x00"
    size = len(data)

    if not user32.OpenClipboard(None):
        return False
    try:
        user32.EmptyClipboard()
        h_global = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
        if not h_global:
            return False
        lock = kernel32.GlobalLock(h_global)
        if not lock:
            return False
        ctypes.memmove(lock, data, size)
        kernel32.GlobalUnlock(h_global)
        if not user32.SetClipboardData(CF_UNICODETEXT, h_global):
            return False
        return True
    finally:
        user32.CloseClipboard()


def paste_text_content(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 统一换行为 CRLF，确保经典记事本也能正确分行显示。
    content = normalize_content(content).replace("\n", "\r\n")

    if not set_clipboard_text(content):
        print("写入剪贴板失败，无法使用粘贴模式。")
        print("可将 USE_CLIPBOARD 设为 False 改用逐字输入。")
        return False

    keyboard.press_and_release("ctrl+v")
    time.sleep(0.3)
    print("已通过剪贴板粘贴全部内容。")
    return True


def normalize_content(content):
    return content.replace("\r\n", "\n").replace("\r", "\n")


def type_text_content(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = normalize_content(f.read())

    lines = content.split("\n")
    total_lines = len(lines)
    prev_prefix = ""

    for index, line in enumerate(lines):
        if index > 0 and index % ESC_CHECK_INTERVAL == 0:
            if keyboard.is_pressed("esc"):
                print("\n检测到 Esc，输入已中止。")
                return False

        if EDITOR_AUTO_INDENT:
            prefix, body = split_leading_whitespace(line)
            if index == 0:
                if prefix and not type_string(prefix):
                    return False
            elif not apply_line_prefix(prev_prefix, prefix):
                return False
            if body and not type_string(body):
                return False
            prev_prefix = prefix
        elif FAST_WRITE:
            if not type_line_fast(line):
                return False
        else:
            if line and not type_string(line):
                return False

        if LINE_PAUSE > 0:
            time.sleep(LINE_PAUSE)

        if index < total_lines - 1:
            press_enter()

        if (index + 1) % 10 == 0:
            print(f"\r进度: {index + 1}/{total_lines} 行", end="", flush=True)

    print(f"\r进度: {total_lines}/{total_lines} 行 - 输入完成！")
    return True


def countdown(seconds):
    print(f"将在 {seconds} 秒后开始输入，请切换到目标窗口！")
    print("请确认输入法已切换为英文。")
    print("按 Esc 可随时中止。")
    for remaining in range(seconds, 0, -1):
        if keyboard.is_pressed("esc"):
            print("\n已取消。")
            sys.exit(0)
        print(f"\r倒计时: {remaining}...", end="", flush=True)
        time.sleep(1)
    print("\r开始输入！          ")


def cleanup():
    for key in ["shift", "ctrl", "alt", "win"]:
        try:
            keyboard.release(key)
        except Exception:
            pass
    try:
        keyboard.unhook_all()
    except Exception:
        pass


def scan_text_files():
    files = []
    for name in sorted(os.listdir(SCRIPT_DIR)):
        if name == SCRIPT_NAME:
            continue
        if name.lower().endswith(CANDIDATE_EXTENSIONS) and os.path.isfile(
            os.path.join(SCRIPT_DIR, name)
        ):
            files.append(name)
    return files


def choose_file():
    files = scan_text_files()
    if not files:
        print(f"错误: 在 {SCRIPT_DIR} 中未找到可输入的文本文件")
        print(f"支持的扩展名: {', '.join(CANDIDATE_EXTENSIONS)}")
        print(f"注意: 不会输入脚本自身 ({SCRIPT_NAME})")
        sys.exit(1)

    if len(files) == 1:
        print(f"自动选择唯一文件: {files[0]}")
        return os.path.join(SCRIPT_DIR, files[0])

    print("可用文件列表:")
    for idx, name in enumerate(files, 1):
        size = os.path.getsize(os.path.join(SCRIPT_DIR, name))
        print(f"  [{idx}] {name}  ({size:,} bytes)")

    while True:
        try:
            choice = input(f"请选择文件编号 (1-{len(files)}): ").strip()
            num = int(choice)
            if 1 <= num <= len(files):
                return os.path.join(SCRIPT_DIR, files[num - 1])
            print(f"请输入 1 到 {len(files)} 之间的数字")
        except ValueError:
            print("请输入有效的数字")
        except (KeyboardInterrupt, EOFError):
            print("\n已取消。")
            sys.exit(0)


def main():
    print("=" * 50)
    print("文本按键模拟输入工具")
    print("=" * 50)

    input_file = choose_file()
    print(f"输入文件: {input_file}")
    print()

    try:
        with open(input_file, "r", encoding="utf-8") as f:
            f.read()
    except FileNotFoundError:
        print(f"错误: 找不到文件 {input_file}")
        sys.exit(1)

    countdown(COUNTDOWN_SECONDS)

    try:
        if USE_CLIPBOARD:
            success = paste_text_content(input_file)
        else:
            success = type_text_content(input_file)
        if success:
            print("所有内容已成功输入！")
        else:
            print("输入被中止。")
    except Exception as e:
        print(f"\n发生异常: {e}")
        print("输入被中断。")
    finally:
        cleanup()


if __name__ == "__main__":
    main()
