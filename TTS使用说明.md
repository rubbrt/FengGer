# qianwen_demo 的本地 GPT-SoVITS 输出

运行 `qianwen_demo.py` 后，程序会自动完成三步：

1. 调用千问生成口播正文；
2. 将千问原始正文保存到 `output/text_backup/`，不做改动；
3. 用本地 `Local_model/feng_voice/` 下的 GPT-SoVITS v2Pro 权重生成 32 kHz WAV。

本地 TTS 使用模型仓库提供的参考音频和参考文本，并采用推荐参数：`top_k=5`、`top_p=1.0`、`temperature=1.0`、`speed=0.95`、`fragment_interval=0.3`、`cut1`（凑四句一切）。模型在一次运行中只加载一次，整篇正文由 GPT-SoVITS 自动切分。

每次运行使用独立时间戳，不会覆盖已有结果：

```text
output/
├─ text_backup/
│  └─ qianwen_时间戳.txt
└─ gpt_sovits_tts/
   └─ qianwen_时间戳/
      ├─ gpt_sovits_qianwen_时间戳.wav
      └─ manifest.json
```

`manifest.json` 会记录问题、文本备份、模型路径、参考音频、推理参数以及音频时长，方便复盘和 A/B 对比。

旧的千问云端 TTS 实现仍保留在 `qianwen_tts.py`；如需回退，只需把 `qianwen_demo.py` 的 import 改回该模块。

请仅在已取得必要授权的范围内生成和使用音频；不得将合成语音用于误导、冒充、诈骗或其他侵权用途。
