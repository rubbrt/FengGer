# 本地 GPT-SoVITS 声音试听

`gpt_sovits_demo.py` 会直接调用已克隆的 `feng_voice` v2Pro 权重，不启动 WebUI，也不使用千问 API。

首次加载模型需要一点时间；默认使用 RTX 4060 与半精度推理，输出为 32 kHz WAV。

在项目根目录执行：

```powershell
.\Local_model\gpt-sovits-demo-env\Scripts\python.exe .\gpt_sovits_demo.py
```

生成文件默认保存在 `output/local_gpt_sovits/`。指定文案和输出文件：

```powershell
.\Local_model\gpt-sovits-demo-env\Scripts\python.exe .\gpt_sovits_demo.py `
  --text "这事没那么复杂，先把眼前的活干明白。" `
  --output .\output\local_gpt_sovits\test.wav
```

Demo 固定采用模型仓库说明中的参考音频 `Local_model/feng_voice/merged_000008.wav`、对应参考文本，以及推荐参数：`top_k=5`、`top_p=1.0`、`temperature=1.0`、`speed=0.95`、`fragment_interval=0.3`、`cut1`（凑四句一切）。

运行环境位于 `Local_model/gpt-sovits-demo-env`，它复用了 `openmontage-video` Conda 环境中的 CUDA PyTorch，不会改写原有 Conda 环境。Windows/Python 3.11 下将官方 `opencc` 换为兼容的 `opencc-python-reimplemented`，接口保持一致。

请仅在已取得必要授权的范围内生成和使用音频；不得将合成语音用于误导、冒充、诈骗或其他侵权用途。
