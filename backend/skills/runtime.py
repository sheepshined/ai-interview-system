"""runtime.py — 技能 L2/L3 资源访问与脚本安全校验 (SKILL_RUNTIME_PLAN §5/§9)。

  - L2 正文: 从 loader 缓存取 SKILL.md 正文 (激活时注入);
  - L3 references/: 目录清单 + 单篇读取 (路径穿越拦截);
  - L3 scripts/: 解析脚本路径 (技能目录内前缀校验 + 扩展名白名单) 并执行。

脚本执行四重限制 (§9.4): execute 闸门 + always_confirm (在 tools/skills.py 声明)
  + 路径前缀校验 + 超时/输出截断。
"""
import asyncio
import os
import subprocess
import sys
from typing import List, Optional, Tuple

from assistant.budget import truncate_output
from skills import loader

REFERENCE_SUFFIX = ".md"
ALLOWED_SCRIPT_EXT = (".py", ".mjs", ".js")
SCRIPT_TIMEOUT_SECONDS = 30
SCRIPT_OUTPUT_CHARS = 8000
_SCRIPT_PREFIX = "scripts" + os.sep


def read_skill_body(name: str) -> str:
    """L2: 激活技能时读取其 SKILL.md 正文。"""
    skill = loader.get_skill(name)
    return skill.body if skill else ""


def _safe_join(root: str, *parts: str) -> Optional[str]:
    """规范化后做前缀校验, 阻断 ../ 路径穿越 (SKILL_RUNTIME_PLAN §9.4)。"""
    if not root:
        return None
    base = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(base, *parts))
    if candidate != base and not candidate.startswith(base + os.sep):
        return None
    return candidate


def list_references(name: str) -> List[str]:
    """references/ 下的文件名清单 (不含子目录, 仅供模型选择)。"""
    skill = loader.get_skill(name)
    if not skill:
        return []
    ref_dir = os.path.join(skill.meta.dir, "references")
    try:
        names = sorted(os.listdir(ref_dir))
    except OSError:
        return []
    return [n for n in names
            if n.endswith(REFERENCE_SUFFIX)
            and os.path.isfile(os.path.join(ref_dir, n))]


def read_reference(name: str, file_name: str) -> Tuple[str, bool]:
    """读单篇 references 文档, 返回 (文本, 是否截断)。非法/不存在返回 ("", False)。"""
    skill = loader.get_skill(name)
    if not skill:
        return "", False
    if (not file_name or file_name.startswith(".")
            or "/" in file_name or "\\" in file_name
            or not file_name.endswith(REFERENCE_SUFFIX)):
        return "", False
    path = _safe_join(skill.meta.dir, "references", file_name)
    if not path or not os.path.isfile(path):
        return "", False
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return "", False
    return truncate_output(text)


def resolve_script(name: str, script: str) -> Optional[str]:
    """解析技能 scripts/ 内的脚本路径并做安全校验, 非法返回 None。

    限制: 仅相对 scripts/ 的 .py/.mjs/.js; 规范化后必须仍在技能目录内 (§9.4)。
    """
    skill = loader.get_skill(name)
    if not skill:
        return None
    script = (script or "").strip()
    if script.startswith(_SCRIPT_PREFIX):
        script = script[len(_SCRIPT_PREFIX):]
    if (not script or script.startswith(".")
            or "/" in script or "\\" in script):
        return None
    if os.path.splitext(script)[1].lower() not in ALLOWED_SCRIPT_EXT:
        return None
    path = _safe_join(skill.meta.dir, "scripts", script)
    if not path or not os.path.isfile(path):
        return None
    return path


def _script_command(path: str) -> Optional[List[str]]:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".py":
        return [sys.executable, path]
    if ext in (".mjs", ".js"):
        return ["node", path]
    return None


def _run_sync(command: List[str], cwd: str) -> dict:
    try:
        proc = subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=SCRIPT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return {"ok": False, "found": True,
                "message": f"脚本执行超时 (>{SCRIPT_TIMEOUT_SECONDS}s), 已终止"}
    except OSError as exc:
        return {"ok": False, "found": False, "message": f"脚本无法执行: {exc}"}
    stdout = (proc.stdout or "")[:SCRIPT_OUTPUT_CHARS]
    return {"ok": proc.returncode == 0, "found": True,
            "returncode": proc.returncode, "stdout": stdout,
            "stderr": (proc.stderr or "")[-1000:], "cwd": cwd}


async def run_script(name: str, script: str) -> dict:
    """执行技能脚本。cwd 限定技能目录, 超时/输出截断见 §9.4。"""
    path = resolve_script(name, script)
    if not path:
        return {"ok": False, "found": False,
                "message": "脚本路径非法或不存在 (仅允许技能 scripts/ 内的 .py/.mjs/.js)"}
    command = _script_command(path)
    if command is None:
        return {"ok": False, "found": False, "message": "不支持的脚本扩展名"}
    skill = loader.get_skill(name)
    return await asyncio.to_thread(_run_sync, command, skill.meta.dir)
