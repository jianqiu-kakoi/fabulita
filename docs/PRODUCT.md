# fabulita 产品设计（PM 视角）

## 一句话

把你的生词表变成一本"专为你写的"可朗读分级故事书。

## 用户画像

| 画像 | 场景 | 入口 |
|---|---|---|
| **学习者**（主要）：自学外语，有老师给的/教材上的词表，不会命令行 | 拿到 PDF/CSV 词表 → 想要"能读、能听、能点词查义"的材料 | **Studio 网页** |
| **折腾型学习者**：会用 ChatGPT/Claude，愿意自己管数据 | 长期积累多个词表，要 git 管理、批量 TTS | **CLI** |
| **老师/内容作者**：给学生做材料 | 批量生成 → 导出单文件发给学生（微信/邮件直接传） | Studio 或 CLI |

核心洞察:产出物是**单 HTML 文件**这一点是传播机制——学生/朋友收到文件就能用，
不需要装任何东西，这是 LUTE 类自托管方案做不到的。

## 用户旅程（Studio，MVP）

```
① 新建项目        选目标语言(es/en/ja/…) + 释义语言 + 项目名
② 导入词表        上传 CSV/TSV 或直接粘贴（word,gloss[,note]）
③ 看覆盖率        进度条 + 未覆盖词 chips
④ 生成故事        [复制 Prompt] → 贴到任意 LLM → 把返回的 JSON 贴回来
⑤ 校验入库        自动校验（字段/id/词是否真的用上）→ 进备选池
⑥ 读与筛选        内嵌预览（点词查义 + 浏览器朗读）→ 接受 / 拒绝
⑦ 循环 ④-⑥       直到覆盖率 100%
⑧ 导出           a) 阅读页 index.html（离线可用，发给任何人）
                  b) 项目包 bundle.json（喂给 CLI 做神经 TTS / git 管理）
```

数据存 localStorage，多项目。**无后端、无账号、无上传服务器**——词表数据不离开浏览器，
这是隐私卖点，也是零运维卖点。

## Studio ↔ CLI 关系

同一套 JSON 格式，双向互通：

- Studio「导出项目包」→ `fabulita unpack bundle.json` → 变成 CLI 项目目录
- CLI 项目目录的 JSON 手动贴回 Studio 也能用
- 神经 TTS（edge-tts）只在 CLI：浏览器出于 CORS 限制无法调用；Studio 导出的阅读页
  回退到浏览器 speechSynthesis，页面里注明"用 CLI 可升级为神经语音"

## MVP 边界（刻意不做）

- ❌ 调用 LLM API（key 管理、计费、代理——破坏零后端；prompt 复制粘贴够用）
- ❌ SRS 复习（Anki 导出/FSRS 是 roadmap，不进 MVP）
- ❌ 词形还原/词典集成（LLM 在生成时已给出屈折形式的 gloss）
- ❌ 移动 App / 账号系统 / 云同步

## 语言支持策略

- **内容语言**：es/en 等空格分词语言开箱即用；**ja/zh 用词表贪心最长匹配分词**
  （无形态分析器依赖，A1/N5 级短句够用；复杂分词是 roadmap）
- **界面语言**：zh / en / es / ja 四语，跟随 localStorage

## 成功指标（开源项目口径）

1. GitHub stars / HN 或 r/languagelearning 帖子的讨论质量
2. "从词表到能听的故事书"首次成功时间 < 10 分钟（Studio 路径）
3. Issue 里出现非中文用户 = 跨出种子用户圈
