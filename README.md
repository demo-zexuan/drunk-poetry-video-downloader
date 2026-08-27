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
| `--format` | yt-dlp 格式表达式(默认有 ffmpeg 时合并最高画质) |
| `--cookies cookies.txt` | 年龄限制/登录验证时使用浏览器导出的 cookies |
| `--archive` | 断点记录文件, 默认 `downloads/archive.txt`(重复运行自动跳过已下载) |
| `--limit-rate 5M` | 限速下载 |
| `-q` | 静默模式 |

## 输出

- 视频文件: `downloads/<标题> [<视频ID>].mp4`
- 断点记录: `downloads/archive.txt`(已下载的自动跳过)
- 视频元数据: `downloads/metadata.jsonl`(每行一个 JSON: 标题、上传日期、时长、播放量等)

## 依赖系统工具

- **ffmpeg** — 合成最高画质 + 音轨必需; 未安装时自动退化为单文件最佳画质
  - macOS: `brew install ffmpeg` / Windows: `winget install Gyan.FFmpeg` / Debian: `sudo apt install ffmpeg`

## 注意事项

- YouTube 会限制频繁请求; 下载大量视频遇限流时可用 `--cookies` 传入登录 cookie。
- 如需下载更多频道, 直接传频道地址: `uv run python main.py "https://www.youtube.com/@其他频道/videos"`。
