# 秒图语音工厂

秒图语音工厂是一款面向 Windows 的桌面语音克隆工具，使用 Python + PySide6 开发，当前接入 Gitee AI `IndexTTS-2` 语音合成接口。

## 功能

- 开始克隆：每一行是一条独立文案，可单独生成、重新生成、新增或删除。
- 音色库：维护音色名称、Voice、音色参考 URL、情绪参考 URL、情绪强度和参考文本。
- 批量生成：支持多行并发生成，并可在设置中调整“同时生成数量”。
- 失败隔离：某一行失败不会影响其他行，失败原因会在弹窗和任务日志中显示。
- 音频预览：生成后不会自动播放；点击播放后显示进度条、暂停播放和倍速选项。
- 音频保存：不依赖 FFmpeg，程序会按接口实际返回的音频类型保存为 `wav` 或 `mp3`。
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
8. 回到 `设置`，点击 `测试连通性`。
9. 连通正常后即可在 `开始克隆` 中生成音频。

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

## 打包 EXE

安装 PyInstaller：

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
```

执行打包脚本：

```powershell
.\build_exe.ps1
```

生成文件位于：

```text
dist\秒图语音工厂\秒图语音工厂.exe
```

## 项目结构

```text
app/
  core/
    config.py              配置读写和旧配置迁移
  services/
    gitee_tts.py           Gitee AI 语音合成接口
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
