"""Telegram Bot 发送模块: 把已下载的视频发送到群聊并附带归档评论。

用法 (被 main.py 调用):
    from telegram_bot import build_caption, send_video

    ok, err = send_video(
        token=os.environ["TELEGRAM_BOT_TOKEN"],
        chat_id=os.environ["TELEGRAM_CHAT_ID"],
        title="【小酒对瓶吹】日本专题: xxx",
        filepath=Path("downloads/xxx.mp4"),
    )

依赖 requests。视频超过 Telegram Bot API 上传上限(默认 50MB)时
自动用 ffmpeg 压缩到限制内再上传, 原始文件保持不变。
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Callable

import requests

DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # Telegram Bot API 单文件上传上限
CHANNEL_PREFIX_RE = re.compile(r"^[【\[]\s*小酒对瓶吹\s*[】\]]\s*")
TAG_SPLIT_RE = re.compile(r"[：:｜|\-_—\s]+")
TAG_CLEAN_RE = re.compile(r"[^\w\u4e00-\u9fff]+")  # hashtag 只保留字母数字/下划线/中文


def build_caption(title: str) -> str:
    """生成归档评论: `#视频归档 #<专题tag>`。

    I. tag 提取规则
    1. 去掉标题开头【小酒对瓶吹】前缀
    2. 取剩余文本第一个分隔符(： | - 空格等)之前的短语作为专题名
    3. 清理为合法 hashtag 字符
       (1) 例: 【小酒对瓶吹】日本专题: 攻略 -> #视频归档 #日本专题
       (2) 例: 【小酒对瓶吹】M05一期聊透: ... -> #视频归档 #M05一期聊透
    II. 兜底
    1. 无法提取时仅保留固定 tag #视频归档
    """
    text = CHANNEL_PREFIX_RE.sub("", (title or "").strip())
    # 取第一个分隔符前的部分作为 tag
    tag = TAG_SPLIT_RE.split(text, maxsplit=1)[0]
    tag = TAG_CLEAN_RE.sub("", tag).strip()
    if not tag:
        return "#视频归档"
    return f"#视频归档 #{tag}"


def get_duration(path: Path) -> float:
    """用 ffprobe 获取视频时长(秒), 失败时返回 0。"""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(path),
            ],
            capture_output=True, text=True, timeout=120,
        )
        return float(result.stdout.strip() or 0)
    except (OSError, subprocess.SubprocessError, ValueError):
        return 0.0


def compress_to_size(
    src: Path,
    max_bytes: int,
    workdir: Path | None = None,
) -> Path | None:
    """用 ffmpeg 把 src 压缩到 max_bytes 以内, 返回新文件路径; 失败返回 None。"""
    duration = get_duration(src)
    if duration <= 0:
        return None

    # I. 计算目标码率
    # 1. 总码率 = 目标大小 / 时长, 预留 10% 容器与交错开销
    total_bps = int(max_bytes * 8 * 0.9 / duration)
    # 2. 音频固定 96k, 剩余给视频; 视频最低 200k 保证画面可用
    video_bps = max(200_000, total_bps - 96_000)

    # II. 压缩
    dst_dir = workdir or src.parent
    dst = dst_dir / f"{src.stem}.telegram.mp4"
    vk = video_bps // 1000
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-i", str(src),
        "-c:v", "libx264", "-preset", "veryfast",
        "-b:v", f"{vk}k",
        "-maxrate", f"{int(vk * 1.2)}k",
        "-bufsize", f"{vk * 2}k",
        "-c:a", "aac", "-b:a", "96k",
        "-movflags", "+faststart",
        str(dst),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=1800)
    except (OSError, subprocess.SubprocessError):
        return None
    return dst if dst.exists() else None


def send_video(
    token: str,
    chat_id: str,
    title: str,
    filepath: Path,
    max_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
) -> tuple[bool, str]:
    """把视频发送到 Telegram 群聊, 返回 (是否成功, 错误信息)。

    超过 max_bytes 时自动压缩; 压缩使用临时副本, 不修改原始文件。
    """
    caption = build_caption(title)
    upload_path = filepath
    compressed_path: Path | None = None

    try:
        if filepath.stat().st_size > max_bytes:
            compressed_path = compress_to_size(filepath, max_bytes)
            if compressed_path is None:
                return False, "文件超过上传限制且自动压缩失败"
            upload_path = compressed_path

        with open(upload_path, "rb") as f:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendVideo",
                data={
                    "chat_id": chat_id,
                    "caption": caption,
                },
                files={"video": (upload_path.name, f)},
                timeout=600,
            )
        try:
            payload = resp.json()
        except ValueError:
            return False, f"Telegram 响应无法解析 (HTTP {resp.status_code})"
        if not payload.get("ok"):
            desc = payload.get("description") or "未知错误"
            return False, f"Telegram API 错误: {desc}"
        return True, ""
    except requests.RequestException as exc:
        return False, f"请求 Telegram 失败: {exc}"
    finally:
        if compressed_path is not None and compressed_path.exists():
            compressed_path.unlink()


def make_sender(
    token: str,
    chat_id: str,
    max_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
) -> Callable[[str, Path], tuple[bool, str]]:
    """返回发送函数, 供 main.py 在下载完成后调用: sender(title, filepath) -> (ok, err)。"""
    def sender(title: str, filepath: Path) -> tuple[bool, str]:
        return send_video(token, chat_id, title, filepath, max_bytes)

    return sender
