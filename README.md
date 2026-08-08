FengGer/
│
├─ feng_web.py                 # FastAPI 后端入口，串起生成、配音、分镜、渲染
├─ qianwen_demo.py             # 调用千问生成口播文案
├─ qianwen_local_tts.py        # 本地 GPT-SoVITS 长文配音主逻辑
├─ gpt_sovits_demo.py          # GPT-SoVITS 单条配音测试脚本
├─ qianwen_tts.py              # 旧版/备用 TTS 实现
├─ video_composer.py           # 根据分镜数据生成视频 HTML 时间线
│
├─ prompt.txt                  # 文案生成提示词
├─ 峰哥语录.txt                 # 文案参考素材
├─ 常见议题.txt                 # 议题参考素材
├─ requirements.txt            # Python 依赖
├─ 启动网页.ps1                # 启动本地 Web 服务
│
├─ web/                        # 前端页面
│  ├─ index.html               # 文案生成页
│  ├─ production.html          # 配音、分镜、视频导出页
│  ├─ generate.js              # 文案生成页交互
│  ├─ production.js            # 配音、分镜编辑、渲染交互
│  ├─ common.js                # 通用接口请求和状态逻辑
│  └─ material.css             # 页面样式
│
├─ 峰哥表情包/                  # 本地图片素材库
│  └─ xxx.png                  # 分镜中的 asset_id 对应这些图片
│
├─ Local_model/                # 本地推理环境和模型文件
│  ├─ GPT-SoVITS/              # GPT-SoVITS 源码与依赖
│  ├─ feng_voice/              # GPT/SoVITS 权重、参考音频等
│  └─ gpt-sovits-demo-env/     # Python 虚拟环境
│
├─ video_renderer/             # 视频渲染项目
│  ├─ package.json             # HyperFrames 渲染命令
│  ├─ design.md                # 视频视觉设计规范
│  ├─ hyperframes.json         # 渲染器配置
│  ├─ index.html               # 每次渲染时动态生成的动画页面
│  ├─ current_storyboard.json  # 当前分镜数据
│  └─ assets/
│     └─ runs/
│        └─ run_id/            # 单次任务的音频与表情包副本
│
├─ output/                     # 所有运行产物
│  ├─ text_backup/             # 用户选定的文案备份
│  ├─ gpt_sovits_tts/
│  │  └─ run_id/
│  │     ├─ xxx.wav            # 配音结果
│  │     └─ manifest.json      # 文案、模型参数、时长等记录
│  └─ videos/
│     └─ xxx.mp4               # 最终导出视频
│
└─ input/                      # 预留的授权参考音频目录
