# Python 开发工程师面试题库

---
<!-- id:py_001 | category:Python基础 | difficulty:1 | difficulty_label:初级 -->
### Q: 解释 Python 的 GIL 是什么？它如何影响多线程编程？
### A: GIL (Global Interpreter Lock) 是 CPython 解释器中的全局解释器锁，确保同一时刻只有一个线程执行 Python 字节码。这导致 CPU 密集型任务在多线程下无法利用多核优势，但 I/O 密集型任务仍能从多线程中受益（因为 I/O 操作会释放 GIL）。解决方案包括使用 multiprocessing 多进程、异步编程 (asyncio)，或使用其他 Python 实现。
### S:
- 准确解释了 GIL 是全局解释器锁且存在于 CPython
- 正确区分了 CPU 密集和 I/O 密集型任务的不同影响
- 提到了 multiprocessing 或 asyncio 作为解决方案

---
<!-- id:py_002 | category:Python基础 | difficulty:2 | difficulty_label:中级 -->
### Q: 装饰器的实现原理是什么？举三个实际应用场景。
### A: 装饰器本质是接受函数作为参数并返回新函数的高阶函数，基于闭包实现。Python 的 @ 语法糖使得装饰器使用更简洁。应用场景：1) 日志记录 (自动记录函数调用时间和参数) 2) 权限校验 (Flask/Django 的 @login_required) 3) 缓存 (functools.lru_cache 缓存函数返回值)。
### S:
- 准确描述了装饰器是高阶函数+闭包的实现原理
- 提到了 @ 语法糖
- 给出了至少 2 个实际场景（日志、权限、缓存）

---
<!-- id:py_003 | category:Python基础 | difficulty:1 | difficulty_label:初级 -->
### Q: 列表推导式和生成器表达式的区别是什么？什么时候该用哪个？
### A: 列表推导式 `[x for x in range(10)]` 立即计算并返回完整列表，占内存。生成器表达式 `(x for x in range(10))` 惰性求值，返回生成器对象，不占内存，适合大数据量处理。当数据量大或不需要一次性获取所有结果时，优先使用生成器表达式。
### S:
- 区分了立即求值和惰性求值
- 提到了内存占用的区别
- 给出了选型建议

---
<!-- id:py_004 | category:Python基础 | difficulty:2 | difficulty_label:中级 -->
### Q: Python 中深拷贝和浅拷贝的区别？
### A: 浅拷贝 `copy.copy()` 只复制对象的第一层，内部的嵌套对象仍是引用同一内存。深拷贝 `copy.deepcopy()` 递归复制所有层级的对象，完全独立。对于不可变对象，深浅拷贝行为相同。
### S:
- 准确区分了浅拷贝只复制一层、深拷贝递归复制
- 提到了 copy.copy 和 copy.deepcopy
- 提到了不可变对象的特殊情况

---
<!-- id:py_005 | category:Python基础 | difficulty:2 | difficulty_label:中级 -->
### Q: Python 的 with 语句上下文管理器原理。在什么场景下使用？
### A: with 语句基于上下文管理器协议，对象需实现 `__enter__` 和 `__exit__` 方法。`__enter__` 在进入 with 块时执行并返回资源，`__exit__` 在离开时执行清理（无论是否异常）。常见场景：文件操作、数据库连接、线程锁。
### S:
- 提到了 __enter__ 和 __exit__ 两个核心方法
- 说明了 __exit__ 无论是否异常都会执行
- 给出了至少 1 个实际应用场景

---
<!-- id:py_006 | category:Python进阶 | difficulty:3 | difficulty_label:高级 -->
### Q: Python 的 asyncio 如何工作？协程和线程的区别是什么？
### A: asyncio 基于事件循环和协程，是单线程的并发模型。协程通过 async/await 实现协作式调度，遇到 await 时让出控制权。线程是操作系统调度的抢占式切换。协程开销远小于线程，适合 I/O 密集型高并发。但不能并行执行 CPU 密集任务。关键概念：event loop、coroutine、task、Future。
### S:
- 解释了 asyncio 是单线程事件循环模型
- 区分了协程的协作式调度和线程的抢占式调度
- 提到了协程适合 I/O 密集但不适合 CPU 密集

---
<!-- id:py_007 | category:Django | difficulty:2 | difficulty_label:中级 -->
### Q: Django ORM 中 select_related 和 prefetch_related 的区别？
### A: select_related 使用 SQL JOIN 一次性获取关联数据，适用于外键（ForeignKey）和一对一（OneToOne）关系。prefetch_related 使用额外的查询并 Python 层面连接，适用于多对多（ManyToMany）和反向外键。前者减少 SQL 查询次数但造成大表 JOIN，后者执行多条查询但各自简单。
### S:
- 区分了 JOIN 方式和额外查询方式
- 正确说明了各自适用场景（ForeignKey vs ManyToMany）
- 提到了 N+1 查询问题

---
<!-- id:py_008 | category:FastAPI | difficulty:2 | difficulty_label:中级 -->
### Q: FastAPI 和 Flask 的核心区别？高性能的原因是什么？
### A: FastAPI 支持异步原生、自动 OpenAPI 文档、Pydantic 数据验证、基于 Starlette 和 Uvicorn 高性能。Flask 是同步模型、WSGI + 插件生态成熟。FastAPI 高性能原因：1) 异步非阻塞 2) Starlette 底层 3) Uvicorn ASGI 服务器 4) Pydantic 高效序列化。选 FastAPI 用于 API 服务/微服务/高并发。
### S:
- 区分了异步原生和同步模型的核心差异
- 提到了 OpenAPI 文档自动生成
- 解释了异步、Starlette、ASGI 等高性能原因

---
<!-- id:py_009 | category:Python进阶 | difficulty:3 | difficulty_label:高级 -->
### Q: 如何处理 Python 项目中的循环导入问题？
### A: 1) 延迟导入（在函数内部 import）2) 重构模块结构，提取公共依赖到第三个模块 3) 使用 import 模块名而非 from 模块 import 成员 4) 利用 Python 的动态特性，模块首次导入后被缓存到 sys.modules。根本解决方法是遵循依赖反转原则。
### S:
- 提到了延迟导入作为临时方案
- 提到重构模块结构作为根本方案
- 提到了 sys.modules 缓存机制

---
<!-- id:py_010 | category:Python进阶 | difficulty:3 | difficulty_label:高级 -->
### Q: Python 的垃圾回收机制是怎样的？三种方式分别是什么场景？
### A: Python 使用引用计数为主、标记清除和分代回收为辅的 GC 机制。引用计数：对象引用数为 0 时立即回收。标记清除：处理循环引用，标记可达对象后清除不可达对象。分代回收：将对象按存活时间分为 0/1/2 三代，新对象在 0 代，存活越久代数越高，低代数回收频率更高。触发时机：引用计数实时，标记清除和分代回收在特定阈值触发。
### S:
- 提到了引用计数、标记清除、分代回收三种机制
- 解释了引用计数和标记清除各自的适用场景
- 提到了分代回收的三代划分和频率差异

---
<!-- id:py_011 | category:系统设计 | difficulty:3 | difficulty_label:高级 -->
### Q: 设计一个高并发的 Python 微服务，你会选择什么技术栈？为什么？
### A: FastAPI + asyncio + Redis 缓存 + PostgreSQL + Docker + RabbitMQ/Kafka。FastAPI 支持原生异步高性能；Redis 做缓存和限流；PostgreSQL 支持并发读取；RabbitMQ/Kafka 解耦服务间通信；Docker + K8s 编排。关键点：数据库连接池 (SQLAlchemy async)、避免 GIL 限制（CPU 密集服务考虑 Go/Java）、限流熔断保护下游、APM 链路追踪。
### S:
- 提到了异步框架 FastAPI
- 提到了消息队列解耦
- 提到了缓存、连接池、限流熔断等关键点
- 提到了容器化和编排

---
<!-- id:py_012 | category:Python基础 | difficulty:1 | difficulty_label:初级 -->
### Q: *args 和 **kwargs 分别是什么？在函数签名中如何使用？
### A: *args 将不定数量的位置参数打包为 tuple，**kwargs 将不定数量的关键字参数打包为 dict。函数定义时 `def func(a, *args, **kwargs)` 表示 a 为必须参数，其余位置参数进 args，关键字参数进 kwargs。调用时也可用 * 和 ** 解包序列和字典传入。
### S:
- 区分了 *args 是 tuple 和 **kwargs 是 dict
- 理解了位置参数和关键字参数的区别
- 提到了解包语法（调用时传递）

---
<!-- id:py_013 | category:Python基础 | difficulty:2 | difficulty_label:中级 -->
### Q: 什么是元类 (metaclass)？举一个实际应用场景。
### A: 元类是创建类的类，默认是 type。通过 `__new__` 和 `__init__` 控制类的创建过程。应用：1) Django ORM 用元类收集 Model 字段定义 2) 注册模式（自动将子类注册到注册表）3) API 接口参数自动校验。大部分场景用装饰器或继承就够了，不到万不得已不用元类。
### S:
- 准确描述了元类是"创建类的类"
- 提到了 __new__ 和 __init__ 控制类创建
- 给出了至少 1 个实际场景（Django ORM / 注册模式）

---
<!-- id:py_014 | category:DevOps | difficulty:2 | difficulty_label:中级 -->
### Q: Docker 部署 Python 应用时，Dockerfile 的最佳实践有哪些？
### A: 1) 使用多阶段构建减少镜像体积 2) 用 .dockerignore 排除不必要文件 3) 不要以 root 运行，创建专用用户 4) 生产用 gunicorn/uvicorn 而非 flask run 5) 依赖用 requirements.txt 锁定版本 6) 合理利用 Docker 层缓存（先 COPY requirements 再 RUN pip 最后 COPY 代码）7) 设置 HEALTHCHECK 健康检查 8) 合理配置 WORKDIR。
### S:
- 提到了多阶段构建
- 提到了 .dockerignore 和层缓存优化
- 提到了非 root 用户运行和健康检查

---
<!-- id:py_015 | category:Python进阶 | difficulty:2 | difficulty_label:中级 -->
### Q: Python 中的可变对象和不可变对象有哪些？这如何影响函数传参？
### A: 不可变对象：数字(int/float)、字符串、元组、frozenset；可变对象：列表、字典、集合、自定义对象。Python 函数的参数传递本质是"对象引用传递"：实参把对象的引用副本传给形参，既不是值传递也不是引用传递。不可变对象在函数内重新赋值不影响外部（因为创建了新对象），可变对象在函数内修改内容会影响外部。
### S:
- 正确列举了可变和不可变对象的类型
- 理解了 Python 传参是对象引用传递
- 解释了为什么不可变对象在函数内修改不影响外部

---
<!-- id:py_016 | category:数据库 | difficulty:2 | difficulty_label:中级 -->
### Q: 数据库索引的原理？什么时候索引会失效？
### A: 索引本质是 B+Tree 数据结构，通过有序存储加速查找。索引失效场景：1) WHERE 条件对索引列做函数运算 (WHERE YEAR(col)=2024) 2) 前导模糊查询 (LIKE '%abc') 3) 联合索引未遵循最左前缀匹配 4) 类型隐式转换 (WHERE varchar_col=123) 5) OR 条件中部分列无索引。Python 中对应：用 Django ORM 的 explain() 查看执行计划，确保索引命中。
### S:
- 解释了索引是 B+Tree 有序存储
- 列举了至少 3 种索引失效场景
- 提到了最左前缀匹配原则
