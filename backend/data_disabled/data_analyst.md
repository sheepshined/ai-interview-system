# 数据分析师面试题库

---
<!-- id:da_001 | category:SQL | difficulty:1 | difficulty_label:初级 -->
### Q: SQL 中 INNER JOIN / LEFT JOIN / RIGHT JOIN / FULL JOIN 的区别?
### A: INNER JOIN 只返回两表匹配的行; LEFT JOIN 返回左表所有行, 右表无匹配填 NULL; RIGHT JOIN 返回右表所有行, 左表无匹配填 NULL; FULL JOIN 返回两表所有行, 无匹配处填 NULL。JOIN 基于关联键匹配, 多表关联时注意表顺序和索引以避免笛卡尔积。LEFT JOIN 最常用, 用于"保留主表全部, 附带补充信息"。
### S:
- 正确描述了四种JOIN的返回范围
- 说明了无匹配时填NULL
- 提到基于关联键匹配
- 提到LEFT JOIN常用场景

---
<!-- id:da_002 | category:SQL | difficulty:2 | difficulty_label:中级 -->
### Q: 什么是窗口函数? 举例 ROW_NUMBER / RANK / SUM OVER 的用法。
### A: 窗口函数在不聚合行的情况下计算分组内"窗口"的值, 语法: 函数() OVER (PARTITION BY 列 ORDER BY 列)。ROW_NUMBER() 给分组内行编号(唯一); RANK() 分组内排名(并列跳号); SUM(列) OVER(PARTITION BY...) 累计求和不压缩行数。典型场景: 每个部门薪资Top3、累计销售额、同比环比。区别于 GROUP BY: 窗口函数保留明细行。
### S:
- 说明了窗口函数保留明细行的特点
- 写出了 OVER(PARTITION BY...ORDER BY...) 语法
- 区分了 ROW_NUMBER(唯一) 与 RANK(并列跳号)
- 提到典型业务场景(TopN/累计)

---
<!-- id:da_003 | category:Python | difficulty:2 | difficulty_label:中级 -->
### Q: 用 Pandas 如何做分组聚合? merge 和 concat 的区别?
### A: 分组聚合用 df.groupby('key')['col'].agg(['mean','sum']), 支持多函数多列。merge 是按关联键合并DataFrame(类似SQL JOIN), how='left'/'inner'; concat 是按行或按列拼接(类似UNION/列追加), axis=0行拼接axis=1列拼接。merge 处理"关联", concat 处理"堆叠"。还可透视 pivot_table 和 melt 长宽转换。
### S:
- 写出了 groupby+agg 分组聚合用法
- 区分了 merge(按键关联JOIN) 与 concat(按行/列堆叠)
- 提到 how/axis 参数
- 提到 pivot_table/melt

---
<!-- id:da_004 | category:统计 | difficulty:2 | difficulty_label:中级 -->
### Q: AB 测试如何判断结果是否显著? 提及 p 值和功效。
### A: AB 测试先定指标和最小样本量(基于期望提升幅度、显著性水平α通常0.05、功效1-β通常0.8)。跑满样本后用假设检验(比例用卡方/Z检验, 均值用t检验)算 p 值: p<α 拒绝原假设, 认为差异显著。功效(1-β)是"真实有差异时能检出"的概率, 功效不足会漏判。注意多变量时 Bonferroni 校正、辛普森悖论、peeking 提前停止。
### S:
- 提到设定显著性水平α(0.05)与功效(1-β,0.8)
- 提到最小样本量计算
- 解释了 p值<α 判显著
- 提到至少1个陷阱(辛普森/peeking/多重比较)

---
<!-- id:da_005 | category:可视化 | difficulty:1 | difficulty_label:初级 -->
### Q: 不同数据类型该用什么图表? 如何避免误导性可视化?
### A: 时序数据用折线; 类别比较用柱状(分类多时用条形); 占比用饼图(类别少)或堆叠柱; 分布用直方图/箱线; 关联用散点。避免误导: 坐标轴不从0起(夸大差异)、3D饼图、过小样本、色盲不友好配色、双轴误导。原则是"让数据说话", 标注来源和样本量。Python 用 matplotlib/seaborn/plotly。
### S:
- 给出至少4种数据类型对应的图表
- 提到坐标轴不从0起的误导
- 提到3D饼图/双轴等常见误导
- 提到标注来源样本量

---
<!-- id:da_006 | category:业务 | difficulty:2 | difficulty_label:中级 -->
### Q: 如何从0到1搭建一套业务指标体系? 以电商为例。
### A: 北极星指标定核心(电商如GMV), 向下拆解分层: 获客(新增/获客成本CAC)、激活(首单转化)、留存(DAU/MAU/留存率)、变现(ARPU/客单价)、推荐(K因子)。遵循 SMART 可量化、OSM(目标-策略-度量)分层。建立指标字典(口径/计算逻辑/数据源/负责人), 搭看板监控, 设阈值告警。注意虚荣指标(总注册数)与北极星区分。
### S:
- 提到北极星指标(GMV)
- 给出分层拆解(获客/激活/留存/变现/推荐)
- 提到指标字典(口径/负责人)
- 区分虚荣指标与北极星
