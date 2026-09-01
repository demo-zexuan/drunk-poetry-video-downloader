"""下载指定 YouTube 频道的全部视频(基于 yt-dlp), 并可自动发送到 Telegram 群聊。

用法示例:
    uv run python main.py                        # 下载 https://www.youtube.com/@DrunkPoetry/videos 下所有视频
    uv run python main.py --dry-run              # 只列出所有视频, 不下载
    uv run python main.py --limit 5              # 只下载最新 5 个视频
    uv run python main.py -o ~/Videos/poetry     # 自定义保存目录
    uv run python main.py --cookies cookies.txt  # 遇到年龄限制/需要登录时传入浏览器导出的 cookies
    uv run python main.py --telegram-token <TOKEN> --telegram-chat <CHAT_ID>
                                                # 下载完成并校验通过后发送到 Telegram 群聊
                                                # (也可用环境变量 TELEGRAM_BOT_TOKEN /
                                                #  TELEGRAM_CHAT_ID)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable

from telegram_bot import make_sender
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

DEFAULT_URL = "https://www.youtube.com/@DrunkPoetry/videos"
DEFAULT_OUTPUT_DIR = "downloads"

META_FIELDS = (
    "id",
    "title",
    "uploader",
    "upload_date",
    "duration",
    "view_count",
    "webpage_url",
    "description",
)


def check_disk_space(path: Path, min_free_gb: float = 5.0) -> None:
    """检查目标磁盘是否有足够可用空间，避免下载失败。"""
    try:
        disk = shutil.disk_usage(path)
    except OSError:
        return

    free_gb = disk.free / (1024 ** 3)
    print(f"磁盘剩余空间: {free_gb:.1f} GiB ({path})")
    if free_gb < min_free_gb:
        print(
            f"警告: 可用空间仅 {free_gb:.1f} GiB，低于建议阈值 {min_free_gb:.0f} GiB，下载前请清理空间。",
            file=sys.stderr,
        )


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="drunk-poetry-downloader",
        description="下载 YouTube 频道的所有视频。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "url",
        nargs="?",
        default=DEFAULT_URL,
        help="频道地址(也可以是频道下的任意视频页)",
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=Path,
        default=Path(DEFAULT_OUTPUT_DIR),
        help="视频保存目录",
    )
    parser.add_argument(
        "--archive",
        type=Path,
        default=None,
        help="已下载视频 ID 记录文件(断点续传, 重复运行自动跳过); 默认 <输出目录>/archive.txt",
    )
    parser.add_argument(
        "--format", dest="format_", default=None,
        help="yt-dlp 格式表达式; 默认: 有 ffmpeg 时优先 H.264+AAC(mp4 兼容)组合, 否则 best",
    )
    parser.add_argument("--limit", type=int, default=None,
                        help="只下载最新 N 个视频(频道列表按新到旧排序)")
    parser.add_argument("--cookies", type=Path, default=None,
                        help="Netscape 格式 cookies 文件(可解决年龄限制/登录要求)")
    parser.add_argument("--limit-rate", default=None,
                        help="限速, 如 5M 或 1M/kbps")
    parser.add_argument("--retries", type=int, default=10,
                        help="下载重试次数")
    parser.add_argument("--keep-going", action="store_true",
                        help="单个视频失败不中断, 继续下载其余视频")
    parser.add_argument("--dry-run", action="store_true",
                        help="只列出频道里的所有视频, 不下载")
    parser.add_argument("--telegram-token", default=None,
                        help="Telegram Bot Token; 也读取环境变量 TELEGRAM_BOT_TOKEN")
    parser.add_argument("--telegram-chat", default=None,
                        help="目标群聊/频道 ID; 也读取环境变量 TELEGRAM_CHAT_ID")
    parser.add_argument("--telegram-max-mb", type=int, default=50,
                        help="Telegram 单文件上传上限(MB), 超过时自动压缩再上传")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="关闭进度条和日志")
    return parser


def load_dotenv(path: Path | None = None) -> None:
    """从 .env 文件加载环境变量 (KEY=VALUE), 不覆盖已存在的变量。

    支持 # 注释与引号包裹的值; 供未设置环境变量时读取本地配置。
    路径默认为脚本同目录下的 .env。
    """
    env_path = path or (Path(__file__).resolve().parent / ".env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


def resolve_format(requested: str | None) -> str:
    """确定默认输出格式。

    有 ffmpeg 时:
    1. 优先 mp4 兼容组合 (H.264 + AAC), 保证任何播放器都有画面和声音;
    2. 回退 bestvideo+bestaudio 由 yt-dlp 自动选择合适容器 (如 webm/mkv);
    3. 最后单文件最佳。

    避免默认选中 AV1/VP9 + Opus 的高画质组合 -- 这类格式在 mp4 容器中
    很多播放器(尤其 macOS QuickTime)无法正常出声。
    """
    if requested:
        return requested
    if shutil.which("ffmpeg"):
        return (
            "bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]"
            "/bestvideo+bestaudio/best"
        )
    print(
        "提示: 未检测到 ffmpeg, 将使用单文件最佳画质(无独立音轨合并)。"
        "\n安装后质量更高:  brew install ffmpeg",
        file=sys.stderr,
    )
    return "best"


def make_progress_hook(
    quiet: bool,
    metadata_write: Callable[[dict], None] | None = None,
    info_store: dict[str, dict] | None = None,
) -> tuple[Callable[[dict], None], list[str]]:
    """返回 (进度回调, 已完成视频标题列表)。

    yt-dlp 传给 progress hook 的字典中 info 位于 "info_dict" 键,
    在 status == "finished" 时可通过其写入元数据, 并按 id 缓存
    完整 info (供后续 Telegram 发送时解析标题使用)。
    """
    done: list[str] = []
    last_pct = {"v": 0.0}

    def hook(d: dict) -> None:
        if d.get("status") == "finished":
            info = d.get("info_dict", {}) or {}
            title = info.get("title") or Path(d.get("filename", "")).stem
            if title not in done:
                done.append(title)
                if not quiet:
                    print(f"  ✔ 已下载: {title}")
            if metadata_write is not None:
                metadata_write(info)
            vid = info.get("id")
            if vid and info_store is not None:
                info_store[vid] = info
            last_pct["v"] = 0.0
        elif d.get("status") == "downloading" and not quiet:
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            pct = d.get("downloaded_bytes", 0) / total * 100 if total else 0.0
            if pct < last_pct["v"] - 0.1:
                sys.stdout.write("\n")
            sys.stdout.write(
                f"\r  {pct:6.1f}%  {d.get('_speed_str', '') or '':>10}"
                f"  ETA {d.get('_eta_str', '') or '-':>5}  "
            )
            sys.stdout.flush()
            if pct >= 100:
                sys.stdout.write("\n")
                sys.stdout.flush()
            last_pct["v"] = pct

    return hook, done


def make_metadata_writer(output_dir: Path) -> Callable[[dict], None]:
    """把每个成功下载的视频信息追加写入 metadata.jsonl。"""
    meta_path = output_dir / "metadata.jsonl"
    seen: set[str] = set()
    lock = threading.Lock()

    def write(info: dict) -> None:
        vid = info.get("id")
        if not vid or vid in seen:
            return
        seen.add(vid)
        record = {k: info.get(k) for k in META_FIELDS}
        with lock:
            with meta_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return write


def _extract_video_id(filepath: str) -> str | None:
    """从成品文件名 '标题 [id].ext' 中提取视频 id。"""
    m = re.search(r"\[([A-Za-z0-9_-]+)\](?:\.[A-Za-z0-9]+)?$", filepath)
    return m.group(1) if m else None


def _title_from_path(filepath: str) -> str:
    """从成品文件名中回退解析标题 (去掉 ' [id]' 后缀)。"""
    stem = Path(filepath).stem
    return re.sub(r"\s*\[[A-Za-z0-9_-]+\]$", "", stem)


def make_verify_hook(
    quiet: bool,
    sender: Callable[[str, Path], tuple[bool, str]] | None = None,
    info_store: dict[str, dict] | None = None,
) -> Callable[[str], None]:
    """合并完成后用 ffprobe 校验成品是否包含音频流 (签名接收文件路径)。

    yt-dlp 的 post_hooks 回调参数是最终文件路径字符串。
    防止下载中断/格式只含视频时把无声文件当成成品交付。
    校验通过且配置了 Telegram sender 时, 自动把视频发送到群聊。
    若无 ffprobe 则跳过校验(也不发送)。
    """
    if not shutil.which("ffprobe"):
        return lambda filepath: None

    def verify(filepath: str) -> None:
        if not filepath or not Path(filepath).exists():
            return
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-select_streams", "a",
                    "-show_entries", "stream=index",
                    "-of", "csv=p=0", filepath,
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (OSError, subprocess.SubprocessError):
            return
        if result.returncode == 0 and result.stdout.strip():
            # 校验通过: 有音频流才算完整, 此时才允许发送到 Telegram
            if sender is not None:
                _send_after_verify(filepath, sender, info_store)
            return
        print(
            f"\n⚠️ 警告: 文件未检测到音频流, 很可能是下载中断或格式不含音轨:"
            f"\n  {filepath}"
            "\n建议删除该文件后重新运行脚本(校验未通过, 不会发送到 Telegram)。",
            file=sys.stderr,
        )

    return verify


def _send_after_verify(
    filepath: str,
    sender: Callable[[str, Path], tuple[bool, str]],
    info_store: dict[str, dict] | None,
) -> None:
    """校验通过后调用 Telegram 发送; 失败仅告警, 不影响下载流程。"""
    vid = _extract_video_id(filepath)
    info = (info_store or {}).get(vid, {}) if vid else {}
    title = info.get("title") or _title_from_path(filepath)
    ok, err = sender(title, Path(filepath))
    if ok:
        print(f"  📮 已发送到 Telegram: {title}")
    else:
        print(f"\n⚠️ Telegram 发送失败: {err}", file=sys.stderr)


def dry_run(url: str) -> int:
    """列出频道所有视频, 不下载。"""
    opts = {
        "extract_flat": True,  # 只取列表页信息, 速度快
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "noplaylist": False,
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if not info:
        print(f"无法解析该地址: {url}", file=sys.stderr)
        print("可尝试: 去掉开头的 @ 使用完整频道地址, 或改用 /videos 结尾的形式。", file=sys.stderr)
        return 1

    entries = list(info.get("entries") or [])
    if not entries:
        print(f"该频道下没有找到可下载的视频: {url}", file=sys.stderr)
        return 1
    print(f"频道: {info.get('title') or url}")
    print(f"共 {len(entries)} 个视频\n")
    for i, e in enumerate(entries, 1):
        dur = e.get("duration")
        dur_s = f"{int(dur // 60):d}:{int(dur % 60):02d}" if dur else "?:??"
        print(f"{i:>3}. {e.get('title')}  [{dur_s}]  https://www.youtube.com/watch?v={e.get('id')}")
    return 0


def run_download(args: argparse.Namespace) -> int:
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    check_disk_space(output_dir.parent)
    archive_path = args.archive or (output_dir / "archive.txt")
    fmt = resolve_format(args.format_)

    # I. Telegram 配置 (命令行参数优先, 其次环境变量)
    token = args.telegram_token or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = args.telegram_chat or os.environ.get("TELEGRAM_CHAT_ID")
    sender = None
    if token and chat_id:
        sender = make_sender(
            token, chat_id, args.telegram_max_mb * 1024 * 1024
        )
        print(
            f"Telegram 通知已启用: 群聊 {chat_id} "
            f"(单文件上限 {args.telegram_max_mb} MB)"
        )
    else:
        print(
            "提示: 未配置 Telegram, 下载完成后不会发送到群聊。"
            "可用 --telegram-token/--telegram-chat 或环境变量"
            " TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID 启用。"
        )

    # II. 钩子: 进度(记录信息/写 metadata) + 校验(音频检查/发送)
    info_store: dict[str, dict] = {}
    progress_hook, done = make_progress_hook(
        args.quiet,
        make_metadata_writer(output_dir),
        info_store,
    )

    opts: dict[str, Any] = {
        "format": fmt,
        "outtmpl": str(output_dir / "%(title)s [%(id)s].%(ext)s"),
        # 不强制容器: yt-dlp 会根据所选流自动选择 (h264+aac→mp4, vp9+opus→webm),
        # 避免 opus 音频被塞进 mp4 导致部分播放器无声。
        "download_archive": str(archive_path),
        "continue_dl": True,
        "noplaylist": False,
        "playlist_items": f"1-{args.limit}" if args.limit else None,
        "retries": args.retries,
        "fragment_retries": args.retries,
        "ignoreerrors": args.keep_going,
        "quiet": args.quiet,
        "no_warnings": args.quiet,
        "progress_hooks": [progress_hook],
        "post_hooks": [make_verify_hook(args.quiet, sender, info_store)],
        "cookiefile": str(args.cookies) if args.cookies else None,
        "limit_rate": args.limit_rate,
    }

    print(f"开始下载: {args.url}")
    print(f"保存目录: {output_dir}")
    print(f"断点文件: {archive_path} (已下载的视频会自动跳过)")
    if args.limit:
        print(f"只下载最新 {args.limit} 个视频")
    print(f"格式: {fmt}")

    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(args.url, download=True)
    except DownloadError as exc:
        print(f"\n下载失败: {exc}", file=sys.stderr)
        return 1

    if info is None:
        print(f"\n下载失败: 无法解析地址 {args.url}", file=sys.stderr)
        return 1

    print(f"\n完成: 本次新下载 {len(done)} 个视频(其余已在 archive 中, 自动跳过)。")
    return 0


def main() -> int:
    # Windows 控制台默认 GBK, 强制 UTF-8 以正常显示中文
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    # 从项目根目录 .env 加载本地配置 (不覆盖已有环境变量)
    load_dotenv()

    args = make_parser().parse_args()
    try:
        if args.dry_run:
            return dry_run(args.url)
        return run_download(args)
    except KeyboardInterrupt:
        print("\n已取消。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
