# Annotation JSON Schema v1.0

This document defines the source-of-truth data format produced by `annotation-tool.html` and consumed by `result-viewer.html` and downstream analysis tools.

## Design principles

1. **Structured event stream is the source of truth.** Images and text reports are derived views.
2. **Error is the atomic unit of analysis**, not strokes or images. Each error has exactly one bounding box.
3. **Coordinates live in image-pixel space** (`naturalWidth × naturalHeight`), not screen space.
4. **`badcase_count` is auto-derived** from `errors.length`. Never stored as an independent override.

## File layout in exported ZIP

```
批阅标注结果_<timestamp>.zip
├── _session.json              # session index (annotator-level)
├── _stats.jsonl               # derived: one row per error, for analysis
├── taxonomy.json              # snapshot of taxonomy used during this session
└── <task_id>/
    ├── annotations/
    │   └── default.json       # annotator "default"'s annotation (the source of truth)
    └── source.<ext>           # original image (for viewer bbox overlay)
```

For multi-annotator (v2+), `annotations/` contains `<annotator_id>.json` per annotator and optionally `review.json` for adjudication.

## `annotations/<annotator_id>.json`

```json
{
  "schema_version": "1.0",
  "image": {
    "task_id": "db45c6d8-04ed-4a71-a7d2-2179957bd9b4",
    "source_path": "未匹配/1/1.jpg",
    "source_hash": "sha256:9f2c1a...",
    "width": 2480,
    "height": 3508,
    "metadata": {
      "task_ids": ["db45c6d8-04ed-4a71-a7d2-2179957bd9b4"]
    }
  },
  "annotation": {
    "status": "annotated",
    "errors": [
      {
        "error_id": "err_01",
        "error_type": "ocr",
        "error_subtype": "char_wrong",
        "severity": null,
        "comment": "把 7 识别成 1",
        "marks": [
          {
            "mark_id": "m_01",
            "role": "primary",
            "type": "bbox",
            "geometry": {
              "bbox": [120, 338, 80, 42],
              "points": null
            },
            "color": "#3498db",
            "width": 2
          }
        ],
        "annotator_id": "default",
        "created_at": "2026-06-29T10:00:00.123Z",
        "updated_at": "2026-06-29T10:00:04.456Z",
        "duration_ms": 3200
      }
    ],
    "session_id": "sess_20260629_001",
    "annotator_id": "default",
    "started_at": "2026-06-29T09:58:00.000Z",
    "saved_at": "2026-06-29T10:02:00.000Z",
    "total_duration_ms": 240000,
    "client": {
      "tool_version": "2.0.0",
      "browser": "Mozilla/5.0..."
    }
  }
}
```

### Field semantics

| Field | Type | Required | Notes |
|---|---|---|---|
| `schema_version` | string | ✓ | `"1.0"`. Bump on breaking changes. |
| `image.task_id` | string | ✓ | UUID from `metadata.yaml`. |
| `image.source_path` | string | ✓ | Relative path within original folder. |
| `image.source_hash` | string \| null | ✓ | `sha256:<hex>`. `null` if hash computation failed (file:// + SubtleCrypto unavailable). |
| `image.width`, `image.height` | int \| null | ✓ | Natural pixel dimensions of source image. `null` when the tool serialized before the image finished loading (e.g. file:// + Safari slow load). Consumers should handle null gracefully. |
| `image.metadata` | object | ✓ | Pass-through from `metadata.yaml`. Always includes `task_ids`. |
| `annotation.status` | enum | ✓ | One of: `pending`, `annotated`, `skipped`. v2 adds `reviewed`, `adjudicated`. |
| `annotation.errors` | array | ✓ | Empty array if status is `skipped` or `pending`. |
| `errors[].error_id` | string | ✓ | Unique within this file. Format: `err_NN`. |
| `errors[].error_type` | string | ✓ | References `taxonomy.categories[].id`. |
| `errors[].error_subtype` | string \| null | | References `taxonomy.categories[].subtypes[].id`. |
| `errors[].severity` | int \| null | | 1-3. v1 not exposed in UI; always `null` for new data. |
| `errors[].comment` | string | | Free text. May be empty string. |
| `errors[].marks` | array | ✓ | May be empty for comment-only errors added via the viewer (no bbox drawn). When non-empty, exactly one mark must have `role: "primary"`. |
| `marks[].role` | enum | ✓ | `primary` (counted) or `note` (decorative, not counted). |
| `marks[].type` | enum | ✓ | `bbox` (v1 only). Reserved: `point`, `arrow`, `stroke`. |
| `marks[].geometry.bbox` | [x,y,w,h] \| null | | Required when `type === "bbox"` AND mark exists. `null` only for migrated historical data where location was rasterized. Image-pixel coords. |
| `marks[].color` | string | | Hex color from taxonomy category. |
| `errors[].annotator_id` | string | ✓ | `"default"` in v1. |
| `errors[].created_at`, `updated_at` | ISO 8601 | ✓ | UTC. |
| `errors[].duration_ms` | int | | Time spent on this error. v1 may be 0 if not tracked. |
| `annotation.session_id` | string | ✓ | Groups annotations from one work session. |
| `annotation.annotator_id` | string | ✓ | Matches each error's `annotator_id`. |
| `annotation.started_at`, `saved_at` | ISO 8601 | ✓ | When this image's annotation session began/ended. |
| `annotation.total_duration_ms` | int | | Wall-clock time on this image. |

### Invariants

- `badcase_count` is never stored; consumers compute as `errors.length`.
- An error with `marks: []` is a comment-only error (no spatial location). This is allowed when errors are added via the viewer (which has no bbox drawing UI) or for migrated data with unrecoverable location.
- When `marks` is non-empty, exactly one mark has `role: "primary"`.
- `marks[].geometry.bbox` uses `[x, y, w, h]` in image-pixel space. `x, y` is top-left corner.
- For migrated historical data, a mark with `type: "bbox"` and `bbox: null` is permitted; `comment` notes the data loss.

## `_session.json`

```json
{
  "schema_version": "1.0",
  "session_id": "sess_20260629_001",
  "annotator_id": "default",
  "annotator_name": null,
  "source_folder": "未匹配/",
  "started_at": "2026-06-29T09:55:00Z",
  "ended_at": "2026-06-29T11:20:00Z",
  "total_images": 50,
  "status_count": { "annotated": 48, "skipped": 2, "pending": 0 },
  "error_type_count": { "ocr": 12, "topic": 8, "solution": 5, "judgment": 3 },
  "images": [
    {
      "task_id": "db45c6d8-...",
      "source_path": "未匹配/1/1.jpg",
      "status": "annotated",
      "error_count": 2,
      "annotation_file": "db45c6d8-.../annotations/default.json"
    }
  ]
}
```

`status_count` and `error_type_count` are derived; consumers may recompute.

## `_stats.jsonl`

One JSON object per line, flat row per error. Suitable for `pd.read_json(lines=True)`:

```json
{"task_id":"db45c6d8-...","image":"1.jpg","error_id":"err_01","error_type":"ocr","subtype":"char_wrong","bbox":[120,338,80,42],"comment":"把 7 识别成 1","annotator_id":"default","severity":null,"duration_ms":3200,"saved_at":"2026-06-29T10:02:00Z"}
```

## Backward compatibility

- v1 viewer reads `annotations/default.json` first, falls back to legacy `error_info.txt` parsing if absent.
- Legacy data migrated via `migrate_legacy_zip.py` produces `annotations/default.json` with `bbox: null` (location unrecoverable).
