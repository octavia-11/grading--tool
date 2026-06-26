# 图片批阅标注工具 + 结果查看工具

本项目包含两个基于浏览器的本地静态网页工具：

1. **图片批阅标注工具** — 对批阅任务图片进行标注，支持鼠标勾画、选择 Badcase 数量和错误原因，并将结果打包导出
**[https://shiren23.github.io/grading-image-annotation-tool/annotation-tool.html](https://shiren23.github.io/grading-image-annotation-tool/annotation-tool.html)**
2. **标注结果查看工具** — 查看标注工具导出的结果，浏览带批注的图片和错误信息，并支持复制任务 ID
**[https://shiren23.github.io/grading-image-annotation-tool/result-viewer.html](https://shiren23.github.io/grading-image-annotation-tool/result-viewer.html)**

所有数据均在浏览器本地处理，不会上传到任何服务器。

## 功能特性

### 标注工具功能

- 🖼️ **自动识别任务结构**：选择批阅任务文件夹后，自动匹配图片与 `metadata.yaml` 中的任务编号
- ✏️ **红笔/蓝笔勾画标记**：直接在图片上绘制痕迹，支持画笔、橡皮擦、线条粗细调节
- 🔢 **Badcase 数量**：提供 1、2 快捷按钮，也支持自定义输入
- 🏷️ **错误原因分类**：切题、OCR、解题、判题，四类原因支持多选
- 💾 **保存/跳过合一**：有标注信息则保存，无标注则跳过，自动跳转下一张
- 📦 **一键导出 ZIP**：按任务编号命名文件夹，输出带痕迹的图片和错误信息文本
- 🔍 **图片缩放模式**：适应高度（一屏看全图）/ 适应宽度（横向铺满，纵向滚动）
- ⌨️ **键盘快捷键支持**：提升标注效率

### 结果查看工具功能

- 📂 **导入结果文件夹**：直接选择标注工具导出的 ZIP 解压后的文件夹
- 🖼️ **查看带批注图片**：清晰展示每张 marked_ 图片
- 📋 **查看错误信息**：Badcase 数量、错误原因、文件夹路径等详细信息
- 📋 **一键复制任务 ID**：点击复制按钮即可复制任务编号到剪贴板
- ✏️ **原始报告可编辑**：右侧「原始报告」支持就地编辑、保存并下载新的 `error_info.txt` 替换原文件；保存后会自动重新解析 Badcase 数量、错误原因等字段
- 🔍 **图片缩放支持**：适应高度 / 适应宽度两种查看模式
- ⌨️ **键盘导航**：上下箭头快速切换任务

## 🚀 在线使用（推荐）

两个工具均已通过 **GitHub Pages** 部署，无需下载安装：

### 标注工具
👉 **[https://shiren23.github.io/grading-image-annotation-tool/annotation-tool.html](https://shiren23.github.io/grading-image-annotation-tool/annotation-tool.html)**

### 结果查看工具
👉 **[https://shiren23.github.io/grading-image-annotation-tool/result-viewer.html](https://shiren23.github.io/grading-image-annotation-tool/result-viewer.html)**

> 注意：所有图片和数据均在浏览器本地处理，不会上传到任何服务器。

## 快速开始

### 环境要求

- 现代浏览器（推荐 Chrome / Edge / Safari）
- 不需要安装任何后端服务或依赖

### 部署方式

本工具是单个 HTML 文件，部署非常简单：

#### 方式一：在线使用（推荐）

- **标注工具**： [https://shiren23.github.io/grading-image-annotation-tool/annotation-tool.html](https://shiren23.github.io/grading-image-annotation-tool/annotation-tool.html)
- **结果查看工具**： [https://shiren23.github.io/grading-image-annotation-tool/result-viewer.html](https://shiren23.github.io/grading-image-annotation-tool/result-viewer.html)

1. 打开对应工具页面
2. 点击「选择文件夹」按钮
3. 选择对应文件夹即可使用

#### 方式二：直接本地打开

1. 下载仓库中的 `annotation-tool.html` 或 `result-viewer.html`
2. 用浏览器直接双击打开该文件
3. 点击「选择文件夹」按钮即可

#### 方式三：通过本地 HTTP 服务器访问

如果你希望更稳定的本地访问体验，可以启动一个静态文件服务器：

```bash
# 进入项目目录
cd grading-image-annotation-tool

# Python 3
python3 -m http.server 8080

# 或用 Node.js
npx serve .
```

然后在浏览器访问 `http://localhost:8080/annotation-tool.html`

#### 方式四：部署到任意静态网站托管服务

由于本工具是纯前端静态页面，可以部署到：

- GitHub Pages
- Vercel
- Netlify
- 任意 Nginx / Apache 静态站点

只需将 `annotation-tool.html` 上传到托管服务即可。

## 使用说明

### 1. 准备批阅任务文件夹

确保你的文件夹结构如下：

```
批阅任务文件夹/
├── 未匹配/
│   ├── 1/
│   │   ├── 1.jpg              # 任务图片
│   │   └── metadata.yaml      # 包含 task_ids
│   ├── 2/
│   │   ├── 2.jpg
│   │   └── metadata.yaml
│   └── ...
└── 学生卷/
    ├── 张三/
    │   ├── 张三.jpg
    │   └── metadata.yaml
    └── ...
```

`metadata.yaml` 内容示例：

```yaml
task_ids:
  - "db45c6d8-04ed-4a71-a7d2-2179957bd9b4"
```

### 2. 加载任务

1. 打开工具页面
2. 点击左上角「📁 选择文件夹」按钮
3. 在弹出的文件选择器中，选中**批阅任务文件夹**（最外层文件夹）
4. 工具会自动扫描所有子文件夹，匹配图片与 YAML 文件

### 3. 进行标注

#### 左侧标记栏

- **Badcase 数量**：点击 `1` 或 `2`，或在输入框中填入具体数字
- **错误原因**：点击对应按钮可多选，支持 `切题`、`OCR`、`解题`、`判题`

#### 右侧图片区域

- **画笔**：按住鼠标左键在图片上拖动，绘制红笔痕迹
- **橡皮**：擦除已绘制的痕迹
- **粗细**：选择 2px / 4px / 6px 三种线条粗细
- **清空**：清除当前图片上的所有痕迹

### 4. 保存或跳过

- 如果你进行了任何标注（勾画 / 选择数量 / 选择原因），点击「✓ 保存标注」
- 如果当前图片没有问题、不需要标注，直接点击「→ 跳过此图」（按钮会根据当前状态自动切换文字）
- 保存后会自动跳转到下一张图片

### 5. 导出结果

完成所有标注后，点击右上角「📦 导出结果」按钮，会下载一个 ZIP 文件，结构如下：

```
批阅标注结果_2026-06-10T12-00-00.zip
├── db45c6d8-04ed-4a71-a7d2-2179957bd9b4/    # 以任务编号命名的文件夹
│   ├── marked_1.jpg                          # 带有红笔勾画痕迹的图片
│   ├── error_info.txt                        # 错误信息文本
│   └── task_id.txt                           # 任务编号
├── bda0718b-3e30-4cc4-93b1-265eb54a86d2/
│   └── ...
└── 标注报告.txt                               # 总标注统计报告
```

`error_info.txt` 示例：

```
任务编号: db45c6d8-04ed-4a71-a7d2-2179957bd9b4
文件夹: 未匹配/1
图片名称: 1.jpg
标注时间: 2026-06-10T12:00:00.000Z

Badcase 数量: 2
错误原因: 切题, OCR

--- 详细信息 ---
是否有勾画痕迹: 是
```

### 6. 使用结果查看工具浏览标注结果

1. 将导出的 ZIP 文件解压到本地
2. 打开 **结果查看工具**（`result-viewer.html`）
3. 点击「选择文件夹」，选中解压后的**标注结果文件夹**
4. 工具会自动扫描所有任务子文件夹，展示带批注的图片和错误信息
5. 左侧任务列表点击切换不同任务，右侧信息面板展示详细信息
6. 点击任务编号旁的「复制」按钮即可复制任务 ID
7. 如需修改某任务的报告：在右侧「原始报告」区域点击「✏️ 编辑」，修改文本后点击「💾 保存」，工具会自动重新解析相关字段，并下载新的 `error_info.txt`（在支持的浏览器中可直接覆盖原文件）

## 快捷键

### 标注工具快捷键

| 快捷键 | 功能 |
|--------|------|
| `←` `→` | 上一张 / 下一张图片 |
| `S` / `Enter` | 保存标注 / 跳过此图 |

### 结果查看工具快捷键

| 快捷键 | 功能 |
|--------|------|
| `↑` `↓` | 上一个 / 下一个任务 |
| `←` `→` | 上一个 / 下一个任务 |

## 浏览器兼容性

- ✅ Chrome / Edge（推荐）
- ✅ Safari
- ✅ Firefox

> 注意：由于浏览器安全策略，本工具通过 JavaScript 读取本地文件夹并导出 ZIP，所有数据处理均在浏览器本地完成，不会上传到任何服务器。

## 文件说明

| 文件 | 说明 |
|------|------|
| `annotation-tool.html` | **标注工具**主页面，独立可运行 |
| `result-viewer.html` | **结果查看工具**主页面，独立可运行 |
| `test_annotation_tool.py` | 标注工具 Playwright 自动化测试脚本（16 项测试） |
| `test_result_viewer.py` | 结果查看工具 Playwright 自动化测试脚本（10 项测试） |
| `test_data/` | 标注工具测试数据 |
| `test_results/` | 结果查看工具测试数据（模拟导出结果） |
| `annotation-tool-prototype.html` | 早期 UI 原型页面 |
| `README.md` | 本说明文件 |

## 运行测试

如果你想验证工具功能是否正常，可以运行自动化测试：

```bash
# 安装 Playwright for Python
pip3 install playwright
python3 -m playwright install chromium

# 运行测试
python3 test_annotation_tool.py
```

测试将自动启动本地 HTTP 服务器，并通过无头浏览器完成 14 项功能测试。

## 许可证

MIT License
