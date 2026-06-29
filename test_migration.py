#!/usr/bin/env python3
"""
migrate_legacy_zip.py 的单元测试。
"""

import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from migrate_legacy_zip import (
    parse_error_info,
    map_reason_to_category,
    migrate_task_dir,
    build_v2_annotation,
    DEFAULT_REASON_MAP,
)


SAMPLE_ERROR_INFO = """任务编号: db45c6d8-04ed-4a71-a7d2-2179957bd9b4
文件夹: 未匹配/1
图片名称: 1.jpg
标注时间: 2026-06-10T12:00:00.000Z

Badcase 数量: 2
错误原因: 切题, OCR

--- 详细信息 ---
是否有勾画痕迹: 是
"""


def make_legacy_task(root: Path, task_id: str, reasons: str, has_drawing: bool = True):
    td = root / task_id
    td.mkdir(parents=True)
    (td / "error_info.txt").write_text(
        f"""任务编号: {task_id}
文件夹: 未匹配/1
图片名称: 1.jpg
标注时间: 2026-06-10T12:00:00.000Z

Badcase 数量: 2
错误原因: {reasons}

--- 详细信息 ---
是否有勾画痕迹: {'是' if has_drawing else '否'}
""",
        encoding="utf-8",
    )
    (td / "task_id.txt").write_text(task_id, encoding="utf-8")
    # 1x1 png 占位
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000d49444154789c63000100000005000101a5f645770000000049454e44ae426082"
    )
    (td / "marked_1.jpg").write_bytes(png)
    return td


def test_parse_error_info():
    info = parse_error_info(SAMPLE_ERROR_INFO)
    assert info["taskId"] == "db45c6d8-04ed-4a71-a7d2-2179957bd9b4"
    assert info["folderPath"] == "未匹配/1"
    assert info["imageName"] == "1.jpg"
    assert info["badcaseCount"] == 2
    assert info["reasons"] == ["切题", "OCR"]
    assert info["hasDrawing"] is True
    print("  ✓ parse_error_info 正确")


def test_map_reason_to_category():
    assert map_reason_to_category("切题", DEFAULT_REASON_MAP) == "topic"
    assert map_reason_to_category("OCR", DEFAULT_REASON_MAP) == "ocr"
    assert map_reason_to_category("解题", DEFAULT_REASON_MAP) == "solution"
    assert map_reason_to_category("判题", DEFAULT_REASON_MAP) == "judgment"
    # 模糊匹配
    assert map_reason_to_category("其它", DEFAULT_REASON_MAP) is None
    print("  ✓ map_reason_to_category 正确")


def test_build_v2_annotation_schema():
    info = {"reasons": ["切题", "OCR"], "timestamp": "2026-06-10T12:00:00.000Z"}
    ann = build_v2_annotation(
        task_id="t1",
        source_path="未匹配/1/1.jpg",
        image_name="1.jpg",
        info=info,
        source_hash="sha256:abc",
        img_w=None,
        img_h=None,
    )
    assert ann["schema_version"] == "1.0"
    assert ann["image"]["task_id"] == "t1"
    assert ann["image"]["source_hash"] == "sha256:abc"
    assert ann["annotation"]["status"] == "annotated"
    assert len(ann["annotation"]["errors"]) == 2
    e1 = ann["annotation"]["errors"][0]
    assert e1["error_type"] == "topic"
    assert e1["error_subtype"] is None
    assert e1["marks"][0]["geometry"]["bbox"] is None
    assert "历史数据" in e1["comment"]
    print("  ✓ build_v2_annotation schema 正确")


def test_migrate_task_dir_in_place():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        task_dir = make_legacy_task(root, "t001", "切题, OCR")

        report = migrate_task_dir(task_dir, dry_run=False)
        assert report["skipped"] == []
        assert (task_dir / "annotations" / "default.json").exists()
        assert not (task_dir / "error_info.txt").exists()
        assert not (task_dir / "task_id.txt").exists()
        assert not (task_dir / "marked_1.jpg").exists()
        assert (task_dir / "source.jpg").exists()

        data = json.loads((task_dir / "annotations" / "default.json").read_text(encoding="utf-8"))
        assert data["annotation"]["status"] == "annotated"
        assert len(data["annotation"]["errors"]) == 2
        assert data["annotation"]["errors"][0]["error_type"] == "topic"
        assert data["annotation"]["errors"][1]["error_type"] == "ocr"
        assert data["image"]["source_hash"].startswith("sha256:")
    print("  ✓ 就地迁移行为正确")


def test_migrate_dry_run_does_not_mutate():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        task_dir = make_legacy_task(root, "t002", "解题")
        report = migrate_task_dir(task_dir, dry_run=True)
        assert not (task_dir / "annotations" / "default.json").exists()
        assert (task_dir / "error_info.txt").exists()
        assert (task_dir / "marked_1.jpg").exists()
        assert any("write annotations/default.json" in a for a in report["actions"])
    print("  ✓ dry-run 不写盘")


def test_already_migrated_skip():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        task_dir = make_legacy_task(root, "t003", "判题")
        (task_dir / "annotations").mkdir()
        (task_dir / "annotations" / "default.json").write_text("{}", encoding="utf-8")
        report = migrate_task_dir(task_dir, dry_run=False)
        assert any("already_migrated" in s for s in report["skipped"])
    print("  ✓ 已迁移目录正确跳过")


def test_load_reason_map_from_yaml():
    """M2 fix: 加载 reason_map.yaml 自定义映射"""
    import tempfile
    from migrate_legacy_zip import load_reason_map, parse_simple_yaml
    # 内置 reason_map.yaml 应能加载
    here = Path(__file__).parent
    m = load_reason_map(here / "reason_map.yaml")
    assert m["切题"] == "topic"
    assert m["OCR"] == "ocr"

    # 极简 YAML 解析
    parsed = parse_simple_yaml("""
# 注释
切题: topic
OCR: ocr
"解题": solution
""")
    assert parsed == {"切题": "topic", "OCR": "ocr", "解题": "solution"}

    # 缺失文件回退到默认
    m2 = load_reason_map(Path("/nonexistent/path/foo.yaml"))
    assert m2 == {"切题": "topic", "OCR": "ocr", "解题": "solution", "判题": "judgment"}
    print("  ✓ reason_map.yaml 加载与回退正确")


def test_unmapped_reason_warns_and_falls_back():
    """M2: 未识别的 reason 应兜底为 topic 并在 comment 标注"""
    import tempfile
    info = {"reasons": ["未知错误类型"], "timestamp": "2026-06-10T12:00:00.000Z"}
    ann = build_v2_annotation(
        task_id="t1", source_path="x/1.jpg", image_name="1.jpg",
        info=info, source_hash="sha256:abc", img_w=None, img_h=None,
    )
    e = ann["annotation"]["errors"][0]
    assert e["error_type"] == "topic"
    assert "未识别原因" in e["comment"]
    # color 也应被回填
    assert e["marks"][0]["color"] == "#e74c3c"
    print("  ✓ 未识别 reason 兜底 + warning 正确")


def test_migrate_output_dir_preserves_source():
    """M5 fix: --output 目录模式应复制后迁移，不破坏源"""
    import tempfile
    import subprocess
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "src"
        src.mkdir()
        make_legacy_task(src, "t001", "切题")

        out = Path(td) / "out"
        r = subprocess.run(
            [sys.executable, str(HERE / "migrate_legacy_zip.py"),
             str(src), "--output", str(out)],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, f"stderr: {r.stderr}"

        # 源目录应保持原样（error_info.txt 仍在）
        assert (src / "t001" / "error_info.txt").exists(), "源被破坏了"
        assert (src / "t001" / "marked_1.jpg").exists(), "源图被删了"

        # 输出目录应包含迁移后的结构
        assert (out / "t001" / "annotations" / "default.json").exists()
        assert (out / "t001" / "source.jpg").exists()
        assert not (out / "t001" / "error_info.txt").exists()
    print("  ✓ --output 目录模式保留源")


def test_migrate_via_zip(tmp_path=None):
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("result_root/t001/error_info.txt",
                    "任务编号: t001\n错误原因: 切题\n标注时间: 2026-06-10T12:00:00.000Z\n")
        zf.writestr("result_root/t001/task_id.txt", "t001")
        # 1x1 png
        png = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
            "890000000d49444154789c63000100000005000101a5f645770000000049454e44ae426082"
        )
        zf.writestr("result_root/t001/marked_1.jpg", png)
    buf.seek(0)

    with tempfile.TemporaryDirectory() as td:
        zip_path = Path(td) / "input.zip"
        zip_path.write_bytes(buf.getvalue())
        # 运行迁移脚本
        import subprocess
        out_zip = Path(td) / "out.zip"
        r = subprocess.run(
            [sys.executable, str(HERE / "migrate_legacy_zip.py"),
             str(zip_path), "--output", str(out_zip)],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert out_zip.exists()

        with zipfile.ZipFile(out_zip) as zf:
            names = zf.namelist()
            assert any("annotations/default.json" in n for n in names), names
            assert not any("error_info.txt" in n for n in names), names
    print("  ✓ ZIP 迁移流程正确")


def main():
    print("=" * 60)
    print("migrate_legacy_zip.py - 单元测试")
    print("=" * 60)
    passed = 0
    failed = 0
    for fn in [
        test_parse_error_info,
        test_map_reason_to_category,
        test_build_v2_annotation_schema,
        test_migrate_task_dir_in_place,
        test_migrate_dry_run_does_not_mutate,
        test_already_migrated_skip,
        test_load_reason_map_from_yaml,
        test_unmapped_reason_warns_and_falls_back,
        test_migrate_output_dir_preserves_source,
        test_migrate_via_zip,
    ]:
        try:
            print(f"\n[{fn.__name__}]")
            fn()
            passed += 1
        except AssertionError as e:
            print(f"  ✗ FAIL: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ ERROR: {type(e).__name__}: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"测试完成: 通过 {passed} 项, 失败 {failed} 项")
    print("=" * 60)
    if failed > 0:
        sys.exit(1)
    print("\n✓ 所有测试通过！")


if __name__ == "__main__":
    main()
