#!/usr/bin/env python3
"""
标注结果查看工具 - 自动化测试脚本
使用 Playwright 进行端到端测试
"""

import asyncio
import http.server
import socketserver
import threading
import re

from playwright.async_api import async_playwright, expect

PORT = 8766
BASE_URL = f"http://localhost:{PORT}/result-viewer.html"


class QuietHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
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
    """注入模拟数据（新 v2 schema 形态）"""
    await page.evaluate("""
        async () => {
            // 创建模拟图片
            const canvas = document.createElement('canvas');
            canvas.width = 800;
            canvas.height = 600;
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = '#f5f5f5';
            ctx.fillRect(0, 0, 800, 600);
            ctx.fillStyle = '#e74c3c';
            ctx.beginPath();
            ctx.arc(200, 200, 30, 0, Math.PI * 2);
            ctx.stroke();
            const dataUrl = canvas.toDataURL('image/jpeg');

            function mkError(eid, etype, subtype, comment, bbox) {
                return {
                    error_id: eid,
                    error_type: etype,
                    error_subtype: subtype,
                    severity: null,
                    comment: comment,
                    marks: [{
                        mark_id: 'm_' + eid,
                        role: 'primary',
                        type: 'bbox',
                        geometry: { bbox: bbox, points: null },
                        color: null,
                        width: 2
                    }],
                    annotator_id: 'default',
                    created_at: '2026-06-10T12:00:00.000Z',
                    updated_at: '2026-06-10T12:00:00.000Z',
                    duration_ms: 3000
                };
            }

            resultItems = [
                {
                    taskId: 'db45c6d8-04ed-4a71-a7d2-2179957bd9b4',
                    folderName: 'db45c6d8-04ed-4a71-a7d2-2179957bd9b4',
                    imageName: 'source.jpg',
                    imageUrl: dataUrl,
                    schemaVersion: '1.0',
                    source: 'v2',
                    annotation: {
                        status: 'annotated',
                        errors: [
                            mkError('err_01', 'topic', 'off_topic', '答非所问', [100, 100, 80, 60]),
                            mkError('err_02', 'ocr', 'char_wrong', '单字识别错', [300, 200, 90, 70])
                        ],
                        session_id: 'sess_test',
                        annotator_id: 'default',
                        started_at: '2026-06-10T12:00:00.000Z',
                        saved_at: '2026-06-10T12:05:00.000Z'
                    }
                },
                {
                    taskId: 'bda0718b-3e30-4cc4-93b1-265eb54a86d2',
                    folderName: 'bda0718b-3e30-4cc4-93b1-265eb54a86d2',
                    imageName: 'source.jpg',
                    imageUrl: dataUrl,
                    schemaVersion: '1.0',
                    source: 'v2',
                    annotation: {
                        status: 'annotated',
                        errors: [
                            mkError('err_01', 'judgment', 'wrong_conclusion', '对错结论错', [50, 50, 200, 150])
                        ],
                        session_id: 'sess_test',
                        annotator_id: 'default',
                        started_at: '2026-06-10T12:05:00.000Z',
                        saved_at: '2026-06-10T12:08:00.000Z'
                    }
                },
                {
                    taskId: 'aabbccdd-1122-3344-5566-77889900aabb',
                    folderName: 'aabbccdd-1122-3344-5566-77889900aabb',
                    imageName: 'source.jpg',
                    imageUrl: dataUrl,
                    schemaVersion: '1.0',
                    source: 'v2',
                    annotation: {
                        status: 'annotated',
                        errors: [
                            mkError('err_01', 'topic', 'incomplete', '未覆盖要点', [10, 10, 100, 50]),
                            mkError('err_02', 'ocr', 'char_missing', '漏字', [200, 100, 80, 40]),
                            mkError('err_03', 'solution', 'calc', '计算错', [400, 300, 150, 100])
                        ],
                        session_id: 'sess_test',
                        annotator_id: 'default',
                        started_at: '2026-06-10T12:10:00.000Z',
                        saved_at: '2026-06-10T12:15:00.000Z'
                    }
                }
            ];

            initUI();
            loadTask(0);
        }
    """)


async def run_tests():
    print("=" * 60)
    print("标注结果查看工具 - 自动化测试")
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
            # ============ 测试 1: 页面加载 ============
            print("\n[测试 1] 页面加载...")
            await page.goto(BASE_URL, wait_until="networkidle")
            title = await page.title()
            assert title == "标注结果查看工具"

            empty_state = page.locator("#emptyState")
            await expect(empty_state).to_be_visible()
            print("  ✓ 页面加载成功")
            passed += 1

            # ============ 测试 2: 数据加载与UI切换 ============
            print("\n[测试 2] 数据加载与UI切换...")
            await inject_mock_data(page)
            await asyncio.sleep(0.5)

            await expect(empty_state).to_be_hidden()
            await expect(page.locator("#taskList")).to_be_visible()
            await expect(page.locator("#imageArea")).to_be_visible()
            await expect(page.locator("#infoPanel")).to_be_visible()

            count = await page.locator("#taskCount").text_content()
            assert "3 个任务" == count, f"任务数错误: {count}"
            print("  ✓ 数据注入成功，UI切换正确")
            passed += 1

            # ============ 测试 3: 任务列表渲染 ============
            print("\n[测试 3] 任务列表渲染...")
            items = page.locator(".task-item")
            await expect(items).to_have_count(3)

            first = items.nth(0)
            await expect(first).to_have_class(re.compile("active"))
            print("  ✓ 任务列表渲染正确")
            passed += 1

            # ============ 测试 4: 信息面板显示 ============
            print("\n[测试 4] 信息面板显示...")
            taskIdEl = page.locator(".task-id-value")
            await expect(taskIdEl).to_contain_text("db45c6d8")

            # 第一个任务有 2 个错误
            badge = page.locator(".badcase-badge")
            await expect(badge).to_have_text("2")

            # 错误卡片渲染
            errorCards = page.locator(".error-card")
            await expect(errorCards).to_have_count(2)

            # v2 schema 标记
            sourceTag = page.locator(".source-tag.v2")
            await expect(sourceTag).to_be_visible()
            print("  ✓ 信息面板显示正确")
            passed += 1

            # ============ 测试 5: bbox overlay 渲染 ============
            print("\n[测试 5] bbox overlay 渲染...")
            # 等待图片加载完毕
            await page.wait_for_function("document.getElementById('previewImage').naturalWidth > 0", timeout=3000)
            await asyncio.sleep(0.3)
            # canvas 应有像素被绘制（不是全透明）
            drawn = await page.evaluate("""
                () => {
                    const c = document.getElementById('bboxOverlay');
                    if (!c || c.width === 0) return false;
                    const ctx = c.getContext('2d');
                    const data = ctx.getImageData(0, 0, c.width, c.height).data;
                    for (let i = 3; i < data.length; i += 4) {
                        if (data[i] > 0) return true;
                    }
                    return false;
                }
            """)
            assert drawn, "bbox overlay canvas 没有内容"
            print("  ✓ bbox overlay 渲染正确")
            passed += 1

            # ============ 测试 6: 任务切换 ============
            print("\n[测试 6] 任务切换...")
            second = page.locator(".task-item").nth(1)
            await second.click()
            await asyncio.sleep(0.3)

            await expect(second).to_have_class(re.compile("active"))
            taskIdEl = page.locator(".task-id-value")
            await expect(taskIdEl).to_contain_text("bda0718b")

            badge = page.locator(".badcase-badge")
            await expect(badge).to_have_text("1")
            print("  ✓ 任务切换正常")
            passed += 1

            # ============ 测试 7: 复制任务ID ============
            print("\n[测试 7] 复制任务ID...")
            copyBtn = page.locator(".copy-btn").first
            await copyBtn.click()
            await asyncio.sleep(0.3)

            btn_text = await copyBtn.text_content()
            assert "已复制" in btn_text, f"复制后按钮应显示已复制，实际: {btn_text}"
            print("  ✓ 复制任务ID功能正常")
            passed += 1

            # ============ 测试 8: 导航按钮 ============
            print("\n[测试 8] 导航按钮...")
            await page.locator("#nextBtn").click()
            await asyncio.sleep(0.3)

            taskIdEl = page.locator(".task-id-value")
            await expect(taskIdEl).to_contain_text("aabbccdd")

            await page.locator("#prevBtn").click()
            await asyncio.sleep(0.3)
            await expect(taskIdEl).to_contain_text("bda0718b")
            print("  ✓ 导航按钮正常")
            passed += 1

            # ============ 测试 9: 键盘导航 ============
            print("\n[测试 9] 键盘导航...")
            # 先点击图片区域让焦点离开 input
            await page.locator("#imageArea").click()
            await page.keyboard.press("ArrowDown")
            await asyncio.sleep(0.3)
            await expect(taskIdEl).to_contain_text("aabbccdd")

            await page.keyboard.press("ArrowUp")
            await asyncio.sleep(0.3)
            await expect(taskIdEl).to_contain_text("bda0718b")
            print("  ✓ 键盘导航正常")
            passed += 1

            # ============ 测试 10: 缩放切换 ============
            print("\n[测试 10] 缩放切换...")
            box = page.locator("#imageBox")
            wrapper = page.locator("#imageWrapper")

            await expect(box).not_to_have_class(re.compile("fit-width"))

            await page.locator("#zoomBtn").click()
            await asyncio.sleep(0.3)
            await expect(box).to_have_class(re.compile("fit-width"))

            await page.locator("#zoomBtn").click()
            await asyncio.sleep(0.3)
            await expect(box).not_to_have_class(re.compile("fit-width"))
            print("  ✓ 缩放切换正常")
            passed += 1

            # ============ 测试 11: 边界导航按钮状态 ============
            print("\n[测试 11] 边界导航按钮状态...")
            await page.locator(".task-item").nth(0).click()
            await asyncio.sleep(0.3)

            prevBtn = page.locator("#prevBtn")
            nextBtn = page.locator("#nextBtn")
            await expect(prevBtn).to_be_disabled()
            await expect(nextBtn).to_be_enabled()

            await page.locator(".task-item").nth(2).click()
            await asyncio.sleep(0.3)
            await expect(prevBtn).to_be_enabled()
            await expect(nextBtn).to_be_disabled()
            print("  ✓ 边界按钮状态正确")
            passed += 1

            # ============ 测试 12: 编辑模式 - 字段级编辑 ============
            print("\n[测试 12] 编辑模式 - 字段级编辑...")
            await page.locator(".task-item").nth(0).click()
            await asyncio.sleep(0.3)

            # 进入编辑模式
            await page.locator("#editReportBtn").click()
            await asyncio.sleep(0.3)

            # 应看到 select 下拉和 textarea
            typeSelects = page.locator(".error-edit-row select[data-field='error_type']")
            await expect(typeSelects).to_have_count(2)
            print("  ✓ 编辑模式字段渲染正确")
            passed += 1

            # ============ 测试 13: 添加错误 ============
            print("\n[测试 13] 添加错误...")
            await page.locator(".add-error-btn").click()
            await asyncio.sleep(0.3)

            editRows = page.locator(".error-edit-row")
            await expect(editRows).to_have_count(3)

            # 退出编辑后，badge 应显示 3
            await page.locator("#finishReportBtn").click()
            await asyncio.sleep(0.3)
            badge = page.locator(".badcase-badge")
            await expect(badge).to_have_text("3")
            print("  ✓ 添加错误功能正常")
            passed += 1

            # ============ 测试 14: 删除错误 ============
            print("\n[测试 14] 删除错误...")
            await page.locator("#editReportBtn").click()
            await asyncio.sleep(0.3)

            # 删除第一个错误
            deleteBtn = page.locator(".error-delete-btn").first
            await deleteBtn.click()
            await asyncio.sleep(0.3)

            editRows = page.locator(".error-edit-row")
            await expect(editRows).to_have_count(2)

            # 退出后 badge 应显示 2
            await page.locator("#finishReportBtn").click()
            await asyncio.sleep(0.3)
            badge = page.locator(".badcase-badge")
            await expect(badge).to_have_text("2")
            print("  ✓ 删除错误功能正常")
            passed += 1

            # ============ 测试 15: bbox overlay 缩放正确（B1 fix） ============
            print("\n[测试 15] bbox overlay 跟随图片缩放...")
            # 重新加载第一个任务（含 2 个 bbox）
            await page.locator(".task-item").nth(0).click()
            await asyncio.sleep(0.3)
            await page.wait_for_function(
                "document.getElementById('previewImage').naturalWidth > 0", timeout=3000
            )
            await asyncio.sleep(0.3)

            # canvas CSS 尺寸应等于 img 显示尺寸（不是 naturalWidth）
            sizing = await page.evaluate("""
                () => {
                    const img = document.getElementById('previewImage');
                    const c = document.getElementById('bboxOverlay');
                    const ir = img.getBoundingClientRect();
                    const cr = c.getBoundingClientRect();
                    return {
                        imgW: ir.width, imgH: ir.height,
                        canvasW: cr.width, canvasH: cr.height,
                        naturalW: img.naturalWidth
                    };
                }
            """)
            # canvas CSS 尺寸应接近 img 显示尺寸（允许小数误差）
            assert abs(sizing["canvasW"] - sizing["imgW"]) < 5, \
                f"canvas CSS width {sizing['canvasW']} != img display width {sizing['imgW']}"
            assert abs(sizing["canvasH"] - sizing["imgH"]) < 5, \
                f"canvas CSS height {sizing['canvasH']} != img display height {sizing['imgH']}"
            # canvas 内部分辨率仍是 naturalWidth
            assert sizing["naturalW"] == 800, f"natural width 错误: {sizing['naturalW']}"
            print(f"  ✓ bbox overlay CSS 缩放正确（canvas {sizing['canvasW']:.0f}×{sizing['canvasH']:.0f}，natural 800x600）")
            passed += 1

            # ============ 测试 16: 排序 + 徽章（badcase 优先 / 无 badcase 次之） ============
            print("\n[测试 16] 排序 + 徽章...")
            # 重新注入混合数据：1 个 annotated + 2 个 no_badcase，故意乱序
            await page.evaluate("""
                async () => {
                    const canvas = document.createElement('canvas');
                    canvas.width = 800; canvas.height = 600;
                    const dataUrl = canvas.toDataURL('image/jpeg');

                    function mkErr(eid) {
                        return {
                            error_id: eid, error_type: 'ocr', error_subtype: 'char_wrong',
                            severity: null, comment: 'x',
                            marks: [{ mark_id: 'm_'+eid, role: 'primary', type: 'bbox',
                                      geometry: { bbox: [10,10,50,50], points: null },
                                      color: null, width: 2 }],
                            annotator_id: 'default',
                            created_at: '2026-06-10T12:00:00Z', updated_at: '2026-06-10T12:00:00Z',
                            duration_ms: 1000
                        };
                    }

                    resultItems = [
                        {
                            taskId: 'clean-001', folderName: 'clean-001', imageName: 'source.jpg',
                            imageUrl: dataUrl, schemaVersion: '1.0', source: 'v2',
                            annotation: { status: 'no_badcase', errors: [], session_id: 's',
                                          annotator_id: 'default', started_at: '2026-06-10T12:00:00Z',
                                          saved_at: '2026-06-10T12:01:00Z' }
                        },
                        {
                            taskId: 'badcase-001', folderName: 'badcase-001', imageName: 'source.jpg',
                            imageUrl: dataUrl, schemaVersion: '1.0', source: 'v2',
                            annotation: { status: 'annotated', errors: [mkErr('err_01')],
                                          session_id: 's', annotator_id: 'default',
                                          started_at: '2026-06-10T12:00:00Z',
                                          saved_at: '2026-06-10T12:01:00Z' }
                        },
                        {
                            taskId: 'clean-002', folderName: 'clean-002', imageName: 'source.jpg',
                            imageUrl: dataUrl, schemaVersion: '1.0', source: 'v2',
                            annotation: { status: 'no_badcase', errors: [], session_id: 's',
                                          annotator_id: 'default', started_at: '2026-06-10T12:00:00Z',
                                          saved_at: '2026-06-10T12:01:00Z' }
                        }
                    ];

                    sortResultItemsByBadcase();
                    currentIndex = 0;
                    initUI();
                    loadTask(0);
                }
            """)
            await asyncio.sleep(0.4)

            # 排序后：第 1 项应是 badcase-001（唯一有 errors 的）
            task_ids = await page.evaluate("""
                () => Array.from(document.querySelectorAll('.task-item .task-id'))
                          .map(el => el.textContent.trim())
            """)
            assert task_ids[0] == 'badcase-001', \
                f"排序后首位应为 badcase-001，实际: {task_ids[0]}"
            assert set(task_ids[1:]) == {'clean-001', 'clean-002'}, \
                f"无 badcase 项应排在后面，实际: {task_ids}"

            # 徽章：第 1 项 = "1 个错误"，后两项 = "无 badcase"
            badges = await page.evaluate("""
                () => Array.from(document.querySelectorAll('.task-item .badge'))
                          .map(el => el.textContent.trim())
            """)
            assert badges[0] == '1 个错误', f"首项徽章应为 '1 个错误'，实际: {badges[0]}"
            assert badges[1] == '无 badcase', f"第 2 项徽章应为 '无 badcase'，实际: {badges[1]}"
            assert badges[2] == '无 badcase', f"第 3 项徽章应为 '无 badcase'，实际: {badges[2]}"

            # 统计行：1 错误 · 1 有 / 2 无 · 3 任务
            stats_html = await page.locator("#totalBadcaseInfo").text_content()
            assert '1' in stats_html and '2' in stats_html and '3' in stats_html, \
                f"统计行应反映 1 错误/1 有/2 无/3 任务，实际: {stats_html}"
            print(f"  ✓ 排序正确（badcase 优先），徽章 + 统计同步更新")
            passed += 1

            # ============ 测试 17: judgments 卡片渲染 ============
            print("\n[测试 17] judgments 卡片...")
            await page.evaluate("""
                async () => {
                    const canvas = document.createElement('canvas');
                    canvas.width = 800; canvas.height = 600;
                    const dataUrl = canvas.toDataURL('image/jpeg');

                    resultItems = [
                        {
                            taskId: 'judge-test', folderName: 'judge-test', imageName: 'source.jpg',
                            imageUrl: dataUrl, schemaVersion: '1.0', source: 'v2',
                            annotation: {
                                status: 'annotated',
                                errors: [],
                                judgments: [
                                    {question_no:'1(1)', status:'correct'},
                                    {question_no:'1(2)', status:'wrong'},
                                    {question_no:'2',   status:'unmarked'},
                                    {question_no:'3',   status:'correct'}
                                ],
                                session_id:'s', annotator_id:'default',
                                started_at:'2026-06-10T12:00:00Z',
                                saved_at:'2026-06-10T12:01:00Z'
                            }
                        }
                    ];
                    sortResultItemsByBadcase();
                    currentIndex = 0;
                    initUI();
                    loadTask(0);
                }
            """)
            await asyncio.sleep(0.4)

            # 应渲染 4 个 jchip
            chips = page.locator(".jchip")
            await expect(chips).to_have_count(4)

            # 状态色：correct/wrong/unmarked
            chip_classes = await page.evaluate("""
                () => Array.from(document.querySelectorAll('.jchip'))
                          .map(el => el.className)
            """)
            # 题号 + 类
            chip_data = await page.evaluate("""
                () => Array.from(document.querySelectorAll('.jchip'))
                          .map(el => ({text: el.textContent.trim(), cls: el.className}))
            """)
            by_q = {d['text']: d['cls'] for d in chip_data}
            assert 'correct' in by_q.get('1(1)', ''), f"1(1) 应为 correct：{by_q}"
            assert 'wrong' in by_q.get('1(2)', ''), f"1(2) 应为 wrong：{by_q}"
            assert by_q.get('2', '').strip() == 'jchip', f"2 应为 unmarked（仅基础类）：{by_q}"
            assert 'correct' in by_q.get('3', ''), f"3 应为 correct：{by_q}"

            # 摘要行：共 4 题 · 对 2 · 错 1 · 未判 1
            jsummary = await page.evaluate("""
                () => {
                    const sec = Array.from(document.querySelectorAll('.info-section'))
                        .find(s => s.querySelector('.info-section-title')?.textContent.trim() === '题号判题');
                    return sec ? sec.textContent.replace(/\\s+/g, ' ').trim() : '';
                }
            """)
            assert '共 4 题' in jsummary and '对 2' in jsummary and '错 1' and '未判 1' in jsummary, \
                f"摘要行错误：{jsummary}"
            print(f"  ✓ judgments 卡片渲染正确（4 chips，状态色 + 摘要对齐）")
            passed += 1

        except Exception as e:
            print(f"  ✗ 测试失败: {e}")
            failed += 1
            await page.screenshot(path="test_viewer_failure.png")
            print("  调试截图已保存: test_viewer_failure.png")

        finally:
            await context.close()
            if browser:
                await browser.close()

    server.shutdown()

    print("\n" + "=" * 60)
    print(f"测试完成: 通过 {passed} 项, 失败 {failed} 项")
    print("=" * 60)

    if failed > 0:
        import sys
        sys.exit(1)
    else:
        print("\n✓ 所有测试通过！")


if __name__ == "__main__":
    asyncio.run(run_tests())
