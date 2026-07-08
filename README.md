# 秒图语音工厂

秒图语音工厂是一款面向 Windows 的桌面语音克隆工具，使用 Python + PySide6 开发，当前接入 Gitee AI `IndexTTS-2` 语音合成接口。

## 功能

- 开始克隆：每一行是一条独立文案，可单独生成、重新生成、新增或删除。
- 音色库：维护音色名称、Voice、音色参考 URL、情绪参考 URL、情绪强度和参考文本。
- 批量生成：支持多行并发生成，并可在设置中调整“同时生成数量”。
- 失败隔离：某一行失败不会影响其他行，失败原因会在弹窗和任务日志中显示。
- 音频预览：生成后不会自动播放；点击播放后显示进度条、暂停播放和倍速选项。
- 停顿处理：可将语音中的长静音压缩为更短停顿，支持 `mp3` 自动处理。
- 音频保存：不依赖 FFmpeg，程序会按接口实际返回的音频类型保存为 `wav` 或 `mp3`。
- 格式识别：保存前会读取音频文件头，避免出现 `.mp3` 后缀但实际是 WAV 内容导致 PR 等剪辑软件导入失败。
- 设置：支持 API Key、Base URL、模型、默认输出目录、接口异常时自动切换和连通性测试。

## 环境要求

- Windows 10/11
- Python 3.10 或更高版本
- 可访问 Gitee AI 接口的网络环境
- Gitee AI API Key

## 安装运行

建议使用项目内虚拟环境，避免 Windows 全局 Python 目录的权限或 DLL 占用问题。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

启动应用：

```powershell
.\.venv\Scripts\python.exe .\main.py
```

如果已经激活虚拟环境，也可以直接运行：

```powershell
python .\main.py
```

## 首次配置

1. 打开 `设置`。
2. 填写 Gitee AI `API Key`。
3. 确认 `Base URL` 为 `https://ai.gitee.com/v1`。
4. 确认模型为 `IndexTTS-2`。
5. 点击 `保存设置`。
6. 进入 `音色库`，添加或编辑音色。
7. 确保音色参考 URL 和情绪参考 URL 都是公网可访问的 mp3/wav 链接。
8. 如需缩短句子中间停顿，可在 `设置` 中启用 `停顿处理` 并调整参数。
9. 回到 `设置`，点击 `测试连通性`。
10. 连通正常后即可在 `开始克隆` 中生成音频。

也可以通过环境变量临时提供 API Key：

```powershell
$env:GITEE_AI_API_KEY = "你的 Gitee AI API Key"
.\.venv\Scripts\python.exe .\main.py
```

## 音色 URL 要求

Gitee AI 接口需要服务器主动拉取参考音频，因此音色 URL 必须满足：

- 使用 `http://` 或 `https://`
- 浏览器无登录也能直接打开
- 指向真实音频文件，建议使用 `mp3` 或 `wav`
- 不支持本地路径，例如 `C:\xxx\voice.mp3`

## 任务日志

生成开始、成功和失败会记录到本机应用数据目录：

```text
%APPDATA%\MiaoTuVoiceFactory\logs\tasks.jsonl
```

停顿处理结果也会写入这个文件：

- `silence_trim_finished`：停顿处理已执行。重点看 `compressed_segments`、`original_duration_ms`、`processed_duration_ms`，分别表示压缩了几段静音、处理前时长、处理后时长。
- `silence_trim_failed`：停顿处理失败，程序会保留原始音频。重点看 `error` 字段，通常用于判断是音频解码失败、文件格式不支持，还是其他处理异常。

可以用记事本直接打开：

```powershell
notepad "$env:APPDATA\MiaoTuVoiceFactory\logs\tasks.jsonl"
```

旧版本配置会自动从以下目录读取：

```text
%APPDATA%\XiaoMiVoiceClone\config.json
```

读取后，新配置会保存到：

```text
%APPDATA%\MiaoTuVoiceFactory\config.json
```

## 文件命名

生成音频的文件名规则：

```text
voice_年月日_时分秒_毫秒_行号_文案前五字.ext
```

示例：

```text
voice_20260707_153012_428_01_船上丢下去.mp3
```

程序会自动移除 Windows 文件名不允许的字符；如果文案开头没有可用字符，则使用 `文案` 作为兜底名称。

## 停顿处理

`设置` 中可以启用停顿处理，并由用户自行填写参数：

- `最短静音`：静音持续超过多久才会被处理，默认 `350 ms`。
- `保留停顿`：被压缩后的静音保留多长，默认 `180 ms`。
- `静音阈值`：低于多少音量视为静音，默认 `-45 dB`。

参数含义：

- `最短静音` 控制“多长的空白才算需要处理”。例如设置为 `350 ms` 时，`200 ms` 的短停顿会保留原样，`500 ms` 或 `1000 ms` 的长停顿会被压缩。这个值越小，程序越容易处理停顿；值越大，只会处理更明显的长停顿。
- `保留停顿` 控制“压缩后还留下多长停顿”。例如原本有 `800 ms` 的静音，最短静音为 `350 ms`、保留停顿为 `180 ms` 时，这段停顿会被缩短到大约 `180 ms`。这个值越小节奏越紧凑，越大越自然。
- `静音阈值` 控制“多小的声音会被当作静音”。例如 `-45 dB` 是较通用的默认值；调到 `-60 dB` 会更严格，只有非常安静才算静音；调到 `-35 dB` 会更宽松，较小的人声尾音或呼吸声也可能被当作静音。

建议参数：

```text
自然口播：最短静音 600 ms，保留停顿 350 ms，静音阈值 -45 dB
短视频口播：最短静音 350 ms，保留停顿 180 ms，静音阈值 -45 dB
高密度口播：最短静音 220 ms，保留停顿 100 ms，静音阈值 -45 dB
```

处理流程是 `mp3 解码 -> 静音检测 -> 压缩长静音 -> 重新编码 mp3`。这会带来轻微二次编码损耗，语音内容通常可以接受。若停顿处理失败，程序会保留原始生成音频，并在任务日志中记录失败原因。

该功能使用 `miniaudio` 解码音频、`numpy` 检测静音、`lameenc` 重新编码 mp3，不依赖 FFmpeg。

## 常见问题

### API Key 无效或已过期

重新在 `设置` 中填写正确的 API Key，点击 `保存设置`，再点击 `测试连通性`。

### 参考音频 URL 拉取失败

检查音色库中的音色参考 URL 和情绪参考 URL。它们必须是公网可访问链接，不能是本地文件路径。

### 接口请求超时

可能是接口处理时间较长或并发过高。可以在 `设置` 中降低“同时生成数量”，稍后重试。

### 生成完成后没有自动播放

这是当前设计。生成完成后，需要用户点击当前行的 `播放` 按钮。

### 为什么不内置 FFmpeg

应用播放、暂停、进度和倍速使用 PySide6 的 QtMultimedia。为了减少安装包体积，当前版本不再内置 FFmpeg，也不需要用户单独安装 FFmpeg。

### PR 或剪辑软件导入音频失败

接口有时会返回 WAV 内容，但响应头或目标文件名可能让程序误保存为 `.mp3`。当前版本会优先读取音频文件头判断真实格式，实际是 WAV 就保存为 `.wav`，实际是 MP3 才保存为 `.mp3`。

旧版本生成的异常文件如果出现 `.mp3` 后缀但无法导入 PR，可以尝试把后缀改为 `.wav` 后重新导入。

## 更新记录

### 2026-07-07

- 新增停顿处理：支持用户自定义最短静音、保留停顿和静音阈值。
- 新增 mp3 静音处理链路：`miniaudio` 解码、`numpy` 检测、`lameenc` 重新编码。
- 修复部分 WAV 生成文件停顿处理失败的问题：WAV 文件优先使用 Python 标准库读取，避免 `miniaudio` 对某些 PCM WAV 解码失败。
- 优化停顿处理反馈：生成完成后会显示压缩段数和处理前后时长；日志会记录本次使用的停顿处理参数。
- 修复音频扩展名识别：优先根据文件头判断 WAV/MP3，避免剪辑软件因后缀和真实格式不一致而导入失败。
- 优化打包脚本：补充 `_cffi_backend` 打包规则，修复打包后启动缺少 cffi 依赖的问题。

## 打包 EXE

安装打包工具：

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
```

执行打包脚本：

```powershell
.\build_exe.ps1
```

脚本会优先使用项目内 `.venv\Scripts\python.exe`，如果不存在才回退到系统 `python`。

生成文件位于：

```text
dist\秒图语音工厂\秒图语音工厂.exe
```

发布给用户时，请复制或压缩整个目录：

```text
dist\秒图语音工厂
```

不要只单独拷贝 `秒图语音工厂.exe`，它需要同目录下的 `_internal` 运行库。用户电脑无需安装 Python、PySide6、numpy、FFmpeg 等环境。

打包缓存和产物不会提交到 Git：

```text
build/
dist/
*.spec
```

## 项目结构

```text
app/
  core/
    config.py              配置读写和旧配置迁移
  services/
    gitee_tts.py           Gitee AI 语音合成接口
    silence_trim.py        静音压缩和 mp3 重新编码
    task_log.py            任务日志
  ui/
    qt_main_window.py      主窗口和页面逻辑
    widgets.py             行组件和导航组件
    workers.py             后台异步任务
assets/
  icons/
    app.ico                应用图标
    audio-lines.svg        图标源文件
    LICENSE.md             图标许可说明
main.py                    程序入口
build_exe.ps1              Windows 打包脚本
requirements.txt           Python 依赖
```

## 图标来源

应用图标改编自开源 Lucide `audio-lines` 图标。

- Source: https://lucide.dev/icons/audio-lines
- License: ISC License
- 项目内说明：`assets/icons/LICENSE.md`
