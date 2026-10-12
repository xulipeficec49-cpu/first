# 长方形绕 CD 旋转一周的体积（讲题视频）

**题**：长方形 ABCD，BC=6 厘米，AB=10 厘米，对角线 AC、BD 交于 O。图①涂色部分（上下两个三角形 AOD、BOC）
以 CD 所在直线为轴旋转一周，求扫出的立体图形（图②）的体积。

**参考答案（顺着它讲，方法一）**：`1/3×3.14×6²×10 − 1/3×3.14×3²×5×2 = 282.6`，`282.6×2 = 565.2`（立方厘米）。
讲法：把 △AOD 补成大三角形 ADC（补上 △DOC）→ 绕 CD 转出大圆锥（半径 6、高 10）→ △DOC 转出上下两个小圆锥
（O 是长方形中心：半径 6÷2=3、高 10÷2=5）→ 大圆锥减两个小圆锥 = 282.6 → 下面的 △BOC 对称，再乘 2。
结尾"想一想"：忘了减空腔会算成 753.6（多 188.4 = 空腔的 2 倍）。数字已用分层积分独立验算（`make_sb.py` 的 `check_numbers`）。

## 文件

| 文件 | 说明 |
|---|---|
| `make_sb.py` | 生成分镜（旋转用角度变量 `ph` 驱动点坐标，圆用 `pcurve` 椭圆；生成前自动验算数字） |
| `长方形旋转体积.json` | 分镜（`python make_sb.py` 生成；`meta.tts.engine = "mai"`） |

## 状态

- 分镜 `check`：0 ERROR / 0 WARN；`preview --fake` 的 46 个定格帧逐张看过；渲染链路（Chromium + ffmpeg）在云端容器跑通。
- 配音：走 OpenRouter 的微软 **MAI-Voice-2.1**，音色 **zh-CN-Mei**（`.claude/skills/math-explain-video-pro/scripts/tts_mai.py`）。
  **需要 OpenRouter Key**（环境变量 `OPENROUTER_API_KEY`，或 `~/.openrouter_api_key`；不要贴进聊天）。

## 出片（有 Key 之后）

```bash
cd videos/changfangxing-xuanzhuan
S=../../.claude/skills/math-explain-video-pro/scripts
python $S/make_video.py 长方形旋转体积.json check
python $S/make_video.py 长方形旋转体积.json tts          # 逐句合成，约 85 句
python $S/letter_check.py 长方形旋转体积.json            # 字母（ABCD、AOD…）逐句复核；没有百炼 Key 时自动用 OpenRouter 识别
python $S/audio_check.py 长方形旋转体积.json
python $S/make_video.py 长方形旋转体积.json preview      # 不带 --fake：核对真实时序
python $S/make_video.py 长方形旋转体积.json render       # 约 6 分钟
```

渲染在云端容器要用容器里的 Chromium：`make_video.py` 的 `open_page` 已加回退（找不到 Chrome 时自动用 `/opt/pw-browsers/chromium-*`）。
