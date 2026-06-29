#!/usr/bin/env python3
"""
将旧版标注结果（marked_*.jpg + error_info.txt）迁移到 v2 schema
（source.<ext> + annotations/default.json）。

用法:
    python3 migrate_legacy_zip.py <input_zip_or_dir> [--output <path>] [--dry-run]

输入:
    - ZIP 文件：解压后处理，输出新 ZIP
    - 目录：就地处理或输出到 --output 指定目录

输出结构:
    <task_id>/
        source.<ext>            # 从 marked_*.jpg 复制
        annotations/
            default.json        # v2 schema

行为:
    - 读取 error_info.txt 的 reasons，映射为 errors[]
    - bbox 字段一律 null（位置信息已栅格化、无法恢复），comment 标注迁移来源
    - 删除 error_info.txt 和 task_id.txt（信息已进 JSON）
    - 计算 source.<ext> 的 sha256

dry-run 只打印 diff，不写盘。
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = "1.0"
ANNOTATOR_ID = "default"

# taxonomy 颜色（与 taxonomy.json 保持同步；用于回填 marks[].color）
TAXONOMY_COLORS = {
    "topic": "#e74c3c",
    "ocr": "#3498db",
    "solution": "#f39c12",
    "judgment": "#9b59b6",
}

DEFAULT_REASON_MAP = {
    "切题": "topic",
    "OCR": "ocr",
    "解题": "solution",
    "判题": "judgment",
}


def load_reason_map(explicit_path: Optional[Path] = None) -> dict:
    """加载 reason_map.yaml；失败回退到 DEFAULT_REASON_MAP。"""
    candidates = []
    if explicit_path:
        candidates.append(explicit_path)
    else:
        candidates.append(Path(__file__).parent / "reason_map.yaml")
        candidates.append(Path.cwd() / "reason_map.yaml")

    for p in candidates:
        if not p.exists():
            continue
        try:
            return parse_simple_yaml(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"⚠️ 加载 {p} 失败: {e}，使用内置映射", file=sys.stderr)
            return dict(DEFAULT_REASON_MAP)
    return dict(DEFAULT_REASON_MAP)


def parse_simple_yaml(text: str) -> dict:
    """极简 YAML 解析（只支持 `key: value` 行，避免引入 PyYAML 依赖）。"""
    result = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("---"):
            continue
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip().strip('"\'')
        v = v.strip().strip('"\'')
        if k and v:
            result[k] = v
    return result

LEGACY_FIELD_PATTERNS = {
    "taskId": re.compile(r"^任务编号:\s*(.+)$"),
    "folderPath": re.compile(r"^文件夹:\s*(.+)$"),
    "imageName": re.compile(r"^图片名称:\s*(.+)$"),
    "timestamp": re.compile(r"^标注时间:\s*(.+)$"),
    "badcaseCount": re.compile(r"^Badcase\s*数量:\s*(\d+)"),
    "reasons": re.compile(r"^错误原因:\s*(.+)$"),
    "hasDrawing": re.compile(r"^是否有勾画痕迹:\s*(是|否)"),
}


def parse_error_info(text: str) -> dict:
    info: dict = {"reasons": []}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("---"):
            continue
        for key, pat in LEGACY_FIELD_PATTERNS.items():
            m = pat.match(line)
            if not m:
                continue
            if key == "reasons":
                info["reasons"] = [r.strip() for r in m.group(1).split(",") if r.strip()]
            elif key == "badcaseCount":
                info[key] = int(m.group(1))
            elif key == "hasDrawing":
                info[key] = m.group(1) == "是"
            else:
                info[key] = m.group(1).strip()
    return info


def map_reason_to_category(reason: str, reason_map: dict) -> Optional[str]:
    if reason in reason_map:
        return reason_map[reason]
    # 模糊兜底
    upper = reason.upper()
    if "OCR" in upper:
        return "ocr"
    if "切" in reason and "题" in reason:
        return "topic"
    if "解" in reason:
        return "solution"
    if "判" in reason:
        return "judgment"
    return None


# 模块级 reason_map，由 main() 初始化
REASON_MAP: dict = dict(DEFAULT_REASON_MAP)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def build_v2_annotation(task_id: str, source_path: str, image_name: str,
                        info: dict, source_hash: str, img_w: Optional[int],
                        img_h: Optional[int], reason_map: Optional[dict] = None) -> dict:
    reason_map = reason_map or REASON_MAP
    reasons = info.get("reasons", [])
    errors = []
    unmapped_reasons = []
    for i, r in enumerate(reasons, start=1):
        cat = map_reason_to_category(r, reason_map)
        if cat is None:
            unmapped_reasons.append(r)
            cat = "topic"  # 兜底分类
            comment_text = f"（历史数据，未识别原因 '{r}'，归入切题；位置信息未保留）"
        else:
            comment_text = "（历史数据，位置信息未保留，迁移自 error_info.txt）"
        errors.append({
            "error_id": f"legacy_{i:02d}",
            "error_type": cat,
            "error_subtype": None,
            "severity": None,
            "comment": comment_text,
            "marks": [{
                "mark_id": f"legacy_m_{i}",
                "role": "primary",
                "type": "bbox",
                "geometry": {"bbox": None, "points": None},
                "color": TAXONOMY_COLORS.get(cat, "#e74c3c"),
                "width": 2,
            }],
            "annotator_id": ANNOTATOR_ID,
            "created_at": info.get("timestamp"),
            "updated_at": info.get("timestamp"),
            "duration_ms": None,
        })

    if unmapped_reasons:
        print(f"⚠️ task={task_id} 未识别的 reasons: {unmapped_reasons}", file=sys.stderr)

    return {
        "schema_version": SCHEMA_VERSION,
        "image": {
            "task_id": task_id,
            "source_path": source_path,
            "source_hash": source_hash,
            "width": img_w,
            "height": img_h,
            "metadata": {"task_ids": [task_id]},
        },
        "annotation": {
            "status": "annotated" if errors else "pending",
            "errors": errors,
            "session_id": None,
            "annotator_id": ANNOTATOR_ID,
            "started_at": info.get("timestamp"),
            "saved_at": info.get("timestamp"),
            "total_duration_ms": 0,
            "client": {"tool_version": "migrate-1.0.0", "browser": None},
        },
    }


IMAGE_EXT_PATTERN = re.compile(r"\.(jpg|jpeg|png|gif|webp|bmp)$", re.IGNORECASE)


def is_image(name: str) -> bool:
    return bool(IMAGE_EXT_PATTERN.search(name))


def migrate_task_dir(task_dir: Path, dry_run: bool = False, reason_map: Optional[dict] = None) -> dict:
    """处理单个任务子目录，返回 diff 报告。"""
    report = {"task_dir": str(task_dir), "actions": [], "skipped": []}

    files = {p.name: p for p in task_dir.iterdir() if p.is_file()}
    error_info_file = files.get("error_info.txt")
    task_id_file = files.get("task_id.txt")
    marked = next((v for k, v in files.items() if k.startswith("marked_") and is_image(k)), None)
    existing_source = next((v for k, v in files.items() if k.startswith("source.") and is_image(k)), None)
    existing_json = (task_dir / "annotations" / "default.json").exists()

    if existing_json:
        report["skipped"].append("already_migrated (annotations/default.json exists)")
        return report

    if not error_info_file and not marked:
        report["skipped"].append("no error_info.txt or marked_*.jpg")
        return report

    task_id = task_dir.name
    if task_id_file:
        try:
            task_id = task_id_file.read_text(encoding="utf-8").strip() or task_id
        except Exception:
            pass

    info = {"reasons": []}
    if error_info_file:
        try:
            info = parse_error_info(error_info_file.read_text(encoding="utf-8"))
        except Exception as e:
            report["skipped"].append(f"error_info.txt parse failed: {e}")

    if "taskId" in info and info["taskId"]:
        task_id = info["taskId"]

    if existing_source:
        source_path = existing_source
        report["actions"].append(f"reuse existing source: {source_path.name}")
    elif marked:
        ext = marked.suffix.lower()
        new_path = task_dir / f"source{ext}"
        if not dry_run:
            shutil.copy2(marked, new_path)
            marked.unlink()
        source_path = new_path
        report["actions"].append(f"copy {marked.name} -> {new_path.name}; delete {marked.name}")
    else:
        report["skipped"].append("no marked_*.jpg or source.* to use")
        return report

    source_hash = sha256_of(source_path) if source_path.exists() else None

    ann_dir = task_dir / "annotations"
    payload = build_v2_annotation(
        task_id=task_id,
        source_path=info.get("folderPath", "") + "/" + (info.get("imageName") or source_path.name),
        image_name=info.get("imageName") or source_path.name,
        info=info,
        source_hash=source_hash,
        img_w=None,
        img_h=None,
        reason_map=reason_map,
    )

    if not dry_run:
        ann_dir.mkdir(exist_ok=True)
        (ann_dir / "default.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if error_info_file and error_info_file.exists():
            error_info_file.unlink()
        if task_id_file and task_id_file.exists():
            task_id_file.unlink()

    report["actions"].append(f"write annotations/default.json ({len(payload['annotation']['errors'])} errors)")
    if error_info_file:
        report["actions"].append(f"delete {error_info_file.name}")
    if task_id_file:
        report["actions"].append(f"delete {task_id_file.name}")
    return report


def iter_task_dirs(root: Path):
    if not root.is_dir():
        return
    for p in sorted(root.iterdir()):
        if p.is_dir() and p.name != "annotations":
            yield p


def migrate_root(root: Path, dry_run: bool, reason_map: Optional[dict] = None) -> list:
    reports = []
    for task_dir in iter_task_dirs(root):
        reports.append(migrate_task_dir(task_dir, dry_run=dry_run, reason_map=reason_map))
    return reports


def print_report(reports, dry_run):
    print(f"\n{'=== DRY RUN ===' if dry_run else '=== MIGRATION COMPLETE ==='}")
    migrated = 0
    skipped = 0
    for r in reports:
        if r["skipped"]:
            skipped += 1
            print(f"  [SKIP] {r['task_dir']}: {', '.join(r['skipped'])}")
        else:
            migrated += 1
            print(f"  [OK]   {r['task_dir']}")
            for a in r["actions"]:
                print(f"         - {a}")
    print(f"\n总计: 迁移 {migrated} 个，跳过 {skipped} 个")


def safe_zip_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    """解压 ZIP，拒绝包含 .. 或绝对路径的成员（防 path traversal）。"""
    dest = dest.resolve()
    for member in zf.infolist():
        member_path = (dest / member.filename).resolve()
        if not str(member_path).startswith(str(dest)):
            raise ValueError(f"恶意路径（拒绝解压）: {member.filename}")
        zf.extract(member, dest)


def looks_like_task_dir(d: Path) -> bool:
    """d 是否像一个任务子目录（含 error_info.txt 或 marked_* 或 source.* 或 annotations/）。"""
    if not d.is_dir():
        return False
    for p in d.iterdir():
        if p.name == "error_info.txt":
            return True
        if p.name.startswith("marked_") and is_image(p.name):
            return True
        if p.name.startswith("source.") and is_image(p.name):
            return True
        if p.is_dir() and p.name == "annotations":
            return True
    return False


def find_migration_root(work: Path) -> Path:
    """ZIP 解压后可能多一层包装目录。返回真正包含任务子目录的层。"""
    # 直接看 work 子目录是否有任务特征
    sub_dirs = [p for p in work.iterdir() if p.is_dir()]
    direct_task_count = sum(1 for d in sub_dirs if looks_like_task_dir(d))
    if direct_task_count > 0:
        return work
    # 否则看是否只有一个包装层
    if len(sub_dirs) == 1:
        candidate = sub_dirs[0]
        if any(looks_like_task_dir(c) for c in candidate.iterdir() if c.is_dir()):
            return candidate
    return work


def main():
    global REASON_MAP
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="输入 ZIP 文件或目录")
    ap.add_argument("--output", "-o", help="输出路径（ZIP 或目录）。默认就地写。")
    ap.add_argument("--dry-run", action="store_true", help="只打印 diff，不写盘")
    ap.add_argument("--reason-map", help="自定义 reason_map.yaml 路径（默认用脚本同目录的）")
    args = ap.parse_args()

    REASON_MAP = load_reason_map(Path(args.reason_map) if args.reason_map else None)

    in_path = Path(args.input).expanduser().resolve()
    if not in_path.exists():
        sys.exit(f"输入不存在: {in_path}")

    is_zip = in_path.is_file() and in_path.suffix.lower() == ".zip"

    if is_zip:
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "unpacked"
            work.mkdir()
            with zipfile.ZipFile(in_path) as zf:
                safe_zip_extract(zf, work)
            root = find_migration_root(work)

            reports = migrate_root(root, dry_run=args.dry_run, reason_map=REASON_MAP)
            print_report(reports, args.dry_run)

            if args.dry_run:
                return

            out_path = Path(args.output) if args.output else in_path.with_name(in_path.stem + "_v2.zip")
            if out_path.suffix.lower() != ".zip":
                out_path = out_path.with_suffix(".zip")
            with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for p in root.rglob("*"):
                    if p.is_file():
                        zf.write(p, p.relative_to(root))
            print(f"\n输出 ZIP: {out_path}")
    else:
        # 目录模式：如果指定 --output，先拷贝再在拷贝上迁移；否则就地迁移
        if args.output:
            out_path = Path(args.output)
            if out_path.exists() and any(out_path.iterdir()):
                sys.exit(f"输出目录非空，拒绝覆盖: {out_path}")
            out_path.mkdir(parents=True, exist_ok=True)
            shutil.copytree(in_path, out_path, dirs_exist_ok=True)
            migrate_root(out_path, dry_run=args.dry_run, reason_map=REASON_MAP)
            if args.dry_run:
                return
            print(f"\n输出目录: {out_path}")
        else:
            reports = migrate_root(in_path, dry_run=args.dry_run, reason_map=REASON_MAP)
            print_report(reports, args.dry_run)


if __name__ == "__main__":
    main()
