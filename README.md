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
| `--cookies cookies.txt` | 年龄限制/会员视频时使用浏览器导出的 Netscape cookies |
| `--cookies-from-browser chrome` | 直接从浏览器读取 cookies, 如 chrome/firefox/safari/edge |
| `--username user@example.com` | YouTube 登录账号 |
| `--password 123456` | YouTube 登录密码 |
| `--archive` | 断点记录文件, 默认 `downloads/archive.txt`(重复运行自动跳过已下载) |
| `--limit-rate 5M` | 限速下载 |
| `-q` | 静默模式 |

## 输出

- 视频文件: `downloads/<标题> [<视频ID>].mp4`
- 断点记录: `downloads/archive.txt`(已下载的自动跳过)
- 视频元数据: `downloads/metadata.jsonl`(每行一个 JSON: 标题、上传日期、时长、播放量等)

## 登录下载会员/受限视频

当 YouTube 视频要求登录、会员权限或年龄验证时, 可使用下面任一方式:

```bash
# 方式 1: .env (推荐)
#    在 .env 中写:
#    YOUTUBE_USERNAME=your_account@example.com
#    YOUTUBE_PASSWORD=your_password
#    YOUTUBE_COOKIES_FROM_BROWSER=chrome

# 方式 2: 命令行参数
uv run python main.py --username your_account@example.com --password your_password
uv run python main.py --cookies cookies.txt
uv run python main.py --cookies-from-browser chrome

# 方式 3: 环境变量
export YOUTUBE_USERNAME=your_account@example.com
export YOUTUBE_PASSWORD=your_password
export YOUTUBE_COOKIES_FROM_BROWSER=chrome
uv run python main.py
```

> 说明: 从浏览器读取 cookies 一般最稳定; 若你已登录 YouTube 会员账号, 直接导出 Netscape cookies 文件或者让 yt-dlp 从浏览器 cookie 中读取更容易绕过会员/年龄限制。

## 依赖系统工具

- **ffmpeg** — 合成视频 + 音轨必需; 未安装时自动退化为单文件最佳画质
  - macOS: `brew install ffmpeg` / Windows: `winget install Gyan.FFmpeg` / Debian: `sudo apt install ffmpeg`
- 下载完成后脚本会用 ffprobe 自动校验成品是否包含音频流, 防止无声视频

## 注意

- YouTube 会限制频繁请求; 下载大量视频遇限流时可用 `--cookies` / `--cookies-from-browser` 传入登录 cookie。
- 会员视频最稳妥的方式通常是使用浏览器 cookies, 例如 `--cookies-from-browser chrome` 或从浏览器导出 `cookies.txt` 后再下载。
- 如需下载更多频道, 直接传频道地址: `uv run python main.py "https://www.youtube.com/@其他频道/videos"`。
