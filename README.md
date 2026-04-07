# wjx-autofill

这是一个基于 Playwright 的问卷星（WJX）填空题自动填写脚本。脚本通过题干关键字匹配答案，题目顺序变化不会影响填写结果，适用于常见的文本输入类型（text、email、tel、textarea 等）。

主要特性

- 按题干关键字填充答案
- 通过 `config.json` 配置 URL、默认值、关键字-答案对以及定时开始时间
- 支持在页面打开后自动点击“立即报名/立即开始”等入口按钮（可配置选择器或匹配文本）

快速开始

1. 安装依赖并安装 Playwright 浏览器：

```powershell
pip install -r requirements.txt
python -m playwright install
```

2. 编辑 `config.json`（见下节配置说明），然后运行：

```powershell
python wjx_fill.py
```

可选参数

- `--config <path>` 指定配置文件路径（默认：`config.json`）
- `--headless` 使用无头模式运行（不显示浏览器界面）

配置说明（config.json）

建议至少填写 `url`。常用字段：

- `url`（必需）：问卷页面 URL
- `default_text`（可选）：未匹配到关键字时使用的默认文本
- `start_time`（可选）：计划开始时间（见支持格式）
- `page_load_timeout`（可选）：页面加载超时时间，单位毫秒（默认 30000）
- `fill_delay`（可选）：每次填写之间的延迟，单位毫秒（默认 500）
- `keyword_answers`（可选）：关键字与答案的数组，格式为 [{"keyword":"...","answer":"..."}, ...]
- `entry_selectors`（可选）：进入问卷页时尝试点击的 CSS 选择器数组（优先匹配）
- `entry_texts`（可选）：进入问卷页时尝试匹配并点击的可见文本数组（次优先）

示例配置：

```json
{
  "url": "https://www.wjx.top/vm/xxxx.aspx",
  "default_text": "默认填写",
  "start_time": "09:00",
  "page_load_timeout": 30000,
  "fill_delay": 500,
  "entry_selectors": ["button.join", "#enter"],
  "entry_texts": ["立即报名", "立即开始"],
  "keyword_answers": [
    {"keyword": "姓名", "answer": "张三"},
    {"keyword": "学号", "answer": "20240001"}
  ]
}
```

关于 `start_time`（计划开始时间）

- 支持 24 小时制时间，格式：
  - `HH:MM`（例如 `09:00`，解释为当天的该时刻）
  - `HH:MM:SS`（例如 `09:00:00`）
  - `YYYY-MM-DD HH:MM` / `YYYY-MM-DD HH:MM:SS`（带日期）
  - `now` 表示立即开始
- 如果未设置或为空，脚本会立即开始；如果指定时间已过，脚本也会立即开始。

关于入口点击（进入问卷）

有些问卷打开后需要先点击一个“立即报名/立即开始”之类的按钮才能进入填写区域。脚本会按顺序尝试：

1. 使用 `entry_selectors` 中的 CSS 选择器逐一查找并点击（优先）
2. 使用 `entry_texts` 中的可见文本逐一查找并点击
3. 使用内置的常见中文按钮文本（如“立即报名”）进行匹配并点击

如果你知道按钮的 class 或 id，建议在 `entry_selectors` 中写精确选择器以保证点击成功。

注意事项与最佳实践

- 请确保你对目标问卷有操作权限并遵守平台规则。
- 脚本默认只填写不自动提交，避免误操作。如需自动提交，请自行修改脚本添加提交按钮的选择器与点击逻辑（谨慎使用）。
- 如果填写失败或未找到输入框，尝试增大 `page_load_timeout`、减小或增大 `fill_delay`，或调整 `TITLE_SELECTORS`、`entry_selectors`。

常见问题

Q: 页面没有被填写？

A: 可能原因包括页面结构与默认选择器不匹配、页面未完全加载、按钮未被正确点击进入。建议手动在浏览器中用开发者工具定位题干元素与输入控件，并把合适的选择器或入口选择器写入 `config.json`。

Q: 如何立即开始测试？

A: 将 `start_time` 设为 `now` 或在 `config.json` 中删除 `start_time` 字段，脚本会立即开始。

Q: 如何在无头模式运行？

A: 添加命令行参数 `--headless`：

```powershell
python wjx_fill.py --headless
```

示例运行（Windows PowerShell）

```powershell
pip install -r requirements.txt
python -m playwright install
python wjx_fill.py --config "config.json"
```

演示

仓库中包含 `demo.gif`，展示了运行效果。


