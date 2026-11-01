"""Run the assistant evaluation cases through the real LangGraph.

The model is the configured real LLM. External data sources are deterministic
fixtures so the run measures routing and graph behavior instead of depending on
a developer's local reports or notes.

Usage:
    .venv/Scripts/python.exe tests/assistant_eval.py --runs 1
    .venv/Scripts/python.exe tests/assistant_eval.py --runs 3 --case route-004
"""
import argparse
import asyncio
import hashlib
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

CASES = Path(__file__).with_name("data") / "assistant_cases.jsonl"
DEFAULT_RESULT = Path(__file__).with_name("results") / "assistant_eval_latest.json"


def load_cases():
    with CASES.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _ns(obj):
    if isinstance(obj, dict):
        return SimpleNamespace(**{key: _ns(value) for key, value in obj.items()})
    if isinstance(obj, list):
        return [_ns(value) for value in obj]
    return obj


class _TraceProxy:
    def __init__(self, counts):
        self._counts = counts

    def __getattr__(self, name):
        return SimpleNamespace(count=self._counts.get(name, 0))


def _message_text(message) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


def build_namespace(final_state, events, answer_text, extra=None):
    trace = final_state.get("tool_trace") or []
    counts = Counter(entry.get("tool") for entry in trace)
    # 技能路由断言命名空间 (SKILL_RUNTIME_PLAN §8): from skill_trace 统计激活次数
    activations = [entry.get("skill")
                   for entry in (final_state.get("skill_trace") or [])
                   if entry.get("event") == "activate"]
    skill_counts = Counter(activations)
    memory_events = [event for event in events
                     if event.get("type") == "memory_written"]
    namespace = {
        "tool_trace": _TraceProxy(counts),
        "skill_trace": _TraceProxy(skill_counts),
        "activated_skills": sorted(skill_counts),
        "activation_count": sum(skill_counts.values()),
        "pending_action": _ns(final_state.get("pending_action") or None),
        "memory_written": _ns(memory_events[-1]) if memory_events else None,
        "last_message_is_question": answer_text.rstrip().endswith(("?", "？")),
        "asks_a_question": "?" in answer_text or "？" in answer_text,
        "report_detail_reads": (
            counts.get("read_report_radar", 0)
            + counts.get("read_report_weak_points", 0)
            + counts.get("read_report_md", 0)
        ),
        "mentions_resume_entry": (
            "简历" in answer_text and any(word in answer_text
                                     for word in ("上传", "粘贴", "配置"))
        ),
    }
    namespace.update(extra or {})
    return namespace


def check_case(case, final_state, events, answer_text, extra=None):
    if any(event.get("type") == "error" for event in events):
        return "failed"
    criteria = case.get("criteria", {})
    criterion_type = criteria.get("type")
    if criterion_type == "state_assert":
        namespace = build_namespace(final_state, events, answer_text, extra)
        try:
            passed = bool(eval(criteria["assert"], {"__builtins__": {}}, namespace))  # noqa: S307
        except (AttributeError, KeyError, TypeError, ValueError, NameError):
            passed = False
        return "passed" if passed else "failed"
    if criterion_type == "contains_all":
        passed = all(text in answer_text for text in criteria["assert"])
        return "passed" if passed else "failed"
    return "pending_review"


def _install_fixtures(root: Path):
    import application_store
    import config
    import kb_llm
    import kb_parent
    from assistant import deps, vector_index
    from resume import store

    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    config.REPORTS_DIR = str(reports)
    records = root / "interview_records"
    records.mkdir(parents=True, exist_ok=True)
    config.INTERVIEW_RECORDS_DIR = str(records)
    store.init_db(str(root / "resumes.db"))
    application_store.init_db(str(root / "applications.db"))
    # 技能运行时: 铺上内置技能 (backend/skills), 保证 L1 目录与 skill_routing 用例可见
    from skills import loader as skill_loader
    skill_loader.reload(skill_loader.SKILLS_ROOT)
    vector_index.search = lambda *args, **kwargs: []
    vector_index.upsert = lambda *args, **kwargs: None
    vector_index.delete = lambda *args, **kwargs: None
    vector_index.clear = lambda *args, **kwargs: None

    contexts = [{
        "note_id": 1,
        "title": "RAG 手册",
        "text": "分块重叠用于保留跨边界语义，常从块大小的 10%-20% 开始调参。",
        "score": 0.93,
    }]
    kb_parent.search = lambda username, question, top_k: contexts[:top_k]
    kb_llm.answer_from_knowledge = lambda question, found: {
        "answer": "分块重叠用于保留跨边界语义。",
        "sources": [{"title": item["title"], "note_id": item["note_id"]}
                    for item in found],
        "sparse": False,
    }

    class Retriever:
        def get_question(self, topic, role, top_k):
            return [{"id": "q-rag-1", "question": "如何设计 RAG 分块策略？",
                     "category": "RAG", "difficulty": 2}][:top_k]

        def get_categories(self, role):
            return ["RAG", "Agent", "提示词工程"]

    deps.get_retriever = lambda: Retriever()
    return reports


async def _execute_contract(case, run_index):
    """Exercise deterministic production contracts without calling the LLM."""
    from pydantic import ValidationError
    import asr
    import config
    from assistant import db
    from assistant.context_compression import maybe_compress_session
    from jd_analysis import JdAnalysis
    from resume import store
    import application_store

    contract = case.get("contract")
    passed = False
    details = {}
    if contract == "resume_user_isolation":
        record = store.create_resume(
            f"contract_alice_{run_index}", "张三 Python",
            {"name": "张三", "skills": ["Python"]}, source="text",
        )
        hidden = store.get_resume(f"contract_bob_{run_index}", record["id"])
        passed = hidden is None
        details = {"resume_id": record["id"], "cross_user_visible": hidden is not None}
    elif contract == "jd_forbids_score":
        try:
            JdAnalysis.model_validate({
                "hard_constraints": [], "gaps": [], "next_questions": [],
                "keyword_matches": [], "missing_keywords": [], "suggestions": [],
                "score": 99,
            })
        except ValidationError:
            passed = True
        details = {"forbidden_score_rejected": passed}
    elif contract == "summary_compaction":
        old_threshold = config.ASSISTANT_SUMMARY_TOKEN_THRESHOLD
        old_keep = config.ASSISTANT_SUMMARY_KEEP_MESSAGES
        try:
            config.ASSISTANT_SUMMARY_TOKEN_THRESHOLD = 1
            config.ASSISTANT_SUMMARY_KEEP_MESSAGES = 2
            username = f"contract_summary_{run_index}"
            session = db.create_session(username, "summary contract")
            for role, text in (("user", "早期目标"), ("assistant", "早期结论"),
                               ("user", "当前问题"), ("assistant", "当前回答")):
                db.append_message(session["id"], role, text)

            class Snapshot:
                tasks = []
                values = {"messages": [], "pending_action": {}}

            class Graph:
                async def aupdate_state(self, *_):
                    return None

            async def summarize(_previous, _rows):
                return "用户早期目标及其结论。"

            result = await maybe_compress_session(
                Graph(), {}, username, session["id"], snapshot=Snapshot(),
                summarize=summarize,
            )
            full = db.list_messages(username, session["id"])
            context = db.list_context_messages(username, session["id"])
            passed = result["compressed"] == 2 and len(full) == 4 and len(context) == 2
            details = {"full_messages": len(full), "context_messages": len(context)}
        finally:
            config.ASSISTANT_SUMMARY_TOKEN_THRESHOLD = old_threshold
            config.ASSISTANT_SUMMARY_KEEP_MESSAGES = old_keep
    elif contract == "voice_transcript_safety":
        control = asr.clean_transcript("<|zh|>请介绍项目")
        filler = asr.clean_transcript("谢谢观看")
        repeated = asr.clean_transcript("你好你好你好你好")
        passed = control == "请介绍项目" and filler == "" and repeated == "你好"
        details = {"control_tokens_removed": control, "filler": filler,
                   "repeat_collapsed": repeated}
    elif contract == "jd_version_isolation":
        username = f"contract_jd_{run_index}"
        item = application_store.create(username, {"company": "Fixture", "role_title": "Dev", "jd_text": "Python"})
        version_id = item["jd_version"]["id"]
        foreign = application_store.get_jd_version("foreign_user", item["id"], version_id)
        write = application_store.save_jd("foreign_user", item["id"], "forged", "", 1)
        restore = application_store.save_jd("foreign_user", item["id"], "", "", 1, restore_id=version_id)
        passed = foreign is None and write is None and restore is None and application_store.get(username, item["id"])["jd_text"] == "Python"
        details = {"cross_user_read": foreign is not None, "cross_user_write": write is not None, "cross_user_restore": restore is not None}
    else:
        raise RuntimeError(f"未知 contract: {contract}")
    return {
        "run": run_index,
        "status": "passed" if passed else "failed",
        "contract": contract,
        "details": details,
    }


def _write_report_fixtures(reports: Path, username: str):
    for index, score in enumerate((4.2, 5.1, 4.8), start=1):
        report_id = f"interview_report_2026100{index}_12000{index}_{username}_llm_app"
        payload = {
            "report_id": report_id,
            "username": username,
            "role_title": "大模型应用开发工程师",
            "avg_score": score,
            "total_questions": 5,
            "timestamp": f"2026-10-0{index}T12:00:0{index}",
            "category_scores": {"RAG": score},
            "questions": [{"round": 1, "question": "如何设计分块？",
                           "score": score, "category": "RAG"}],
            "weaknesses": ["RAG 分块与召回评估"],
            "learning_suggestions": ["补充离线召回评估实验"],
        }
        (reports / f"{report_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_record_fixtures(username: str):
    """为内容级检索用例铺记录 fixtures (含关键词 RRF 融合, 按用户隔离)。"""
    import config

    records_dir = Path(config.INTERVIEW_RECORDS_DIR)
    for index in (1, 2):
        name = f"interview_records_2026100{index}_12000{index}_ab{index}cd.md"
        body = (
            f"# AI 模拟面试记录\n\n- **用户**: {username}\n"
            "- **岗位**: 大模型应用开发工程师\n\n"
            "## 第1题\n\n**题目**: 混合检索两路结果怎么融合？\n\n"
            "**你的回答**:\n我用了 RRF 融合, BM25_WEIGHT=0.4, VECTOR_WEIGHT=0.6, K=60。\n"
        )
        (records_dir / name).write_text(body, encoding="utf-8")


async def _execute_case(graph, case, run_index, reports):
    from assistant import db

    username = f"eval_{case['id'].replace('-', '_')}_{run_index}"
    _write_report_fixtures(reports, username)
    _write_record_fixtures(username)
    session = db.create_session(username, f"{case['id']} run {run_index}")
    thread_id = f"as_{username}_{session['id']}"
    payload = {
        "messages": [HumanMessage(content=case["input"])],
        "username": username,
        "session_id": session["id"],
        "thread_id": thread_id,
        "env_ongoing_interview": bool(case.get("context", {}).get("ongoing_interview")),
    }
    events, final = [], {}
    async for mode, item in graph.astream(
        payload, {"configurable": {"thread_id": thread_id}},
        stream_mode=["custom", "values"],
    ):
        if mode == "custom" and isinstance(item, dict):
            events.append(item)
        elif mode == "values" and isinstance(item, dict):
            final = item
    answer = ""
    for message in reversed(final.get("messages") or []):
        if isinstance(message, AIMessage):
            answer = _message_text(message)
            break
    activations = [entry.get("skill") for entry in (final.get("skill_trace") or [])
                   if entry.get("event") == "activate"]
    extra = {
        "expected_skills": case.get("expected_skills", []),
        "forbidden_skills": case.get("forbidden_skills", []),
        "max_activations": case.get("max_activations"),
        # 误触发: 声明"不应触发"的用例里却发生了激活
        "skill_false_trigger": bool(activations) and bool(case.get("no_trigger")),
    }
    status = check_case(case, final, events, answer, extra)
    tools = [entry.get("tool") for entry in final.get("tool_trace") or []]
    return {
        "run": run_index,
        "status": status,
        "tools": tools,
        "activated_skills": sorted(set(activations)),
        "activation_count": len(activations),
        "skill_false_trigger": extra["skill_false_trigger"],
        "pending_kind": (final.get("pending_action") or {}).get("kind"),
        "answer_sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest(),
        "answer_excerpt": answer[:600],
    }


def aggregate_status(statuses):
    statuses = set(statuses)
    if "failed" in statuses or not statuses:
        return "failed"
    return "pending_review" if "pending_review" in statuses else "passed"


async def execute_run(graph, case, run_index, reports):
    """Keep one failed case from discarding all completed evaluation evidence."""
    try:
        if case.get("type") == "contract":
            return await _execute_contract(case, run_index)
        if case.get("type") == "trajectory":
            return await _execute_trajectory(graph, case, run_index, reports)
        return await _execute_case(graph, case, run_index, reports)
    except Exception as exc:
        return {"run": run_index, "status": "failed", "error_type": type(exc).__name__}


async def _execute_trajectory(graph, case, run_index, reports):
    """Continue the same checkpoint and resume its real confirmation interrupt."""
    import application_store as store
    from assistant import db

    username = f"eval_{case['id'].replace('-', '_')}_{run_index}"
    _write_report_fixtures(reports, username)
    session = db.create_session(username, case["id"])
    initial = store.create(username, {"company": "Eval Fixture", "role_title": "Developer",
                                      "jd_text": "Python", "job_url": "https://example.test/job"})
    if case.get("seed_second_version"):
        store.save_jd(username, initial["id"], "SQL", initial["job_url"], 1)
    template = {"application_id": initial["id"], "version_id": initial["jd_version"]["id"]}
    cfg = {"configurable": {"thread_id": f"as_{username}_{session['id']}"}}
    steps, operation_ids = [], []
    for index, step in enumerate(case["steps"]):
        snapshot = await graph.aget_state(cfg)
        pending = snapshot.values.get("pending_action") or {}
        before = store.get(username, initial["id"])
        if step.get("external_update"):
            store.save_jd(username, initial["id"], step["external_update"], before["job_url"], before["jd_version"]["version"])
        if "decision" in step:
            if not pending or not any(task.interrupts for task in snapshot.tasks):
                steps.append({"step": index + 1, "status": "failed", "error": "No confirmation interrupt to resume"})
                break
            payload = Command(resume={"action": step["decision"], "reason": "evaluation", "args": {}})
        else:
            if pending:
                steps.append({"step": index + 1, "status": "failed", "error": "Unresolved proposal blocks the next turn"})
                break
            payload = {"messages": [HumanMessage(content=step["input"].format(**template))],
                       "username": username, "session_id": session["id"],
                       "thread_id": cfg["configurable"]["thread_id"], "env_ongoing_interview": False}
        events, final = [], {}
        async for mode, item in graph.astream(payload, cfg, stream_mode=["custom", "values"]):
            if mode == "custom" and isinstance(item, dict):
                events.append(item)
            elif mode == "values" and isinstance(item, dict):
                final = item
        messages = final.get("messages") or []
        answer = next((_message_text(m) for m in reversed(messages) if isinstance(m, AIMessage)), "")
        current = store.get(username, initial["id"])
        pending = final.get("pending_action") or {}
        if pending.get("operation_id"):
            operation_ids.append(pending["operation_id"])
        call_ids = [c["id"] for m in messages if isinstance(m, AIMessage) for c in m.tool_calls]
        result_ids = [m.tool_call_id for m in messages if isinstance(m, ToolMessage)]
        results = [e for e in events if e.get("type") == "tool_result"]
        extra = {
            "application_jd_version": current["jd_version"]["version"],
            "application_jd_text": current["jd_text"],
            "jd_source_preserved": current["job_url"] == initial["job_url"],
            "tool_pairs_complete": Counter(call_ids) == Counter(result_ids),
            "last_tool_ok": results[-1]["ok"] if results else None,
            "approval_distinct": len(operation_ids) == len(set(operation_ids)),
            "pending_tool_name": ((pending.get("args") or {}).get("calls") or [{}])[0].get("name"),
        }
        status = check_case(step, final, events, answer, extra)
        steps.append({"step": index + 1, "status": status, "decision": step.get("decision"),
                      "tools": [e["name"] for e in results], "state": extra,
                      "pending_kind": pending.get("kind"), "answer_excerpt": answer[:600]})
    return {"run": run_index, "status": aggregate_status(s["status"] for s in steps), "steps": steps}


def skill_false_trigger_summary(case_results):
    """技能误触发率: 声明"不应触发"的用例 (no_trigger) 里发生激活的比例 (§8)。"""
    no_trigger_runs = sum(len(item["runs"]) for item in case_results
                          if item.get("no_trigger"))
    false_trigger_runs = sum(1 for item in case_results if item.get("no_trigger")
                             for run in item["runs"]
                             if run.get("skill_false_trigger"))
    return {
        "no_trigger_runs": no_trigger_runs,
        "false_trigger_runs": false_trigger_runs,
        "rate": round(false_trigger_runs / no_trigger_runs, 4)
        if no_trigger_runs else 0.0,
    }


async def run(args):
    import config
    from assistant import db, permission
    from assistant.graph import build_assistant_graph

    cases = load_cases()
    if args.case:
        cases = [case for case in cases if case["id"] == args.case]
        if not cases:
            raise RuntimeError(f"未知 case: {args.case}")
    if any(case.get("type") != "contract" for case in cases) and not config.LLM_API_KEY:
        raise RuntimeError("未配置 LLM_API_KEY/DEEPSEEK_API_KEY，无法运行真实图评测")

    with tempfile.TemporaryDirectory(
        prefix="assistant-eval-", ignore_cleanup_errors=True
    ) as temp:
        root = Path(temp)
        db.init_db(str(root / "assistant.db"))
        permission.reset_for_tests()
        reports = _install_fixtures(root)
        graph = build_assistant_graph().compile(checkpointer=MemorySaver())
        case_results = []
        for case in cases:
            runs = []
            for run_index in range(1, args.runs + 1):
                result = await execute_run(graph, case, run_index, reports)
                runs.append(result)
                print(f"{case['id']} run={run_index}: {result['status']} "
                      f"tools={result.get('tools', [])}")
            overall = aggregate_status(item["status"] for item in runs)
            case_results.append({"id": case["id"], "status": overall,
                                 "criteria": case["criteria"], "runs": runs,
                                 "no_trigger": bool(case.get("no_trigger")),
                                 "expected_skills": case.get("expected_skills", [])})

    # 技能误触发率: 声明"不应触发"的用例里发生激活的比例 (SKILL_RUNTIME_PLAN §8)
    summary = Counter(item["status"] for item in case_results)
    result_doc = {
        "model": config.LLM_MODEL_FAST,
        "cases_sha256": hashlib.sha256(CASES.read_bytes()).hexdigest(),
        "runs_per_case": args.runs,
        "summary": dict(summary),
        "skill_false_trigger": skill_false_trigger_summary(case_results),
        "cases": case_results,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"result={output}")
    print(f"summary={dict(summary)}")
    return 1 if summary.get("failed") else 0


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3, choices=range(1, 6))
    parser.add_argument("--case", default="")
    parser.add_argument("--output", default=str(DEFAULT_RESULT))
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parse_args())))
