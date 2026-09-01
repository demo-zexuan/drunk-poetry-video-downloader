# DrunkPoetry 视频下载器

使用 [uv](https://docs.astral.sh/uv/) 管理、基于 [yt-dlp](https://github.com/yt-dlp/yt-dlp) 的
YouTube 频道批量下载工具, 默认下载 https://www.youtube.com/@DrunkPoetry/videos 频道下的**所有**视频。

## 快速开始

```bash
# 1. 安装依赖(自动创建 .venv)
uv sync

# 2. 先看看频道里有哪些视频(不下载)
uv run python main.py --dry-run

# 3. 下载全部视频
uv run python main.py
```

## 常用选项

| 选项 | 说明 |
| --- | --- |
| `URL`(位置参数) | 频道地址, 默认 `https://www.youtube.com/@DrunkPoetry/videos` |
| `-o, --output-dir` | 保存目录, 默认 `downloads/` |
| `--limit N` | 只下载最新 N 个视频 |
| `--dry-run` | 只列出所有视频, 不下载 |
| `--format` | yt-dlp 格式表达式(默认优先 H.264+AAC 的 mp4 兼容组合, 保证任何播放器有声音) |
| `--cookies cookies.txt` | 年龄限制/登录验证时使用浏览器导出的 cookies |
| `--archive` | 断点记录文件, 默认 `downloads/archive.txt`(重复运行自动跳过已下载) |
| `--limit-rate 5M` | 限速下载 |
| `--telegram-token <TOKEN>` | Telegram Bot Token(也读 `TELEGRAM_BOT_TOKEN`) |
| `--telegram-chat <ID>` | 目标群聊 ID(也读 `TELEGRAM_CHAT_ID`) |
| `--telegram-max-mb 50` | Telegram 上传上限(MB), 超过自动压缩后再发送 |
| `-q` | 静默模式 |

## 输出

- 视频文件: `downloads/<标题> [<视频ID>].mp4`
- 断点记录: `downloads/archive.txt`(已下载的自动跳过)
- 视频元数据: `downloads/metadata.jsonl`(每行一个 JSON: 标题、上传日期、时长、播放量等)

## 自动发送到 Telegram 群聊

下载完成并通过音频校验后, 自动把视频发送到群聊, 评论格式为:

```
#视频归档 #<专题tag>
```

- `#视频归档` 固定
- 第二个 tag 取自视频标题: 去掉开头的 `【小酒对瓶吹】` 后, 取其第一个分隔符(`：` 等)之前的短语
  - 例: `【小酒对瓶吹】日本专题：xxx` → `#视频归档 #日本专题`
  - 例: `【小酒对瓶吹】M05一期聊透：xxx` → `#视频归档 #M05一期聊透`

启用方式(三选一):

```bash
# 1. 推荐: 项目根目录 .env 文件 (脚本启动时自动加载, 已加入 .gitignore)
#    cp .env.example .env
#    在 .env 中填写:
#    TELEGRAM_BOT_TOKEN=<BOT_TOKEN>
#    TELEGRAM_CHAT_ID=<CHAT_ID>

# 2. 命令行参数
uv run python main.py --telegram-token <BOT_TOKEN> --telegram-chat <CHAT_ID>

# 3. 环境变量
export TELEGRAM_BOT_TOKEN=<BOT_TOKEN>
export TELEGRAM_CHAT_ID=<CHAT_ID>
uv run python main.py
```

> 说明: Telegram Bot API 单文件上传上限默认 50MB; 超过时脚本会先用 ffmpeg
> 自动压缩到限制内再上传(`--telegram-max-mb` 可调), 原始文件保持不变。
> 需要先在 [@BotFather](https://t.me/BotFather) 创建 Bot 获取 Token, 并把 Bot
> 加入目标群聊(群 ID 可用 [@userinfobot](https://t.me/userinfobot) 查询)。
> 无音频流的残缺文件不会发送。

## 依赖系统工具

- **ffmpeg** — 合成视频 + 音轨必需; 未安装时自动退化为单文件最佳画质
  - macOS: `brew install ffmpeg` / Windows: `winget install Gyan.FFmpeg` / Debian: `sudo apt install ffmpeg`
- 下载完成后脚本会用 ffprobe 自动校验成品是否包含音频流, 防止无声视频

## 注意事项

- YouTube 会限制频繁请求; 下载大量视频遇限流时可用 `--cookies` 传入登录 cookie。
- 如需下载更多频道, 直接传频道地址: `uv run python main.py "https://www.youtube.com/@其他频道/videos"`。
