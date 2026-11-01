# 大模型应用开发工程师面试题库

---
<!-- id:llm_rag_001 | category:RAG | difficulty:1 | difficulty_label:初级 | type:scenario -->
### Q: 请简述什么是 RAG？它的核心目的是什么？
### SCENARIO: 候选人在简历中提到了熟悉大模型应用开发，面试官希望确认其对 RAG 基础概念的理解。
### A: 
为什么： RAG（Retrieval-Augmented Generation，检索增强生成）是一种将外部知识库与大语言模型（LLM）结合的技术架构。
如何解决/核心目的：
解决幻觉问题： 通过检索真实的外部文档作为上下文，约束模型生成，减少胡编乱造。
解决时效性问题： 无需重新训练模型，只需更新外部知识库即可让模型获取最新信息。
解决缺乏垂直领域知识： 弥补通用大模型在特定私有数据上的知识盲区。
数据安全与隐私： 数据保留在本地或私有库中，无需微调上传到公有云模型。
### S:
- 能准确说出 RAG 的全称及"检索+生成"的基本原理
- 能列举出 RAG 解决的至少两个核心痛点（如幻觉、时效性、私有数据）
- 理解 RAG 与微调（Fine-tuning）的区别，知道 RAG 不需要改变模型权重
### GOOD:
- 回答结构清晰，先定义后讲价值
- 能够结合业务场景（如企业知识库问答）举例说明 RAG 的必要性
### BAD:
- 将 RAG 等同于微调，认为 RAG 需要训练模型参数
- 只能说出定义，无法解释为什么要用 RAG（即不知道它解决了什么问题）
### FOLLOWUP:
- RAG 和微调（Fine-tuning）相比，各自的优缺点是什么？在什么场景下你会优先选择 RAG？
- RAG 的基本工作流程是怎样的？

---
<!-- id:llm_rag_002 | category:RAG | difficulty:2 | difficulty_label:中级 | type:scenario -->
### Q: 请详细描述 RAG 的标准工作流程，并解释 Naive RAG、Advanced RAG 和 Modular RAG 的区别。
### SCENARIO: 候选人已经理解了 RAG 的定义，面试官进一步考察其对 RAG 架构演进和具体实现流程的掌握程度。
### A: 
为什么： 不同的 RAG 架构对应着不同的工程复杂度和效果要求，从简单原型到工业级应用需要不同的设计。
如何解决/流程与分类：
标准流程：
索引阶段（Indexing）： 数据加载 -> 文本清洗 -> 分块（Chunking） -> 向量化（Embedding） -> 存入向量数据库。
检索阶段（Retrieval）： 用户提问 -> 问题向量化 -> 在向量库中相似度搜索 -> 召回相关 Chunk。
生成阶段（Generation）： 将召回的 Chunk 与原始问题拼接成 Prompt -> 输入 LLM -> 生成最终答案。
分类区别：
Naive RAG（朴素 RAG）： 最基础的"索引-检索-生成"三部曲，无额外优化，容易受噪声干扰。
Advanced RAG（高级 RAG）： 在 Naive 基础上增加了预检索（查询重写、扩展）和后检索（重排序 Rerank、过滤）优化策略，提升检索质量。
Modular RAG（模块化 RAG）： 将 RAG 流程解耦为独立模块（如路由模块、融合模块），支持灵活编排和替换组件（如引入 HyDE、多路召回），适应复杂场景。
### S:
- 清晰描述索引、检索、生成三个阶段的步骤
- 准确区分 Naive、Advanced、Modular 三种范式的核心差异
- 提到 Advanced RAG 中的关键优化点（如 Rerank、Query Rewrite）
### GOOD:
- 流程图式地口述整个过程，逻辑严密
- 能指出 Naive RAG 的局限性（如检索不准、上下文窗口限制），从而引出 Advanced/Modular 的必要性
### BAD:
- 混淆索引阶段和检索阶段的操作
- 不知道 Advanced RAG 具体"高级"在哪里，只是堆砌名词
### FOLLOWUP:
- 在 Advanced RAG 中，你常用哪些方法来优化检索效果？
- 什么是 HyDE（假设性文档嵌入）？它属于哪种 RAG 范式？

---
<!-- id:llm_rag_003 | category:RAG | difficulty:2 | difficulty_label:中级 | type:scenario -->
### Q: 在 RAG 系统中，如何评估检索效果？如果召回率低，你有哪些优化策略？
### SCENARIO: 项目上线后发现模型经常回答"我不知道"或者答非所问，面试官考察候选人的问题排查与优化能力。
### A: 
为什么： 检索是 RAG 的基石，"Garbage In, Garbage Out"，如果检索不到相关文档，生成端再强也无法给出正确答案。
如何解决/评估与优化：
评估指标：
Context Precision（上下文精确度）： 检索到的文档中有多少是真正相关的。
Context Recall（上下文召回率）： 所有相关文档中有多少被成功检索到了。
Faithfulness（忠实度）： 生成的答案是否完全基于检索到的上下文，有无幻觉。
Answer Relevancy（答案相关性）： 最终答案是否回答了用户的问题。
提升召回率的策略：
优化分块（Chunking）： 调整 Chunk 大小，使用语义分块或滑动窗口，避免关键信息被切断。
改进检索模型： 使用更高质量的 Embedding 模型，或结合关键词检索（混合检索 Hybrid Search）。
查询优化： 使用 Query Rewrite（查询重写）、Multi-query（多查询扩展）或 HyDE 技术，让查询向量更接近文档向量分布。
元数据过滤： 利用文档的元数据（如时间、类别）先进行硬过滤，缩小检索范围，提高精度。
### S:
- 列举出至少两个 RAG 评估指标（如 Recall, Precision, Faithfulness）
- 提供具体的提升召回率的技术手段（混合检索、Query 改写、分块优化等）
- 理解"检索"与"生成"评估维度的不同
### GOOD:
- 能够区分"检索质量"和"生成质量"的评估指标
- 提出的优化策略具有可操作性，且能解释原理（例如：为什么要用混合检索？因为向量检索擅长语义，关键词检索擅长专有名词）
### BAD:
- 只关注最终答案好不好，忽略了中间检索环节的评估
- 提出的方案过于笼统，如"换个更好的模型"，而没有具体的工程手段
### FOLLOWUP:
- 什么是 HyDE？它是如何帮助提升检索效果的？
- 在实际项目中，你是如何构建测试集来评估这些指标的？

---
<!-- id:llm_rag_004 | category:RAG | difficulty:3 | difficulty_label:高级 | type:scenario -->
### Q: 在处理长文档或复杂结构文档时，如何避免分块（Chunking）导致的信息丢失？请介绍 Parent Document Retriever 或类似的机制。
### SCENARIO: 业务场景中有很多长篇 PDF 报告或法律合同，直接切分后上下文破碎，导致模型理解错误。面试官考察高阶工程技巧。
### A: 
为什么： 固定长度分块会破坏段落完整性，导致代词指代不明或缺乏背景信息；但如果不分块，又超出 Embedding 模型或 LLM 的上下文限制。
如何解决/机制原理：
问题本质： 小 Chunk 利于精准匹配（高召回），但缺乏上下文（低精度/难理解）；大 Chunk context 丰富，但向量表示模糊（低召回）。
Parent Document Retriever（父文档检索器）：
原理： 将文档切分为较小的子块（Child Chunks）用于建立索引和检索，但在数据库中保留其所属的较大父块（Parent Chunk）或全文映射关系。
流程： 检索时匹配到小的 Child Chunk -> 根据 ID 找到对应的 Parent Chunk -> 将内容更丰富的 Parent Chunk 送入 LLM。
优势： 兼顾了检索的颗粒度（细粒度匹配）和生成的上下文完整性（粗粒度输入）。
其他方案：
滑动窗口重叠（Overlap）： 相邻 Chunk 之间保留部分重叠文本。
句子窗口检索（Sentence Window Retrieval）： 索引单个句子，检索后扩展前后 N 个句子作为上下文。
自动合并检索（Auto-merging Retriever）： 类似树状结构，检索叶子节点，若多个叶子节点命中同一父节点，则合并返回父节点。
### S:
- 深刻理解分块大小对检索和生成的矛盾影响
- 准确解释 Parent Document Retriever 的工作原理（小块检索，大块返回）
- 了解其他替代方案（如 Overlap, Sentence Window）
### GOOD:
- 能清晰阐述"检索粒度"与"上下文粒度"的权衡（Trade-off）
- 结合 LlamaIndex 或 LangChain 的具体实现逻辑进行解释
### BAD:
- 认为只要把 Chunk 设得越大越好，忽略了向量检索的语义稀释问题
- 不知道如何在工程上实现"小块索引，大块返回"的映射关系
### FOLLOWUP:
- 除了 Parent Document，LlamaIndex 还有哪些特殊的索引类型（如 Summary Index, Tree Index）？它们分别适用什么场景？
- 对于包含表格和图片的 PDF，你会如何处理？

---
<!-- id:llm_rag_005 | category:RAG | difficulty:2 | difficulty_label:中级 | type:scenario -->
### Q: 请介绍常见的向量数据库，并在选型时你会考虑哪些因素？
### SCENARIO: 团队准备搭建 RAG 系统基础设施，需要选择合适的向量存储方案，面试官考察技术选型能力。
### A: 
为什么： 向量数据库是 RAG 系统的核心组件，直接影响检索速度、并发能力和运维成本。
如何解决/选型分析：
常见向量数据库特点：
Milvus / Zilliz： 专为大规模向量设计，分布式架构，性能强，适合生产环境，但部署运维相对复杂。
Elasticsearch (ES)： 传统搜索引擎，现支持向量检索（kNN），优势在于可同时做关键词+向量混合检索，适合已有 ES 基建的团队。
Pinecone / Weaviate / Qdrant： 云原生或专用向量库，API 友好，开箱即用，Qdrant 基于 Rust 性能好，Weaviate 支持 GraphQL。
Chroma / FAISS： 轻量级，常用于本地开发、原型验证或嵌入式场景，不适合大规模高并发生产。
pgvector： PostgreSQL 插件，适合数据量不大、希望复用现有 PG 数据库的场景，简化架构。
选型考量因素：
数据规模： 百万级 vs 亿级向量。
查询延迟与吞吐（QPS）： 实时性要求。
功能需求： 是否需要混合检索、元数据过滤、动态更新。
运维成本： 自托管 vs 云服务，团队技术栈熟悉度。
生态集成： 是否与 LangChain/LlamaIndex 无缝对接。
### S:
- 列举出至少 3-4 种主流向量数据库及其核心特点
- 能从数据量、性能、运维、功能等维度阐述选型逻辑
- 区分"开发/原型阶段"与"生产环境"的不同选择
### GOOD:
- 不盲目推崇某一种数据库，而是根据场景（Scenario-based）给出建议
- 提到混合检索（Hybrid Search）的重要性，并指出哪些库原生支持较好（如 ES, Weaviate, Milvus）
### BAD:
- 只知道名字，说不出区别，或者认为所有向量库都一样
- 在生产环境推荐 Chroma 或纯内存 FAISS，忽略持久化和并发问题
### FOLLOWUP:
- 如果我们的数据需要频繁更新（增删改），这对向量库选型有什么影响？
- 如何实现向量检索和关键词检索的融合（Hybrid Search）？权重如何分配？

---
<!-- id:llm_rag_006 | category:RAG | difficulty:2 | difficulty_label:中级 | type:scenario -->
### Q: 在 RAG 系统中，文本分块（Chunking）有哪些常见策略？如何避免分块导致语义割裂？
### SCENARIO: 候选人在搭建 RAG 知识库时，发现直接按固定字符数切分文档效果很差，面试官考察其对数据预处理细节的掌握。
### A: 
为什么： 分块策略直接决定了向量检索的粒度和上下文完整性。固定长度切分容易切断句子或段落，导致代词指代不明、语义缺失；而块太大则会导致向量表示模糊，降低检索精度。
如何解决/常见策略：
固定大小分块（Fixed-size Chunking）： 按字符数或 Token 数切分，通常配合重叠（Overlap）机制，保留相邻块的边界信息，缓解割裂问题。
基于语义的分块（Semantic Chunking）： 利用 NLP 工具或 Embedding 模型计算句子间的相似度，在语义转折点进行切分，保证每个块的主题一致性。
递归字符分块（Recursive Character Splitting）： LangChain 默认策略，按段落、句子、单词等层级递归切分，尽量保持自然语言结构的完整性。
文档结构分块： 利用 PDF/Markdown 的标题、段落、表格等天然结构进行切分。
高级检索器配合（如 Parent Document Retriever）： 索引小块（Child Chunks）用于精准匹配，检索后返回其所属的大块（Parent Chunk）给 LLM，兼顾检索精度与上下文完整性。
### S:
- 列举出至少 3 种分块策略（固定大小、语义分块、递归分块等）
- 解释 Overlap（重叠）机制的作用
- 理解"检索粒度"与"上下文粒度"的矛盾，并提出解决方案（如 Parent Document）
### GOOD:
- 能结合具体文档类型（如 PDF、代码、法律合同）推荐合适的分块策略
- 清晰阐述小块索引、大块返回的工程实现逻辑
### BAD:
- 认为分块越大越好，忽略向量检索的语义稀释问题
- 只知道固定长度切分，不了解语义分块或重叠机制
### FOLLOWUP:
- 对于包含大量表格的 PDF 文档，你会如何进行分块和索引？
- 如何评估当前分块策略是否合理？有哪些量化指标？

---
<!-- id:llm_rag_007 | category:RAG | difficulty:3 | difficulty_label:高级 | type:scenario -->
### Q: 请解释 Self-RAG 的核心思想及其工作流程。它与传统 RAG 相比有什么优势？
### SCENARIO: 团队发现传统 RAG 经常检索到无关文档，或者在不需要检索时强行检索导致回答生硬，面试官考察候选人对前沿 RAG 架构的了解。
### A: 
为什么： 传统 RAG 是"盲目检索"，无论用户问题是否需要外部知识都会触发检索，且无法判断检索到的文档是否真正相关，容易导致噪声引入或回答不自然。
如何解决/Self-RAG 原理：
核心思想： 让 LLM 学会自我反思（Self-Reflection），通过生成特殊的"反思令牌"（Reflection Tokens）来动态控制检索行为并评估生成质量。
工作流程：
检索判定（Retrieve）： 模型先判断当前问题是否需要检索外部知识（输出 [Retrieval] 或 [No Retrieval]）。
相关性评估（IsRel）： 若触发检索，模型评估召回的文档是否与问题相关（输出 [Relevant] / [Irrelevant]）。
生成与支撑度评估（IsSup）： 基于相关文档生成答案，并检查答案中的每个陈述是否有文档支撑（输出 [Supported] / [Unsupported]）。
效用评估（IsUse）： 评估最终答案是否完整回答了用户问题。
优势：
按需检索： 避免不必要的检索，提升效率和回答流畅度。
质量可控： 通过反思令牌过滤无关文档和幻觉内容，显著提升事实准确性。
自适应： 无需复杂的外部规则引擎，模型自身具备路由和评估能力。
### S:
- 准确说出 Self-RAG 的四个核心反思令牌（Retrieve, IsRel, IsSup, IsUse）
- 解释 Self-RAG 如何实现"按需检索"和"自我评估"
- 对比传统 RAG，指出 Self-RAG 在准确性和效率上的提升
### GOOD:
- 能清晰描述反思令牌在推理阶段的具体作用机制
- 提到 Self-RAG 需要微调（Fine-tuning）基座模型以学会生成反思令牌
### BAD:
- 将 Self-RAG 等同于简单的 Re-rank 或 Query Rewrite
- 不知道 Self-RAG 需要对模型进行专门训练/微调
### FOLLOWUP:
- Self-RAG 的反思令牌是如何训练出来的？需要什么样的数据集？
- 在实际工程中，Self-RAG 的推理延迟会比传统 RAG 高吗？如何优化？

---
<!-- id:llm_rag_008 | category:RAG | difficulty:3 | difficulty_label:高级 | type:scenario -->
### Q: 什么是 RAG Fusion？它是如何解决单一查询检索不全的问题的？
### SCENARIO: 用户提问比较模糊或包含多个意图时，单次向量检索往往只能召回部分相关信息，面试官考察多路召回与融合策略。
### A: 
为什么： 用户的原始查询（Query）可能表述不清、过于宽泛或包含多个子问题，单一查询生成的向量在向量空间中只能覆盖局部区域，导致召回不全（Low Recall）。
如何解决/RAG Fusion 流程：
查询扩展（Query Expansion）： 利用 LLM 将原始查询改写为多个不同视角、不同表述的子查询（Multi-Query）。例如，将"如何减肥？"扩展为"饮食控制方法"、"运动燃脂技巧"、"生活习惯调整"等。
并行检索（Parallel Retrieval）： 对原始查询和所有扩展查询分别进行向量检索，得到多组候选文档列表。
结果融合与重排（Fusion & Rerank）：
去重： 合并多路召回结果，去除重复文档。
reciprocal rank fusion (RRF) 或加权打分： 根据文档在各路检索中的排名进行综合打分，优先保留被多次命中或排名靠前的文档。
可选 Rerank： 使用 Cross-Encoder 对融合后的结果进行精排。
优势： 显著提升召回率（Recall），覆盖用户意图的多个维度，降低因单一查询表述偏差导致的漏检风险。
### S:
- 清晰描述 RAG Fusion 的三个步骤：查询扩展、并行检索、结果融合
- 解释 Multi-Query 的作用原理
- 提到结果融合时的去重和排序策略（如 RRF）
### GOOD:
- 能举例说明什么样的问题适合用 RAG Fusion（如复合型问题、模糊查询）
- 了解 RRF（Reciprocal Rank Fusion）算法的基本逻辑
### BAD:
- 将 RAG Fusion 与 HyDE 混淆
- 只提到多路检索，忽略了结果融合与去重的关键步骤
### FOLLOWUP:
- RAG Fusion 会增加系统的延迟和成本吗？如何在效果和性能之间做权衡？
- 除了 LLM 生成多查询，还有其他查询扩展的方法吗？

---
<!-- id:llm_rag_009 | category:RAG | difficulty:2 | difficulty_label:中级 | type:scenario -->
### Q: RAG 系统的评估体系通常包含哪些维度？请解释 RAGAS 框架中的核心指标。
### SCENARIO: 项目上线后需要量化 RAG 的效果以便持续迭代，面试官考察候选人对 RAG 评估方法论的掌握。
### A: 
为什么： RAG 系统涉及检索和生成两个阶段，单纯评估最终答案无法定位问题根源（是检索没找对，还是生成没用好）。需要细粒度的评估指标来指导优化。
如何解决/RAGAS 核心指标：
检索阶段指标：
Context Precision（上下文精确度）： 检索到的上下文中，真正相关的比例。衡量检索结果的"纯度"，避免噪声干扰 LLM。
Context Recall（上下文召回率）： 标准答案中的关键信息，有多少能在检索到的上下文中找到。衡量检索是否"找全"了必要信息。
生成阶段指标：
Faithfulness（忠实度/无幻觉）： 生成的答案是否完全基于检索到的上下文，有无编造事实。这是 RAG 最核心的安全指标。
Answer Relevancy（答案相关性）： 最终答案是否直接、完整地回答了用户的问题，有无答非所问或冗余信息。
评估方法：
人工评估： 构建 Golden Dataset（标准问答对），人工打分。
LLM-as-a-Judge： 使用强模型（如 GPT-4）自动评估上述指标，适合大规模自动化测试。
### S:
- 准确列出 RAGAS 的四大核心指标（Context Precision, Context Recall, Faithfulness, Answer Relevancy）
- 区分"检索阶段"和"生成阶段"的评估维度
- 解释 Faithfulness 为何是 RAG 区别于普通 LLM 的关键指标
### GOOD:
- 能清晰解释每个指标的计算逻辑或业务含义
- 提到 LLM-as-a-Judge 的局限性（如偏见、成本）及人工评估的必要性
### BAD:
- 只用 BLEU/ROUGE 等传统 NLP 指标评估 RAG，忽略事实性和检索质量
- 混淆 Context Precision 和 Answer Relevancy 的概念
### FOLLOWUP:
- 在没有标准答案（Golden Answer）的情况下，如何评估 RAG 的效果？
- 如何构建一个高质量的 RAG 评估测试集？

---
<!-- id:llm_rag_010 | category:RAG | difficulty:3 | difficulty_label:高级 | type:scenario -->
### Q: 如何让 RAG 系统支持多模态数据（如图片、表格、PDF 中的图表）？请简述 Multi-modal RAG 的实现思路。
### SCENARIO: 业务文档中包含大量产品截图、财务表格和流程图，纯文本 RAG 无法处理这些信息，面试官考察多模态 RAG 的架构设计能力。
### A: 
为什么： 现实世界的企业知识大量存在于非文本模态中（图片、表格、图表），纯文本 Embedding 无法捕捉视觉和结构化信息，导致这部分知识在 RAG 中"丢失"。
如何解决/Multi-modal RAG 实现思路：
方案一：统一向量空间（Unified Embedding Space）
使用多模态 Embedding 模型（如 CLIP, OpenCLIP, Jina CLIP）将文本和图片映射到同一向量空间。
检索时，无论是文本查图片，还是图片查文本，都在同一空间计算相似度。
生成时，将检索到的图片 URL/Base64 和文本一起传给多模态 LLM（如 GPT-4V, Gemini）。
方案二：图转文 + 传统 RAG（Captioning/OCR + Text RAG）
利用 VLM（视觉语言模型）或 OCR 工具提取图片/表格中的文字和语义描述（Caption）。
将提取的文本与原文档关联，存入传统文本向量库。
检索时走文本流程，生成时将原图和相关文本一起提供给 LLM。
优势：兼容现有文本 RAG 基建；劣势：依赖 OCR/Caption 质量，可能丢失视觉细节。
方案三：结构化解析（针对表格/PDF）
使用专用工具（如 Unstructured, LlamaParse, Camelot）解析 PDF 中的表格为 HTML/Markdown/JSON。
将结构化数据单独索引，或转换为自然语言描述后索引。
检索时识别查询意图，路由到表格库或文本库。
关键挑战： 多模态 Embedding 模型选型、图文对齐精度、多模态 LLM 的上下文窗口限制、存储成本。
### S:
- 提出至少两种多模态 RAG 的实现方案（统一向量空间 vs 图转文）
- 针对表格/PDF 提出专门的结构化解析策略
- 意识到多模态 RAG 对 LLM 的要求（需支持 Vision 输入）
### GOOD:
- 能根据业务场景（如重视觉细节 vs 重数据查询）推荐合适方案
- 提到具体的工具链（如 LlamaParse, CLIP, GPT-4V）
### BAD:
- 认为只需把图片转成文字就能解决所有问题，忽略图表趋势、布局等视觉信息
- 不知道多模态 Embedding 模型的存在，试图用文本模型硬编码图片
### FOLLOWUP:
- 在多模态 RAG 中，如何评估图片检索的准确性？
- 如果文档中既有文本又有图表，如何做混合检索和结果融合？

---
<!-- id:llm_transformer_001 | category:Transformer | difficulty:2 | difficulty_label:中级 | type:scenario -->
### Q: Transformer 的 Encoder 有哪些子层？为什么要设计残差连接和层归一化？
### SCENARIO: 面试官让候选人在白板上画出 Encoder 的内部结构，并追问残差连接的设计动机。
### A: 
为什么： 深层网络面临梯度消失与性能退化问题，原文堆叠 6 层 Encoder，必须依靠残差结构保证可训练性。
结构与解决：
子层一：多头自注意力机制（Multi-Head Self-Attention），建模序列中任意位置的依赖关系。
子层二：位置前馈网络（FFN），两层全连接 + 激活函数，各位置共享参数，提供非线性变换。
残差 + 层归一化： 每个子层都有残差连接，输出 = LayerNorm(x + Sublayer(x))。
残差的意义： 梯度可直接回传到浅层，缓解梯度消失；网络只需学习残差（差异）映射，优化更容易；防止深层网络退化。
### S:
- 准确说出两个子层及残差+LN 的输出公式
- 解释残差连接对梯度消失/网络退化问题的作用
- 知道 FFN 在各位置间参数共享
### GOOD:
- 能写出 output = LayerNorm(x + Sublayer(x))，并区分 Post-LN 与 Pre-LN
- 理解残差让网络学习"差异映射"而非完整映射
### BAD:
- 只提注意力，遗漏 FFN 子层
- 认为残差连接只是为了加快收敛，说不出退化问题
### FOLLOWUP:
- Transformer 为什么使用 LN 而不是 BN？
- Transformer 的参数和计算量主要集中在哪些部分？

---
<!-- id:llm_transformer_002 | category:Transformer | difficulty:3 | difficulty_label:高级 | type:scenario -->
### Q: 请写出缩放点积注意力公式，并解释：为什么用点积而不是加法？为什么要除以 √d_k？padding mask 如何处理？
### SCENARIO: 面试官给出公式 Attention(Q,K,V)=Softmax(QK^T/√d_k)V，逐一追问每个设计细节背后的原因。
### A: 
为什么： 注意力的本质是按 Q、K 相似度对 V 加权求和，相似度的计算方式与数值稳定性直接决定效率和效果。
各设计点解释：
点积 vs 加法： 加法式（Bahdanau）注意力需要额外的单隐藏层网络计算分数；点积可用高度优化的矩阵乘法实现，更快、更省空间。但当 d_k 较大时点积数值会变大，必须缩放。
为什么 scaled： d_k 较大时内积结果绝对值大，会把 softmax 推入梯度极小的饱和区，导致梯度消失；除以 √d_k 将内积方差拉回 1 左右，稳定梯度与训练。
padding mask： 在 score 矩阵的 padding 位置填充极小值（-1e9 / -inf），使 softmax 后这些位置权重趋近 0，避免 pad token 参与注意力。
### S:
- 正确写出公式并说明 Q、K、V 各符号含义
- 解释 scaled 的真正原因（softmax 饱和、梯度消失）
- 说明 padding mask 的填充方式及其对 softmax 的影响
### GOOD:
- 能从方差角度解释：点积方差为 d_k，故除以 √d_k
- 区分 padding mask 与 causal mask 的不同使用场景
### BAD:
- 只答"防止数值过大"，说不出与 softmax 梯度的关系
- 混淆 padding mask 和 causal mask
### FOLLOWUP:
- Q、K、V 的维度必须相同吗？（Q、K 需投影到相同 d_k 才能点积；V 的维度 d_v 可以不同）
- 为什么 Q 和 K 要用不同的投影矩阵，而不是共用同一个？

---
<!-- id:llm_transformer_003 | category:Transformer | difficulty:2 | difficulty_label:中级 | type:scenario -->
### Q: Decoder 的自注意力和 Encoder 有何区别？为什么需要 sequence mask？Encoder 和 Decoder 之间如何交互？
### SCENARIO: 面试官确认候选人了解 Transformer 整体架构后，深入考察自回归生成机制的细节。
### A: 
为什么： 解码器逐 token 生成，训练时必须防止"看到未来答案"（信息泄漏），否则训练失效、无法泛化。
区别与交互：
Encoder 自注意力： 双向可见，能关注整个序列（仅加 padding mask）。
Decoder 自注意力： 在 padding mask 之上叠加因果掩码（Causal / Look-ahead Mask），位置 i 只能看到 ≤ i 的位置，保证自回归特性，防止未来信息泄漏。
交互方式：交叉注意力（Cross-Attention / Encoder-Decoder Attention）：Query 来自解码器上一层的输出，Key 和 Value 来自编码器的输出，解码器借此关注源序列的相关部分。
掩码的意义： 保证训练与推理行为一致，维持自回归属性（Autoregressive Property）。
### S:
- 准确说出 Decoder 自注意力比 Encoder 多了因果掩码
- 准确说出 Cross-Attention 中 Q/K/V 的来源
- 解释掩码与自回归生成的关系
### GOOD:
- 能说明因果掩码的实现方式（上三角置 -inf）
- 理解 Decoder 训练时靠因果掩码仍可一次性并行计算整条序列
### BAD:
- 认为 Decoder 也是双向注意力
- 说 Cross-Attention 的 Q 来自编码器
### FOLLOWUP:
- Decoder 能并行化吗？训练和推理阶段有何区别？
- 为什么 GPT 只用了 Decoder 部分也能工作？

---
<!-- id:llm_transformer_004 | category:Transformer | difficulty:2 | difficulty_label:中级 | type:scenario -->
### Q: Transformer 为什么使用 LayerNorm 而不是 BatchNorm？它的并行性体现在哪里？
### SCENARIO: 候选人提到 Transformer 训练快、适合长序列，面试官追问归一化细节与并行计算原理。
### A: 
为什么： 文本是变长序列数据，BN 依赖 batch 统计量的假设在 NLP 场景不成立。
LN vs BN：
LN 按单个样本、在特征维度独立归一化，不依赖 batch size；BN 在 batch 维度算统计量，小 batch 或变长序列下统计不稳定。
序列数据各位置长度不一，BN 无法对齐；LN 对每个 token 一致处理，更适合序列建模。
LN 训练与推理行为一致；BN 推理需依赖滑动平均统计量，存在 train/inference gap。
并行性：
Encoder： 无时间递归，整条序列同时参与注意力和 FFN 计算，可完全并行，这是相对 RNN 顺序计算的核心优势。
Decoder： 训练时借助因果掩码可整条目标序列一次并行计算；推理时自回归逐 token 生成，无法并行（可用 KV Cache 加速）。
### S:
- 说明 LN 与 BN 的归一化维度差异及 LN 适合序列数据的原因
- 区分 Decoder"训练可并行、推理串行"
- 提到 RNN 因时间递归无法并行的对比
### GOOD:
- 能提到 Pre-LN 比 Post-LN 训练更稳定
- 能延伸到 KV Cache 等推理加速手段
### BAD:
- 认为 Decoder 推理也能完全并行
- 只说"LN 更好"但讲不出维度差异
### FOLLOWUP:
- Pre-LN 和 Post-LN 的区别是什么？
- KV Cache 的原理是什么？解决了什么问题？

---
<!-- id:llm_transformer_005 | category:Transformer | difficulty:3 | difficulty_label:高级 | type:scenario -->
### Q: Transformer 为什么使用多头注意力而不是单头？Q 和 K 为什么要用不同的投影矩阵？
### SCENARIO: 面试官展示原文多头注意力结构图与消融实验表格，考察候选人对设计动机的理解深度。
### A: 
为什么： 单头注意力会把多种关系信息"平均掉"；多头类比 CNN 的多卷积核，捕获不同子空间的特征。
多头的作用：
将 Q、K、V 通过不同矩阵投影到 h 个子空间，每个头独立做注意力后拼接再经 W_O 输出；使模型能在不同位置共同关注来自不同表示子空间的信息。
单头会平均化，难以同时捕获语法、语义等多种关系；原文消融实验表明减少头数性能下降。
Q/K 用不同矩阵：
若 Q、K 共用同一投影，score 矩阵将对称，且向量与自身点积最大，注意力会过度集中在自身位置，表达力受限。
不同投影允许非对称的注意关系（i 关注 j 的程度 ≠ j 关注 i 的程度），显著增强表达能力。
### S:
- 解释多头的"子空间"作用及与 CNN 多通道的类比
- 引用原文消融实验的结论
- 说明 Q/K 相同带来的对称性与自关注问题
### GOOD:
- 能完整写出多头拼接 + 输出投影的流程
- 理解 W_Q/W_K/W_V 线性变换的本质是增强表达力、投影到不同子空间
### BAD:
- 认为多头只是为了并行加速
- 无法解释 Q、K 为何不能共享矩阵
### FOLLOWUP:
- 头数越多越好吗？头数如何选择？
- Transformer 的计算量主要集中在哪里？（注意力 O(n²) 矩阵运算 + FFN 线性层）

---
<!-- id:llm_transformer_006 | category:Transformer | difficulty:3 | difficulty_label:高级 | type:scenario -->
### Q: Transformer 有哪些优缺点？相比 RNN/LSTM 有何差异？如何处理超长文本？
### SCENARIO: 业务需要对上万 token 的长文档建模，面试官考察候选人对 Transformer 局限性的认识与长文本方案储备。
### A: 
为什么： 自注意力 O(n²) 的复杂度是长文本的核心瓶颈，必须通过稀疏/线性注意力或工程手段突破。
优缺点与对比：
优点： 并行处理、训练效率高；自注意力直接建模任意距离依赖，路径长度 O(1)，优于 RNN 的 O(n)；模块化易扩展；多任务 SOTA。
缺点： 时间与显存复杂度 O(n²)，对超长序列不友好；本身无递归/卷积，需位置编码注入位置信息；依赖大规模预训练数据。
与 RNN/LSTM 对比： 并行性（并行 vs 串行）；长依赖路径 O(1) vs O(n)（LSTM 靠门控缓解梯度消失但仍串行）；复杂度 O(n²d) vs O(nd²)。
超长文本方案：
截断/分块（Chunking）、滑动窗口注意力。
层次化注意力（句子级 -> 文档级）。
稀疏注意力： Longformer（局部窗口 + 全局注意力）、BigBird，复杂度降至 O(n)。
低秩/近似： Reformer 的 LSH 注意力、Performer 的线性注意力。
工程优化： KV Cache、FlashAttention；位置外推方法（RoPE、位置插值、ALiBi）。
### S:
- 准确说出优缺点与复杂度对比
- 列举至少 3 种长文本方案并说明原理
- 区分"模型结构改进"与"工程优化"两类方案
### GOOD:
- 能说明各长文本方案的复杂度变化（O(n²)->O(n)）
- 能结合业务给出组合方案（如分块+检索、长窗口模型）
### BAD:
- 只说"换更长上下文的模型"，没有具体方法
- 误以为 LSTM 比 Transformer 更擅长长文本
### FOLLOWUP:
- FlashAttention 的原理是什么？它优化的是计算量还是显存 IO？
- 位置编码有哪些类型？RoPE 相比绝对位置编码的优势？

---
<!-- id:llm_transformer_007 | category:Transformer | difficulty:2 | difficulty_label:中级 | type:scenario -->
### Q: 深度学习中常见的注意力机制有哪些？请系统梳理。
### SCENARIO: 面试收尾阶段，面试官让候选人系统梳理注意力家族，考察知识广度与分类能力。
### A: 
为什么： 注意力从 seq2seq 的辅助机制发展为通用建模组件，系统梳理有助于在不同任务中正确选型。
梳理：
Soft Attention： Bahdanau（加性）、Luong（乘性），可微、对所有位置计算权重。
Hard Attention： 采样离散位置，需强化学习训练，不可直接反向传播。
Self-Attention： 缩放点积、多头，Transformer 的核心。
Cross-Attention： 两条序列间交互，如 Encoder-Decoder 注意力、视觉问答。
层次化 / 局部 / 滑动窗口注意力： 面向长文本的结构设计。
图注意力（GAT）： 图结构数据的邻居聚合。
卷积注意力： SE-Net（通道注意力）、CBAM（通道+空间）。
其他变体： 时间注意力、Dual Attention、残差注意力、多尺度注意力、Co-Attention、自适应注意力等。
Transformers 家族： BERT（双向 Encoder）、GPT（单向 Decoder）等。
### S:
- 按 soft/hard、self/cross、面向结构等维度分类
- 正确对应代表模型（Bahdanau、Luong、SE-Net、GAT、BERT/GPT）
- 能说明各类注意力的适用场景
### GOOD:
- 有清晰的分类框架，而非罗列名词
- 能把注意力机制与具体任务（翻译、图像、图学习）关联
### BAD:
- 只知道 self-attention，把注意力等同于 Transformer
- 混淆 Cross-Attention 与 Self-Attention 的概念
### FOLLOWUP:
- Cross-Attention 和 Self-Attention 的区别是什么？请举例说明。
- 你在项目中用过哪种注意力变体？为什么选择它？

---
<!-- id:llm_transformer_008 | category:Transformer | difficulty:3 | difficulty_label:高级 | type:scenario -->
### Q: 在构建 AI Agent 时，为什么 KV-Cache 命中率是决定延迟和成本的关键指标？如何通过上下文设计提升 KV-Cache 命中率？
### SCENARIO: 团队开发的 Agent 在多轮交互中响应越来越慢、Token 成本飙升，面试官考察候选人对底层推理优化与上下文编排的理解。
### A: 
为什么： LLM 是自回归模型，只要有一个 token 变动，其后所有 token 的 KV-Cache 就会失效（Cache Miss），需要重新计算。Agent 每轮上下文都在增长，若 prompt 前缀不稳定，会导致缓存几乎无法复用，极大增加计算延迟和 API 成本。
如何解决/提升策略：
保持 Prompt 前缀绝对稳定： 将系统指令（System Prompt）、固定工具定义等不变内容放在最前面，确保多轮对话中前缀完全一致，最大化 Cache Hit。
确定性序列化： 上下文只能追加，避免修改历史动作或观测结果；确保代码执行过程、JSON 对象键的顺序等具有确定性，防止因序列化差异破坏缓存。
显式缓存断点： 部分框架不支持自动增量缓存，需手动在上下文中插入缓存断点，且断点应包含在系统提示词尾部。
路由一致性： 使用 vLLM 等框架时，开启 prefix caching，并通过 session ID 将同一会话的请求路由到同一 worker，避免跨节点缓存失效。
### S:
- 理解 KV-Cache 失效机制（前缀任一 token 变动导致后续全部重算）
- 提出至少 2 种提升命中率的具体手段（前缀稳定、确定性序列化、路由一致）
- 知道输入输出 token 比例对缓存效率的影响（如 Manus 约 100:1）
### GOOD:
- 能从"前缀匹配"角度解释为什么动态插入工具或打乱顺序会致命
- 提到 session affinity / 路由到同一 worker 的工程实践
### BAD:
- 认为 KV-Cache 只是模型内部的事，与应用层上下文编排无关
- 建议在每轮对话中动态调整 System Prompt 或工具列表
### FOLLOWUP:
- 如果必须动态加载工具，如何在不破坏 KV-Cache 的前提下实现？
- prefix caching 在 vLLM 中的实现原理是什么？

---
<!-- id:llm_skills_001 | category:Skills | difficulty:2 | difficulty_label:中级 | type:scenario -->
### Q: 请清晰区分 Prompt、Agent、Agent Skills、MCP、Rules 和 Memory 这六个常被混淆的概念，并说明它们各自的关注点。
### SCENARIO: 候选人在简历中写了"基于 Agent 开发"，面试官让其系统梳理 Agent 生态中的核心概念边界，考察基础认知是否扎实。
### A: 
为什么： 这些概念分别对应 AI 应用的不同抽象层级，混用会导致架构设计混乱、复用性差。理清边界是工程化落地的前提。
各概念关注点与定义：
Prompt（提示词）： 关注"说什么"。一次性输入文本/指令，用完即走，不可复用。
Agent（智能体）： 关注"谁来做"。一个正在运行的 AI 执行实例。关键误区纠正： Agent 本质像进程/线程，任务结束即销毁，不可复用；真正被复用的是 Agent 的配置（Prompt、Skills、Rules 等）。
Agent Skills（技能）： 关注"怎么做"。可复用的工作方法模块，跨任务、跨会话通用，教 AI 处理某一类特定问题（沉淀下来的 SOP）。
MCP（模型上下文协议）： 关注"用什么工具"。外部工具和数据访问的协议，负责连接外部世界。
Rules（规则）： 关注"不能做什么"。全局行为约束，始终生效，像法律底线。
Memory（记忆）： 关注"记住什么"。负责存储长期状态和信息。
一句话总结： Prompt 是临时的，Agent 是干活的苦力（用完就换），Skills 才是沉淀下来的 SOP。
### S:
- 准确说出 6 个概念各自的"关注点"关键词
- 纠正"Agent 可复用"的常见误区，指出真正复用的是配置
- 明确 Skills 的本质是"可复用的 SOP/工作方法模块"
### GOOD:
- 能用"进程 vs 配置"的类比解释 Agent 的不可复用性
- 清晰区分 Skills（怎么做）与 MCP（用什么工具）、Rules（不能做什么）的边界
### BAD:
- 把 Prompt 和 Skills 混为一谈，认为写个好 prompt 就等于有了 skill
- 认为 Agent 实例本身可以跨任务复用
### FOLLOWUP:
- 如果一个需求既要调用外部 API 又要遵循固定流程，应该用 MCP 还是 Skills？如何配合？
- Rules 和 Skills 都会影响模型行为，它们的优先级和生效范围有何不同？

---
<!-- id:llm_skills_002 | category:Skills | difficulty:2 | difficulty_label:中级 | type:scenario -->
### Q: Agent Skills 的核心价值是什么？为什么说它"改变的是 AI 的做事方式而非智商"？在工程化项目中它解决了什么问题？
### SCENARIO: 团队发现同样的 prompt 有时产出专业级代码、有时产出简陋 demo，效果不稳定，面试官考察候选人对 Skills 工程化价值的理解。
### A: 
为什么： 简单 Demo 靠"灵光一现"即可，但真实项目需要日复一日处理复杂业务逻辑，最在意的是稳定性而非偶发的高质量。纯 Prompt 无法保证每次都用同一套章法办事。
核心价值与原理：
本质是"规约"而非"教学"： Skill 不手把手教 AI 写具体代码或灌输语法，而是约定做事方式。例如前端设计 Skill 告诉 AI"你必须像资深设计师那样思考，考虑视觉层级、留白、现代 UI 审美标准"——它改变的是 AI 的做事方式/思维框架，而非提升其底层智商。
三大工程价值：
标准化： 让 AI 处理同类任务时有一套固定章法，不靠运气。
减少幻觉： 通过明确步骤和约束，告诉 AI 哪些判断不能糊弄、哪些优先级最高。
可复用： 在一个项目打磨好的"前端设计 Skill""代码审查 Skill"可直接搬到下一个项目。
能力升级路径： 把人类工作经验从一次性 Prompt，升级为可组合、可复用、可长期使用的能力模块。
### S:
- 点明 Skills 解决的核心痛点是"稳定性"而非"灵光一现"
- 解释 Skill 是"规约/做事方式"而非"具体代码教学"
- 列出标准化、减少幻觉、可复用三大价值
### GOOD:
- 能用 To-Do List 案例对比说明：同样 prompt，加前端设计 Skill 后界面从"能用"变"专业"
- 理解 Skills 是把经验沉淀为可组合的能力模块
### BAD:
- 认为 Skill 就是更长的 prompt 或代码模板
- 只谈"让 AI 更聪明"，说不出稳定性和复用性的工程意义
### FOLLOWUP:
- 如何评估一个 Skill 是否设计得好？有哪些衡量标准？
- Skills 和 RAG 的知识库有什么本质区别？

---
<!-- id:llm_skills_003 | category:Skills | difficulty:1 | difficulty_label:初级 | type:scenario -->
### Q: 在实际项目中如何获取和使用 Agent Skills？是否必须从零编写？请介绍主流的 Skills 资源生态。
### SCENARIO: 候选人表示想在自己的项目引入 Skills，但担心编写成本高，面试官考察其对社区生态的了解和落地务实程度。
### A: 
为什么： 绝大多数场景不需要从零写 Skills，社区生态已非常成熟，直接复用现成技能可大幅降低落地成本。
如何解决/资源生态：
无需从零编写： 好消息是绝大多数时候根本不需要自己从头写。
两大宝藏库：
Anthropic 官方 Skills 仓库： 不仅有现成技能，更重要的是定义了行业规范，官方推荐的标准写法都在此，是学习标准姿势的权威来源。
Awesome Cloud Skills： 汇集上百上千个 Skills 的社区项目，覆盖场景极多，网站交互友好（像命令行界面），支持按分类浏览和按用途搜索。
使用方式： 把现成 Skills 下载放到项目目录（如 .cursor/skills），AI 助手即可瞬间学会这些新本事。
未来趋势： 会用 AI 写代码不再稀奇，懂得如何设计和组合 Agent Skills、让 AI 稳定高效地在工程体系里干活，才是拉开差距的关键。
### S:
- 明确"大多数情况无需从零编写"
- 说出 Anthropic 官方仓库（行业规范）和 Awesome Cloud Skills（社区聚合）两个资源
- 知道 Skills 的存放位置约定（如 .cursor/skills）
### GOOD:
- 强调官方仓库的价值在于"定义行业规范"而非仅仅提供代码
- 理解 Skills 的组合与设计能力是工程师的核心竞争力
### BAD:
- 认为 Skills 必须自己手写，不了解社区生态
- 把 Skills 仓库当成普通代码 snippet 集合，忽视其规范性意义
### FOLLOWUP:
- 下载的社区 Skill 如何适配到自己项目的技术栈？需要做哪些改造？
- 当多个 Skills 之间产生冲突时，如何仲裁和组合？

---
<!-- id:llm_tool_001 | category:工具调用 | difficulty:3 | difficulty_label:高级 | type:scenario -->
### Q: Agent 系统中工具越来越多时，为什么应该"利用 Mask 而非删除"来管理工具上下文？请解释 Auto / Required / Specified 三种调用模式的实现原理。
### SCENARIO: 团队的 Agent 接入了上百个 MCP 工具，曾尝试像 RAG 一样动态增删工具，结果出现缓存失效、模型困惑选错工具等问题，面试官考察候选人的工具治理策略。
### A: 
为什么：
缓存代价： 工具定义通常位于上下文最前面，任何增删都会改变前缀，直接作废 KV-Cache。
一致性代价： history 中提到的工具一旦从上下文消失，模型会困惑甚至幻觉。
能力代价： 工具越多，模型越容易误行动或走低效路径，"工具越多的 Agent 可能越笨"。
如何解决：
核心原则 Mask, Don't Remove： 工具定义常驻上下文前部，不需要的工具用 mask 屏蔽而非物理删除；用上下文感知的状态机管理工具，在解码阶段用 logits mask 禁止或强制某些动作；工具名统一前缀化（如 browser_、shell_）便于按组 mask。
三种调用模式（通过给 assistant 预填充前缀实现，以 Hermes 格式为例）：
Auto（自动模式）： 模型可调用也可不调用工具，完全自主决定。实现：仅预填充回复前缀（<|im_start|>assistant），模型既可输出普通文本也可发起工具调用。适合大多数常规场景，自由度最高。
Required（必须调用）： 强制模型必须调用某个工具（具体调哪个由模型选择），不能直接回复文本。实现：预填充到工具调用起始标记（如 <|im_start|>assistant<tool_call>），把解码输出空间锁死在"工具调用"上。适合"这一步非借助工具不可"的场景（如查询天气、执行 SQL）。
Specified（指定调用）： 强制模型必须调用指定的某一个工具，连工具选择都替模型决定。实现：进一步预填充到具体工具名与参数起始（如 <|im_start|>assistant<tool_call>{"name": "get_weather", "arguments":），模型只需补全剩余参数。适合"明确知道该用哪个工具"的场景，从根本上杜绝选错。
### S:
- 理解 Mask, Don't Remove 的核心原则（工具常驻上下文、用 mask 而非删除）及其对 KV-Cache 与上下文一致性的意义
- 能解释 Auto / Required / Specified 三种模式的自自由度差异（可调可不调 -> 必须调 -> 指定调）
- 知道通过预填充 assistant 前缀约束解码行为（logits/解码阶段控制）的实现原理
### GOOD:
- 能说明"工具越多的 Agent 可能越笨"的根因（选择空间增大导致误行动、走低效路径）
- 提到工具名前缀化（browser_/shell_）与按组 mask 的工程实践
### BAD:
- 认为像 RAG 一样动态增删工具是合理的，忽略 KV-Cache 失效与上下文一致性问题
- 混淆 Required 与 Specified 的区别，说不出二者的自由度差异
### FOLLOWUP:
- prefix caching 在 vLLM 中的实现原理是什么？
- 当工具数量超过上下文窗口限制时，如何做工具分层或按需加载？

---
<!-- id:llm_memory_001 | category:Memory | difficulty:2 | difficulty_label:中级 | type:scenario -->
### Q: 在基于大模型的 Agent 中，为什么长期记忆的状态维护至关重要？请介绍最基础的两种记忆获取方式：全量历史对话与滑动窗口。
### SCENARIO: 团队的多轮客服机器人经常出现"答非所问、忘记上文"的问题，面试官让候选人从最基础的记忆机制讲起，考察对 LangChain Memory 组件的理解。
### A: 
为什么： 大模型本身无状态，每次调用都是独立的；多轮对话的连贯性完全依赖外部记忆组件把相关上下文重新喂给模型。记忆被视为 Agent 架构的关键组件之一（参考 Lilian Weng《基于大模型的 Agent 构成》）。
两种基础方式：
获取全量历史对话（ConversationBufferMemory）：
原理： 把整个用户对话历史完整存入 memory，每轮全部加载进 prompt。
场景： 电信客服——用户先问账单、再问网络连接，需记住账单细节才能提供连贯服务。
缺点： 上下文随轮次线性增长，token 成本和延迟飙升，易超窗口上限。
滑动窗口获取最近部分对话（ConversationBufferWindowMemory）：
原理： 只保留最近 k 次互动（如 k=1），丢弃更早的历史。
场景： 电商咨询——用户问完手机续航又问配送方式，AI 只需专注最近一两个问题，回复更快更聚焦。
缺点： 彻底丢失窗口外的早期信息，无法回溯远期上下文。
### S:
- 说明大模型无状态、记忆是 Agent 关键组件
- 准确说出 BufferMemory（全量）与 BufferWindowMemory（滑动窗口 k）的原理差异
- 指出各自优缺点与适用场景
### GOOD:
- 能对应到 LangChain 具体类名并写出关键参数（如 k=1）
- 清晰对比"全量保连贯 vs 窗口省成本但丢远期信息"的权衡
### BAD:
- 认为模型自己能记住历史，不需要外部 memory
- 混淆 Buffer 和 Window 的区别
### FOLLOWUP:
- 滑动窗口的 k 值如何选取？有没有动态调整的策略？
- 全量历史超过上下文窗口时除了滑动窗口还有什么办法？

---
<!-- id:llm_memory_002 | category:Memory | difficulty:2 | difficulty_label:中级 | type:scenario -->
### Q: 除了原始文本记忆，如何通过"实体抽取"和"知识图谱"来增强 Agent 的长期记忆？请说明 ConversationEntityMemory 与 ConversationKGMemory 的区别。
### SCENARIO: 法律咨询和医疗问诊场景中，对话涉及大量人名、条款、病症等关键信息，单纯存原文效率低且易遗漏关联，面试官考察结构化记忆方案。
### A: 
为什么： 原始对话文本冗余度高，关键实体及其关系淹没在长文本中；结构化抽取能让 AI 精准记住"谁是谁、什么关系"，提供更个性化的建议。
两种方式：
获取历史对话中实体信息（ConversationEntityMemory）：
原理： 用 LLM 从对话中抽取关键实体及其属性/关系，单独存储；检索时按实体召回相关细节。
场景： 法律咨询——客户提到特定案件名称、法律条款、个人信息（如"去年交通事故获赔建议"），AI 记住这些实体后给出更准确的法律建议。
输出结构： 同时返回 history 和 entities（如 {'莫尔索': '《LLM应用全栈开发》的作者'}）。
利用知识图谱获取实体及其联系（ConversationKGMemory）：
原理： 不仅抽取实体，还构建实体间的关系图谱（三元组），形成包含症状、病史、健康关联的知识网络。
场景： 医疗咨询——病人描述多个症状和过往病史（糖尿病史、经常口渴疲劳），KG 构建病症-病史-健康关联图谱，提供更全面深入的医疗建议。
区别： EntityMemory 侧重"实体->属性"的扁平记录；KGMemory 侧重"实体—关系—实体"的网状关联，能做关系推理。
### S:
- 区分 EntityMemory（实体属性）与 KGMemory（实体间关系图谱）
- 说出各自典型场景（法律/医疗）
- 理解结构化记忆相对纯文本的优势（精准、可推理）
### GOOD:
- 能说明 KGMemory 输出的是关系网络，支持关联推理
- 指出两者都依赖 LLM 做抽取，存在抽取准确性与额外调用成本
### BAD:
- 把 EntityMemory 和 KGMemory 当成一回事
- 忽视结构化抽取带来的额外 LLM 调用开销和误差累积
### FOLLOWUP:
- 知识图谱的实体/关系抽取出错时如何校正？
- 这两种方式与向量检索记忆相比，各自适合什么类型的问题？

---
<!-- id:llm_memory_003 | category:Memory | difficulty:3 | difficulty_label:高级 | type:scenario -->
### Q: 当对话很长时，如何用"摘要"和"向量检索"来平衡记忆的深度与成本？请对比 ConversationSummaryMemory、SummaryBufferMemory、TokenBufferMemory 和 VectorStoreRetrieverMemory。
### SCENARIO: 教育辅导、技术支持、金融咨询、新闻问答等不同业务对记忆的需求各异，面试官让候选人针对"既要近期细节又要远期概览""按相关性召回"等需求选型。
### A: 
为什么： 全量记忆成本高、窗口记忆丢信息、结构化记忆有抽取开销；摘要和向量检索分别从"压缩概括"和"按需相关性召回"两个维度解决长对话记忆问题。
四种方式对比：
阶段性总结摘要（ConversationSummaryMemory）：
用 LLM 对历史对话持续滚动总结成一段摘要，替代原始历史。
场景： 教育辅导——总结之前的辅导内容和学生疑问点，后续提供针对性解释。
优点省 token；缺点摘要会丢失细节、有信息损耗。
兼顾最新对话与早期摘要（ConversationSummaryBufferMemory）：
保留最近几次交互的详细原文 + 更早历史的摘要，二者结合。
场景： 技术支持/软件排障——保留近期详细错误信息，同时有历史问题处理摘要，便于识别和解决。
回溯最近和最关键的对话（ConversationTokenBufferMemory）：
按 token 数而非轮次限制记忆长度，聚焦最近且最关键的信息，避免记忆过多导致混乱。
场景： 金融咨询——客户问投资、市场动态、财务规划等多个问题，按 token 预算保留最关键内容。
基于向量检索对话信息（VectorStoreRetrieverMemory）：
把历史对话切片 embedding 存入向量库（如 Chroma），按当前问题的语义相似度召回最相关片段，而非按时间顺序。
场景： 新闻事件问答——从大量历史新闻中检索与当前问题最相关的信息，即使它不是最新的也能提供准确背景。
### S:
- 准确区分四种记忆机制的触发维度（摘要/token 预算/语义相似度）
- 为每种机制匹配正确场景
- 说明 SummaryBuffer 是"近期原文+远期摘要"的混合策略
### GOOD:
- 能画出"时间维度（Buffer/Window/Token）vs 压缩维度（Summary）vs 相关性维度（Vector）"的选型框架
- 指出 VectorStore 记忆打破时间顺序、按语义召回的独特价值
### BAD:
- 把所有摘要类记忆混为一谈，说不出 SummaryBuffer 的混合特性
- 认为向量检索一定优于其他方案，忽视其召回不稳定的风险
### FOLLOWUP:
- 实际生产中如何组合多种记忆机制（如短期 Buffer + 长期 Vector + 摘要）？
- ConversationSummaryMemory 的摘要本身会越来越长，如何控制？

---
<!-- id:llm_ft_001 | category:微调 | difficulty:2 | difficulty_label:中级 | type:scenario -->
### Q: 为什么需要提示学习（Prompting）？什么是 Prompting，它相比 Full Fine-Tuning 有什么优点？
### SCENARIO: 团队面对一个新下游任务，纠结是做大模型全量微调还是用提示方法，面试官让候选人从动机和原理讲起，考察对 Prompt Learning 本质的理解。
### A: 
为什么需要： 面对特定下游任务时，Full Fine-Tuning（对预训练模型所有参数微调）太过低效；而如果只固定预训练模型的某些层、仅微调接近下游任务的那几层参数，又难以达到较好效果。需要一种介于"零成本 prompt"和"高成本全量微调"之间的方案。
什么是 Prompting： 在输入中提供上下文和任务相关信息，帮助模型更好理解要求并生成正确输出。例如情感分析任务中，把分类任务转换为"填空"任务——在句子前加前缀"该句子的情感是"，让 BERT 学习"积极/消极"与该填空位的关联。
优点：
最小化微调参数量与计算复杂度： 通过少量可调参数提升预训练模型在新任务上的性能。
缓解训练成本： 即使计算资源受限，也能利用预训练模型的知识快速适应新任务，实现高效迁移学习。
### S:
- 说清 Full FT 低效、部分层微调效果差的两难困境
- 解释 Prompting 是把任务转为"填空/完形"形式引导模型
- 点明核心优点：参数少、成本低、高效迁移
### GOOD:
- 能用情感分析"该句子的情感是[MASK]"的例子说明任务重构思想
- 理解 Prompting 是连接预训练知识与下游任务的桥梁
### BAD:
- 把 Prompting 等同于"写好提示词"的工程技巧，忽视其作为微调范式的一面
- 说不出它相对 Full Fine-Tuning 的参数效率优势
### FOLLOWUP:
- Prompting 和前面讲的 Agent Skills/Prompt 工程有什么层次上的区别？
- 什么样的任务特别适合用 Prompting 而非微调？

---
<!-- id:llm_ft_002 | category:微调 | difficulty:3 | difficulty_label:高级 | type:scenario -->
### Q: 请详细对比 Prefix-tuning 和 Prompt-tuning 的思路、优缺点，并说明二者的核心区别。
### SCENARIO: 候选人在做参数高效微调选型，面试官让其深入辨析两种经典 soft-prompt 方法，考察对底层机制的掌握深度。
### A: 
Prefix-tuning（前缀微调）：
思路： ① 在输入 token 前构造一段任务相关的 virtual tokens 作为 Prefix；② 训练时只更新 Prefix 部分参数，Transformer 其余参数固定；③ 在 Prefix 前加 MLP 结构（将 Prefix 分解为更小维度 input 经 MLP 组合输出），训练完只保留 Prefix 参数，防止直接更新导致训练不稳定。
优点： 可学习"隐式 prompts"（人工离散 prompt 无法更新参数）；一个批次可处理多用户/任务样本；相比 full fine-tuning 只更新 Prefix 参数。
缺点： 占用序列长度、有额外计算开销；每层都加 prompt 参数，改动较大。
Prompt-tuning（指示微调）：
思路： ① 将 prompt 扩展到连续空间，仅在输入层添加 prompt 连续向量，反向传播更新这些向量（非人工设计 prompts）；② 冻结原始模型权重，只训练 prompts 参数，一个模型可做多任务推理；③ 可用 LSTM 建模 prompt 向量间关联性。
缺点： 训练难度大、不一定省时间（parameter efficient != training efficient，省显存但训练时间可能更长）；多个 prompt token 相互独立可能影响效果；在 NLU 上对正常大小预训练模型表现不佳；现有方法难处理困难序列标注任务。
核心区别：
适用任务： Prefix-tuning 针对 NLG、服务 GPT 架构；Prompt-tuning 考虑所有类型语言模型。
添加位置： Prefix-tuning 限定输入前部添加；Prompt-tuning 可在任意位置添加。
向量添加方式： Prefix-tuning 每层都添加以保证效果；Prompt-tuning 可以只在输入层添加。
### S:
- 准确说出两者思路差异（Prefix 每层+MLP 稳定 vs Prompt 仅输入层连续向量）
- 列出各自优缺点
- 从适用任务、添加位置、添加方式三维度对比区别
### GOOD:
- 能指出 Prefix-tuning 用 MLP 重参数化是为了训练稳定性这一关键细节
- 澄清"parameter efficient != training efficient"的常见误解
### BAD:
- 把两者完全等同，说不出"每层添加 vs 仅输入层添加"的关键差异
- 忽视 Prompt-tuning 在 NLU/序列标注任务上的局限
### FOLLOWUP:
- 为什么 Prefix-tuning 要在每层都加 prefix，而 Prompt-tuning 只在输入层加也够用？
- Prompt-tuning 训练时间长的问题有哪些缓解手段？

---
<!-- id:llm_ft_003 | category:微调 | difficulty:3 | difficulty_label:高级 | type:scenario -->
### Q: P-tuning 和 P-tuning v2 分别解决了什么问题？请说明 P-tuning 的思路、优缺点，以及 v2 相对 v1 的改进。
### SCENARIO: 团队发现 Prompt-tuning 在小模型上效果差、序列标注任务搞不定，面试官考察候选人对 P-tuning 系列演进的理解。
### A: 
为什么需要 P-tuning： 大模型的 Prompt 构造方式严重影响下游任务效果。如 GPT 系列 AR 模型在自然语言理解 NLU 上效果不如 BERT 双向模型；GPT-3 虽用人工构造模板做 in-context learning，但人工模板变化敏感，加一个词/变个词都可能造成巨大波动。研究表明 prompt 训练可显著提升 few-shot/zero-shot 效果，但自动化搜索模板成本高且结果不稳定。
P-tuning（v1）思路：
可学习的 Embedding 层设计： 将 Prompt 转为可学习 Embedding 层。
prompt encoder 设计： 用 prompt encoder（双向 LSTM + 两层 MLP 组成）对 Prompt Embedding 做一层处理，建模 token 间相互依赖，并提供更好的初始化。
优点： 引入 prompt encoder 建模 token 依赖、提供更优初始化。
缺点： 复杂性增加、看着不太像 prompt 了；token 编码虽连续但与输入结合时可能不连续，中间可能插入输入。
P-tuning v2 改进：
目标： 让 Prompt Tuning 在不同参数规模预训练模型、不同下游任务上都能达到匹配 Fine-tuning 的效果。
思路： ① Deep Prompt Encoding： 采用 Prefix-tuning 做法，在输入前面每层加入可微调的 Prompts tokens；② 移除重参数化编码器（Prefix-tuning 的 MLP、P-tuning 的 LSTM）；③ 解决了 Prompt Tuning 无法在小模型上有效提升的问题；④ 将 Prompt Tuning 拓展至 NER 等序列标注任务。
缺点： 抛弃了 prompt learning 中常用的 verbalizer，回归传统 CLS/token label 分类范式，某种程度上弱化了"prompt 的味道"。
### S:
- 说清 P-tuning v1 用 LSTM+MLP 的 prompt encoder 建模依赖
- 指出 v2 的核心是 Deep Prompt Encoding（每层加 prompt）+ 移除重参数化编码器
- 明确 v2 解决的两大问题：小模型失效、序列标注任务不可用
### GOOD:
- 能清晰画出 v1->v2 的演进脉络（吸收 Prefix-tuning 的"每层加"思想）
- 指出 v2 放弃 verbalizer 回归 CLS 分类是其"弱化 prompt 味道"的代价
### BAD:
- 混淆 P-tuning v1 和 v2，说不出 Deep Prompt Encoding
- 忽视 v1 在小模型和序列标注上的失败是 v2 的直接动机
### FOLLOWUP:
- P-tuning v2 和 LoRA 相比，各自的适用场景和优劣是什么？
- verbalizer 被抛弃后，对生成类任务有什么影响？

---
<!-- id:llm_ft_004 | category:微调 | difficulty:2 | difficulty_label:中级 | type:scenario -->
### Q: 什么是 LoRA？请解释它的核心思路、特点，并用一句话简单描述其工作原理。
### SCENARIO: 团队想低成本微调一个大模型适配业务，候选人提到用 LoRA，面试官让其从最基础的原理解释起，考察是否真正理解而非只会调包。
### A: 
什么是 LoRA： Low-Rank Adaptation，通过低秩分解来模拟参数的改变量，从而以极小的参数量实现大模型的间接训练。
核心思路：
在原模型旁边增加一个旁路，通过低秩分解（先降维再升维）来模拟参数的更新量。
训练时原模型固定，只训练降维矩阵 A 和升维矩阵 B。
推理时可将 BA 加到原权重上，不引入额外推理延迟。
初始化：A 采用高斯分布初始化，B 初始化为全 0，保证训练开始时旁路为零矩阵（即初始等价于原模型）。
可插拔式切换任务：当前任务 W0+B1A1，将 lora 部分减掉换成 B2A2 即可实现任务切换。
特点：
将 BA 加到 W 上可消除推理延迟；
可通过插拔形式切换到不同任务；
设计比较好，简单且效果好。
一句话描述： 冻结预训练模型的矩阵参数，选择用 A、B 矩阵来替代更新量，在下游任务时只更新 A 和 B。
### S:
- 准确说出"低秩分解/先降维再升维"的核心思想
- 说明 A 高斯初始化、B 零初始化以保证训练起点等价原模型
- 点明推理时可合并、无额外延迟、可插拔切换任务
### GOOD:
- 能写出 h = Wx + BAx 的公式并解释 r（秩）远小于 d 的参数节省原理
- 强调"零初始化 B 保证训练开始旁路为零"这一关键工程细节
### BAD:
- 只说"加个小矩阵"，说不出低秩分解和初始化策略
- 认为 LoRA 推理时有额外开销（实际可合并消除）
### FOLLOWUP:
- 为什么是 B 初始化为 0 而不是 A？反过来会怎样？
- 秩 r 的大小如何影响表达能力和参数量？

---
<!-- id:llm_ft_005 | category:微调 | difficulty:3 | difficulty_label:高级 | type:scenario -->
### Q: 请对比 QLoRA 和 AdaLoRA 相对 LoRA 的改进思路与各自特点，它们分别解决了什么问题？
### SCENARIO: 候选人在显存受限和资源动态分配两个场景下做选型，面试官考察其对 LoRA 两大主流变体的理解深度。
### A: 
QLoRA：
思路： ① 使用一种新的高精度技术将预训练模型量化为 4 bit；② 添加一组可学习的低秩适配器权重，通过量化权重的反向传播梯度进行微调。
特点/解决的问题： 显著降低对显存的要求，同时模型训练速度会慢于 LoRA。解决的是显存瓶颈——让单卡也能微调超大模型。
AdaLoRA：
思路： 对 LoRA 的一种改进，根据重要性评分动态分配参数预算给权重矩阵——将关键的增量矩阵分配高秩以捕捉更精细、任务特定的信息，而将较不重要的矩阵保持低秩，以防止过拟合并节省计算预算。
解决的问题： 标准 LoRA 对所有层/矩阵用统一秩 r，但不同层重要性不同；AdaLoRA 实现自适应秩分配，把参数预算花在刀刃上。
### S:
- 说清 QLoRA = 4bit 量化基座 + 低秩适配器，主攻显存
- 说清 AdaLoRA = 按重要性评分动态分配秩，主攻参数预算效率
- 指出 QLoRA 训练速度慢于 LoRA 的代价
### GOOD:
- 能区分两者优化维度不同：QLoRA 优化"基座存储（量化）"，AdaLoRA 优化"适配器秩分配（动态）"
- 指出 AdaLoRA 的重要性评分机制是其核心创新
### BAD:
- 把 QLoRA 和 AdaLoRA 的改进点搞混
- 忽视 QLoRA 训练速度变慢的 trade-off
### FOLLOWUP:
- QLoRA 的 4bit 量化会不会损失精度？NF4、双量化是什么？
- AdaLoRA 的重要性评分具体怎么计算？

---
<!-- id:llm_ft_006 | category:微调 | difficulty:2 | difficulty_label:中级 | type:scenario -->
### Q: LoRA 微调有哪些优点和缺点？在已有 LoRA 模型上如何继续训练？rank 和 alpha 参数该如何选取？
### SCENARIO: 团队已上线一个 LoRA 适配版本，现在要在新数据上迭代，并就超参数配置请教，面试官考察实战经验。
### A: 
优点：
一个中心模型服务多个下游任务，节省参数存储量；
推理阶段不引入额外计算量（可合并）；
与其它参数高效微调方法正交，可有效组合；
训练任务比较稳定，效果比较好；
几乎不添加任何推理延迟（适配器权重可与基本模型合并）。
缺点： 参与训练的模型参数虽不多（百万到千万级），但效果比全量微调差很多；在 LLM 上个人感觉表现差距挺大（扩散模型上没那么强）。
在已有 LoRA 上继续训练： 已有的 lora 模型只训练了一部分数据，要训练另一部分数据时，可在该 lora 上继续训练，或把 base 模型合并后再叠一层 lora，或从头开始训练一个新 lora。实践中常把之前的 LoRA 与 base model 合并后继续训练，以保留之前的知识和能力；训练新的 LoRA 时加入一些之前的训练数据是需要的，另外每次都要考虑成本。
参数选取：
Rank： 取值作者对比了 1-64，效果上 Rank 在 4-8 之间最好，再高并没有效果提升。不过论文实验面向下游单一监督任务，因此需根据指令微调等更广场景，Rank 选择还是需要在 8 以上取值测试。
alpha： 是个缩放参数，本质和 learning rate 相同，为简化默认 alpha = rank，只调整 lr，这样可以简化超参。
### S:
- 列出 LoRA 五大优点（多任务/无推理开销/正交可组合/稳定/可合并）
- 诚实指出缺点：效果仍逊于全量微调
- 给出 rank 4-8 经验值、alpha=rank 的简化策略
- 说明继续训练的几种方式及"合并 base+旧 lora 再训"的实践
### GOOD:
- 能给出 rank/alpha 的具体经验值和"alpha=rank 简化超参"的工程技巧
- 说明继续训练时需混入旧数据以防遗忘
### BAD:
- 盲目把 rank 设很大，不理解 4-8 通常足够的经验结论
- 不知道 alpha 与 learning rate 的等效关系
### FOLLOWUP:
- LoRA 应该作用于 Transformer 的哪些参数矩阵（q/k/v/o/gate/up/down）？如何选择 lora_target？
- LoRA 权重是否可以合并？多个 LoRA 如何叠加？

---
<!-- id:llm_ft_007 | category:微调 | difficulty:3 | difficulty_label:高级 | type:scenario -->
### Q: LoRA 的矩阵为什么要这样初始化（A 高斯、B 全 0）？LoRA 权重能否合并？能否逐层调整最优 rank？如何避免过拟合？
### SCENARIO: 候选人深入追问 LoRA 的若干工程细节，面试官借此考察其对底层机制和训练 trick 的掌握。
### A: 
初始化原因： 矩阵 B 初始化为 0、A 用高斯初始化。若 A、B 都初始化为 0，会与深度网络全 0 初始化一样容易使梯度消失（此时所有神经元功能等价）。若 A、B 都用高斯初始化，则网络训练刚开始就有概率得到一个过大的偏移值 ΔW，引入太多噪声导致难以收敛。因此一部分正常初始化（A）、一部分置 0（B），是为了训练开始时维持网络原有输出（旁路为 0），同时保证真正开始学习后能更好收敛。
权重合并： 可以。将多个 LoRA 权重合并，训练中保持 LoRA 权重独立并在前向传播时添加，训练后可合并权重以简化操作。
逐层调整 rank： 理论上可以为不同层选择不同 LoRA rank（类似不同层设不同学习率），但由于增加了调优复杂性，实际中很少执行（AdaLoRA 正是自动化解决此问题）。
避免过拟合： 减小或增加数据集大小可帮助减少过拟合；还可尝试增加优化器的权重衰减率或 LoRA 层的 dropout 值。
其它相关要点（来自图中高频问题）：
加速训练： 只更新部分参数（如原文只更新 Self Attention，实际也可选只更新部分层）；减少通信时间（参数少->多卡传输数据少）；采用混合精度 SDP16/FP8/INT8 量化。LoRA 优点是低秩分解直观、不少场景效果接近全量微调、预测阶段不增加推理成本。
内存影响因素： 模型大小、批量大小、LoRA 参数数量、数据集特性；使用较短训练序列可节省内存。
优化器： 除 Adam/AdamW，Sophia 等也值得研究（用梯度曲率而非方差归一化，可能提升效率和性能）。
### S:
- 准确解释"A 高斯 + B 零"初始化避免梯度消失与初始噪声的两难
- 说明权重可合并、逐层 rank 理论可行但实践少做
- 给出过拟合缓解手段（数据量/weight decay/dropout）
### GOOD:
- 能从"梯度消失 vs 初始噪声过大"两个极端解释初始化设计的精妙
- 把逐层 rank 与 AdaLoRA 的动机联系起来
### BAD:
- 说不清为什么不能 A、B 都置 0 或都用高斯
- 对过拟合只会说"加数据"，提不出 weight decay/dropout
### FOLLOWUP:
- LoRA 这种微调方法和全参数比起来有什么劣势？什么情况下必须全量微调？
- ChatGLM-6B 的 LoRA 权重有多大（rank 8、target=query_key_value 下大约 15M）？

---
<!-- id:llm_rag_011 | category:RAG | difficulty:2 | difficulty_label:中级 | type:scenario -->
### Q: 在 RAG 系统中，为什么需要对文本进行分块（Chunking）？不分块或分块不当会带来什么问题？
### SCENARIO: 团队搭建 RAG 知识库时直接把整篇文档塞进向量库，检索效果很差，面试官让候选人从原理上解释分块的必要性。
### A: 
为什么需要分块： 使用 LLM 时切勿忽略文本分块的重要性，其对处理结果好坏有重大影响。
两个核心原因：
信息丢失的风险： 试图一次性提取整个文档嵌入向量，虽然可以捕捉整体上下文，但可能会忽略掉许多针对特定主题的重要信息，导致生成的信息不够精确或有所缺失。
分块大小的限制： 在使用 OpenAI 等模型时，分块大小是一个关键的制约因素。例如 GPT-4 模型有 32K 的窗口大小，尽管对大多数情况不是问题，但从一开始就考虑到分块大小是很重要的。
结论： 恰当地实施文本分块不仅能提升文本的整体品质和可读性，还能预防由于信息丢失或不当分块引起的问题。这就是为何在处理长文档时，采用文本分块而非直接处理整个文档至关重要的原因。
### S:
- 说出"信息丢失风险"和"分块大小/上下文窗口限制"两大原因
- 说明整篇嵌入会稀释特定主题的细节信息
- 点明分块对检索精度和可读性的影响
### GOOD:
- 能联系到 embedding 模型本身也有输入长度上限，不只是 LLM 窗口
- 理解分块是"召回精度"与"上下文完整性"之间的权衡
### BAD:
- 认为分块只是为了凑模型窗口，忽视信息丢失/检索精度维度
- 说不出整篇嵌入为何会丢失细节
### FOLLOWUP:
- chunk_size 设大和设小各有什么 trade-off？
- 分块大小应该参考 embedding 模型还是 LLM 的窗口？

---
<!-- id:llm_rag_012 | category:RAG | difficulty:2 | difficulty_label:中级 | type:scenario -->
### Q: 请介绍几种常见的文本分块方法：固定长度分块、正则拆分、Spacy 分句，以及 LangChain 的 CharacterTextSplitter，它们各自的原理和适用场景是什么？
### SCENARIO: 候选人在为不同格式的语料选择分块策略，面试官考察其对基础分块方法的掌握广度。
### A: 
1. 一般的固定长度分块： 不借助任何规则，直接按固定长度切分（如 chunk_size=128，循环切片）。简单粗暴，但容易切断语义。
2. 正则拆分（split_sentences）：
原理： 用正则表达式匹配中文标点符号（如 。！？；）来识别句子边界，将长文本拆成更短的句子，再过滤空字符串。
特点： 比固定长度更尊重语义边界；但对一些长度很长的句子容易从中间切开；基于模式匹配，不如复杂语法/语义分析精确，但大多数情况下满足基本句子分割需求，实现简单。
补充： 还有其它技术可使用，如词性标注（POS tagging）等。
3. Spacy Text Splitter：
原理： Spacy 是用于执行 NLP 各种任务的库，具有文本拆分功能，能在分句时保留分词结果的上下文信息（如加载 zh_core_web_sm 中文模型按 sents 迭代）。
特点： 基于单词词性和语法结构分句，比纯正则更符合语言规律。
4. LangChain CharacterTextSplitter：
原理： 一般设置参数 chunk_size、chunk_overlap、separator、strip_whitespace，按指定分隔符（如空格）切分。
特点： LangChain 封装，参数化灵活，支持重叠（overlap）避免边界信息丢失。
### S:
- 区分四种方法的切分依据（固定长度/正则标点/语法词性/分隔符）
- 指出正则分块对超长句仍会切断的局限
- 提到 chunk_overlap 重叠机制的作用
### GOOD:
- 能说明 Spacy 基于词性语法、比正则更懂语言结构
- 强调 overlap 是为缓解切分边界处语义断裂
### BAD:
- 把所有分块方法当成一回事
- 不知道 overlap 的存在和意义
### FOLLOWUP:
- chunk_overlap 设多大合适？过大过小各有何问题？
- 中文场景下用 Spacy 还是正则更好？

---
<!-- id:llm_rag_013 | category:RAG | difficulty:3 | difficulty_label:高级 | type:scenario -->
### Q: LangChain 的 RecursiveCharacterTextSplitter 与普通 CharacterTextSplitter 有何不同？针对 HTML、Markdown、Python 代码、LaTeX 等结构化文本，应如何选择专用分块方法？
### SCENARIO: 团队的语料包含网页、技术文档、代码等多种格式，用通用分块破坏了结构语义，面试官考察候选人对结构化分块方案的了解。
### A: 
RecursiveCharacterTextSplitter vs CharacterTextSplitter：
不同点： Recursive 不需要预设单一分隔符，而是按一组分隔符的优先级顺序递归切分（默认 ["\n\n", "\n", " ", ""]，即段落->换行->空格->字符）。
机制： 先尝试用第一个分隔符（段落）分，若块仍太大，则用下一个分隔符（换行）继续分，依此类推，直到块足够小。这样能最大程度保留文本的自然结构层级。
结构化文本专用分块方法：
HTML（HTMLHeaderTextSplitter）： 一种结构感知工具，在 HTML 元素级别拆分，并为每个分块添加与之相关的标题元数据（如 h1/h2/h3 -> Header 1/2/3）。能精准处理 HTML 文档结构，仅提取 headers_to_split_on 中指定的标题。
Markdown（MarkdownHeaderTextSplitter）： 根据 Markdown 语法规则（标题、代码块、图片、列表）切分，基于文档结构特性有效分块，通过 headers_to_split_on（如 #/##/### -> Header 1/2/3）按标题层级拆分并附加 metadata，便于根据标题精确定位内容。
Python 代码（PythonCodeTextSplitter）： 专为代码设计，按代码结构（类、函数定义等）切分，保持代码逻辑单元完整。
LaTeX（LatexTextSplitter）： 专为 LaTeX 设计，通过解析 LaTeX 命令创建各个块（章节、小节等），产生更加准确且与上下文相关的分块结果，提升后续检索效果。
### S:
- 说清 Recursive 按分隔符优先级递归切分的机制及默认顺序
- 为 HTML/Markdown/代码/LaTeX 匹配正确的专用 Splitter
- 指出结构化分块会附加标题/层级 metadata 的价值
### GOOD:
- 能解释 Recursive "先段落再换行再空格"的递归降级逻辑
- 强调结构化分块保留标题 metadata 对检索定位的帮助
### BAD:
- 用通用 CharacterTextSplitter 切代码/HTML，破坏结构
- 不知道 Recursive 的分隔符优先级机制
### FOLLOWUP:
- 这些结构化分块的 metadata（标题层级）在检索时如何利用？
- 代码分块时如何处理跨函数的调用关系？

---
<!-- id:llm_rag_014 | category:RAG | difficulty:2 | difficulty_label:中级 | type:scenario -->
### Q: 在文本分块和向量存储的工程实践中，有哪些常见踩坑点？LanceDB 这类向量数据库有什么特点？
### SCENARIO: 团队的 RAG 系统在代码分块和向量存储环节频繁出问题，面试官考察候选人的工程实战经验和避坑意识。
### A: 
常见踩坑点（以代码分块为例）：
在处理代码分块过程中，任何重载的代码都可能完全改变其原有含义。因此为了保持代码的原始意图和准确性、避免产生误解或错误，设置重叠部分（overlap）是必要的。
选定分块处理数据时，重要的一步是根据数据存入并将其存储在向量数据库（Vector DB）中。
LanceDB 的特点：
上面的例子中使用 LanceDB 来存储数据块及其对应的嵌入。
LanceDB 是一个无需配置、开箱即用的向量数据库，其数据持久化在磁盘上，允许用户在不超出预算的情况下实现扩展。
此外，LanceDB 与 Python 数据生态系统兼容，因此可以将它与现有数据工具（如 pandas、pyarrow 等）结合使用。
工程要点总结：
代码等语义敏感文本必须设 overlap，防止重载/上下文被切断导致语义失真。
向量库选型要考虑：是否免配置、是否磁盘持久化、能否低成本扩展、是否与现有数据栈（pandas/pyarrow）兼容。
### S:
- 指出代码分块必须设 overlap 以防重载语义被破坏
- 说出 LanceDB 免配置/磁盘持久化/兼容 pandas-pyarrow 的特点
- 体现"分块->向量化->存储"全链路的工程视角
### GOOD:
- 能从"代码重载改变语义"的具体例子论证 overlap 的必要性
- 把向量库选型落到成本、持久化、生态兼容等工程维度
### BAD:
- 忽视代码分块的特殊性，用普通文本策略处理
- 对向量库只知 Chroma/Pinecone，不了解 LanceDB 等嵌入式方案
### FOLLOWUP:
- LanceDB 和 Chroma、Milvus 相比各自适合什么规模？
- 分块后的 embedding 更新（文档变更）如何增量处理？

---
<!-- id:llm_mcp_001 | category:MCP | difficulty:3 | difficulty_label:高级 | type:scenario -->
### Q: 在构建一个需要访问本地文件、数据库和外部API的AI助手时，如何设计其架构以确保安全性与可扩展性？请结合MCP协议说明你的方案。
### SCENARIO: 你正在为一家金融科技公司开发一款智能投顾助手，该助手需要读取用户本地的投资组合文件（如CSV）、查询内部风控数据库、并调用第三方市场数据API。公司安全部门要求所有外部工具调用必须经过标准化接口，且不能直接暴露后端服务给LLM。你需要设计一个既能满足功能需求又符合安全规范的架构。
### A: 
为什么采用MCP协议：
解耦与安全隔离： MCP将LLM应用与具体工具实现分离，LLM只通过标准JSON-RPC 2.0接口通信，不直接接触文件系统或数据库，避免权限滥用。
统一协议栈： 无论底层是本地文件、SQL数据库还是HTTP API，都封装成MCP Server，客户端只需处理一种协议，降低复杂度。
动态发现与组合： 支持MCP Inspector等工具自动发现可用Server，便于模块化扩展新工具（如新增"舆情分析"Server）。
如何解决：
1. 架构分层：
LLM应用层： 仅含MCP Client，负责解析自然语言指令并转换为MCP请求。
MCP Server层： 分别部署File Server（读写本地CSV）、DB Server（执行SQL查询）、API Server（调用外部REST API）。
传输层： 使用stdio（本地进程间）或SSE（跨网络）作为通信载体。
2. 安全控制：
每个Server独立运行沙箱环境，限制其访问范围（如File Server只能读指定目录）。
通过MCP Protocol的capabilities字段声明权限，Client按需授权。
3. 扩展机制：
新增工具只需开发对应MCP Server并注册到Inspector，无需修改LLM主程序。
支持多Server并行调用（如同时查数据库+调API），提升响应效率。
### S:
- 正确识别MCP的核心价值：解耦、安全、标准化
- 清晰描述三层架构（Client/Server/Transport）及各自职责
- 提出具体的安全措施（沙箱、能力声明）和扩展方案（动态注册）
### GOOD:
- 能结合场景举例说明各组件作用（如"File Server专管CSV读取"）
- 强调协议无关性（stdio/SSE均可承载JSON-RPC）
- 提及生态工具链（MCP Inspector用于调试和发现）
### BAD:
- 混淆MCP与普通API网关，未突出"LLM专用协议"特性
- 忽略安全设计，假设LLM可直接调用数据库
- 将MCP Server等同于微服务，忽视其轻量级、单一职责特点
### FOLLOWUP:
- 如果需要在浏览器中运行LLM应用，MCP架构该如何调整？（提示：考虑SSE替代stdio）
- 当多个MCP Server返回冲突结果时（如数据库说账户余额不足，但API显示有信用额度），如何在Client层做决策融合？

---
<!-- id:llm_mcp_002 | category:MCP | difficulty:2 | difficulty_label:中级 | type:scenario -->
### Q: 在需要快速构建一个具备数学计算能力的 AI Agent 时，相比于原生 MCP SDK，为什么推荐使用 FastMCP？请结合代码实现简述其优势。
### SCENARIO: 你所在的团队正在开发一个智能财务助手，需要让 LLM 具备加减乘除的基础计算能力。之前的开发者尝试使用原生 MCP Python SDK 编写 Server，发现需要处理大量的 JSON Schema 定义、协议握手和错误处理代码，导致开发效率低下且代码难以维护。作为技术负责人，你决定引入 FastMCP 框架来重构这部分功能，并向团队解释这一决策的技术依据。
### A: 
为什么选择 FastMCP：
1. 极简开发体验（Pythonic）： FastMCP 利用 Python 装饰器（如 @mcp.tool()）和类型提示（Type Hints），自动将 Python 函数转换为符合 MCP 规范的工具。开发者无需手动编写繁琐的 JSON Schema 或处理底层的 JSON-RPC 消息。
2. 抽象层级更高： 它屏蔽了传输层（stdio/SSE）和协议层的复杂性，让开发者专注于业务逻辑（即"做什么"而不是"怎么通信"）。
3. 生态集成： FastMCP 现已成为官方 MCP Python SDK 的一部分，稳定性与兼容性有保障。
如何解决（实现方案）：
1. 服务端（Server）：
初始化 FastMCP 实例。
使用 @mcp.tool() 装饰器定义 add, subtract, multiply, divide 函数。
直接在函数签名中定义参数类型（如 a: float, b: float），框架会自动生成 InputSchema。
通过 mcp.run(transport='sse') 一行代码启动服务。
2. 客户端（Client）：
使用 fastmcp.Client 连接服务。
在 LLM 的对话循环中，解析 LLM 返回的 tool_call，通过 client.call_tool 直接调用远程函数，无需手动构造 RPC 请求包。
### S:
- 能指出 FastMCP 通过装饰器和类型提示简化了 Schema 定义和协议处理
- 清楚 Server 端只需关注业务逻辑函数，Client 端负责 LLM 与 Tool 的桥接
- 提到 @mcp.tool() 装饰器的作用以及自动类型转换机制
### GOOD:
- 能够对比原生 SDK 的痛点（手动写 JSON Schema、处理 RPC 细节）与 FastMCP 的解决方案
- 准确描述 @mcp.tool() 如何将 Python 函数映射为 MCP Tool
- 提到 FastMCP 支持 SSE 和 stdio 多种传输模式的便捷切换
### BAD:
- 认为 FastMCP 只是一个简单的 HTTP 封装，忽略了其对 MCP 协议标准的严格遵循
- 无法解释装饰器背后的自动化原理（如类型 introspection）
- 混淆了 LLM Client（如 OpenAI SDK）与 MCP Client（FastMCP Client）的职责
### FOLLOWUP:
- 如果需要在 FastMCP 中添加一个需要访问外部数据库的复杂工具，如何处理异步 IO 和超时控制？
- FastMCP 如何处理工具执行过程中的异常？这些异常是如何反馈给 LLM 的？

---
<!-- id:llm_tool_002 | category:工具调用 | difficulty:2 | difficulty_label:中级 | type:scenario -->
### Q: 在 AI Agent 开发中，如何实现一个能够自动分析本地 TXT 文件并生成统计报告的智能助手？请描述从环境配置到 Agent 逻辑实现的完整流程。
### SCENARIO: 公司希望利用现有的大模型能力，开发一个内部工具，允许员工上传或指定本地的 .txt 日志文件，AI 能够自动读取内容、分析关键指标并生成摘要。你需要基于 Qwen-Agent 或类似的 Agent 框架，结合 MCP 思想（或直接使用工具调用），设计并实现这个"TXT 文件统计智能助手"。面试官希望你展示从依赖管理到核心代码逻辑的完整落地能力。
### A: 
为什么这样设计：
能力解耦： 将"文件读取"和"统计分析"作为独立的工具（Tool）或 Agent 能力，便于复用和测试。
安全性： 限制文件访问路径（如只允许访问特定资源目录 ROOT_RESOURCE），防止路径遍历攻击。
交互性： 利用 WebUI 或 CLI 提供人机交互接口，让用户能直观看到分析结果。
如何解决（实施步骤）：
1. 环境准备：
安装依赖： dashscope (用于调用 Qwen API), qwen-agent (Agent 框架)。
配置 API Key： 通过环境变量 DASHSCOPE_API_KEY 管理密钥。
2. 资源管理：
定义 ROOT_RESOURCE 路径，确保 Agent 只能在该目录下读取文件，保障系统安全。
3. Agent 初始化 (init_agent_service)：
模型配置： 指定使用的 LLM（如 qwen-max）。
工具注册： 逻辑上需注册一个 read_txt_file 工具，该工具接收文件名，拼接 ROOT_RESOURCE 路径后读取内容。
系统提示词： 设定 Agent 的角色为"TXT 文件统计助手"，明确其任务是读取文件并分析。
4. 运行逻辑：
用户输入指令（如"分析 data.txt"）。
Agent 识别意图，调用文件读取工具获取内容。
LLM 根据内容进行统计分析并生成自然语言报告。
### S:
- 必须提到对文件读取路径的限制（ROOT_RESOURCE），不能随意读取系统文件
- 正确使用 Agent 框架（如 Qwen-Agent）的初始化流程，包括 LLM 配置和工具/函数注册
- 涵盖从环境变量配置、依赖安装到 Agent 实例化的全过程
### GOOD:
- 详细解释了 ROOT_RESOURCE 的作用及其在安全沙箱中的意义
- 清晰描述了 Agent 如何通过 Function Calling 机制触发文件读取操作
- 提到了 API Key 的安全管理方式（环境变量而非硬编码）
### BAD:
- 直接在代码中硬编码 API Key
- 允许 Agent 读取任意路径的文件（如 /etc/passwd），缺乏安全边界意识
- 混淆了 Agent 的"思考过程"与"工具执行过程"，认为 LLM 直接具备了读文件能力（实际上是 LLM 调用工具读文件）
### FOLLOWUP:
- 如果 TXT 文件非常大（超过 LLM 上下文窗口），该如何优化这个 Agent 的处理逻辑？（提示：分块读取、Map-Reduce 策略）
- 如何为这个 Agent 添加"写入文件"的功能，同时保证不会覆盖重要数据？

---
<!-- id:llm_prompt_001 | category:提示词工程 | difficulty:2 | difficulty_label:中级 | type:scenario -->
### Q: 在业务场景中，如何系统性地设计一个高质量的 Prompt？请结合 Prompt Engineering 最佳实践说明你的方法论。
### SCENARIO: 你加入了一家电商公司的 AI 应用团队，负责优化客服机器人的回复质量。目前的机器人经常答非所问、输出格式混乱，业务方抱怨不断。你的 leader 要求你从 Prompt 工程的角度系统性地重构提示词，而不是零散地"碰运气"修改。你需要向团队阐述一套完整的 Prompt 设计方法论，并给出可落地的优化方案。
### A: 
为什么要系统化设计 Prompt：
Prompt 是人与模型交互的唯一接口： Prompt 是一串人为构造的输入序列，用于引导 GPT 等模型生成期望的输出。模型输出的质量上限很大程度上取决于提示词的质量。
零散调优不可复现： 没有方法论的修改如同"抽卡"，无法沉淀经验，也无法在团队协作中保持一致性。
最佳实践可量化提升效果： 明确目标、提供上下文、使用具体指示、提供示例等手段，能显著降低歧义、提升输出稳定性。
如何解决（设计方法论）：
明确目标： 清晰描述期望模型完成的任务或回答的问题，避免目标模糊导致输出偏离。
提供上下文： 为模型补充必要的背景信息，分为"有上下文"和"无上下文"两种模式，按需提供。
使用具体指示： 用精确的动词和约束描述需求（如"写一篇关于…的文章"），避免含糊措辞。
提供示例（Few-shot）： 通过输入-输出样例让模型模仿预期行为。
使用分步指示： 将复杂任务拆解为多个步骤，逐步引导模型完成。
控制输出长度： 明确字数或段落限制，防止冗长或过短。
使用占位符和模板： 用占位符（如 {topic}）构建可复用的提示词模板，便于工程化集成。
反复试验和调整： Prompt 优化是迭代过程，需不断测试、对比、修正。
指定输出格式： 明确要求 JSON、Markdown、表格、代码等结构化格式，便于下游程序解析。
使用多轮对话： 通过对话历史逐步细化需求，引导模型逼近理想结果。
使用反思和迭代： 让模型自我检查、自我修正输出，提升可靠性。
### S:
- 能系统列举多项最佳实践，而非只提"写清楚一点"
- 强调指定输出格式、使用模板占位符等工程化手段
- 认识到 Prompt 优化是反复试验的过程，而非一次成型
### GOOD:
- 能将最佳实践与业务场景结合（如"客服场景用模板+占位符保证格式稳定"）
- 提到 CRISPE 等框架（CR: Capacity and Role、I: Insight、S: Statement、P: Personality、E: Experiment）作为设计思路
- 区分"提示技术"（Zero-shot/Few-shot/CoT）与"工程实践"（模板、迭代、格式控制）两个层面
### BAD:
- 认为 Prompt 优化就是"换个说法试试"，缺乏体系
- 忽视输出格式控制，导致下游解析失败
- 不知道 Prompt 需要持续迭代，期望一版定稿
### FOLLOWUP:
- CRISPE 框架的五个要素分别是什么？如何在实际业务 Prompt 中套用？
- 当业务需求变更时，如何管理 Prompt 的版本和回归测试？

---
<!-- id:llm_prompt_002 | category:提示词工程 | difficulty:3 | difficulty_label:高级 | type:scenario -->
### Q: Zero-shot、Few-shot、Chain-of-Thought、ReAct、Reflexion、Prompt Chaining 这些提示技术分别适用于什么场景？请对比说明并给出选型建议。
### SCENARIO: 你的团队正在为一个智能问答系统选型提示技术。系统中有多种任务类型：简单的翻译请求、需要格式对齐的信息抽取、复杂的数学推理、需要调用外部工具的多步任务等。团队内部对"到底用哪种提示技术"争论不休，有人主张全部用 CoT，有人主张全部 Zero-shot 以节省 token。作为技术骨干，你需要给出一个清晰的对比分析和选型标准。
### A: 
为什么需要区分这些技术：
不同任务的复杂度、可靠性要求、token 成本不同，单一技术无法通吃。
每种技术解决的核心矛盾不同： Zero-shot 解决"零示例启动"，Few-shot 解决"格式对齐"，CoT 解决"推理能力激发"，ReAct 解决"推理+行动结合"，Reflexion 解决"自我纠错"，Prompt Chaining 解决"复杂任务分解"。
各技术定义与适用场景：
Zero-shot（零样本）： 不提供任何示例，直接让模型完成任务。适用于简单、模型已充分掌握的任务（如"将这句话翻译成英文"），成本最低。
Few-shot（少样本）： 在提示中提供若干输入-输出示例，让模型归纳模式。适用于需要格式对齐、风格模仿的任务（如情感分类、特定格式抽取）。
Chain-of-Thought（CoT，思维链）： 引导模型逐步推理，展示中间思考步骤后再给出答案。适用于数学计算、逻辑推理等复杂任务，能显著提升推理准确率。
ReAct（Reasoning + Acting）： 让模型交替进行推理（Reason）和行动（Act），可调用外部工具或获取外部信息。适用于需要查资料、调用 API 的多步任务，是 Agent 的核心范式。
Reflexion（反思）： 让模型在生成后自我评估、反思错误并改进输出。适用于对质量要求高、允许迭代的任务（如代码生成、文案打磨）。
Prompt Chaining（提示链）： 将复杂任务拆成多个子提示，前一步输出作为后一步输入，串联执行。适用于长流程任务（如"先写大纲->再写正文->最后润色"），提升可控性和可调试性。
选型建议：
简单任务 -> Zero-shot；需格式对齐 -> Few-shot；纯推理 -> CoT；需外部交互 -> ReAct；需高质量迭代 -> Reflexion；长流程拆解 -> Prompt Chaining。
### S:
- 能准确定义每种技术，不混淆 CoT 与 ReAct
- 能为每种技术给出典型适用场景
- 提到 Few-shot/CoT 会增加 token 消耗，需权衡成本与效果
### GOOD:
- 清晰区分 ReAct（推理+外部行动）与 CoT（纯内部推理链）
- 能举出图中类似的例子（如 Few-shot 的 "The dog is in the garden" 分类示例）
- 给出"由简入繁"的选型路径：先 Zero-shot，效果不足再升级
### BAD:
- 把所有技术混为一谈，认为"都是多写点提示"
- 在简单任务上滥用 CoT/Few-shot，浪费 token 且增加延迟
- 不知道 ReAct 需要工具调用能力支撑，纯文本场景误用
### FOLLOWUP:
- CoT 中"let's think step by step"这类引导语为什么有效？有没有更可控的写法？
- Prompt Chaining 与 Agent 的任务规划（Planning）有什么异同？

---
<!-- id:llm_prompt_003 | category:提示词工程 | difficulty:2 | difficulty_label:中级 | type:scenario -->
### Q: 在工程化落地中，如何设计结构化输出（JSON/Markdown/表格/代码）的 Prompt？请说明技巧与常见坑。
### SCENARIO: 你的公司正在搭建一个 LLM 数据管道：上游让模型从用户评论中提取结构化信息（姓名、年龄、城市等），下游用程序解析 JSON 入库。但上线后频繁出现 JSON 格式错误、字段缺失、多余解释文字等问题，导致解析服务报错。你被指派去解决这个"结构化输出不稳定"的问题，需要给出一套 Prompt 层面的解决方案。
### A: 
为什么要重视结构化输出：
结构化输出是 Prompt Engineering 中最能体现工程价值的部分： 模型输出要被程序消费，必须格式稳定、可解析。
自然语言输出对人不友好、对程序不可用；指定格式（JSON、Markdown、表格、代码）才能打通 LLM 与下游系统。
如何解决（设计技巧）：
明确指定格式类型： 在 Prompt 中直接声明"以 JSON 格式输出"、"生成 Markdown 表格"等，让模型知道目标形态。
提供格式示例（示例驱动）： 给出完整的输出样例（如 JSON 示例 {"name": "Alice", "age": 30, "city": "New York"}），让模型严格模仿结构。
定义字段与约束： 明确每个字段的名称、类型、含义，避免模型自由发挥（如规定 age 为数字、city 为字符串）。
禁止多余内容： 明确要求"只输出 JSON，不要任何解释文字"，防止模型附加前言后语破坏解析。
使用模板占位： 用模板固化结构，仅让模型填充内容部分。
结合分步与反思： 对复杂抽取任务，先让模型思考再按格式输出，或让其自检格式合法性。
常见坑：
模型输出带 markdown 代码块标记（```json），解析前需剥离。
字段名大小写或拼写不稳定，需示例强约束。
嵌套结构过深时模型易出错，应尽量扁平化。
应用场景举例（图中案例）：
数据处理： 从非结构化文本提取 JSON（如日期、地址解析）。
代码生成： 按规范生成函数代码。
函数定义： 生成符合签名的 Python 函数。
表格生成： 将数据整理为 Markdown 表格。
### S:
- 能给出"声明格式+示例+字段约束+禁止废话"的组合拳
- 提到解析端的防御性处理（剥离代码块标记、字段校验）
- 能列举 JSON、Markdown、表格、代码等多种结构化形态
### GOOD:
- 提到用完整示例（而非口头描述）锁定输出结构
- 意识到模型输出不稳定，需要"Prompt 约束 + 程序校验"双保险
- 结合图中示例（如生成 JSON 格式数据、Markdown 表格、代码模板）具体说明
### BAD:
- 只写"请输出 JSON"一句，不给示例和字段定义
- 完全依赖模型自觉，不做下游校验和容错
- 忽视 token 成本和格式复杂度的平衡，设计过深的嵌套结构
### FOLLOWUP:
- 当模型偶尔输出非法 JSON 时，除了重试，还有哪些工程手段？（提示：JSON mode、function calling、正则修复）
- 结构化输出与 Function Calling 的关系是什么？各自适用什么场景？

---
<!-- id:llm_prompt_004 | category:提示词工程 | difficulty:3 | difficulty_label:高级 | type:scenario -->
### Q: 如何在实际业务中应用 Prompt 技术完成数据处理、代码生成、创意生成等任务？同时如何防范 Prompt 带来的风险与安全问题？
### SCENARIO: 你负责为公司搭建一个"AI 生产力平台"，平台上要支持多种 Prompt 应用：数据提取与转换、代码生成、函数定义、分类任务、创意文案生成、内容生成、信息汇总等。安全团队同时提出警告：近期业界频发"提示注入攻击"和"敏感信息泄露"事件，要求你在平台设计阶段就纳入风险管控。你需要同时回答"怎么用得好"和"怎么防得住"两个问题。
### A: 
为什么需要"应用+安全"双视角：
Prompt 应用覆盖面广（数据处理、代码生成、创意生成、内容生成、汇总信息、分类任务等），是平台价值的来源。
但 Prompt 也是攻击面： 用户输入可能携带注入指令，模型可能输出敏感或有害内容，必须同步设计安全层。
如何应用（典型场景）：
数据处理： 用结构化输出 Prompt 从原始数据中提取、转换信息（如日期标准化、地址解析为 JSON）。
代码生成： 描述功能需求+输入输出示例，让模型生成可运行代码（如 calculate_average 函数）。
函数定义： 给定签名和描述，生成符合规范的函数体。
分类任务： 用 Few-shot 提供分类示例，让模型对文本归类（如情感正负面）。
创意生成： 设定角色、主题、风格，生成广告文案、故事等。
内容生成： 按大纲生成文章、报告、邮件等长文本。
汇总信息： 对长文档做摘要、要点提炼。
如何防范风险（安全设计）：
识别风险类型： 提示注入（用户输入覆盖系统指令）、敏感信息泄露、有害内容生成、幻觉输出误导业务。
输入侧管控： 对用户输入做隔离与过滤，明确系统指令优先级，限制可执行动作范围。
输出侧管控： 设置内容安全审核，对敏感字段脱敏，关键决策不直接依赖模型输出。
流程侧管控： 结合 Reflexion/校验环节自检，结构化输出加程序校验，重要操作人工确认。
持续监控： 记录 Prompt 与输出日志，定期红队测试，迭代加固。
### S:
- 能覆盖数据处理、代码生成、分类、创意、汇总等多类应用场景
- 主动识别提示注入、泄露等风险，而非只谈功能
- 给出输入、输出、流程三层管控，而非单一手段
### GOOD:
- 能结合图中案例（如日期提取、代码生成、分类任务）具体说明 Prompt 写法
- 将安全设计前置到平台架构阶段，体现工程成熟度
- 提到"关键决策人工确认"兜底机制
### BAD:
- 只谈应用不谈安全，或只谈安全不懂应用
- 对提示注入攻击毫无概念，允许用户输入直接拼接进系统指令
- 让模型输出直接驱动高危操作（如删库、转账）无任何校验
### FOLLOWUP:
- 请举例说明一次"提示注入攻击"的攻击路径，以及你的防御方案在哪一层拦截？
- 在创意生成类任务中，如何平衡"发散性"与"品牌合规性"的 Prompt 设计

---
<!-- id:llm_deploy_001 | category:部署 | difficulty:2 | difficulty_label:中级 | type:scenario -->
### Q: 在 Windows 环境下基于 Docker 本地部署 Coze 时，如何规划环境准备阶段以确保 Docker Desktop 稳定运行？请说明虚拟化方案选型与 Docker 性能优化的关键配置。
### SCENARIO: 你所在的团队希望在本地搭建私有的 Coze（扣子）AI 应用开发平台，以实现数据隐私安全并自由切换大模型服务商。你被指派负责在 Windows 10/11 开发机上完成部署。在动手拉取镜像前，你需要先向团队说明环境准备的完整方案：包括系统要求、虚拟化技术如何开启、以及 Docker Desktop 安装后必须做的性能优化配置，避免后续出现镜像拉取失败或 C 盘爆满的问题。
### A: 
为什么要重视环境准备：
底层依赖： Docker Desktop 在 Windows 上依赖 CPU 虚拟化技术，若 BIOS/UEFI 中未开启虚拟化，容器引擎根本无法启动。
网络与存储痛点： 国内直接拉取 Docker Hub 镜像极易失败；默认镜像和数据存储在 C 盘，长期运行会迅速占满系统盘。
如何解决（环境准备方案）：
系统与硬件检查：
操作系统需为 Windows 10/11 64位（专业版/企业版/教育版，Build 19041+），至少 4GB RAM。
确认 CPU 虚拟化已在 BIOS/UEFI 中启用。
虚拟化方案选型（二选一）：
WSL 2（推荐）： 官方推荐，性能更优，与 Linux 生态集成度高。通过管理员 PowerShell 执行 wsl --install，并用 wsl --set-default-version 2 确保使用 WSL2。
Hyper-V： 传统稳定方案，通过"控制面板->启用或关闭 Windows 功能"勾选 Hyper-V 及其子选项后重启。
Docker Desktop 安装与优化：
自定义路径： 用命令行 start /w "Docker Desktop Installer.exe" install --installation-dir=D:\Program Files\Docker 安装到非系统盘。
镜像加速器（关键）： 在 Settings->Docker Engine 的 JSON 中添加 registry-mirrors（如 DaoCloud、阿里云地址），加速 docker pull。
数据存储迁移： 在 Settings->Resources->Advanced 修改 "Disk image location" 到非 C 盘路径。
验证： 终端执行 docker --version 确认安装成功。
### S:
- 明确 Docker 依赖 CPU 虚拟化，并能对比 WSL 2 与 Hyper-V 两种方案
- 提到镜像加速器配置和存储路径迁移两个关键优化点
- 知道自定义安装路径到非系统盘的命令行方式
### GOOD:
- 能给出 WSL 2 的具体安装命令（wsl --install、wsl --set-default-version 2）
- 准确指出镜像加速器的配置位置（Docker Engine JSON 的 registry-mirrors 字段）
- 强调"先开虚拟化再装 Docker"的依赖顺序
### BAD:
- 不知道需要开启 CPU 虚拟化，导致 Docker 启动失败后无从排查
- 忽略镜像加速器配置，部署时卡在镜像拉取阶段
- 全程使用默认 C 盘路径，导致系统盘空间耗尽
### FOLLOWUP:
- WSL 2 与 Hyper-V 在架构上有何本质区别？为什么官方更推荐 WSL 2？
- 如果配置了镜像加速器仍然拉取失败，还有哪些排查方向？

---
<!-- id:llm_deploy_002 | category:部署 | difficulty:2 | difficulty_label:中级 | type:scenario -->
### Q: 部署本地 Coze 时，如何配置大语言模型（LLM）与 Embedding 模型的连接？请说明配置文件的定位、关键字段及参数获取方式。
### SCENARIO: 你已经完成了 Docker 环境准备并克隆了 Coze 源码（coze-studio）。现在需要让本地 Coze 平台能够调用云端大模型进行推理，并可选地启用知识库/文档问答功能。团队使用的是"火山方舟"平台提供的模型服务。你需要向同事演示如何正确配置 LLM 连接文件，以及如何通过环境变量接入 Embedding 模型，确保 base_url、api_key、model 等关键参数填写无误。
### A: 
为什么要这样配置：
解耦设计： Coze 本地实例仅作为开发平台，实际推理计算调用云端大模型 API，因此必须正确打通 LLM 连接。
配置驱动： LLM 通过 YAML 配置文件声明，Embedding 通过 .env 环境变量声明，两者分离便于独立管理。
如何解决（配置步骤）：
配置 LLM 连接：
进入 coze-studio/backend/conf/model/template 目录，复制模板文件（如 model_template_ark_doubao-seed-1.6.yaml）到上一级 model 目录并重命名（去掉 model_template_ 前缀）。
编辑该 YAML，修改 com_config 下三项关键字段：
base_url： 模型服务的 API 基础地址（REST API 域名部分）。
api_key： 模型服务提供的 API Key。
model： 模型服务的 Endpoint ID。
从火山方舟获取参数：
登录火山方舟平台，在"模型广场"创建模型服务（如 Doubao-seed-1.6）。
Endpoint ID 在"API 调用"页面获取；Base URL 取 REST API 请求地址的域名部分；API Key 在"API Key 管理"页面创建/复制。
配置 Embedding 模型（可选，用于知识库/文档问答）：
在 coze-studio/docker 目录复制 .env.example 为 .env。
填入关键环境变量： ARK_EMBEDDING_TYPE、ARK_EMBEDDING_MODEL（Endpoint ID）、ARK_EMBEDDING_KEY（API Key）、ARK_EMBEDDING_DIMS（模型维度，如 2048）、ARK_EMBEDDING_BASE_URL。
### S:
- 准确说出 LLM 配置文件路径与 Embedding 的 .env 路径
- 清楚 base_url/api_key/model 三个字段分别对应火山方舟的哪个参数
- 明白 Embedding 配置是启用知识库/向量化能力的前提
### GOOD:
- 能区分 LLM（YAML 配置）与 Embedding（.env 环境变量）两种不同的配置机制
- 准确说明 Endpoint ID 即为 model 字段的值
- 提到 ARK_EMBEDDING_DIMS 需根据具体模型填写正确维度
### BAD:
- 混淆 base_url 与完整请求 URL，或把 Endpoint ID 填错位置
- 不知道 Embedding 需要单独配置 .env，导致知识库功能不可用
- 直接修改 template 目录下的模板原文件，而非复制到上级目录重命名
### FOLLOWUP:
- 如果想接入非火山方舟的其他模型服务商（如 OpenAI 兼容接口），配置文件该如何调整？
- Embedding 模型维度（DIMS）填错会导致什么后果？

---
<!-- id:llm_deploy_003 | category:部署 | difficulty:2 | difficulty_label:中级 | type:scenario -->
### Q: 如何使用 Docker Compose 一键启动本地 Coze 服务？部署完成后如何验证，并请解析其底层架构组成。
### SCENARIO: LLM 与 Embedding 配置已完成，现在进入部署启动阶段。你需要在终端执行命令拉起所有 Coze 服务容器，并向团队解释这条命令每个参数的含义。启动后，你要说明如何验证部署成功，并画出（或描述）本地 Coze 的整体架构——哪些是前端、后端、中间件容器，哪些是外部云依赖，它们之间如何协同工作。
### A: 
为什么用 Docker Compose：
多容器编排： Coze 由多个服务（Web、Server、Gateway、MySQL、Redis 等）组成，Compose 通过 docker-compose.yml 统一编排，避免手动逐个启动。
Profile 机制： 通过 --profile 可灵活激活基础服务与可选服务。
如何解决（启动与验证）：
启动命令： 进入 coze-studio/docker 目录，执行 docker compose --profile "*" up -d。
docker compose： 编排多容器应用。
--profile "*"： 激活 yml 中定义的所有服务（含基础与可选服务）。
up： 创建并启动容器。
-d： 后台（detached）运行。
首次启动会下载所有镜像，耗时较长。
验证部署：
浏览器访问 http://localhost:8888。
成功标志： 能看到 Coze 欢迎界面，以及"项目开发""个人空间"等 UI 元素。
架构解析：
前端容器： coze-web（UI）。
后端容器： coze-server（业务逻辑）、coze-gateway、coze-workflow、coze-knowledge。
中间件容器： MySQL、Redis。
外部云依赖： 火山方舟 API（提供 LLM 与 Embedding 能力），通过 HTTP/S 调用。
所有容器运行在 Docker Engine 内，由 Docker Compose 读取 yml 编排，宿主机为开发者本机。
### S:
- 能逐项解释 --profile "*"、up、-d 的含义
- 明确访问地址 localhost:8888 及成功标志
- 能区分前端/后端/中间件容器与外部云依赖
### GOOD:
- 准确列出各容器角色（coze-web 前端、coze-server 后端、MySQL/Redis 中间件）
- 强调"本地容器 + 云端模型 API"的混合架构特点
- 提到首次启动需下载镜像、耐心等待
### BAD:
- 不知道 --profile "*" 的作用，导致部分可选服务未启动
- 误以为大模型推理也在本地容器内完成（实际调用云端 API）
- 验证时访问错误端口或不知道成功标志
### FOLLOWUP:
- 如果想只启动部分服务（如不含 monitoring），--profile 该如何调整？
- coze-gateway 与 coze-server 在架构中各自承担什么职责？

---
<!-- id:llm_deploy_004 | category:部署 | difficulty:3 | difficulty_label:高级 | type:scenario -->
### Q: 本地部署 Coze 过程中遇到"端口冲突"和"镜像拉取失败"两类典型问题，如何定位并解决？请结合 docker-compose.yml 配置说明。
### SCENARIO: 你在执行 docker compose up 启动 Coze 时遇到了阻碍：一是终端报错提示 "port is already allocated"，经查是主机的 3306 端口已被本地 MySQL 占用；二是部分镜像拉取极其缓慢甚至超时失败。团队成员等着用平台，你需要快速给出这两个问题的根因分析和解决方案，并说明修改端口映射后是否会影响 Coze 内部服务间的通信。
### A: 
为什么要分类处理：
端口冲突属于"宿主机资源竞争"问题，需调整端口映射；镜像拉取失败属于"网络可达性"问题，需回到加速器配置。两者根因不同，解决方法不同。
如何解决：
问题一：端口冲突（如 3306）：
现象： docker compose up 报错 "port is already allocated"。
原因： 宿主机已有服务（如本地安装的 MySQL）占用了 3306 端口。
解决： 打开 coze-studio/docker/docker-compose.yml，找到 mysql 服务的 ports 配置，将主机映射端口改为未被占用的端口，例如把 "3306:3306" 改为 "3307:3306"。
关键原理： 修改后，Coze 内部容器间仍使用 3306 端口访问 MySQL（容器网络内部端口不变），只是宿主机映射端口变为 3307，因此不影响内部通信，仅避免与宿主机冲突。
问题二：镜像拉取缓慢或失败：
原因： 网络问题，无法稳定连接 Docker Hub。
解决： 回到环境准备阶段，检查 Docker Desktop->Settings->Docker Engine 中是否正确配置了国内镜像加速器（registry-mirrors），确认 JSON 格式无误后重启 Docker 重试。
### S:
- 能给出修改 docker-compose.yml 中 ports 映射的具体操作
- 明确"改宿主机映射端口不影响容器内部通信"这一关键点
- 知道镜像拉取失败应回到镜像加速器配置排查
### GOOD:
- 准确解释 "3307:3306" 中冒号前后分别是宿主机端口与容器内部端口
- 强调容器间通信走 Docker 内部网络，仍用 3306，无需改其他服务配置
- 给出"改完端口->重新 up"的完整闭环
### BAD:
- 直接把容器内部端口也改掉，导致 Coze 后端连不上数据库
- 遇到拉取失败只会反复重试，不知道配置镜像加速器
- 修改 yml 后忘记重新启动容器使配置生效
### FOLLOWUP:
- 除了改端口映射，还有哪些方式可以解决端口冲突？（提示：停掉占用端口的本地服务）
- 如何查看当前是哪个进程占用了宿主机的 3306 端口


---

<!-- id:llm_rag_001_v1 | category:RAG | difficulty:2 | difficulty_label:中级 | type:scenario | variant_of:llm_rag_001 -->
### Q: 请简述什么是 GraphRAG？它的核心目的是什么？
### SCENARIO: 候选人在简历中提到了熟悉知识图谱与大模型结合的应用开发，面试官希望确认其对 GraphRAG 基础概念的理解。
### A:
为什么： GraphRAG（Graph Retrieval-Augmented Generation，图检索增强生成）是一种将知识图谱（Knowledge Graph）与大语言模型（LLM）结合的技术架构。它在传统 RAG 的“向量检索+生成”基础上，引入了图结构来组织与检索知识。

如何解决/核心目的：
解决传统 RAG 的“碎片化检索”问题： 传统 RAG 基于向量相似度召回独立文本块，难以捕捉实体之间的多跳关系。GraphRAG 通过图结构将实体、关系、属性显式建模，能检索到跨文档、跨段落的关联信息。
解决全局性/总结性问题： 对于“整个知识库中反复出现的主题是什么”这类全局问题，传统 RAG 只能召回局部片段，GraphRAG 可通过社区检测与层次化摘要，从全局视角生成答案。
解决幻觉与可解释性问题： 检索路径沿图谱边展开，生成时可追溯实体与关系来源，约束模型输出，减少胡编乱造，并提升可解释性。
解决时效性与私有领域知识： 无需重新训练模型，只需更新图谱中的节点与边即可让模型获取最新、垂直领域的知识；数据保留在本地或私有图数据库中，无需微调上传到公有云模型。
### S:
- 能准确说出 GraphRAG 的全称及“图检索+生成”的基本原理，明确其与传统 RAG 的区别在于引入知识图谱/图结构
- 能列举出 GraphRAG 解决的至少两个核心痛点（如多跳关系、全局总结、可解释性、幻觉、私有数据）
- 理解 GraphRAG 与微调（Fine-tuning）的区别，知道 GraphRAG 不需要改变模型权重
- 能说明图结构在检索中的作用（实体/关系/社区），而非仅把图当作另一种向量索引
### GOOD:
- 回答结构清晰，先定义 GraphRAG 与传统 RAG 的差异，再讲价值
- 能够结合业务场景（如金融风控关系网络、医疗知识图谱问答、企业供应链图谱）举例说明 GraphRAG 的必要性
- 能提到 GraphRAG 的典型流程：图谱构建→社区检测→层次化摘要→图检索→生成
### BAD:
- 将 GraphRAG 等同于传统 RAG，认为只是把向量库换成图数据库，不理解图结构带来的多跳与全局检索能力
- 将 GraphRAG 等同于微调，认为需要训练模型参数
- 只能说出定义，无法解释为什么要用 GraphRAG（即不知道它解决了传统 RAG 的哪些不足）
### FOLLOWUP:
- GraphRAG 与传统 RAG 相比，各自的优缺点是什么？在什么场景下你会优先选择 GraphRAG 而不是传统 RAG？
- 构建 GraphRAG 时，如何从非结构化文档中抽取实体与关系？如果抽取质量不高，会对最终生成效果产生什么影响？

---

<!-- id:llm_transformer_001_v1 | category:Transformer | difficulty:2 | difficulty_label:中级 | type:scenario | variant_of:llm_transformer_001 -->
### Q: 在搭建一个实时金融风控引擎时，你会如何设计其中的“时序特征编码器”模块？请说明它的内部子层构成，以及为什么必须引入残差连接和层归一化。

### SCENARIO: 面试官让你为一个高频交易反欺诈系统设计核心的时序特征编码器，并解释其内部结构和训练稳定性设计。

### A:
在金融风控场景中，我们需要对每笔交易前后的行为序列（如登录、转账、设备切换）进行深度编码。这个编码器本质上是一个多层堆叠的时序特征提取器，其内部结构可以类比为 Transformer 的 Encoder。

**内部子层构成：**
1. **多头时序自注意力子层**：对序列中任意两个时间步的行为建立依赖关系，比如“10 秒前的异地登录”与“当前的大额转账”之间的关联。多头机制让模型同时关注不同时间尺度和不同行为类型的模式。
2. **位置前馈网络子层**：对每个时间步的特征独立进行非线性变换，通常由两层全连接加激活函数组成，各时间步共享参数，用于增强特征表达能力和引入非线性。

**残差连接与层归一化的设计动机：**
每个子层都采用 `输出 = LayerNorm(x + Sublayer(x))` 的结构。原因在于：
- **梯度消失与网络退化**：风控模型往往需要堆叠较深（如 6 层以上）才能捕捉复杂的长程欺诈模式。如果没有残差连接，梯度在反向传播中会逐层衰减，浅层参数几乎无法更新；同时深层网络可能出现退化——训练误差不降反升。
- **残差连接的作用**：让梯度可以“短路”回传到浅层，缓解梯度消失；同时网络只需学习目标与输入之间的残差映射，而不是完整映射，优化难度大幅降低。
- **层归一化的作用**：对每个样本的特征维度做归一化，稳定各层输入分布，加速收敛，并且不依赖 batch 大小，适合线上实时推理中 batch 波动大的场景。

### S:
- 准确说出两个子层：多头自注意力 + 位置前馈网络，并给出 `LayerNorm(x + Sublayer(x))` 的残差+LN 公式
- 解释残差连接对梯度消失和网络退化问题的缓解作用
- 说明 FFN 在各时间步/位置间参数共享
- 能结合金融风控场景说明层归一化相比批归一化在实时推理中的优势

### GOOD:
- 能写出 `output = LayerNorm(x + Sublayer(x))`，并进一步区分 Post-LN 与 Pre-LN 对训练稳定性的影响
- 理解残差让网络学习“残差映射”而非完整映射，并结合风控场景说明深层堆叠的必要性
- 能指出层归一化不依赖 batch 统计量，适合线上单笔或小批量实时推理

### BAD:
- 只提自注意力子层，遗漏前馈网络子层
- 认为残差连接只是为了“加快收敛”，说不出网络退化问题
- 把层归一化和批归一化混为一谈，无法解释实时风控场景下的选择理由

### FOLLOWUP:
- 在这个风控编码器中，如果要把层归一化换成批归一化，线上推理时可能遇到什么问题？
- 这个编码器的参数和计算量主要集中在哪些部分？如果要做线上低延迟优化，你会从哪里入手？

---

<!-- id:llm_skills_001_v1 | category:Skills | difficulty:2 | difficulty_label:中级 | type:scenario | variant_of:llm_skills_001 -->
### Q: 请清晰区分 Prompt、Agent、Agent Skills、MCP、Rules 和 Memory 这六个概念，并结合智能客服系统的设计说明它们各自的关注点。

### SCENARIO: 候选人应聘某电商平台的 AI 客服系统开发岗，简历中写了"主导设计多轮对话 Agent"。面试官要求其从系统架构角度梳理这六个概念的边界，判断其是否具备将业务需求拆解为不同抽象层的能力。

### A:
为什么： 这六个概念对应 AI 应用从"单次交互"到"长期运行系统"的不同抽象层级。在智能客服这类多轮、多工具、多约束的场景中，混用概念会直接导致架构耦合、复用性差、行为不可控。

各概念关注点与定义：

- **Prompt（提示词）**：关注"这一次说什么"。是单次请求的输入指令，用完即弃，不具备跨会话复用能力。例如用户问"我的订单到哪了"，系统拼装的那段话就是 Prompt。
- **Agent（智能体）**：关注"谁在干活"。是一个正在运行的执行实例，类似进程——任务结束即销毁。关键误区纠正：Agent 实例本身不可复用，真正被复用和版本管理的是它的配置（Prompt 模板、Skills、Rules、Memory 结构等）。
- **Agent Skills（技能）**：关注"这类事怎么做"。是可复用的工作方法模块，沉淀的是某一类问题的处理 SOP。例如"退换货处理流程"就是一个 Skill，跨会话、跨用户复用。
- **MCP（模型上下文协议）**：关注"用什么工具/数据源"。是连接外部系统的协议层，负责让 Agent 能查订单库、调用物流 API、访问知识库等。
- **Rules（规则）**：关注"不能做什么"。是全局行为约束，始终生效，类似法律底线。例如"不得泄露用户手机号""不得承诺超出政策的赔付"。
- **Memory（记忆）**：关注"记住什么"。负责存储长期状态，例如用户的历史投诉记录、偏好、当前工单上下文。

一句话总结：Prompt 是这一次的话术，Agent 是当班客服（下班即销毁），Skills 是培训手册里的 SOP，MCP 是工单系统和物流接口，Rules 是合规红线，Memory 是客户档案。

### S:
- 准确说出六个概念各自的"关注点"关键词，并能映射到客服系统的具体组件
- 纠正"Agent 可复用"的常见误区，指出真正复用的是配置（Prompt/Skills/Rules 等）
- 明确 Skills 的本质是"可复用的 SOP/工作方法模块"，而非一次性指令
- 能区分 Skills（怎么做）、MCP（用什么工具）、Rules（不能做什么）三者的边界
- 能说明 Memory 与 Prompt 的区别：前者是持久状态，后者是临时输入

### GOOD:
- 能用"当班客服 vs 培训手册 vs 工单系统 vs 合规红线 vs 客户档案"这类类比，把六个概念串成一个完整系统视图
- 能指出 Agent 实例像进程、配置像镜像/模板，解释为什么复用要落在配置层
- 能结合客服场景说明 Skills 与 MCP 的配合关系，而非孤立罗列定义

### BAD:
- 把 Prompt 和 Skills 混为一谈，认为写好一段客服话术就等于有了一个 Skill
- 认为 Agent 实例本身可以跨会话复用，忽略其"运行态、任务结束即销毁"的本质
- 把 Rules 和 Memory 混淆，认为"记住用户偏好"属于规则约束

### FOLLOWUP:
- 在客服系统中，如果用户要求"帮我查一下上周的退款进度"，这个请求会同时触发哪些概念层的协作？请按调用顺序说明。
- 当 Rules 与某个 Skill 内的步骤发生冲突时（例如 Skill 流程要求先确认身份，但 Rules 要求不得主动索要隐私信息），系统应如何设计优先级与兜底策略？

---

<!-- id:llm_tool_001_v1 | category:工具调用 | difficulty:2 | difficulty_label:中级 | type:scenario | variant_of:llm_tool_001 -->
### Q: 在智能座舱语音助手接入大量车载控制技能时，为什么应该"用能力掩码而非动态卸载"来管理技能上下文？请解释 Auto / Required / Specified 三种技能触发模式的实现原理。

### SCENARIO: 某车企的智能座舱助手接入了数百个车载控制技能（空调、车窗、座椅、导航、音乐、氛围灯等），团队曾尝试根据用户意图动态加载/卸载技能，结果出现响应延迟升高、模型误触发危险操作（如行驶中开窗）等问题，面试官考察候选人的技能治理策略。

### A:
为什么：
缓存代价： 技能定义通常位于上下文最前面，任何增删都会改变前缀，直接作废 KV-Cache，导致首 token 延迟升高。
一致性代价： 对话历史中提到的技能一旦从上下文消失，模型会困惑甚至幻觉，可能在后续轮次误触发已卸载的技能。
能力代价： 技能越多，模型越容易误行动或走低效路径，"技能越多的助手可能越笨"，在车载场景还可能引发安全隐患。
如何解决：
核心原则 Mask, Don't Remove： 技能定义常驻上下文前部，不需要的技能用 mask 屏蔽而非物理删除；用上下文感知的状态机管理技能，在解码阶段用 logits mask 禁止或强制某些动作；技能名统一前缀化（如 hvac_、window_、seat_）便于按组 mask。
三种触发模式（通过给 assistant 预填充前缀实现，以 Hermes 格式为例）：
Auto（自动模式）： 模型可调用也可不调用技能，完全自主决定。实现：仅预填充回复前缀（<|im_start|>assistant），模型既可输出普通文本也可发起技能调用。适合大多数常规场景，自由度最高。
Required（必须调用）： 强制模型必须调用某个技能（具体调哪个由模型选择），不能直接回复文本。实现：预填充到技能调用起始标记（如 <|im_start|>assistant<tool_call>），把解码输出空间锁死在"技能调用"上。适合"这一步非借助技能不可"的场景（如调节空调温度、查询导航路线）。
Specified（指定调用）： 强制模型必须调用指定的某一个技能，连技能选择都替模型决定。实现：进一步预填充到具体技能名与参数起始（如 <|im_start|>assistant<tool_call>{"name": "hvac_set_temp", "arguments":），模型只需补全剩余参数。适合"明确知道该用哪个技能"的场景，从根本上杜绝选错，尤其在行驶安全相关操作中。
### S:
- 理解 Mask, Don't Remove 的核心原则（技能常驻上下文、用 mask 而非删除）及其对 KV-Cache 与上下文一致性的意义
- 能解释 Auto / Required / Specified 三种模式的自由度差异（可调可不调 -> 必须调 -> 指定调）
- 知道通过预填充 assistant 前缀约束解码行为（logits/解码阶段控制）的实现原理
- 能结合车载安全场景说明 Specified 模式对杜绝误触发的价值
### GOOD:
- 能说明"技能越多的助手可能越笨"的根因（选择空间增大导致误行动、走低效路径），并联系到行驶安全
- 提到技能名前缀化（hvac_/window_/seat_）与按组 mask 的工程实践
### BAD:
- 认为像 RAG 一样动态增删技能是合理的，忽略 KV-Cache 失效与上下文一致性问题
- 混淆 Required 与 Specified 的区别，说不出二者的自由度差异
### FOLLOWUP:
- 在车载场景中，如何结合车辆状态（如车速、挡位）动态调整技能掩码？
- 当技能数量超过上下文窗口限制时，如何做技能分层或按需加载？

---

<!-- id:llm_memory_001_v1 | category:Memory | difficulty:2 | difficulty_label:中级 | type:scenario | variant_of:llm_memory_001 -->
### Q: 在基于大模型的医疗问诊助手中，为什么患者长期记忆的状态维护至关重要？请介绍最基础的两种记忆获取方式：全量历史问诊记录与滑动窗口。

### SCENARIO: 某互联网医院正在开发一款多轮问诊助手，上线后发现患者经常抱怨“医生助手忘了刚才说的症状”“重复问已经回答过的问题”。面试官请你从最基础的记忆机制讲起，考察你对大模型记忆组件的理解。

### A:
为什么： 大模型本身是无状态的，每次推理调用都是一次独立的计算过程，不会自动保留上一轮的信息。多轮问诊的连贯性完全依赖外部记忆组件，把与当前问题相关的历史上下文重新拼接到 prompt 中再喂给模型。记忆因此被视为 Agent 架构中的关键组件之一。

两种基础方式：

1. 获取全量历史问诊记录（ConversationBufferMemory）：
- 原理： 把患者从首轮到最后一次的所有对话内容完整存入 memory，每轮调用时全部加载进 prompt。
- 场景： 慢病管理问诊——患者先描述高血压用药史，又提到近期头晕、睡眠差，助手需要记住前面所有症状和用药细节，才能给出连贯、安全的建议。
- 缺点： 上下文随轮次线性增长，token 成本和响应延迟持续上升，容易超出模型上下文窗口上限；同时可能引入大量无关历史，干扰当前判断。

2. 滑动窗口获取最近部分问诊记录（ConversationBufferWindowMemory）：
- 原理： 只保留最近 k 次互动（如 k=2），丢弃更早的历史记录。
- 场景： 轻症快速咨询——患者先问感冒药怎么吃，再问能否同时吃退烧药，助手只需聚焦最近一两轮问题即可，回复更快、更聚焦。
- 缺点： 窗口外的早期信息被彻底丢弃，无法回溯远期上下文；如果关键病史出现在很早的轮次，后续回答可能遗漏重要信息。

### S:
- 说明大模型无状态、记忆是 Agent 关键组件
- 准确说出 BufferMemory（全量）与 BufferWindowMemory（滑动窗口 k）的原理差异
- 指出各自优缺点与适用场景
- 能结合医疗问诊场景说明“全量保连贯 vs 窗口省成本但丢远期信息”的权衡

### GOOD:
- 能对应到 LangChain 具体类名并写出关键参数（如 k=2）
- 能结合医疗场景指出全量记忆有助于追踪病史，滑动窗口适合轻症短对话
- 能清晰对比 token 成本、延迟、信息完整性之间的权衡

### BAD:
- 认为模型自己能记住历史，不需要外部 memory
- 混淆 Buffer 和 Window 的区别，比如把滑动窗口说成保留全部历史
- 只背概念，无法结合问诊场景说明适用性

### FOLLOWUP:
- 滑动窗口的 k 值在医疗问诊场景中如何选取？有没有动态调整的策略？
- 全量问诊记录超过上下文窗口时，除了滑动窗口还有什么办法？

---

<!-- id:llm_ft_001_v1 | category:微调 | difficulty:2 | difficulty_label:中级 | type:scenario | variant_of:llm_ft_001 -->
### Q: 在医疗影像辅助诊断场景中，团队要为一个预训练的视觉-语言大模型适配“肺炎X光片报告生成”任务，纠结是进行全量微调还是采用提示学习（Prompt Learning）。请从动机和原理出发，解释为什么需要提示学习，它是什么，以及相比全量微调有什么优势？

### SCENARIO: 你是医疗AI公司的算法工程师，面试官让你针对一个预训练的视觉-语言大模型（如CLIP或BioViL），说明在标注数据有限、计算资源紧张的情况下，如何用提示学习替代全量微调来完成肺炎X光片报告生成任务。

### A:
为什么需要：全量微调（Full Fine-Tuning）需要更新预训练模型的所有参数，在医疗影像领域，标注数据稀缺、GPU资源昂贵，全量微调极易过拟合且成本极高；而如果只固定大部分层、仅微调最后几层，又难以让模型充分理解“肺炎X光片”这种专业领域与报告生成任务之间的语义鸿沟。因此需要一种介于“零样本提示”和“高成本全量微调”之间的高效适配方案。

什么是提示学习：提示学习不是在输入时随便写一句自然语言指令，而是将下游任务重新形式化为一个“完形填空”或“掩码预测”问题，并引入少量可学习的连续向量（软提示）或离散模板（硬提示），让预训练模型在保持主体参数冻结的情况下，通过优化这些提示参数来适配新任务。例如在肺炎X光片报告生成中，可以把任务转换为：给定影像特征，在模板“该X光片显示[MASK]”中预测“肺部有浸润影/无异常”等医学描述，让模型学习影像特征与报告文本之间的关联。

优点：
- 最小化微调参数量与计算复杂度：只需训练少量提示向量（通常不到总参数的1%），大幅降低显存和训练时间。
- 缓解训练成本与数据依赖：在医疗标注数据只有几百例时，提示学习能利用预训练模型已学到的医学视觉-语言知识，实现高效迁移，避免全量微调带来的灾难性遗忘。
- 灵活适配多任务：同一预训练模型可通过不同提示快速适配肺炎、气胸、结节等多种报告生成任务，无需为每个任务保存一份全量微调权重。

### S:
- 说清全量微调在医疗场景下数据少、算力贵、易过拟合的两难困境
- 解释提示学习是把任务转为“填空/掩码预测”形式，并优化少量提示参数
- 点明核心优点：参数少、成本低、高效迁移，且能缓解灾难性遗忘
- 能结合医疗影像报告生成的具体例子说明任务重构思想

### GOOD:
- 能用“该X光片显示[MASK]”或类似模板说明如何将报告生成转为完形填空
- 理解提示学习是连接预训练视觉-语言知识与下游医疗任务的桥梁，而非简单的“写提示词”
- 能对比全量微调与提示学习在参数量、显存、数据需求上的具体差异

### BAD:
- 把提示学习等同于“在输入里加一句指令”的工程技巧，忽视其作为参数高效微调范式的一面
- 说不出提示学习相对全量微调在参数效率、灾难性遗忘方面的优势
- 无法结合医疗影像场景说明任务重构的具体形式

### FOLLOWUP:
- 在医疗影像报告中，软提示（连续向量）和硬提示（离散模板）各有什么优缺点？你会如何选择？
- 如果预训练模型本身没有见过任何医学影像，提示学习还能有效吗？为什么？

---

<!-- id:llm_mcp_001_v1 | category:MCP | difficulty:2 | difficulty_label:中级 | type:scenario | variant_of:llm_mcp_001 -->
### Q: 你正在为一家三甲医院开发一套临床辅助决策助手，该助手需要读取患者本地电子病历（如PDF/HL7 FHIR资源）、查询院内药品库存与过敏史数据库、并调用外部医学知识库API。医院信息科要求所有外部工具调用必须经过标准化接口，且不能直接暴露HIS系统给LLM。请结合MCP协议说明你的架构设计方案。

### SCENARIO: 你作为医疗AI团队的架构师，需要设计一个符合医疗数据安全规范（如HIPAA等保）的LLM工具调用架构。助手要能访问本地病历文件、院内数据库和外部医学API，同时确保LLM无法直接触碰任何后端系统。

### A:
为什么采用MCP协议：
- 解耦与安全隔离：MCP将LLM应用与具体工具实现分离，LLM只通过标准JSON-RPC 2.0接口通信，不直接接触文件系统或数据库，避免权限滥用。在医疗场景中，这意味着LLM永远无法直接读取病历原文或执行SQL，所有敏感操作都被封装在受控的MCP Server内。
- 统一协议栈：无论底层是本地PDF病历、FHIR资源、SQL数据库还是HTTP医学API，都封装成MCP Server，客户端只需处理一种协议，降低复杂度。
- 动态发现与组合：支持MCP Inspector等工具自动发现可用Server，便于模块化扩展新工具（如新增“药物相互作用检查”Server）。

如何解决：
1. 架构分层：
- LLM应用层：仅含MCP Client，负责解析临床自然语言指令并转换为MCP请求。
- MCP Server层：分别部署File Server（读取本地PDF/FHIR病历）、DB Server（查询药品库存与过敏史）、API Server（调用外部医学知识库）。
- 传输层：使用stdio（本地进程间）或SSE（跨网络）作为通信载体。
2. 安全控制：
- 每个Server独立运行沙箱环境，限制其访问范围（如File Server只能读指定病历目录，DB Server只能执行预定义查询模板）。
- 通过MCP Protocol的capabilities字段声明权限，Client按需授权，例如过敏史查询需要额外审计日志。
- 所有工具调用记录审计日志，满足医疗合规要求。
3. 扩展机制：
- 新增工具只需开发对应MCP Server并注册到Inspector，无需修改LLM主程序。
- 支持多Server并行调用（如同时查药品库存+调医学API），提升响应效率。

### S:
- 正确识别MCP的核心价值：解耦、安全、标准化
- 清晰描述三层架构（Client/Server/Transport）及各自职责
- 提出具体的安全措施（沙箱、能力声明、审计日志）和扩展方案（动态注册）
- 结合医疗场景说明敏感数据隔离（如LLM不直接接触病历原文）

### GOOD:
- 能结合医疗场景举例说明各组件作用（如“File Server专管FHIR资源解析，DB Server只暴露参数化查询接口”）
- 强调协议无关性（stdio/SSE均可承载JSON-RPC），并说明SSE在跨科室网络中的适用性
- 提及生态工具链（MCP Inspector用于调试和发现），并关联医疗合规审计需求

### BAD:
- 混淆MCP与普通API网关，未突出“LLM专用协议”特性
- 忽略安全设计，假设LLM可直接调用HIS数据库或读取病历文件
- 将MCP Server等同于微服务，忽视其轻量级、单一职责特点，导致架构过度复杂

### FOLLOWUP:
- 如果医院要求所有患者数据不得离开内网，但外部医学知识库API必须通过公网调用，MCP架构该如何调整？（提示：考虑SSE与stdio的混合部署及数据脱敏）
- 当药品库存Server返回“库存充足”但过敏史Server返回“患者对该药过敏”时，Client层应如何设计决策融合与告警机制？

---

<!-- id:llm_prompt_001_v1 | category:提示词工程 | difficulty:2 | difficulty_label:中级 | type:scenario | variant_of:llm_prompt_001 -->
### Q: 你所在的团队正在为一款面向中小学的 AI 学习助手设计“错题讲解”功能。当前模型经常把数学题的讲解写成大段散文，学生看不懂，老师也无法直接插入教案。请从 Prompt 工程角度，系统说明你会如何设计一套可复用的高质量提示词方案，而不是靠反复“试提示词”。

### SCENARIO: 你加入了一家教育科技公司，负责 AI 学习助手的题目讲解质量。业务方要求：讲解必须分步骤、格式统一、能直接进入教案系统，并且要能适配不同学科和题型。你需要向团队给出一套完整的 Prompt 设计方法论和落地方案。

### A:
要系统化设计 Prompt，核心原因是：Prompt 是人与模型交互的唯一接口，模型输出质量的上限很大程度上由提示词质量决定；零散调优不可复现，无法沉淀团队经验；而明确目标、提供上下文、具体指示、示例、格式控制等最佳实践，可以显著降低歧义、提升稳定性。

具体方法论可以按以下维度展开：

1. 明确目标：先定义模型要完成的任务，例如“为一道初中数学错题生成分步骤讲解”，而不是笼统地说“讲一下这道题”。
2. 提供上下文：补充题目原文、学生答案、正确答案、学科、年级、教材版本等信息。上下文越充分，模型越不容易答非所问。
3. 使用具体指示：用精确动词和约束描述需求，例如“按‘审题—找知识点—逐步推导—易错点提醒—同类练习’五段式输出”。
4. 提供示例（Few-shot）：给出 1—3 个标准输入输出样例，让模型模仿讲解风格、步骤粒度和语气。
5. 使用分步指示：把复杂讲解拆成多个步骤，逐步引导模型完成，避免一次性生成导致结构混乱。
6. 控制输出长度：明确每步字数或总长度限制，防止过长或过短。
7. 使用占位符和模板：用 `{grade}`、`{subject}`、`{question}`、`{student_answer}` 等占位符构建可复用模板，便于工程化集成。
8. 反复试验和调整：Prompt 优化是迭代过程，需要测试、对比、修正，而不是一次成型。
9. 指定输出格式：明确要求 JSON、Markdown、表格等结构化格式，便于教案系统解析和展示。
10. 使用多轮对话：通过对话历史逐步细化需求，例如先让模型识别知识点，再生成讲解。
11. 使用反思和迭代：让模型自我检查、自我修正输出，例如“请检查推导步骤是否有误，并修正后再输出”。

在教育场景中，还可以把“提示技术”和“工程实践”分开：Zero-shot/Few-shot/CoT 属于提示技术；模板、占位符、版本管理、格式校验属于工程实践。两者结合，才能让错题讲解既稳定又可复用。

### S:
- 能系统列举多项 Prompt 最佳实践，而不是只说“写清楚一点”
- 强调指定输出格式、使用模板占位符等工程化手段
- 认识到 Prompt 优化是反复试验和迭代的过程，而非一次成型
- 能结合教育场景说明如何用上下文、示例、分步指示提升讲解质量
- 能区分提示技术与工程实践两个层面

### GOOD:
- 能结合教育场景给出可落地模板，例如“按五段式输出，并用 JSON 包裹每段内容”
- 提到 Few-shot 示例要覆盖不同学科或题型，保证泛化性
- 能说明如何用占位符和版本管理让 Prompt 适配多学科、多年级

### BAD:
- 认为 Prompt 优化就是“换个说法试试”，缺乏体系
- 忽视输出格式控制，导致教案系统无法解析
- 不知道 Prompt 需要持续迭代，期望一版定稿
- 只给一个笼统提示词，没有上下文、示例和结构约束

### FOLLOWUP:
- 如果同一道题要同时输出“学生版讲解”和“教师版教案”，你会如何设计 Prompt 结构来复用上下文？
- 当教材版本或考试大纲更新时，如何管理 Prompt 的版本和回归测试？

---

<!-- id:llm_deploy_001_v1 | category:部署 | difficulty:2 | difficulty_label:中级 | type:scenario | variant_of:llm_deploy_001 -->
### Q: 你所在的游戏工作室需要在一台 Windows 11 工作站上，用 Docker 本地部署一套开源的实时语音转文字（ASR）服务，用于内部测试游戏内语音聊天的字幕功能。在拉取镜像之前，请说明环境准备阶段需要做哪些关键规划，以确保 Docker Desktop 稳定运行、推理服务能正常调用 GPU，并避免后续出现镜像拉取失败或磁盘爆满的问题。

### SCENARIO: 你是游戏工作室的后端工程师，团队要在一台 Windows 11 工作站上基于 Docker 本地部署开源 ASR 服务，用于测试游戏内语音转文字功能。这台机器配有 NVIDIA 显卡，你需要先向团队说明环境准备的完整方案，包括系统与虚拟化检查、Docker Desktop 安装优化，以及 GPU 支持的前置条件。

### A:
为什么要重视环境准备：
底层依赖：Docker Desktop 在 Windows 上依赖 CPU 虚拟化技术，若 BIOS/UEFI 中未开启虚拟化，容器引擎根本无法启动。此外，本场景需要 GPU 推理，还需提前确认显卡驱动与容器 GPU 支持链路。
网络与存储痛点：国内直接拉取 Docker Hub 镜像极易失败；默认镜像和数据存储在 C 盘，ASR 模型动辄数 GB，长期运行会迅速占满系统盘。
如何解决（环境准备方案）：
系统与硬件检查：
操作系统需为 Windows 10/11 64位（专业版/企业版/教育版，Build 19041+），至少 4GB RAM（ASR 场景建议 16GB+）。
确认 CPU 虚拟化已在 BIOS/UEFI 中启用。
确认 NVIDIA 显卡驱动已安装，且版本满足 CUDA 容器要求。
虚拟化方案选型（二选一）：
WSL 2（推荐）： 官方推荐，性能更优，与 Linux 生态集成度高，且支持 GPU 直通（需在 WSL 内安装对应驱动）。通过管理员 PowerShell 执行 wsl --install，并用 wsl --set-default-version 2 确保使用 WSL2。
Hyper-V： 传统稳定方案，通过“控制面板->启用或关闭 Windows 功能”勾选 Hyper-V 及其子选项后重启。但 GPU 直通配置相对繁琐。
Docker Desktop 安装与优化：
自定义路径： 用命令行 start /w "Docker Desktop Installer.exe" install --installation-dir=D:\Program Files\Docker 安装到非系统盘。
镜像加速器（关键）： 在 Settings->Docker Engine 的 JSON 中添加 registry-mirrors（如 DaoCloud、阿里云地址），加速 docker pull。
数据存储迁移： 在 Settings->Resources->Advanced 修改 "Disk image location" 到非 C 盘路径，避免 ASR 模型撑爆系统盘。
GPU 支持前置： 安装 NVIDIA Container Toolkit（WSL 2 场景下由 Docker Desktop 集成支持），后续运行时需加 --gpus all 参数。
验证： 终端执行 docker --version 确认安装成功，并可用 docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi 验证 GPU 是否可在容器内调用。

### S:
- 明确 Docker 依赖 CPU 虚拟化，并能对比 WSL 2 与 Hyper-V 两种方案，且指出 WSL 2 对 GPU 直通更友好
- 提到镜像加速器配置和存储路径迁移两个关键优化点，并结合 ASR 模型体积说明存储迁移的必要性
- 知道自定义安装路径到非系统盘的命令行方式
- 提到 GPU 推理场景下需确认显卡驱动与容器 GPU 支持（NVIDIA Container Toolkit / --gpus all）

### GOOD:
- 能给出 WSL 2 的具体安装命令（wsl --install、wsl --set-default-version 2），并说明 WSL 2 支持 GPU 直通
- 准确指出镜像加速器的配置位置（Docker Engine JSON 的 registry-mirrors 字段）
- 强调“先开虚拟化再装 Docker”的依赖顺序，并补充 GPU 验证命令（nvidia-smi 容器内测试）

### BAD:
- 不知道需要开启 CPU 虚拟化，导致 Docker 启动失败后无从排查
- 忽略镜像加速器配置，部署时卡在镜像拉取阶段
- 全程使用默认 C 盘路径，ASR 模型下载后系统盘空间耗尽
- 完全忽略 GPU 支持的前置条件，容器启动后无法调用显卡做推理

### FOLLOWUP:
- 在 WSL 2 方案下，容器内调用 GPU 与在原生 Linux 上调用 GPU 在驱动链路上有何差异？为什么 WSL 2 不需要在发行版内单独安装 NVIDIA 驱动？
- 如果配置了镜像加速器仍然拉取失败，除了换镜像源，还有哪些排查方向？

