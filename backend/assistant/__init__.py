"""assistant 包 — 统筹智能体层 (AGENT_PLAN.md)。

边界不变量: 本包只"提议"不"擅自执行"。面试 StateGraph (agent/graph.py) 与
知识库内核 (knowledge.py / kb_parent.py / retrieval/) 只被调用, 不被修改。
"""
