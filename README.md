# 图片批阅标注工具 + 结果查看工具

本项目包含两个基于浏览器的本地静态网页工具，配合一个迁移脚本，构成完整的「标注 → 查看 → 分析」数据流：

1. **图片批阅标注工具** — 用矩形框（bbox）在图片上框选错误位置，每个框绑定一个错误类型和说明。导出结构化 JSON。
   **[https://shiren23.github.io/grading-image-annotation-tool/annotation-tool.html](https://shiren23.github.io/grading-image-annotation-tool/annotation-tool.html)**
2. **标注结果查看工具** — 浏览标注结果，在原图上叠加 bbox，支持字段级编辑错误列表。
   **[https://shiren23.github.io/grading-image-annotation-tool/result-viewer.html](https://shiren23.github.io/grading-image-annotation-tool/result-viewer.html)**
3. **迁移脚本** `migrate_legacy_zip.py` — 把旧版（marked_*.jpg + error_info.txt）结果迁移到新 schema。

所有数据均在浏览器本地处理，不会上传到任何服务器。

## v2 数据模型（error-centric）

每条错误 = 一个 bbox + 一个错误类型 + 一句说明。坐标存在图像像素空间 `[x, y, w, h]`，与显示分辨率解耦。

导出 ZIP 结构：

```
批阅标注结果_2026-06-10T12-00-00.zip
├── _session.json                              # 会话级元数据
├── _stats.jsonl                               # 派生统计（一行一错误，便于 grep/jq）
├── taxonomy.json                              # 分类法快照
├── db45c6d8-04ed-4a71-a7d2-2179957bd9b4/
│   ├── annotations/
│   │   └── default.json                       # 真相源（v2 schema）
│   └── source.jpg                             # 原图（无栅格化痕迹）
└── bda0718b-3e30-4cc4-93b1-265eb54a86d2/
    └── ...
```

`annotations/default.json` 字段定义见 [`docs/schema.md`](docs/schema.md)。

### 为什么不再有 `error_info.txt` 和 `marked_*.jpg`

- 自由文本不可结构化分析（grep、jq、SQL 都做不了）
- 栅格化把位置信息烧死在像素里，无法分离错误对象和原图
- v2 把它们改成派生视图：原图是真相源，bbox overlay 由 viewer 实时绘制

旧数据不会被丢弃——viewer 自动兼容旧格式（双路解析），迁移脚本可以把它们升级到 v2。

## 功能特性

### 标注工具

- 🖼️ **任务结构自动识别**：从 `metadata.yaml` 匹配任务编号
- 🟦 **bbox 框选标注**：左键拖拽框选错误位置，自动绑定预选的错误类型
- 🏷️ **数据驱动分类**：4 大类（切题/OCR/解题/判题）+ 子类型，由 `taxonomy.js` 配置
- 💬 **逐错误备注**：每个 bbox 一条 comment
- ↩️ **撤销/删除**：Z 撤销最后一个，Delete 删选中，Esc 取消绘制
- 🔢 **Badcase 数量自洽**：错误数 = bbox 数，杜绝对不上账
- 💾 **localStorage 增量持久化**：刷新不丢，启动时提示恢复未导出标注
- 🔐 **sha256 完整性校验**：每张原图算 hash，写入 annotation.json（file:// 失败则置 null）
- 📦 **纯 JSON 导出**：每图一份 `annotations/default.json` + 原图，不再栅格化

### 结果查看工具

- 📂 **双路解析**：v2 JSON 优先，自动回退到 legacy txt
- 🟦 **bbox overlay**：在原图上实时叠加 bbox 矩形，颜色按错误类型分类，带角标序号
- ✏️ **字段级编辑**：每个错误独立编辑（类型下拉 + 子类型联动 + comment），不再是自由文本
- 💾 **JSON 导出**：编辑后下载 `annotation.json`（File System Access API 优先，回退普通下载）
- 🔄 **localStorage 跨会话保留**：旧 key（`gradingReport:`）自动迁移到 `gradingAnnotationV2:`
- ⌨️ **键盘导航**：上下箭头切换任务（输入框中自动失效）
- 🙈 **浮动导航可折叠**

## 🚀 在线使用（推荐）

两个工具均已通过 **GitHub Pages** 部署，无需下载安装：

- **标注工具** 👉 [https://shiren23.github.io/grading-image-annotation-tool/annotation-tool.html](https://shiren23.github.io/grading-image-annotation-tool/annotation-tool.html)
- **结果查看工具** 👉 [https://shiren23.github.io/grading-image-annotation-tool/result-viewer.html](https://shiren23.github.io/grading-image-annotation-tool/result-viewer.html)

> 所有图片和数据均在浏览器本地处理，不会上传到任何服务器。

## 快速开始

### 环境要求

- 现代浏览器（推荐 Chrome / Edge / Safari）
- 不需要后端服务

### 部署方式

#### 方式一：在线使用（推荐）

直接打开上面两个 GitHub Pages 链接即可。

#### 方式二：本地打开

1. 下载仓库中的 `annotation-tool.html`、`result-viewer.html`、`taxonomy.js`
2. **三个文件必须放在同一目录**（taxonomy.js 通过 `<script>` 标签加载，file:// 下不可用 fetch）
3. 用浏览器双击打开

#### 方式三：本地 HTTP 服务器

```bash
cd grading-image-annotation-tool
python3 -m http.server 8080
# 访问 http://localhost:8080/annotation-tool.html
```

#### 方式四：部署到任意静态网站托管服务

GitHub Pages / Vercel / Netlify / 任意 Nginx 静态站点均可。

## 使用说明

### 1. 准备批阅任务文件夹

```
批阅任务文件夹/
├── 未匹配/
│   ├── 1/
│   │   ├── 1.jpg
│   │   └── metadata.yaml      # 包含 task_ids
│   └── ...
└── 学生卷/
    └── 张三/
        ├── 张三.jpg
        └── metadata.yaml
```

`metadata.yaml` 内容示例：

```yaml
task_ids:
  - "db45c6d8-04ed-4a71-a7d2-2179957bd9b4"
```

### 2. 加载任务

1. 打开标注工具页面
2. 点击「📁 选择文件夹」，选择批阅任务文件夹（最外层）
3. 工具自动扫描子文件夹，匹配图片与 YAML

### 3. 进行标注

1. 在左侧 taxonomy 选择器点击错误类型（如「切题」→「答非所问」）
2. 在图片上左键拖拽框选错误位置（框太小会被忽略）
3. 框选完成后在左侧错误列表填写 comment
4. 一个图可以画多个 bbox，每个绑定不同的错误类型
5. Z 撤销最后一个，Delete 删选中，Esc 取消绘制中

### 4. 保存或跳过

- 「✓ 保存标注」（有 bbox 时）— 保存并自动跳到下一张
- 「→ 跳过此图」（无 bbox 时）— 标记 skipped 并跳过

### 5. 导出结果

点击右上角「📦 导出结果」下载 ZIP（结构见上文「v2 数据模型」）。

### 6. 用查看工具浏览

1. 解压 ZIP（或直接选择解压目录）
2. 打开 `result-viewer.html`
3. 「选择文件夹」→ 选中解压后的目录
4. 工具自动加载，左侧任务列表 + 中间图片（带 bbox overlay）+ 右侧错误详情
5. 「✏️ 编辑」可字段级编辑错误列表（添加/删除/改类型/改 comment）
6. 「💾 下载」生成新的 `annotation.json`（Chrome/Edge 可直接覆盖原文件）

## 旧数据迁移

如果你有旧版的 `marked_*.jpg + error_info.txt` 结果，用迁移脚本升级到 v2：

```bash
# 目录形式（就地迁移）
python3 migrate_legacy_zip.py 批阅标注结果_xxx/

# ZIP 形式（输出新 ZIP）
python3 migrate_legacy_zip.py 批阅标注结果_xxx.zip --output result_v2.zip

# 干跑（只打印 diff，不写盘）
python3 migrate_legacy_zip.py 批阅标注结果_xxx/ --dry-run
```

迁移行为：

- `marked_*.jpg` → 复制为 `source.<ext>`
- `error_info.txt` 的 reasons → 映射到 taxonomy 的 category id，写入 `annotations/default.json`
- **bbox 字段为 null**（位置信息已栅格化、无法恢复），comment 标注「历史数据，位置信息未保留」
- 删除 `error_info.txt` 和 `task_id.txt`（信息已进 JSON）
- 计算 `source.<ext>` 的 sha256

reason → category 映射见 `reason_map.yaml`。

## 分类法自定义

`taxonomy.json` / `taxonomy.js` 定义错误分类。修改后两个工具会同步使用新分类（annotation-tool 用 .js 因为 file:// 不支持 fetch，viewer 同理）。

```json
{
  "version": "1.0",
  "categories": [
    {"id": "topic", "label": "切题", "color": "#e74c3c", "subtypes": [
      {"id": "off_topic", "label": "答非所问"},
      {"id": "incomplete", "label": "未覆盖要点"}
    ]},
    {"id": "ocr", "label": "OCR", "color": "#3498db", "subtypes": [...]},
    {"id": "solution", "label": "解题", "color": "#f39c12", "subtypes": [...]},
    {"id": "judgment", "label": "判题", "color": "#9b59b6", "subtypes": [...]}
  ],
  "severity_levels": [1, 2, 3]
}
```

修改后两个文件需保持同步（taxonomy.js 是 `window.TAXONOMY = {...}` 包装版）。

## 快捷键

### 标注工具

| 快捷键 | 功能 |
|--------|------|
| `←` `→` | 上一张 / 下一张图片 |
| `Z` | 撤销最后一个 bbox |
| `Delete` | 删除选中的 bbox |
| `Esc` | 取消绘制中 |
| `S` / `Enter` | 保存 / 跳过 |

### 结果查看工具

| 快捷键 | 功能 |
|--------|------|
| `↑` `↓` `←` `→` | 切换任务（输入框中失效） |

## 浏览器兼容性

- ✅ Chrome / Edge（推荐，File System Access API 直接覆盖原文件）
- ✅ Safari
- ✅ Firefox（部分 API 降级）

> 注意：file:// 下双击打开时，sha256 计算（SubtleCrypto）可能不可用，annotation.json 的 `source_hash` 字段会置 null，不阻塞导出。

## 文件说明

| 文件 | 说明 |
|------|------|
| `annotation-tool.html` | **标注工具**主页面 |
| `result-viewer.html` | **结果查看工具**主页面 |
| `taxonomy.json` / `taxonomy.js` | 错误分类法（数据 + file:// 兼容包装） |
| `docs/schema.md` | annotation.json 字段定义 |
| `migrate_legacy_zip.py` | 旧 ZIP/目录 → v2 schema 迁移脚本 |
| `reason_map.yaml` | 旧 reasons → 新 category id 映射 |
| `test_annotation_tool.py` | 标注工具 Playwright 测试（16 项） |
| `test_result_viewer.py` | 查看工具 Playwright 测试（14 项） |
| `test_viewer_e2e.py` | 查看工具端到端测试（5 项，含 v2 + legacy 双路径） |
| `test_migration.py` | 迁移脚本单元测试（7 项） |
| `test_data/v2_sample/` | v2 schema 样本（含 source.jpg + annotations/default.json） |
| `test_results/` | 旧版样本（用于测试 legacy 兼容路径） |
| `README.md` | 本说明文件 |

## 运行测试

```bash
# 安装 Playwright
pip3 install playwright
python3 -m playwright install chromium

# 跑全部测试
python3 test_annotation_tool.py        # 16 项
python3 test_result_viewer.py          # 14 项
python3 test_viewer_e2e.py             # 5 项（真实文件解析）
python3 test_migration.py              # 7 项（无浏览器依赖）
```

## 许可证

MIT License
