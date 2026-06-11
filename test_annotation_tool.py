#!/usr/bin/env python3
"""
图片批阅标注工具 - 自动化测试脚本
使用 Playwright 进行端到端测试
"""

import asyncio
import http.server
import socketserver
import threading
import os
import sys
import tempfile
import zipfile
import re
from pathlib import Path

from playwright.async_api import async_playwright, expect

PORT = 8765
BASE_URL = f"http://localhost:{PORT}/annotation-tool.html"


class QuietHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # 静默日志


def start_server():
    """在后台线程启动本地HTTP服务器"""
    handler = QuietHTTPRequestHandler
    httpd = socketserver.TCPServer(("", PORT), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


async def inject_mock_data(page):
    """向页面注入模拟数据，模拟文件夹解析完成后的状态"""
    await page.evaluate("""
        async () => {
            // 创建模拟图片 Blob URL
            const canvas = document.createElement('canvas');
            canvas.width = 800;
            canvas.height = 600;
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = '#f5f5f5';
            ctx.fillRect(0, 0, 800, 600);
            ctx.fillStyle = '#333';
            ctx.font = '20px sans-serif';
            ctx.fillText('Mock Image 1', 350, 300);
            
            const canvas2 = document.createElement('canvas');
            canvas2.width = 800;
            canvas2.height = 600;
            const ctx2 = canvas2.getContext('2d');
            ctx2.fillStyle = '#e8f4f8';
            ctx2.fillRect(0, 0, 800, 600);
            ctx2.fillStyle = '#333';
            ctx2.font = '20px sans-serif';
            ctx2.fillText('Mock Image 2', 350, 300);

            taskItems = [
                {
                    taskId: 'db45c6d8-04ed-4a71-a7d2-2179957bd9b4',
                    folderPath: '未匹配/1',
                    subFolder: '未匹配',
                    idxFolder: '1',
                    imageName: '1.jpg',
                    imageUrl: canvas.toDataURL('image/jpeg')
                },
                {
                    taskId: 'bda0718b-3e30-4cc4-93b1-265eb54a86d2',
                    folderPath: '未匹配/2',
                    subFolder: '未匹配',
                    idxFolder: '2',
                    imageName: '2.jpg',
                    imageUrl: canvas2.toDataURL('image/jpeg')
                },
                {
                    taskId: 'aabbccdd-1122-3344-5566-77889900aabb',
                    folderPath: '学生卷/张三',
                    subFolder: '学生卷',
                    idxFolder: '张三',
                    imageName: '张三.jpg',
                    imageUrl: canvas.toDataURL('image/jpeg')
                }
            ];
            
            initUI();
            initThumbnails();
            loadImage(0);
            updateStats();
        }
    """)


async def run_tests():
    """运行所有测试"""
    print("=" * 60)
    print("图片批阅标注工具 - 自动化测试")
    print("=" * 60)
    
    server = start_server()
    await asyncio.sleep(0.5)  # 等待服务器启动
    
    passed = 0
    failed = 0
    browser = None
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1440, 'height': 900})
        page = await context.new_page()
        
        # 打开控制台日志
        page.on("console", lambda msg: print(f"  [Browser {msg.type}] {msg.text}") if msg.type == "error" else None)
        
        try:
            # ============ 测试 1: 页面加载 ============
            print("\n[测试 1] 页面加载...")
            await page.goto(BASE_URL, wait_until="networkidle")
            title = await page.title()
            assert title == "图片批阅标注工具", f"标题错误: {title}"
            
            # 检查空状态显示
            empty_state = page.locator("#emptyState")
            await expect(empty_state).to_be_visible()
            print("  ✓ 页面加载成功，空状态显示正确")
            passed += 1
            
            # ============ 测试 2: 注入数据后UI切换 ============
            print("\n[测试 2] 数据加载与UI切换...")
            await inject_mock_data(page)
            await asyncio.sleep(0.5)
            
            # 空状态应隐藏，工作区应显示
            await expect(empty_state).to_be_hidden()
            await expect(page.locator("#sidebar")).to_be_visible()
            await expect(page.locator("#contentArea")).to_be_visible()
            await expect(page.locator("#thumbnailBar")).to_be_visible()
            
            # 检查任务信息
            task_id = await page.locator("#taskId").text_content()
            assert "db45c6d8" in task_id, f"任务ID显示错误: {task_id}"
            
            progress = await page.locator("#progressInfo").text_content()
            assert "任务 1 / 3" == progress, f"进度显示错误: {progress}"
            print("  ✓ 数据注入成功，UI切换正确")
            passed += 1
            
            # ============ 测试 3: Badcase 数量选择 ============
            print("\n[测试 3] Badcase 数量选择...")
            btn1 = page.locator('.badcase-btn[data-value="1"]')
            await btn1.click()
            await expect(btn1).to_have_class(re.compile("active"))
            
            input_val = await page.locator("#badcaseInput").input_value()
            assert input_val == "1", f"输入框值错误: {input_val}"
            
            # 点击按钮2
            btn2 = page.locator('.badcase-btn[data-value="2"]')
            await btn2.click()
            await expect(btn2).to_have_class(re.compile("active"))
            await expect(btn1).not_to_have_class(re.compile("active"))
            
            # 自定义输入
            await page.locator("#badcaseInput").fill("5")
            await page.locator("#badcaseInput").blur()
            await expect(btn2).not_to_have_class(re.compile("active"))
            print("  ✓ Badcase 数量选择功能正常")
            passed += 1
            
            # ============ 测试 4: 错误原因多选 ============
            print("\n[测试 4] 错误原因多选...")
            reason1 = page.locator('.reason-btn[data-reason="切题"]')
            reason2 = page.locator('.reason-btn[data-reason="OCR"]')
            reason3 = page.locator('.reason-btn[data-reason="解题"]')
            
            await reason1.click()
            await reason2.click()
            await expect(reason1).to_have_class(re.compile("active"))
            await expect(reason2).to_have_class(re.compile("active"))
            await expect(reason3).not_to_have_class(re.compile("active"))
            
            # 取消选择
            await reason1.click()
            await expect(reason1).not_to_have_class(re.compile("active"))
            print("  ✓ 错误原因多选功能正常")
            passed += 1
            
            # ============ 测试 5: Canvas 绘制 ============
            print("\n[测试 5] Canvas 绘制功能...")
            canvas = page.locator("#drawingCanvas")
            
            # 在 canvas 上画一条线
            box = await canvas.bounding_box()
            await canvas.hover()
            await page.mouse.move(box['x'] + 100, box['y'] + 100)
            await page.mouse.down()
            await page.mouse.move(box['x'] + 200, box['y'] + 200, steps=10)
            await page.mouse.up()
            
            # 检查 canvas 不为空
            is_empty = await page.evaluate("() => isCanvasEmpty()")
            assert not is_empty, "Canvas 绘制后不应为空"
            print("  ✓ Canvas 绘制功能正常")
            passed += 1
            
            # ============ 测试 6: 保存标注逻辑 ============
            print("\n[测试 6] 保存标注逻辑...")
            
            # 配置标注：badcase=2, 原因=切题+OCR, 有绘制
            await page.locator('.badcase-btn[data-value="2"]').click()
            await page.locator('.reason-btn[data-reason="切题"]').click()
            await page.locator('.reason-btn[data-reason="OCR"]').click()
            
            save_btn = page.locator("#saveBtn")
            btn_text = await save_btn.text_content()
            assert "保存标注" in btn_text, f"有标注时应显示'保存标注'，实际: {btn_text}"
            
            # 保存
            await save_btn.click()
            await asyncio.sleep(0.5)
            
            # 应自动跳转到第二张
            progress = await page.locator("#progressInfo").text_content()
            assert "任务 2 / 3" == progress, f"保存后应跳转到第2张，实际: {progress}"
            
            # 检查缩略图红点
            thumb1 = page.locator(".thumbnail-item").nth(0)
            await expect(thumb1).to_have_class(re.compile("marked"))
            print("  ✓ 保存标注逻辑正确，自动跳转正常")
            passed += 1
            
            # ============ 测试 7: 跳过逻辑 ============
            print("\n[测试 7] 跳过逻辑...")
            # 第二张不做任何操作，直接保存（应为跳过）
            await save_btn.click()
            await asyncio.sleep(0.5)
            
            progress = await page.locator("#progressInfo").text_content()
            assert "任务 3 / 3" == progress, f"跳过后应到第3张，实际: {progress}"
            
            thumb2 = page.locator(".thumbnail-item").nth(1)
            await expect(thumb2).not_to_have_class(re.compile("marked"))
            print("  ✓ 跳过逻辑正确")
            passed += 1
            
            # ============ 测试 8: 导航功能 ============
            print("\n[测试 8] 导航功能...")
            await page.locator("#prevBtn").click()
            await asyncio.sleep(0.2)
            progress = await page.locator("#progressInfo").text_content()
            assert "任务 2 / 3" == progress, f"上一张应回到第2张，实际: {progress}"
            
            await page.locator("#nextBtn").click()
            await asyncio.sleep(0.2)
            progress = await page.locator("#progressInfo").text_content()
            assert "任务 3 / 3" == progress, f"下一张应到第3张，实际: {progress}"
            
            # 键盘快捷键
            await page.keyboard.press("ArrowLeft")
            await asyncio.sleep(0.2)
            progress = await page.locator("#progressInfo").text_content()
            assert "任务 2 / 3" == progress, f"左箭头应回到第2张，实际: {progress}"
            print("  ✓ 导航功能正常（按钮+键盘）")
            passed += 1
            
            # ============ 测试 9: 导出按钮状态 ============
            print("\n[测试 9] 导出按钮状态...")
            export_btn = page.locator("#exportBtn")
            await expect(export_btn).to_be_enabled()
            print("  ✓ 有标注数据时导出按钮可用")
            passed += 1
            
            # ============ 测试 10: 工具切换和清空 ============
            print("\n[测试 10] 工具切换和清空...")
            erase_btn = page.locator("#eraseTool")
            await erase_btn.click()
            await expect(erase_btn).to_have_class(re.compile("active"))
            
            await page.locator('.tool-btn:has-text("清空")').click()
            is_empty = await page.evaluate("() => isCanvasEmpty()")
            assert is_empty, "清空后 Canvas 应为空"
            print("  ✓ 工具切换和清空功能正常")
            passed += 1
            
            # ============ 测试 11: 画笔粗细切换 ============
            print("\n[测试 11] 画笔粗细切换...")
            size4 = page.locator('.size-dot[data-size="4"]')
            await size4.click()
            await expect(size4).to_have_class(re.compile("active"))
            
            size2 = page.locator('.size-dot[data-size="2"]')
            await expect(size2).not_to_have_class(re.compile("active"))
            print("  ✓ 画笔粗细切换正常")
            passed += 1
            
            # ============ 测试 12: 保存按钮动态文本 ============
            print("\n[测试 12] 保存按钮动态文本...")
            # 清空所有选择
            await page.evaluate("() => { resetSidebar(); clearCanvas(); }")
            await asyncio.sleep(0.2)
            
            btn_text = await save_btn.text_content()
            assert "跳过" in btn_text, f"无标注时应显示'跳过'，实际: {btn_text}"
            
            # 选择原因
            await page.locator('.reason-btn[data-reason="判题"]').click()
            btn_text = await save_btn.text_content()
            assert "保存" in btn_text, f"有标注时应显示'保存'，实际: {btn_text}"
            print("  ✓ 保存按钮动态文本切换正常")
            passed += 1
            
            # ============ 测试 13: YAML 解析 ============
            print("\n[测试 13] YAML 解析函数...")
            try:
                yaml_text = 'task_ids:\n  - "db45c6d8-04ed-4a71-a7d2-2179957bd9b4"\n  - "second-id-here"'
                context2 = await browser.new_context(viewport={'width': 800, 'height': 600})
                page2 = await context2.new_page()
                await page2.goto(BASE_URL, wait_until="networkidle")
                result = await page2.evaluate(f"""
                    () => {{
                        const text = `{yaml_text}`;
                        return parseYamlTaskIds(text);
                    }}
                """)
                assert len(result) == 2, f"应解析出2个ID，实际: {len(result)}"
                assert result[0] == "db45c6d8-04ed-4a71-a7d2-2179957bd9b4"
                await context2.close()
                print("  ✓ YAML 解析功能正常")
                passed += 1
            except Exception as e:
                print(f"  ✗ YAML 解析测试失败: {e}")
                failed += 1
            
            # ============ 测试 14: 报告生成 ============
            print("\n[测试 14] 报告生成功能...")
            try:
                context3 = await browser.new_context(viewport={'width': 800, 'height': 600})
                page3 = await context3.new_page()
                await page3.goto(BASE_URL, wait_until="networkidle")
                
                report = await page3.evaluate("""
                    () => {
                        annotations = {
                            'test-id-1': {
                                taskId: 'test-id-1',
                                folderPath: '未匹配/1',
                                imageName: '1.jpg',
                                badcaseCount: 2,
                                reasons: ['切题', 'OCR'],
                                hasDrawing: true,
                                timestamp: '2024-01-01T00:00:00Z'
                            }
                        };
                        return generateReport();
                    }
                """)
                assert "批阅标注结果报告" in report
                assert "test-id-1" in report
                assert "Badcase: 2 个" in report
                print("  ✓ 报告生成功能正常")
                passed += 1
                await context3.close()
            except Exception as e:
                print(f"  ✗ 报告生成测试失败: {e}")
                failed += 1

        except Exception as e:
            print(f"  ✗ 测试失败: {e}")
            failed += 1
            # 保存截图用于调试
            await page.screenshot(path="test_failure.png")
            print("  调试截图已保存: test_failure.png")
        
        finally:
            await context.close()
            await browser.close()
    
    server.shutdown()

    # ============ 测试总结 ============
    print("\n" + "=" * 60)
    print(f"测试完成: 通过 {passed} 项, 失败 {failed} 项")
    print("=" * 60)
    
    if failed > 0:
        sys.exit(1)
    else:
        print("\n✓ 所有测试通过！")


if __name__ == "__main__":
    asyncio.run(run_tests())
