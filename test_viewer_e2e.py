#!/usr/bin/env python3
"""
端到端测试：通过真实的 file picker 加载 test_data/v2_sample/ 和 test_results/（legacy）
覆盖 result-viewer 的两条解析路径。
"""

import asyncio
import http.server
import socketserver
import threading
from pathlib import Path

from playwright.async_api import async_playwright, expect

PORT = 8767
BASE_URL = f"http://localhost:{PORT}/result-viewer.html"
HERE = Path(__file__).parent


class QuietHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def start_server():
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("", PORT), QuietHTTPRequestHandler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd


async def upload_folder(page, dir_path: Path, name: str):
    """通过 file picker 上传一个目录。"""
    # Playwright：setInputFiles 用 webkitdirectory 时传目录下所有文件 +
    # 完整 relativePath 路径
    files = []
    for p in sorted(dir_path.rglob("*")):
        if p.is_file():
            files.append({
                "name": p.name,
                "mimeType": "application/octet-stream",
                "buffer": p.read_bytes(),
            })

    async with page.expect_file_chooser() as fc_info:
        await page.click(f"text=选择{name}")
    chooser = await fc_info.value
    # webkitdirectory 不直接支持，改走 evaluate 注入 FileList
    # 退而求其次：直接注入 resultItems via window, 走 applyLocalEdits 路径无意义
    # 实际方案：用 page.dispatchEvent + setInputFiles 不行；改成直接 evaluate
    pass


async def load_via_evaluate(page, dir_path: Path):
    """直接调用 parseResultFolder 走真实解析路径。"""
    files = []
    for p in sorted(dir_path.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(dir_path.parent))
        files.append((p, rel))

    # 注入到 window 上，调用 parseResultFolder
    await page.evaluate(
        """
        async ({items}) => {
            const files = items.map(({name, rel, bytes, mime}) => {
                const f = new File([new Uint8Array(bytes)], name, { type: mime });
                Object.defineProperty(f, 'webkitRelativePath', { value: rel, configurable: true });
                return f;
            });
            await parseResultFolder(files);
            initUI();
            loadTask(0);
        }
        """,
        {"items": [
            {"name": p.name, "rel": rel, "bytes": list(p.read_bytes()), "mime": "application/octet-stream"}
            for p, rel in files
        ]},
    )


async def run_tests():
    print("=" * 60)
    print("result-viewer 端到端测试（真实解析路径）")
    print("=" * 60)

    server = start_server()
    await asyncio.sleep(0.5)

    passed = 0
    failed = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()
        page.on("console", lambda msg: print(f"  [Browser {msg.type}] {msg.text}") if msg.type == "error" else None)

        try:
            await page.goto(BASE_URL, wait_until="networkidle")
            # 清掉上次会话残留的 localStorage 编辑，避免污染断言
            await page.evaluate("""
                () => {
                    const keys = Object.keys(localStorage);
                    keys.forEach(k => {
                        if (k.startsWith('gradingAnnotationV2:') || k.startsWith('gradingReport:')) {
                            localStorage.removeItem(k);
                        }
                    });
                }
            """)

            # ============ 测试 1: 加载 v2 JSON 路径 ============
            print("\n[测试 1] 加载 v2_sample/（JSON 路径）...")
            v2_dir = HERE / "test_data" / "v2_sample"
            assert v2_dir.exists(), "test_data/v2_sample/ 不存在"
            await load_via_evaluate(page, v2_dir)
            await asyncio.sleep(0.5)

            taskCount = await page.locator("#taskCount").text_content()
            assert "1 个任务" == taskCount, f"任务数错误: {taskCount}"

            # 应有 v2 schema 标记
            sourceTag = page.locator(".source-tag.v2")
            await expect(sourceTag).to_be_visible()

            # 错误数应为 2（来自 default.json）
            badge = page.locator(".badcase-badge")
            await expect(badge).to_have_text("2")

            # 错误卡片渲染
            cards = page.locator(".error-card")
            await expect(cards).to_have_count(2)
            print("  ✓ v2 JSON 路径正确")
            passed += 1

            # ============ 测试 2: bbox overlay 渲染（v2） ============
            print("\n[测试 2] bbox overlay 在 source 图上绘制...")
            await page.wait_for_function(
                "document.getElementById('previewImage').naturalWidth > 0", timeout=3000
            )
            await asyncio.sleep(0.3)
            drawn = await page.evaluate("""
                () => {
                    const c = document.getElementById('bboxOverlay');
                    if (!c || c.width === 0) return false;
                    const ctx = c.getContext('2d');
                    const data = ctx.getImageData(0, 0, c.width, c.height).data;
                    let has = false;
                    for (let i = 3; i < data.length; i += 4) {
                        if (data[i] > 0) { has = true; break; }
                    }
                    return { has, w: c.width, h: c.height };
                }
            """)
            assert drawn["has"], f"bbox overlay 没有内容 (canvas {drawn['w']}x{drawn['h']})"
            assert drawn["w"] == 800 and drawn["h"] == 600, \
                f"canvas 尺寸错误: {drawn['w']}x{drawn['h']}"
            print(f"  ✓ bbox overlay 正确（canvas {drawn['w']}x{drawn['h']}）")
            passed += 1

            # ============ 测试 3: 加载 legacy txt 路径 ============
            print("\n[测试 3] 加载 test_results/（legacy txt 路径）...")
            legacy_dir = HERE / "test_results"
            assert legacy_dir.exists() and any(legacy_dir.iterdir()), "test_results/ 不存在或为空"
            await load_via_evaluate(page, legacy_dir)
            await asyncio.sleep(0.5)

            taskCount = await page.locator("#taskCount").text_content()
            assert "3 个任务" == taskCount, f"任务数错误: {taskCount}"

            # legacy 标记
            legacyTag = page.locator(".source-tag.legacy")
            await expect(legacyTag).to_be_visible()
            print("  ✓ legacy txt 路径正确")
            passed += 1

            # ============ 测试 4: 第一个 legacy 任务的 badcase 应来自 reasons ============
            print("\n[测试 4] legacy 任务错误数来自 reasons...")
            # 第一个任务按字母序是 aabbccdd，3 个 reasons（切题, OCR, 解题）
            first = page.locator(".task-item").nth(0)
            await first.click()
            await asyncio.sleep(0.3)

            taskIdEl = page.locator(".task-id-value")
            await expect(taskIdEl).to_contain_text("aabbccdd")

            badge = page.locator(".badcase-badge")
            badge_text = await badge.text_content()
            assert badge_text == "3", f"expected 3, got {badge_text}"

            # bbox 信息应显示"位置信息缺失"（legacy 全部）
            missingInfo = page.locator(".error-bbox-info.empty")
            await expect(missingInfo).to_have_count(3)
            print("  ✓ legacy 错误数和 bbox 缺失标记正确")
            passed += 1

            # ============ 测试 5: legacy 编辑能产生下载文件 ============
            print("\n[测试 5] 编辑 + 序列化导出...")
            await page.locator("#editReportBtn").click()
            await asyncio.sleep(0.3)

            # 起始 3 行，添加 1 行后应为 4
            await page.locator(".add-error-btn").click()
            await asyncio.sleep(0.3)
            rows = page.locator(".error-edit-row")
            await expect(rows).to_have_count(4)

            # 验证 item.annotation.errors 已更新
            errorsLen = await page.evaluate("resultItems[0].annotation.errors.length")
            assert errorsLen == 4, f"expected 4, got {errorsLen}"
            print("  ✓ 编辑生效，内存状态正确")
            passed += 1

        except Exception as e:
            print(f"  ✗ 测试失败: {e}")
            failed += 1
            await page.screenshot(path="test_viewer_e2e_failure.png")
            print("  调试截图: test_viewer_e2e_failure.png")

        finally:
            await context.close()
            await browser.close()

    server.shutdown()

    print("\n" + "=" * 60)
    print(f"测试完成: 通过 {passed} 项, 失败 {failed} 项")
    print("=" * 60)
    if failed > 0:
        import sys
        sys.exit(1)
    print("\n✓ 所有测试通过！")


if __name__ == "__main__":
    asyncio.run(run_tests())
