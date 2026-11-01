"""能力成长档案: 确定性聚合与 API 回归。"""

import json
import os

import auth
import config
import growth
import server
from fastapi.testclient import TestClient


client = TestClient(server.app)


def _report(report_id, username, timestamp, questions, avg_score=5.0,
            dimensions=None, role_title="大模型应用开发工程师",
            difficulty_label="Intermediate", total_questions=None):
    dims = {"accuracy": 5, "completeness": 5, "depth": 5, "clarity": 5}
    if dimensions:
        dims.update(dimensions)
    return {
        "report_id": report_id,
        "username": username,
        "role_key": "llm_app",
        "role_title": role_title,
        "difficulty_label": difficulty_label,
        "avg_score": avg_score,
        "total_questions": total_questions if total_questions is not None else len(questions),
        "timestamp": timestamp,
        "dimensions": dims,
        "categories": [],
        "questions": questions,
        "strengths": [],
        "weaknesses": [],
        "difficulty_changes": [],
        "learning_suggestions": [],
    }


def _q(category, score, difficulty=2, followup=False, hints=0):
    return {"question_id": f"q_{category}_{score}", "question": f"{category}题面",
            "category": category, "score": score, "max_score": 10,
            "had_followup": followup, "difficulty_at_time": difficulty,
            "hints_used": hints, "good_points": [], "bad_points": []}


def _write_reports(reports_dir, reports):
    os.makedirs(reports_dir, exist_ok=True)
    for r in reports:
        with open(os.path.join(reports_dir, f"{r['report_id']}.json"), "w",
                  encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False)


def test_build_growth_aggregates_categories_and_summary(tmp_path):
    reports = [
        _report("r1", "alice", "20261001_100000", [
            _q("RAG", 4), _q("RAG", 6), _q("微调", 3),
        ], avg_score=4.3),
        _report("r2", "alice", "20261002_100000", [
            _q("RAG", 7), _q("Agent", 8, followup=True, hints=1),
        ], avg_score=7.5),
    ]
    _write_reports(str(tmp_path), reports)

    data = growth.build_growth(str(tmp_path), "alice")

    # timeline 按时间正序, 日期与四维取整
    assert [t["report_id"] for t in data["timeline"]] == ["r1", "r2"]
    assert data["timeline"][0]["date"] == "2026-10-01"
    assert data["timeline"][1]["dimensions"]["accuracy"] == 5.0

    # 分类: 弱项置顶 (均分升序), RAG = (4+6+7)/3, 微调 = 3, Agent = 8
    cats = {c["name"]: c for c in data["categories"]}
    assert data["categories"][0]["name"] == "微调"
    assert cats["RAG"]["count"] == 3
    assert cats["RAG"]["avg_score"] == round((4 + 6 + 7) / 3, 1)
    assert cats["RAG"]["low_count"] == 1
    assert cats["RAG"]["delta"] == round(7 - 4, 1)
    assert cats["RAG"]["last_date"] == "2026-10-02"

    # 总览: 题目级均分、追问率、提示次数、趋势 (少于 4 场为 null)
    s = data["summary"]
    assert s["total_reports"] == 2
    assert s["total_questions"] == 5
    assert s["overall_avg"] == round((4 + 6 + 3 + 7 + 8) / 5, 1)
    assert s["followup_rate"] == 0.2
    assert s["hints_used_total"] == 1
    assert s["recent_delta"] is None
    assert s["weakest_category"]["name"] == "微调"
    assert s["best_category"]["name"] == "Agent"
    assert s["first_date"] == "2026-10-01" and s["last_date"] == "2026-10-02"


def test_recent_delta_needs_six_questions_worth_of_history(tmp_path):
    scores = [3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
    reports = [
        _report(f"r{i}", "alice", f"2026100{i}_100000", [_q("RAG", 5)],
                avg_score=scores[i - 1])
        for i in range(1, 7)
    ]
    _write_reports(str(tmp_path), reports)
    data = growth.build_growth(str(tmp_path), "alice")
    # 最近 3 场均分 7.0 - 之前 3 场 4.0 = 3.0
    assert data["summary"]["recent_delta"] == 3.0


def test_growth_user_isolation_and_invalid_files(tmp_path):
    _write_reports(str(tmp_path), [
        _report("mine", "alice", "20261001_100000", [_q("RAG", 5)]),
        _report("theirs", "bob", "20261002_100000", [_q("RAG", 9)]),
    ])
    with open(os.path.join(str(tmp_path), "broken.json"), "w", encoding="utf-8") as f:
        f.write("{not json")

    data = growth.build_growth(str(tmp_path), "alice")
    assert [t["report_id"] for t in data["timeline"]] == ["mine"]
    assert data["summary"]["total_questions"] == 1


def test_growth_empty_dir_returns_zeroed_structure(tmp_path):
    data = growth.build_growth(str(tmp_path), "nobody")
    assert data["timeline"] == [] and data["categories"] == []
    assert data["summary"]["total_reports"] == 0
    assert data["summary"]["overall_avg"] == 0.0
    assert data["summary"]["recent_delta"] is None
    assert data["difficulty_distribution"] == {"1": 0, "2": 0, "3": 0}


def test_growth_api_route_not_swallowed_and_isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "REPORTS_DIR", str(tmp_path))
    _write_reports(str(tmp_path), [
        _report("mine", "growth_alice", "20261001_100000", [_q("RAG", 5)]),
        _report("theirs", "growth_bob", "20261002_100000", [_q("RAG", 9)]),
    ])

    try:
        auth.create_user("growth_alice", "password123")
    except ValueError:
        pass
    headers = {"Authorization": f"Bearer {auth.create_access_token('growth_alice')}"}

    resp = client.get("/api/reports/growth", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["growth"]
    assert data["summary"]["total_reports"] == 1
    assert data["timeline"][0]["report_id"] == "mine"

    # 未登录拒绝
    assert client.get("/api/reports/growth").status_code in (401, 403)
