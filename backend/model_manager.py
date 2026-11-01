"""Verified downloads for local runtime models."""
import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_MANIFEST = BASE_DIR / "model_manifest.json"
CHUNK_SIZE = 1024 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid(path: Path, size: int, sha256: str) -> bool:
    return path.is_file() and path.stat().st_size == size and _sha256(path) == sha256.lower()


def load_manifest(path: Path = DEFAULT_MANIFEST) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    models = payload.get("models")
    if not isinstance(models, list) or not models:
        raise ValueError("模型清单为空或格式无效")
    required = {"name", "url", "destination", "size", "sha256"}
    for item in models:
        if not isinstance(item, dict) or not required.issubset(item):
            raise ValueError("模型清单缺少必要字段")
        destination = Path(item["destination"])
        if destination.is_absolute() or ".." in destination.parts:
            raise ValueError(f"非法模型目标路径: {destination}")
        if not str(item["url"]).startswith("https://"):
            raise ValueError(f"模型地址必须使用 HTTPS: {item['name']}")
        if int(item["size"]) <= 0 or len(str(item["sha256"])) != 64:
            raise ValueError(f"模型完整性信息无效: {item['name']}")
    return models


def _download(item: dict, target: Path, opener=None) -> None:
    opener = opener or urllib.request.urlopen
    part = target.with_name(target.name + ".part")
    target.parent.mkdir(parents=True, exist_ok=True)
    expected_size = int(item["size"])
    offset = part.stat().st_size if part.exists() else 0
    if offset > expected_size:
        part.unlink()
        offset = 0

    headers = {"User-Agent": "SmartSteer-model-manager/1.0"}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    request = urllib.request.Request(item["url"], headers=headers)
    response = opener(request, timeout=60)
    status = getattr(response, "status", response.getcode())
    if offset and status != 206:
        response.close()
        part.unlink(missing_ok=True)
        offset = 0
        request = urllib.request.Request(item["url"], headers={"User-Agent": headers["User-Agent"]})
        response = opener(request, timeout=60)

    mode = "ab" if offset else "wb"
    with response, part.open(mode) as handle:
        while True:
            chunk = response.read(CHUNK_SIZE)
            if not chunk:
                break
            handle.write(chunk)

    if not _valid(part, expected_size, item["sha256"]):
        raise ValueError(f"{item['name']} 下载完成但大小或 SHA-256 校验失败")
    os.replace(part, target)


def fetch_models(manifest_path: Path = DEFAULT_MANIFEST,
                 output: Callable[[str], None] = print) -> list[dict]:
    results = []
    for item in load_manifest(manifest_path):
        target = BASE_DIR / item["destination"]
        if _valid(target, int(item["size"]), item["sha256"]):
            output(f"[跳过] {item['name']} 已存在且校验通过")
            results.append({"name": item["name"], "status": "skipped", "path": str(target)})
            continue
        output(f"[下载] {item['name']} -> {target}")
        try:
            _download(item, target)
        except (OSError, ValueError, urllib.error.URLError) as exc:
            raise RuntimeError(f"模型下载失败: {item['name']}: {exc}") from exc
        output(f"[完成] {item['name']} 大小与 SHA-256 校验通过")
        results.append({"name": item["name"], "status": "downloaded", "path": str(target)})
    return results
