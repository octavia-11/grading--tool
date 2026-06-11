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
    httpd = socketserver.TCPServer(("", PORT), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


async def inject_mock_data(page):
    """注入模拟数据"""
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
            
            resultItems = [
                {
                    taskId: 'db45c6d8-04ed-4a71-a7d2-2179957bd9b4',
                    folderName: 'db45c6d8-04ed-4a71-a7d2-2179957bd9b4',
                    imageName: 'marked_1.jpg',
                    imageUrl: canvas.toDataURL('image/jpeg'),
                    errorInfo: {
                        taskId: 'db45c6d8-04ed-4a71-a7d2-2179957bd9b4',
                        folderPath: '未匹配/1',
                        imageName: '1.jpg',
                        badcaseCount: 2,
                        reasons: ['切题', 'OCR'],
                        hasDrawing: true,
                        timestamp: '2026-06-10T12:00:00.000Z',
                        _raw: '任务编号: db45c6d8...\\nBadcase: 2'
                    }
                },
                {
                    taskId: 'bda0718b-3e30-4cc4-93b1-265eb54a86d2',
                    folderName: 'bda0718b-3e30-4cc4-93b1-265eb54a86d2',
                    imageName: 'marked_2.jpg',
                    imageUrl: canvas.toDataURL('image/jpeg'),
                    errorInfo: {
                        taskId: 'bda0718b-3e30-4cc4-93b1-265eb54a86d2',
                        folderPath: '未匹配/2',
                        imageName: '2.jpg',
                        badcaseCount: 1,
                        reasons: ['判题'],
                        hasDrawing: false,
                        timestamp: '2026-06-10T12:05:00.000Z',
                        _raw: '任务编号: bda0718b...\\nBadcase: 1'
                    }
                },
                {
                    taskId: 'aabbccdd-1122-3344-5566-77889900aabb',
                    folderName: 'aabbccdd-1122-3344-5566-77889900aabb',
                    imageName: 'marked_3.jpg',
                    imageUrl: canvas.toDataURL('image/jpeg'),
                    errorInfo: {
                        taskId: 'aabbccdd-1122-3344-5566-77889900aabb',
                        folderPath: '学生卷/张三',
                        imageName: '张三.jpg',
                        badcaseCount: 3,
                        reasons: ['切题', 'OCR', '解题'],
                        hasDrawing: true,
                        timestamp: '2026-06-10T12:10:00.000Z',
                        _raw: '任务编号: aabbccdd...\\nBadcase: 3'
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
            
            # 第一个任务应高亮
            first = items.nth(0)
            await expect(first).to_have_class(re.compile("active"))
            print("  ✓ 任务列表渲染正确")
            passed += 1
            
            # ============ 测试 4: 信息面板显示 ============
            print("\n[测试 4] 信息面板显示...")
            taskIdEl = page.locator(".task-id-value")
            await expect(taskIdEl).to_contain_text("db45c6d8")
            
            badge = page.locator(".badcase-badge")
            await expect(badge).to_have_text("2")
            
            tags = page.locator(".reason-tag")
            await expect(tags).to_have_count(2)
            print("  ✓ 信息面板显示正确")
            passed += 1
            
            # ============ 测试 5: 任务切换 ============
            print("\n[测试 5] 任务切换...")
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
            
            # ============ 测试 6: 复制任务ID ============
            print("\n[测试 6] 复制任务ID...")
            copyBtn = page.locator(".copy-btn").first
            await copyBtn.click()
            await asyncio.sleep(0.3)
            
            # 检查按钮变为"已复制"
            btn_text = await copyBtn.text_content()
            assert "已复制" in btn_text, f"复制后按钮应显示已复制，实际: {btn_text}"
            print("  ✓ 复制任务ID功能正常")
            passed += 1
            
            # ============ 测试 7: 导航按钮 ============
            print("\n[测试 7] 导航按钮...")
            await page.locator("#nextBtn").click()
            await asyncio.sleep(0.3)
            
            taskIdEl = page.locator(".task-id-value")
            await expect(taskIdEl).to_contain_text("aabbccdd")
            
            await page.locator("#prevBtn").click()
            await asyncio.sleep(0.3)
            await expect(taskIdEl).to_contain_text("bda0718b")
            print("  ✓ 导航按钮正常")
            passed += 1
            
            # ============ 测试 8: 键盘导航 ============
            print("\n[测试 8] 键盘导航...")
            await page.keyboard.press("ArrowDown")
            await asyncio.sleep(0.3)
            await expect(taskIdEl).to_contain_text("aabbccdd")
            
            await page.keyboard.press("ArrowUp")
            await asyncio.sleep(0.3)
            await expect(taskIdEl).to_contain_text("bda0718b")
            print("  ✓ 键盘导航正常")
            passed += 1
            
            # ============ 测试 9: 缩放切换 ============
            print("\n[测试 9] 缩放切换...")
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
            
            # ============ 测试 10: 边界导航按钮状态 ============
            print("\n[测试 10] 边界导航按钮状态...")
            # 点击第一个任务
            await page.locator(".task-item").nth(0).click()
            await asyncio.sleep(0.3)
            
            prevBtn = page.locator("#prevBtn")
            nextBtn = page.locator("#nextBtn")
            await expect(prevBtn).to_be_disabled()
            await expect(nextBtn).to_be_enabled()
            
            # 点击最后一个任务
            await page.locator(".task-item").nth(2).click()
            await asyncio.sleep(0.3)
            await expect(prevBtn).to_be_enabled()
            await expect(nextBtn).to_be_disabled()
            print("  ✓ 边界按钮状态正确")
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
