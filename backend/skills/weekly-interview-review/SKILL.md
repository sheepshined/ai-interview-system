---
name: weekly-interview-review
description: 跨多份报告的面试周复盘标准流程，按「拉趋势 → 定位最弱分类 → 读最近一次低分题的原始回答 → 给出下周 3 条复习计划 → 沉淀记忆」固定顺序执行。触发场景：用户提到复盘、总结最近几场表现、问最近/这周/上周表现如何、弱项在哪、该补什么、要复习计划——命中时必须先激活本技能，不要绕过技能直接拼工具。不用于单份报告的逐题解读。
allowed-tools: get_weakness_trend list_reports read_report_weak_points read_interview_record remember
metadata:
  version: "1.0"
  owner: assistant
  tags: 复盘 弱项 学习计划
---

# 面试周复盘标准流程

对当前用户的近几场面试做一次结构化复盘, 输出可直接执行的复习计划。
**硬约束**: 所有结论必须基于报告雷达与面试记录原文, 不得编造分数或题目。

## 步骤 (顺序固定)

1. **拉趋势**: 调用 `get_weakness_trend(limit=5)` 拿到逐份均分走势与按分类聚合的
   弱项 (`categories` 已按最弱排最前)。
   - 降级: 若 `found=false` (无报告), 直接告诉用户"还没有可复盘的面试记录",
     并建议先完成一场面试, 结束本流程, 不要继续后续步骤。

2. **定位最弱分类**: 取 `categories` 中 `avg_score` 最低且 `count>=1` 的分类作为
   本次复盘的焦点 (通常取前 1-2 个)。若并列, 优先 `low_count` 更高者。

3. **读原始回答**: 对焦点分类, 用 `list_reports` 找最近一份相关报告, 再调用
   `read_report_weak_points(report_id)` 取低分题; 需要逐题原话时用
   `read_interview_record(filename)` 引用原文片段。
   - 降级: 若拿不到具体报告, 仅基于趋势结论作答, 并说明缺少逐题证据。

4. **给出下周 3 条复习计划**: 每条必须能落地——写明"练什么 (具体知识点) +
   怎么练 (动作, 如重写一道题的答案/补一个离线实验) + 验收标准"。禁止泛泛而谈。

5. **沉淀记忆**: 用 `remember(kind="weakness_pattern", importance>=7,
   text=一句话弱项轨迹)` 写入长期记忆, 便于后续会话延续。只记稳定弱项轨迹,
   不记一次性任务细节。

## 输出

Markdown。先给结论 (最弱在哪、趋势如何), 再给依据 (报告 id / 记录文件名),
最后给 3 条复习计划。分数必须带出处。
