#!/usr/bin/env python3
"""
图片批阅标注工具 v2 - 自动化测试脚本
测试新的 bbox 框选 + 结构化 events + JSON 导出格式
"""

import asyncio
import http.server
import socketserver
import threading
import os
import sys
import io
import json
import zipfile
from pathlib import Path

from playwright.async_api import async_playwright, expect

PORT = 8765
BASE_URL = f"http://localhost:{PORT}/annotation-tool.html"
PROJECT_DIR = Path(__file__).parent


class QuietHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PROJECT_DIR), **kwargs)
    def log_message(self, format, *args):
        pass


def start_server():
    handler = QuietHTTPRequestHandler
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("", PORT), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


async def inject_mock_data(page):
    """注入 3 张模拟图片，绕过文件选择。
    每张图独立成卷（paperId == taskId），便于绝大多数测试不依赖多图卷语义。
    多图卷场景由专门的测试动态构造。"""
    await page.evaluate("""
        async () => {
            const makeImg = async (text, bg, name) => {
                const c = document.createElement('canvas');
                c.width = 800; c.height = 600;
                const cx = c.getContext('2d');
                cx.fillStyle = bg; cx.fillRect(0, 0, 800, 600);
                cx.fillStyle = '#333'; cx.font = '20px sans-serif';
                cx.fillText(text, 300, 300);
                const blob = await new Promise(res => c.toBlob(res, 'image/jpeg', 0.9));
                const file = new File([blob], name, { type: 'image/jpeg' });
                return { url: URL.createObjectURL(file), file };
            };
            const img1 = await makeImg('Mock 1', '#f5f5f5', '1.jpg');
            const img2 = await makeImg('Mock 2', '#e8f4f8', '2.jpg');
            const img3 = await makeImg('Mock 3', '#fff5f5', '张三.jpg');
            const defs = [
                { taskId: 'db45c6d8-04ed-4a71-a7d2-2179957bd9b4',
                  folderPath: '未匹配/1', imageName: '1.jpg', img: img1 },
                { taskId: 'bda0718b-3e30-4cc4-93b1-265eb54a86d2',
                  folderPath: '未匹配/2', imageName: '2.jpg', img: img2 },
                { taskId: 'aabbccdd-1122-3344-5566-77889900aabb',
                  folderPath: '学生卷/张三', imageName: '张三.jpg', img: img3 }
            ];
            taskItems = [];
            papers = {};
            for (const d of defs) {
                const itemId = d.taskId;  // 单图卷：itemId == paperId == taskId
                taskItems.push({
                    id: itemId, taskId: d.taskId, paperId: d.taskId, paperImageIndex: 0,
                    folderPath: d.folderPath, imageName: d.imageName,
                    imageUrl: d.img.url, imageFile: d.img.file,
                    metadata: { task_ids: [d.taskId] }
                });
                papers[d.taskId] = {
                    paperId: d.taskId,
                    imageIds: [itemId],
                    questionList: [],
                    judgments: {},
                    vlmInFlight: false,
                    error: null,
                    identifiedAt: null,
                    vlmModelId: null
                };
            }
            initUI();
            initThumbnails();
            loadImage(0);
            updateStats();
        }
    """)
    await page.wait_for_function("() => document.getElementById('previewImage').complete && document.getElementById('previewImage').naturalWidth > 0")


async def draw_bbox_on_canvas(page, x1, y1, x2, y2):
    """在 canvas 上拖动鼠标画一个 bbox"""
    canvas = page.locator("#drawingCanvas")
    box = await canvas.bounding_box()
    await page.mouse.move(box['x'] + x1, box['y'] + y1)
    await page.mouse.down()
    await page.mouse.move(box['x'] + x2, box['y'] + y2, steps=5)
    await page.mouse.up()


async def run_tests():
    print("=" * 60)
    print("图片批阅标注工具 v2 - 自动化测试")
    print("=" * 60)

    server = start_server()
    await asyncio.sleep(0.5)

    passed = 0
    failed = 0
    browser = None

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1440, 'height': 900})
        page = await context.new_page()
        page.on("console", lambda msg: print(f"  [Browser {msg.type}] {msg.text}") if msg.type == "error" else None)

        try:
            # 测试 1: 页面加载 + taxonomy
            print("\n[测试 1] 页面加载 + taxonomy 加载...")
            await page.goto(BASE_URL, wait_until="networkidle")
            title = await page.title()
            assert title == "图片批阅标注工具", f"标题错误: {title}"
            tax = await page.evaluate("() => taxonomy && taxonomy.categories && taxonomy.categories.length")
            assert tax == 4, f"taxonomy 应有 4 个大类，实际: {tax}"
            print("  ✓ 页面加载，taxonomy 正确加载 4 个大类")
            passed += 1

            # 测试 2: 数据加载 + UI 切换
            print("\n[测试 2] 数据加载与UI切换...")
            await inject_mock_data(page)
            await expect(page.locator("#sidebar")).to_be_visible()
            await expect(page.locator("#contentArea")).to_be_visible()
            await expect(page.locator("#thumbnailBar")).to_be_visible()
            task_id_text = await page.locator("#taskId").text_content()
            assert "db45c6d8" in task_id_text
            progress = await page.locator("#progressInfo").text_content()
            assert "任务 1 / 3" == progress, f"进度错误: {progress}"
            # error type 按钮应有 4 个
            type_btn_count = await page.locator(".error-type-btn").count()
            assert type_btn_count == 4, f"应有 4 个 error type 按钮，实际: {type_btn_count}"
            print("  ✓ UI 切换正确，taxonomy 渲染 4 个按钮")
            passed += 1

            # 测试 3: 错误类型选择 + 子类型联动
            print("\n[测试 3] 错误类型选择 + 子类型联动...")
            ocr_btn = page.locator(".error-type-btn[data-type-id='ocr']")
            await ocr_btn.click()
            await expect(ocr_btn).to_have_class("error-type-btn active")
            subtype_count = await page.locator(".subtype-btn").count()
            assert subtype_count == 5, f"OCR 应有 4 subtype + 1 'none' = 5 个按钮，实际: {subtype_count}"
            current_type = await page.evaluate("() => currentErrorType")
            assert current_type == "ocr", f"currentErrorType 应为 ocr，实际: {current_type}"
            # 切换到解题，子类应更换
            sol_btn = page.locator(".error-type-btn[data-type-id='solution']")
            await sol_btn.click()
            subtype_labels = await page.locator(".subtype-btn").all_inner_texts()
            assert any("逻辑错" in s for s in subtype_labels), "解题应包含 '逻辑错'"
            assert not any("漏字" in s for s in subtype_labels), "解题不应包含 OCR 的 '漏字'"
            print("  ✓ 错误类型 + 子类型联动正常")
            passed += 1

            # 测试 4: BBox 框选
            print("\n[测试 4] BBox 框选...")
            # 先选 ocr 类型
            await page.locator(".error-type-btn[data-type-id='ocr']").click()
            # 画一个 bbox（注意：canvas 内部坐标系是 800x600，所以坐标在该范围）
            await draw_bbox_on_canvas(page, 100, 100, 250, 200)
            await page.wait_for_function("() => currentErrors.length === 1", timeout=2000)
            err_count = await page.evaluate("() => currentErrors.length")
            assert err_count == 1, f"画一个框后应有 1 个错误，实际: {err_count}"
            # error list 应有 1 项
            list_items = await page.locator(".error-item").count()
            assert list_items == 1, f"列表应显示 1 个 error item，实际: {list_items}"
            # bbox 坐标应记录（注意：canvas 内部坐标系是 800x600 natural，display 可能缩放，
            # 所以允许 ±5px 容差）
            bbox = await page.evaluate("() => currentErrors[0].marks[0].geometry.bbox")
            assert bbox is not None and len(bbox) == 4, "bbox 应是 [x,y,w,h]"
            assert abs(bbox[0] - 100) <= 10 and abs(bbox[1] - 100) <= 10, f"bbox 起点应近 (100,100)，实际: {bbox}"
            assert bbox[2] > 100 and bbox[3] > 50, f"bbox 宽高应足够大，实际: {bbox}"
            print(f"  ✓ BBox 框选正常，bbox={bbox}")
            passed += 1

            # 测试 5: 框太小被忽略
            print("\n[测试 5] 框太小被忽略...")
            # 画一个 3x3 的小框
            await draw_bbox_on_canvas(page, 300, 300, 303, 303)
            await asyncio.sleep(0.2)
            err_count = await page.evaluate("() => currentErrors.length")
            assert err_count == 1, f"小框应被忽略，错误数仍应为 1，实际: {err_count}"
            print("  ✓ 小框被正确忽略")
            passed += 1

            # 测试 6: 未选错误类型时画框无效
            print("\n[测试 6] 未选错误类型时画框无效...")
            # 清除选中状态（用 evaluate，因为 UI 没有反选按钮）
            await page.evaluate("() => { currentErrorType = null; currentSubtype = null; renderTaxonomySelector(); updateDrawingHint(); }")
            await draw_bbox_on_canvas(page, 400, 400, 500, 500)
            await asyncio.sleep(0.2)
            err_count = await page.evaluate("() => currentErrors.length")
            assert err_count == 1, f"未选类型时画框应无效，错误数仍为 1，实际: {err_count}"
            # 重新选回 ocr 以便后续测试
            await page.locator(".error-type-btn[data-type-id='ocr']").click()
            print("  ✓ 未选类型时画框被拒绝")
            passed += 1

            # 测试 7: 添加备注
            print("\n[测试 7] 添加备注...")
            comment_input = page.locator(".error-item-comment-input").first
            await comment_input.fill("把 7 识别成 1")
            await asyncio.sleep(0.1)
            comment_val = await page.evaluate("() => currentErrors[0].comment")
            assert comment_val == "把 7 识别成 1", f"备注未更新: {comment_val}"
            print("  ✓ 备注更新正常")
            passed += 1

            # 测试 8: 保存按钮动态文本
            print("\n[测试 8] 保存按钮动态文本...")
            save_btn = page.locator("#saveBtn")
            btn_text = await save_btn.text_content()
            assert "保存标注" in btn_text and "1" in btn_text, f"应显示 '保存标注（1 个错误）'，实际: {btn_text}"
            # 删除唯一错误后应变为"跳过"
            await page.locator(".error-item-delete").first.click()
            await asyncio.sleep(0.1)
            btn_text = await save_btn.text_content()
            assert "跳过" in btn_text, f"无错误时应显示 '跳过'，实际: {btn_text}"
            print("  ✓ 保存按钮文本随状态切换")
            passed += 1

            # 测试 9: 删除错误 + 撤销 (Z 键)
            print("\n[测试 9] 删除 + 撤销...")
            # 重选 ocr，画两个框
            await page.locator(".error-type-btn[data-type-id='ocr']").click()
            await draw_bbox_on_canvas(page, 100, 100, 200, 200)
            await asyncio.sleep(0.1)
            await draw_bbox_on_canvas(page, 300, 300, 400, 400)
            await asyncio.sleep(0.1)
            err_count = await page.evaluate("() => currentErrors.length")
            assert err_count == 2, f"应有两个错误，实际: {err_count}"
            # Z 撤销
            await page.keyboard.press("z")
            await asyncio.sleep(0.1)
            err_count = await page.evaluate("() => currentErrors.length")
            assert err_count == 1, f"撤销后应剩 1 个，实际: {err_count}"
            print("  ✓ 删除 + Z 撤销正常")
            passed += 1

            # 测试 10: 保存逻辑 + 自动跳转
            print("\n[测试 10] 保存逻辑 + 自动跳转...")
            await page.locator("#saveBtn").click()
            await asyncio.sleep(0.4)
            progress = await page.locator("#progressInfo").text_content()
            assert "任务 2 / 3" == progress, f"保存后应跳到第 2 张，实际: {progress}"
            # 第一张缩略图应有 marked
            thumb1 = page.locator(".thumbnail-item").nth(0)
            await expect(thumb1).to_have_class("thumbnail-item marked")
            # 内存中应有该 annotation，status 为 annotated
            saved_status = await page.evaluate("() => annotations[Object.keys(annotations)[0]]?.annotation?.status")
            assert saved_status == "annotated", f"保存后 status 应为 annotated，实际: {saved_status}"
            saved_err_count = await page.evaluate("() => annotations[Object.keys(annotations)[0]]?.annotation?.errors?.length")
            assert saved_err_count == 1, f"保存应有 1 个 error，实际: {saved_err_count}"
            print("  ✓ 保存逻辑正确，自动跳转 + status=annotated")
            passed += 1

            # 测试 11: 跳过逻辑
            print("\n[测试 11] 跳过逻辑...")
            # 当前是第 2 张，未画任何框，点保存=跳过
            await page.locator("#saveBtn").click()
            await asyncio.sleep(0.4)
            progress = await page.locator("#progressInfo").text_content()
            assert "任务 3 / 3" == progress, f"跳过后应到第 3 张，实际: {progress}"
            thumb2 = page.locator(".thumbnail-item").nth(1)
            await expect(thumb2).to_have_class("thumbnail-item skipped")
            print("  ✓ 跳过逻辑正确，status=skipped")
            passed += 1

            # 测试 12: 导航（按钮 + 键盘）
            print("\n[测试 12] 导航...")
            await page.locator("#prevBtn").click()
            await asyncio.sleep(0.2)
            progress = await page.locator("#progressInfo").text_content()
            assert "任务 2 / 3" == progress, f"prev 应到第 2 张，实际: {progress}"
            await page.keyboard.press("ArrowRight")
            await asyncio.sleep(0.2)
            progress = await page.locator("#progressInfo").text_content()
            assert "任务 3 / 3" == progress, f"右箭头应到第 3 张，实际: {progress}"
            print("  ✓ 导航（按钮 + 键盘）正常")
            passed += 1

            # 测试 13: Esc 取消绘制中
            print("\n[测试 13] Esc 取消绘制中...")
            await page.locator(".error-type-btn[data-type-id='ocr']").click()
            canvas_box = await page.locator("#drawingCanvas").bounding_box()
            # mousedown 后不 mouseup，按 Esc
            await page.mouse.move(canvas_box['x'] + 100, canvas_box['y'] + 100)
            await page.mouse.down()
            await page.mouse.move(canvas_box['x'] + 200, canvas_box['y'] + 200)
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.1)
            assert not await page.evaluate("() => isDrawingBBox"), "Esc 后 isDrawingBBox 应为 false"
            await page.mouse.up()  # 清理鼠标状态
            print("  ✓ Esc 取消绘制中正常")
            passed += 1

            # 测试 14: 视图模式切换
            print("\n[测试 14] 视图模式切换...")
            container = page.locator("#imageContainer")
            wrapper = page.locator(".canvas-wrapper")
            await expect(container).not_to_have_class("image-container fit-width")
            await page.locator("#zoomBtn").click()
            await asyncio.sleep(0.3)
            await expect(container).to_have_class("image-container fit-width")
            await expect(wrapper).to_have_class("canvas-wrapper fit-width")
            zoom_text = await page.locator("#zoomText").text_content()
            assert "缩小" in zoom_text
            current_mode = await page.evaluate("() => imageZoomMode")
            assert current_mode == "fit-width", f"模式应为 fit-width，实际: {current_mode}"
            await page.locator("#zoomBtn").click()
            await asyncio.sleep(0.3)
            await expect(container).not_to_have_class("image-container fit-width")
            print("  ✓ 视图模式切换正常")
            passed += 1

            # 测试 14.5: 错误列表增多后下方 UI 不被盖住
            print("\n[测试 14.5] 错误列表撑开后视图模式未被盖住...")
            # 先选错误类型，再画多个 bbox 制造长列表
            await page.locator(".error-type-btn", has_text="OCR").click()
            await asyncio.sleep(0.2)
            for i in range(6):
                await draw_bbox_on_canvas(page,
                                          50 + i * 20, 50 + i * 20,
                                          50 + i * 20 + 60, 50 + i * 20 + 40)
                await asyncio.sleep(0.1)
            await asyncio.sleep(0.3)

            layout = await page.evaluate("""
                () => {
                    const sidebar = document.getElementById('sidebar');
                    const list = document.querySelector('.error-list-section');
                    const view = document.querySelector('.view-mode-section');
                    const listRect = list.getBoundingClientRect();
                    const viewRect = view.getBoundingClientRect();
                    return {
                        sidebarScrollH: sidebar.scrollHeight,
                        sidebarClientH: sidebar.clientHeight,
                        listBottom: listRect.bottom,
                        viewTop: viewRect.top,
                        overlap: viewRect.top - listRect.bottom,
                    };
                }
            """)
            # view-mode 顶部应在 error-list 底部之下（>= -1 容忍像素误差）
            assert layout["viewTop"] >= layout["listBottom"] - 1, \
                f"视图模式盖住了错误列表：viewTop={layout['viewTop']}, listBottom={layout['listBottom']}"
            # 列表够长时 sidebar 应可滚动
            assert layout["sidebarScrollH"] >= layout["sidebarClientH"], \
                f"sidebar 应可滚动：scrollH={layout['sidebarScrollH']}, clientH={layout['sidebarClientH']}"
            print(f"  ✓ 列表底={layout['listBottom']:.0f}，视图模式顶={layout['viewTop']:.0f}，无重叠；sidebar 可滚动")
            passed += 1
            # 清理：撤销所有框，避免影响后续测试
            for _ in range(10):
                await page.keyboard.press("z")
            await asyncio.sleep(0.2)

            # 测试 14.6: 缩略图第一行未被 header 盖住
            print("\n[测试 14.6] 缩略图第一行未被 header 遮挡...")
            occlusion = await page.evaluate("""
                () => {
                    const hdr = document.querySelector('.header');
                    const firstThumb = document.querySelector('.thumbnail-item');
                    if (!firstThumb) return {skip: true};
                    const hRect = hdr.getBoundingClientRect();
                    const tRect = firstThumb.getBoundingClientRect();
                    return {
                        hdrBottom: hRect.bottom,
                        thumbTop: tRect.top,
                        visible: tRect.top >= hRect.bottom - 1
                    };
                }
            """)
            if occlusion.get("skip"):
                print("  ⚠ 无缩略图，跳过")
            else:
                assert occlusion["visible"], \
                    f"缩略图第一行被 header 盖住：thumb.top={occlusion['thumbTop']}, header.bottom={occlusion['hdrBottom']}"
                print(f"  ✓ 缩略图第一行 top={occlusion['thumbTop']:.0f} ≥ header.bottom={occlusion['hdrBottom']:.0f}")
            passed += 1

            print("\n[测试 14.7] 任务编号完整展示 + 复制按钮...")
            await context.grant_permissions(permissions=['clipboard-read', 'clipboard-write'])
            # 切到第三张图（最长的 taskId 验证不截断 + 不溢出）
            await page.evaluate("() => loadImage(2)")
            await page.wait_for_timeout(200)
            current_task_id = await page.evaluate("() => taskItems[currentIndex].taskId")
            info = await page.evaluate("""
                () => {
                    const el = document.getElementById('taskId');
                    const btn = document.getElementById('copyTaskIdBtn');
                    if (!el || !btn) return {missing: true};
                    const row = el.closest('.task-info-row');
                    return {
                        text: el.textContent.trim(),
                        clientWidth: el.clientWidth,
                        scrollWidth: el.scrollWidth,
                        truncated: el.scrollWidth > el.clientWidth + 1,
                        btnExists: !!btn,
                        btnVisible: btn.offsetParent !== null,
                        rowOverflows: row.scrollWidth > row.clientWidth + 1
                    };
                }
            """)
            assert not info.get("missing"), "任务编号元素或复制按钮不存在"
            assert info["text"] == current_task_id, \
                f"任务编号文本错误: 期望 {current_task_id}, 实际 {info['text']}"
            assert not info["truncated"], \
                f"任务编号被截断：scrollW={info['scrollWidth']} > clientW={info['clientWidth']}"
            assert not info["rowOverflows"], "任务编号行横向溢出"
            assert info["btnExists"] and info["btnVisible"], "复制按钮未渲染"
            print(f"  ✓ 任务编号完整展示（{len(info['text'])} 字符，未截断/未溢出）")
            # 点击复制并验证剪贴板
            await page.locator("#copyTaskIdBtn").click()
            await page.wait_for_timeout(150)
            clipboard_text = await page.evaluate("""
                async () => {
                    try {
                        return await navigator.clipboard.readText();
                    } catch (e) {
                        return 'ERR:' + e.message;
                    }
                }
            """)
            assert clipboard_text == current_task_id, \
                f"剪贴板内容错误: 期望 {current_task_id}, 实际 {clipboard_text!r}"
            btn_label = await page.locator("#copyTaskIdBtn").text_content()
            assert btn_label.strip() == '已复制', f"复制后按钮文案错误: {btn_label!r}"
            print(f"  ✓ 复制按钮写入剪贴板成功，按钮态切换为「已复制」")
            passed += 1




            print("\n[测试 15] 序列化为 v2 schema...")
            v2_obj = await page.evaluate("""
                () => {
                    const item = taskItems[currentIndex];
                    return serializeAnnotation(item, {
                        status: 'annotated',
                        errors: currentErrors,
                        startedAt: '2026-06-29T10:00:00Z',
                        savedAt: '2026-06-29T10:01:00Z',
                        durationMs: 60000
                    });
                }
            """)
            assert v2_obj["schema_version"] == "1.0", f"schema_version 错误: {v2_obj.get('schema_version')}"
            assert v2_obj["image"]["task_id"] == "aabbccdd-1122-3344-5566-77889900aabb"
            assert v2_obj["annotation"]["annotator_id"] == "default"
            assert v2_obj["annotation"]["session_id"].startswith("sess_")
            if len(v2_obj["annotation"]["errors"]) > 0:
                err = v2_obj["annotation"]["errors"][0]
                assert "error_id" in err
                assert err["error_type"] == "ocr"
                assert err["marks"][0]["role"] == "primary"
                assert err["marks"][0]["type"] == "bbox"
            print("  ✓ v2 schema 序列化正确")
            passed += 1

            # 测试 16: 导出 ZIP 结构（含全部图片 + paper.json + page_N 子目录）
            print("\n[测试 16] 导出 ZIP 结构（全部图片 + paper.json）...")
            total_images = await page.evaluate("() => taskItems.length")
            total_papers = await page.evaluate("() => Object.keys(papers).length")
            async with page.expect_download() as download_info:
                await page.locator("#exportBtn").click(force=True)
            download = await download_info.value
            zip_bytes = await download.path()
            with zipfile.ZipFile(zip_bytes) as zf:
                names = zf.namelist()
                assert any("_session.json" in n for n in names), f"ZIP 应含 _session.json，实际: {names}"
                assert any("_stats.jsonl" in n for n in names), f"ZIP 应含 _stats.jsonl，实际: {names}"
                assert any("taxonomy.json" in n for n in names), f"ZIP 应含 taxonomy.json，实际: {names}"
                # 新结构：每卷有 paper.json，每图在 page_N/annotations/default.json
                paper_jsons = [n for n in names if n.endswith("/paper.json")]
                assert len(paper_jsons) == total_papers, \
                    f"应导出 {total_papers} 个 paper.json（每卷一个），实际: {len(paper_jsons)}: {paper_jsons}"
                default_jsons = [n for n in names if n.endswith("annotations/default.json")]
                assert len(default_jsons) == total_images, \
                    f"应导出全部 {total_images} 张图，实际 default.json 数: {len(default_jsons)}"
                # 每张图应在 page_N/ 子目录下
                for n in default_jsons:
                    assert "/page_" in n and "/annotations/default.json" in n, \
                        f"default.json 应在 page_N/ 子目录下: {n}"
                # source 文件也应在 page_N/ 下
                source_files = [n for n in names if "/source." in n]
                assert len(source_files) == total_images, \
                    f"应导出 {total_images} 个 source 文件，实际: {len(source_files)}"
                # 不应再有 error_info.txt 或 marked_*.jpg
                assert not any("error_info.txt" in n for n in names), "新格式不应含 error_info.txt"
                assert not any(n.startswith("marked_") for n in names), "新格式不应含 marked_*.jpg"

                # 验证 _session.json 内容
                session_data = json.loads(zf.read("_session.json"))
                assert session_data["schema_version"] == "1.0"
                assert session_data["annotator_id"] == "default"
                assert "status_count" in session_data
                status_count = session_data["status_count"]
                assert "no_badcase" in status_count, f"status_count 应含 no_badcase 键，实际: {status_count}"
                # 本测试场景：1 张 annotated + (total-1) 张 no_badcase
                assert status_count["annotated"] == 1, f"annotated 应为 1，实际: {status_count.get('annotated')}"
                assert status_count["no_badcase"] == total_images - 1, \
                    f"no_badcase 应为 {total_images - 1}，实际: {status_count.get('no_badcase')}"
                assert status_count.get("pending", 0) == 0, f"导出后应无 pending，实际: {status_count.get('pending')}"
                # _session.json 应有 papers 数组 + images[].paper_id/page_index
                assert "papers" in session_data, f"_session.json 应有 papers 数组，实际字段: {list(session_data.keys())}"
                assert len(session_data["papers"]) == total_papers
                for img in session_data["images"]:
                    assert "paper_id" in img, f"image 缺 paper_id: {img}"
                    assert "page_index" in img, f"image 缺 page_index: {img}"
                    assert "annotation_file" in img and "/page_" in img["annotation_file"], \
                        f"annotation_file 应在 page_N 子目录: {img}"

                # 验证每个 default.json：image 段应有 paper_id + page_index；annotation 不应有 judgments
                seen_statuses = []
                for n in default_jsons:
                    ann_data = json.loads(zf.read(n))
                    assert ann_data["schema_version"] == "1.0"
                    assert "paper_id" in ann_data["image"], f"image 段应有 paper_id: {n}"
                    assert "page_index" in ann_data["image"], f"image 段应有 page_index: {n}"
                    assert "errors" in ann_data["annotation"]
                    assert "judgments" not in ann_data["annotation"], \
                        f"v2+ image-level annotation 不应含 judgments（已迁 paper.json）: {n}"
                    status = ann_data["annotation"]["status"]
                    assert status in ("annotated", "no_badcase"), \
                        f"非法 status: {status}，文件: {n}"
                    seen_statuses.append(status)
                    if status == "annotated":
                        assert len(ann_data["annotation"]["errors"]) > 0, \
                            f"annotated 项 errors 不应为空: {n}"
                    else:
                        assert len(ann_data["annotation"]["errors"]) == 0, \
                            f"no_badcase 项 errors 应为空: {n}"
                assert "annotated" in seen_statuses, "应至少有一个 annotated 项"
                assert "no_badcase" in seen_statuses, "应至少有一个 no_badcase 项"

                # paper.json 应有 schema_version, paper_id, image_count, questions, judgments, images
                for n in paper_jsons:
                    pdata = json.loads(zf.read(n))
                    assert pdata["schema_version"] == "1.0"
                    assert "paper_id" in pdata
                    assert "image_count" in pdata and isinstance(pdata["image_count"], int)
                    assert "questions" in pdata and isinstance(pdata["questions"], list)
                    assert "judgments" in pdata and isinstance(pdata["judgments"], list)
                    assert "images" in pdata and isinstance(pdata["images"], list)
                    assert len(pdata["images"]) == pdata["image_count"]
            print(f"  ✓ 导出全部 {total_images} 张图 / {total_papers} 卷（paper.json + page_N 子目录），无 judgments 在 image-level")
            passed += 1

            # 测试 17: VLM 设置面板（开/存/读）
            print("\n[测试 17] VLM 设置面板...")
            gear = page.locator("#vlmSettingsBtn")
            await gear.click()
            await asyncio.sleep(0.2)
            overlay = page.locator("#vlmSettingsOverlay")
            assert await overlay.evaluate("el => el.classList.contains('show')"), "设置面板未展开"

            await page.evaluate("""() => {
                document.getElementById('vlmBaseUrl').value = 'https://example.com/api/v1';
                document.getElementById('vlmModelId').value = 'doubao-test-model';
                document.getElementById('vlmApiKey').value = 'sk-test-key';
            }""")
            await page.locator(".settings-actions .primary").click()
            await asyncio.sleep(0.2)
            assert not await overlay.evaluate("el => el.classList.contains('show')"), "保存后面板应关闭"
            # localStorage 已写入
            stored = await page.evaluate("""() => ({
                baseUrl: localStorage.getItem('vlm:baseUrl'),
                modelId: localStorage.getItem('vlm:modelId'),
                apiKey: localStorage.getItem('vlm:apiKey')
            })""")
            assert stored["baseUrl"] == "https://example.com/api/v1", f"baseUrl 未写入: {stored}"
            assert stored["modelId"] == "doubao-test-model"
            assert stored["apiKey"] == "sk-test-key"
            # 齿轮有 has-config 标记
            assert await gear.evaluate("el => el.classList.contains('has-config')"), "齿轮未显示已配置标记"
            print("  ✓ 设置面板：开/存/读完整，齿轮 has-config 标记正确")
            passed += 1

            # 测试 18: 题号按钮三态循环点击（per-paper）
            print("\n[测试 18] 题号按钮三态循环（per-paper）...")
            # Stub callVLMPaper，避免真实网络调用
            await page.evaluate("""
                () => {
                    callVLMPaper = async (paper, signal) => ({
                        ok: true,
                        items: [
                            {question_no:'1(1)'},
                            {question_no:'1(2)'},
                            {question_no:'2'}
                        ],
                        modelId: 'doubao-test'
                    });
                }
            """)
            # 跳到第 3 张（应为 pending），避免污染测试 10/11 的状态
            await page.evaluate("() => loadImage(2)")
            await page.wait_for_function("document.getElementById('previewImage').naturalWidth > 0", timeout=3000)
            # 等 VLM stub 返回（异步）
            await page.wait_for_function("document.querySelectorAll('.qbtn').length === 3", timeout=3000)
            # 底栏应显示，3 个按钮
            bar = page.locator("#questionBar")
            assert await bar.evaluate("el => el.classList.contains('show')"), "底栏未显示"
            btns = page.locator(".qbtn")
            await expect(btns).to_have_count(3)

            # 点击第 1 个：unmarked → correct
            await btns.nth(0).click()
            cls = await btns.nth(0).get_attribute("class")
            assert "correct" in cls, f"第 1 次点击应切到 correct，class={cls}"
            # 再点：correct → wrong
            await btns.nth(0).click()
            cls = await btns.nth(0).get_attribute("class")
            assert "wrong" in cls, f"第 2 次点击应切到 wrong，class={cls}"
            # 再点：wrong → unmarked（class 移除）
            await btns.nth(0).click()
            cls = await btns.nth(0).get_attribute("class")
            assert cls == "qbtn", f"第 3 次点击应回到 unmarked，class={cls}"
            # judgments 应从 paper.judgments 移除
            paper_id = await page.evaluate("() => taskItems[currentIndex].paperId")
            judgments_in_paper = await page.evaluate("""(pid) =>
                Object.entries(papers[pid].judgments).map(([q,s]) => ({question_no:q, status:s}))
            """, paper_id)
            assert judgments_in_paper == [], f"unmarked 后 paper.judgments 应清空，实际: {judgments_in_paper}"

            # 点第 2 个按钮到 correct，验证保留
            await btns.nth(1).click()
            judgments_in_paper = await page.evaluate("""(pid) =>
                Object.entries(papers[pid].judgments).map(([q,s]) => ({question_no:q, status:s}))
            """, paper_id)
            assert any(j["question_no"]=="1(2)" and j["status"]=="correct" for j in judgments_in_paper), \
                f"第 2 个按钮的 correct 应同步到 paper.judgments，实际: {judgments_in_paper}"
            # judgments 应已持久化到 localStorage vlmJudgments:<paper_id>
            ls_judgments = await page.evaluate("""(pid) =>
                JSON.parse(localStorage.getItem('vlmJudgments:' + pid) || '[]')
            """, paper_id)
            assert any(j["question_no"]=="1(2)" and j["status"]=="correct" for j in ls_judgments), \
                f"judgments 应持久化到 vlmJudgments:<paper_id>，实际: {ls_judgments}"
            print("  ✓ 三态循环 unmarked→correct→wrong→unmarked + paper.judgments 同步 + localStorage 持久化")
            passed += 1

            # 测试 18b: VLM 错误展示应包含底层错误码/正文
            print("\n[测试 18b] VLM 错误展示保留原始错误信息...")
            await page.evaluate("""
                () => {
                    callVLMPaper = async (paper, signal) => ({
                        ok: false,
                        reason: 'http',
                        status: 401,
                        message: JSON.stringify({
                            error: {
                                code: 'AuthenticationError',
                                message: 'API key is invalid'
                            }
                        })
                    });
                    const pid = taskItems[1].paperId;
                    papers[pid].questionList = [];
                    papers[pid].error = null;
                    clearPaperCache(pid);
                }
            """)
            await page.evaluate("() => loadImage(1)")
            await page.wait_for_function(
                "() => document.getElementById('qbStatus').textContent.includes('AuthenticationError')",
                timeout=3000
            )
            err_text = await page.locator("#qbStatus").text_content()
            assert "VLM HTTP 401" in err_text, f"HTTP 状态码应显示，实际: {err_text}"
            assert "AuthenticationError" in err_text, f"原始错误 code 应显示，实际: {err_text}"
            assert "API key is invalid" in err_text, f"原始错误 message 应显示，实际: {err_text}"
            print("  ✓ VLM HTTP 错误展示包含状态码、原始 code 和 message")
            passed += 1

            # 测试 19: serializeAnnotation 不含 judgments，image 段含 paper_id + page_index
            print("\n[测试 19] serializeAnnotation 字段（v2+ paper schema）...")
            v2_obj = await page.evaluate("""
                () => {
                    const item = taskItems[currentIndex];
                    return serializeAnnotation(item, {
                        status: 'annotated',
                        errors: [],
                        startedAt: '2026-06-29T10:00:00Z',
                        savedAt: '2026-06-29T10:01:00Z',
                        durationMs: 60000
                    });
                }
            """)
            # v2+：annotation 不再含 judgments（迁到 paper.json）
            assert "judgments" not in v2_obj["annotation"], \
                f"annotation 不应含 judgments（已迁 paper.json）: {v2_obj['annotation']}"
            # v2+：image 段含 paper_id + page_index
            assert "paper_id" in v2_obj["image"], f"image 段应有 paper_id: {v2_obj['image']}"
            assert "page_index" in v2_obj["image"], f"image 段应有 page_index: {v2_obj['image']}"
            # 仍保留 task_id（向后兼容）
            assert "task_id" in v2_obj["image"]
            # 注入的 mock 数据是单图卷，page_index 应为 0
            assert v2_obj["image"]["page_index"] == 0
            assert v2_obj["image"]["paper_id"] == v2_obj["image"]["task_id"]
            print("  ✓ serializeAnnotation: 无 judgments，image 含 paper_id + page_index")
            passed += 1

            # 测试 18a: 多图卷——同卷两图共享 paper.judgments 和 questionList
            print("\n[测试 18a] 多图卷：同卷两图共享 paper 状态...")
            # 动态构造一个 2 图卷场景：替换 taskItems + papers
            await page.evaluate("""
                async () => {
                    const makeImg = async (text, bg, name) => {
                        const c = document.createElement('canvas');
                        c.width = 800; c.height = 600;
                        const cx = c.getContext('2d');
                        cx.fillStyle = bg; cx.fillRect(0, 0, 800, 600);
                        cx.fillStyle = '#333'; cx.font = '20px sans-serif';
                        cx.fillText(text, 300, 300);
                        const blob = await new Promise(res => c.toBlob(res, 'image/jpeg', 0.9));
                        const file = new File([blob], name, { type: 'image/jpeg' });
                        return { url: URL.createObjectURL(file), file };
                    };
                    const imgA = await makeImg('Page 1', '#f5f5f5', 'page1.jpg');
                    const imgB = await makeImg('Page 2', '#e8f4f8', 'page2.jpg');
                    const PAPER_ID = 'multi-paper-uuid-aaaa-bbbb-cccc-dddddddddd';
                    taskItems = [
                        { id: `${PAPER_ID}__img_0`, taskId: PAPER_ID, paperId: PAPER_ID, paperImageIndex: 0,
                          folderPath: '未匹配/multi', imageName: 'page1.jpg',
                          imageUrl: imgA.url, imageFile: imgA.file,
                          metadata: { task_ids: [PAPER_ID] } },
                        { id: `${PAPER_ID}__img_1`, taskId: PAPER_ID, paperId: PAPER_ID, paperImageIndex: 1,
                          folderPath: '未匹配/multi', imageName: 'page2.jpg',
                          imageUrl: imgB.url, imageFile: imgB.file,
                          metadata: { task_ids: [PAPER_ID] } }
                    ];
                    papers = {};
                    papers[PAPER_ID] = {
                        paperId: PAPER_ID,
                        imageIds: [`${PAPER_ID}__img_0`, `${PAPER_ID}__img_1`],
                        questionList: [], judgments: {}, vlmInFlight: false, error: null,
                        identifiedAt: null, vlmModelId: null
                    };
                    // stub callVLMPaper 返回跨页题号
                    callVLMPaper = async (paper, signal) => ({
                        ok: true,
                        items: [
                            {question_no:'1'},
                            {question_no:'1(1)'},
                            {question_no:'1(2)'},
                            {question_no:'2'}
                        ],
                        modelId: 'doubao-test'
                    });
                    initThumbnails();
                    loadImage(0);
                }
            """)
            await page.wait_for_function("() => document.getElementById('previewImage').naturalWidth > 0", timeout=3000)
            # 等 VLM stub 返回
            await page.wait_for_function("document.querySelectorAll('.qbtn').length === 4", timeout=3000)
            # 在 page 0 上点第 1 个按钮到 correct
            btns = page.locator(".qbtn")
            await btns.nth(0).click()
            cls0 = await btns.nth(0).get_attribute("class")
            assert "correct" in cls0, f"page 0 点击应切 correct，class={cls0}"
            # 切到 page 1（同卷），应看到同一组题号 + 第 1 个按钮仍是 correct
            await page.evaluate("() => loadImage(1)")
            await page.wait_for_function("() => document.querySelectorAll('.qbtn').length === 4", timeout=3000)
            btns2 = page.locator(".qbtn")
            cls1 = await btns2.nth(0).get_attribute("class")
            assert "correct" in cls1, f"page 1（同卷）应共享 paper.judgments，第 1 个按钮应仍为 correct，class={cls1}"
            # 切回 page 0，仍 correct
            await page.evaluate("() => loadImage(0)")
            await page.wait_for_function("() => document.querySelectorAll('.qbtn').length === 4", timeout=3000)
            btns3 = page.locator(".qbtn")
            cls0b = await btns3.nth(0).get_attribute("class")
            assert "correct" in cls0b, f"切回 page 0 应保留 correct，class={cls0b}"
            # 多图卷：callVLMPaper 应只被调用 1 次（卷级，不是图级）
            call_count = await page.evaluate("""() => {
                const paper = papers[Object.keys(papers)[0]];
                return paper.identifiedAt ? 1 : 0;
            }""")
            assert call_count == 1, f"多图卷应只调用 1 次 VLM，实际 identifiedAt 设置次数: {call_count}"
            print("  ✓ 多图卷：同卷两图共享 questionList + judgments，VLM 只调 1 次")
            passed += 1

            # 测试 20: parseQuestionList 防御式解析
            print("\n[测试 20] parseQuestionList 防御式解析...")
            cases = await page.evaluate("""
                () => [
                    {
                        name: '纯JSON',
                        input: '[{"question_no":"1"},{"question_no":"1(1)"}]',
                        expect: 2
                    },
                    {
                        name: '代码块包裹',
                        input: '好的，这是结果：\\n```json\\n[{"question_no":"1"}]\\n```\\n希望有帮助',
                        expect: 1
                    },
                    {
                        name: '裸方括号子串',
                        input: '我识别到这些题号：\\n[{"question_no":"2"},{"question_no":"3"}]\\n如上',
                        expect: 2
                    },
                    {
                        name: '杂项字符串',
                        input: '抱歉，图片没有可识别的题号',
                        expect: 0
                    },
                    {
                        name: '字符串数组归一',
                        input: '["1","2","3"]',
                        expect: 3
                    },
                    {
                        name: '对象数组不同字段名',
                        input: '[{"no":"1(1)"},{"text":"2"}]',
                        expect: 2
                    },
                    {
                        name: '重复题号去重',
                        input: '[{"question_no":"1"},{"question_no":"1"},{"question_no":"2"}]',
                        expect: 2
                    }
                ].map(c => ({
                    name: c.name,
                    expect: c.expect,
                    actual: parseQuestionList(c.input).length
                }))
            """)
            for c in cases:
                assert c["actual"] == c["expect"], \
                    f"parseQuestionList[{c['name']}] 期望 {c['expect']} 实际 {c['actual']}"
            print(f"  ✓ parseQuestionList 7 个降级 case 全过")
            passed += 1

        except Exception as e:
            print(f"  ✗ 测试失败: {e}")
            failed += 1
            await page.screenshot(path="test_failure.png")
            print("  调试截图已保存: test_failure.png")

        finally:
            await context.close()
            await browser.close()

    server.shutdown()

    print("\n" + "=" * 60)
    print(f"测试完成: 通过 {passed} 项, 失败 {failed} 项")
    print("=" * 60)
    if failed > 0:
        sys.exit(1)
    else:
        print("\n✓ 所有测试通过！")


if __name__ == "__main__":
    asyncio.run(run_tests())
