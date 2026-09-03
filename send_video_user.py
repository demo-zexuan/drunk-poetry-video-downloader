"""使用 Telegram 个人账号发送本地视频文件。

默认扫描 downloads 目录中的视频并逐个发送。
评论格式固定为: #视频归档 #视频标题
其中视频标题会去掉【】中的内容，并清理为 hashtag 可用字符。
"""

from __future__ import annotations

import asyncio
import argparse
import os
import re
import sys
from pathlib import Path
from typing import Iterable

from telethon import TelegramClient

VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".m4v"}
TRAILING_ID_RE = re.compile(r"\s*\[[A-Za-z0-9_-]+\]$")
CN_BRACKET_RE = re.compile(r"【[^】]*】")
TAG_CLEAN_RE = re.compile(r"[^\w\u4e00-\u9fff]+")


def load_dotenv(path: Path | None = None) -> None:
    env_path = path or (Path(__file__).resolve().parent / ".env")
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"\'')
        if key and key not in os.environ:
            os.environ[key] = value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="send-video-user",
        description="用 Telegram 个人账号发送本地视频文件。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        default=["downloads"],
        help="待发送文件或目录，默认扫描 downloads",
    )
    parser.add_argument(
        "--chat",
        default=None,
        help="目标会话(用户名/频道用户名/群组ID)，也可用 TELEGRAM_CHAT",
    )
    parser.add_argument(
        "--api-id",
        type=int,
        default=None,
        help="Telegram API ID，也可用 TELEGRAM_API_ID",
    )
    parser.add_argument(
        "--api-hash",
        default=None,
        help="Telegram API Hash，也可用 TELEGRAM_API_HASH",
    )
    parser.add_argument(
        "--session",
        default=None,
        help="Telethon 会话名，也可用 TELEGRAM_SESSION",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="最多发送前 N 个视频(按修改时间从旧到新)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅打印将发送的文件与评论，不实际发送",
    )
    return parser.parse_args()


def iter_videos(paths: Iterable[str]) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        p = Path(raw).expanduser()
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS:
            files.append(p)
            continue
        if p.is_dir():
            for child in p.iterdir():
                if child.is_file() and child.suffix.lower() in VIDEO_EXTS:
                    files.append(child)
    # 默认按时间从旧到新，便于归档
    return sorted(set(files), key=lambda x: x.stat().st_mtime)


def extract_title_from_path(path: Path) -> str:
    stem = path.stem
    # 去掉 yt-dlp 输出末尾的 [video_id]
    stem = TRAILING_ID_RE.sub("", stem).strip()
    # 去掉中文书名号样式前缀/片段: 【...】
    stem = CN_BRACKET_RE.sub("", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem or path.stem


def build_caption(path: Path) -> str:
    title = extract_title_from_path(path)
    tag = TAG_CLEAN_RE.sub("", title).strip("_")
    if not tag:
        return "#视频归档"
    return f"#视频归档 #{tag}"


async def send_all(
    client: TelegramClient,
    chat: str,
    files: list[Path],
    dry_run: bool,
) -> int:
    if not files:
        print("未找到可发送的视频文件。", file=sys.stderr)
        return 1

    ok = 0
    for idx, path in enumerate(files, 1):
        caption = build_caption(path)
        print(f"[{idx}/{len(files)}] {path.name}")
        print(f"  评论: {caption}")
        if dry_run:
            continue

        try:
            await client.send_file(
                chat,
                file=str(path),
                caption=caption,
                supports_streaming=True,
            )
            ok += 1
            print("  已发送")
        except Exception as exc:
            print(f"  发送失败: {exc}", file=sys.stderr)

    if dry_run:
        print(f"\n预览完成: 共 {len(files)} 个文件。")
        return 0

    print(f"\n发送完成: 成功 {ok}/{len(files)}")
    return 0 if ok == len(files) else 2


def main() -> int:
    load_dotenv()
    args = parse_args()

    files = iter_videos(args.inputs)
    if args.limit and args.limit > 0:
        files = files[:args.limit]

    if args.dry_run:
        if not files:
            print("未找到可发送的视频文件。", file=sys.stderr)
            return 1
        for idx, path in enumerate(files, 1):
            print(f"[{idx}/{len(files)}] {path.name}")
            print(f"  评论: {build_caption(path)}")
        print(f"\n预览完成: 共 {len(files)} 个文件。")
        return 0

    api_id = args.api_id or os.environ.get("TELEGRAM_API_ID")
    api_hash = args.api_hash or os.environ.get("TELEGRAM_API_HASH")
    chat = args.chat or os.environ.get("TELEGRAM_CHAT")
    session = args.session or os.environ.get("TELEGRAM_SESSION") or "telegram_user"

    if not api_id or not api_hash or not chat:
        print(
            "缺少配置: 需要 TELEGRAM_API_ID / TELEGRAM_API_HASH / TELEGRAM_CHAT",
            file=sys.stderr,
        )
        return 2

    try:
        api_id = int(api_id)
    except ValueError:
        print("TELEGRAM_API_ID 必须是整数", file=sys.stderr)
        return 2

    async def runner() -> int:
        async with TelegramClient(session, api_id, str(api_hash)) as client:
            return await send_all(client, str(chat), files, args.dry_run)

    try:
        return asyncio.run(runner())
    except KeyboardInterrupt:
        print("\n已取消", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
