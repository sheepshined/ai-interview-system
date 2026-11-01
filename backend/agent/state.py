"""
agent/state.py — LangGraph 面试流程共享状态

集中原 InterviewEngine 散落在实例变量上的全部状态,
作为 StateGraph 各节点之间传递的单一数据载体。
运行期间由 checkpointer 按 thread_id 保存暂停点；服务重启持久化不在本轮范围。
"""
from typing import TypedDict, List, Dict, Optional


class InterviewState(TypedDict, total=False):
    # ---- 配置 (configure 节点写入) ----
    thread_id: str
    role_key: str
    role_info: Dict
    difficulty: int
    difficulty_label: str
    total_count: int
    resume_context: str
    resume_skills: List[str]
    candidate_name: str
    # 面试模式: standard=题库检索出题; project=项目深挖(按简历 LLM 生成追问链);
    # hybrid=先按简历出 warmup_count 道项目热身题, 再切回题库检索
    interview_mode: str
    # hybrid 模式的项目热身题数 (默认 5)
    warmup_count: int
    # 岗位 JD 原文 (配置阶段可选提交; 投递档案关联时取档案 JD), 仅作数据不作指令
    jd_text: str
    # 归属用户 (v0.6 鉴权隔离): WS config 时由 server 注入, 写入报告 JSON 用于按用户隔离
    username: str
    # 可选投递档案关联: 面试完成后报告与结果复盘回到同一机会
    application_id: int

    # ---- 面试官人设 ----
    # persona_key: 人设键名 (strict_cto / warm_hr / deep_tech)
    # persona_info: 人设完整信息字典 (name, description, question_style, followup_style)
    persona_key: str
    persona_info: Dict

    # ---- 面试进度 ----
    asked_ids: List[str]
    asked_categories: List[str]
    main_question_count: int
    first_topic_hint: str
    question_index: int

    # ---- 当前轮 ----
    question_id: str
    current_question: Dict
    current_answer_data: Dict
    rendered_question: str
    main_answer: str
    followup_question: str
    followup_answer: str
    followup_context: Dict
    combined_answer: str
    human_answer: Optional[str]
    input_action: str
    force_end: bool

    # ---- 评分记录 ----
    records: List[Dict]
    initial_result: Dict
    final_result: Dict
    initial_score: int
    final_score: int

    # ---- 自适应难度 ----
    # streak: 连续表现计数器。≥7分+1, <4分=-1(立即降级), 4-6分=0(重置)
    # difficulty_changes: 记录每次难度变化的历史(用于报告可视化)
    streak: int
    difficulty_changes: List[Dict]

    # ---- 提示系统 ----
    # hint_count: 当前题目使用的提示次数 (0/1/2)
    hint_count: int

    # ---- 决策 ----
    decision: Dict

    # ---- 文件 ----
    md_path: str
    report_path: str
    report_id: str

    # ---- 调试 ----
    phase: str
