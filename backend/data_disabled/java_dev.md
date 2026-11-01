# Java 开发工程师面试题库

---
<!-- id:java_001 | category:Java基础 | difficulty:1 | difficulty_label:初级 -->
### Q: Java 中 == 和 equals() 的区别？String 的 equals 是如何实现的？
### A: == 比较基本类型的值和引用类型的地址。equals() 是 Object 的方法，默认实现就是 ==，但 String 重写了 equals()，先比较地址，不同则比较字符序列是否相同。自定义类需同时重写 equals() 和 hashCode()，两者契约：equals 相等则 hashCode 必须相等。
### S:
- 区分了 == 比较值和地址，equals 比较内容
- 解释了 String 重写 equals 的方式
- 提到了 equals 和 hashCode 的契约关系

---
<!-- id:java_002 | category:Java基础 | difficulty:2 | difficulty_label:中级 -->
### Q: HashMap 的底层实现原理？JDK 1.8 做了什么优化？
### A: JDK 1.7 是数组 + 链表（头插法），1.8 改为数组 + 链表/红黑树。当链表长度 ≥ 8 且数组长度 ≥ 64 时，链表转为红黑树提升查询效率（O(n)→O(log n)）。扩容时 1.8 不需要 rehash，通过高位运算拆分链表。put 流程：hash → 索引 → 冲突则链表/红黑树插入 → 容量判断扩容。get 流程类似。
### S:
- 描述了数组+链表/红黑树的结构
- 说明了链表转红黑树的条件（长度≥8 且数组≥64）
- 提到了扩容时的高位拆分优化

---
<!-- id:java_003 | category:Java基础 | difficulty:1 | difficulty_label:初级 -->
### Q: ArrayList 和 LinkedList 的区别和各适用于什么场景？
### A: ArrayList：基于动态数组，随机访问 O(1)，尾部追加 O(1)，中间插入/删除 O(n)，内存连续对 CPU 缓存友好。LinkedList：基于双向链表，随机访问 O(n)，头尾操作 O(1)，插入删除 O(1)（需先定位）。选 ArrayList：读多写少、需要随机访问、数据量不大。选 LinkedList：频繁头尾操作（但 ArrayDeque 往往更好）。
### S:
- 区分了数组和链表的底层数据结构
- 准确描述了对应的时间复杂度
- 给出了合理的选型建议

---
<!-- id:java_004 | category:Java并发 | difficulty:3 | difficulty_label:高级 -->
### Q: Java 并发编程中 synchronized 原理？和 Lock 的区别？
### A: synchronized 基于 JVM 内置锁（monitor 对象），JDK 1.6 后引入偏向锁→轻量锁（自旋）→重量锁的锁升级机制。Lock 是 JDK 层面的接口，ReentrantLock 基于 AQS 实现，支持公平锁、可中断获取锁、tryLock 超时、多条件变量 Condition。选 synchronized：简单同步需求。选 Lock：需要超时/中断/公平/多条件绑定。
### S:
- 解释了锁升级机制（偏向→轻量→重量）
- 区分了 JVM 层面和 JDK 层面的锁实现
- 提到了 AQS 和高级特性（公平锁、可中断、tryLock）

---
<!-- id:java_005 | category:Java并发 | difficulty:3 | difficulty_label:高级 -->
### Q: ThreadLocal 的实现原理和内存泄漏问题如何处理？
### A: ThreadLocal 在每个线程的 Thread 对象中维护 ThreadLocalMap，key 是 ThreadLocal 的弱引用，value 是存储的值。内存泄漏原因：ThreadLocal 被 GC 回收后 key 变 null 但 value 仍被线程引用。解决：static 修饰 ThreadLocal、使用时用 try-finally 包裹并在 finally 中调用 remove() 清理。线程池场景尤其需要清理。
### S:
- 解释了 ThreadLocalMap 和弱引用机制
- 准确说明了内存泄漏的根本原因
- 提到了 remove() 和线程池场景的处理

---
<!-- id:java_006 | category:Spring | difficulty:2 | difficulty_label:中级 -->
### Q: Spring 的依赖注入 (DI) 有几种方式？哪种最推荐？为什么？
### A: 1) 构造器注入（推荐）2) Setter 注入 3) 字段注入 (@Autowired)。构造器注入最推荐：保证依赖不可变（final）、避免 NPE（编译期检查）、利于单元测试 mock、明确显示类依赖。字段注入不推荐：破坏单一职责、不利于测试、隐藏依赖关系。Spring 4.3+ 单构造器时 @Autowired 可省略。
### S:
- 列举了三种注入方式
- 明确推荐构造器注入并给出了理由
- 提到了不可变性、编译期检查、测试友好性

---
<!-- id:java_007 | category:Spring | difficulty:2 | difficulty_label:中级 -->
### Q: Spring Boot 的自动配置 (AutoConfiguration) 原理是什么？
### A: 核心通过 @EnableAutoConfiguration → @Import(AutoConfigurationImportSelector) → 读取 spring-boot-autoconfigure 包的 META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports 文件 → 根据 @Conditional 条件注解（@ConditionalOnClass, @ConditionalOnMissingBean 等）决定哪些配置类生效。开发者想覆盖只需自己声明同名 @Bean，条件注解检测到已有 Bean 时会自动跳过。
### S:
- 描述了 AutoConfigurationImportSelector 的加载流程
- 解释了 @Conditional 条件注解的作用
- 提到了开发者覆盖的方式（声明同名 Bean）

---
<!-- id:java_008 | category:JVM | difficulty:3 | difficulty_label:高级 -->
### Q: JVM 内存模型（JMM）中的 happens-before 原则是什么？
### A: JMM 规定 8 条 happens-before 规则：1) 程序次序（同一线程内按代码序）2) volatile 变量写 happens-before 后续读 3) 锁释放 happens-before 后续获取 4) 传递性 5) start() happens-before 线程内所有操作 6) 线程所有操作 happens-before join() 返回 7) 中断 happens-before 被中断线程检测到中断 8) 对象构造完成 happens-before finalize()。理解这些能正确判断多线程场景下变量可见性。
### S:
- 列举了至少 4 条 happens-before 规则
- 解释了 volatile 和锁的 happens-before 关系
- 说明了 happens-before 的作用是保证可见性

---
<!-- id:java_009 | category:Java基础 | difficulty:1 | difficulty_label:初级 -->
### Q: final 关键字在 Java 中有哪几种用法？
### A: 1) final 变量：基本类型值不可变，引用类型引用不可变但对象内容可变 2) final 方法：不可被子类重写 3) final 类：不可被继承，如 String 4) final 参数：方法内不可修改参数引用。final 对 JVM 内联优化有微小帮助，但主要作用是设计层面的不可变性约束，写出更安全的代码。
### S:
- 列举了 final 变量、方法、类三种用法
- 区分了基本类型和引用类型 final 的差异
- 提到了不可变性和设计约束的意义

---
<!-- id:java_010 | category:MyBatis | difficulty:2 | difficulty_label:中级 -->
### Q: MyBatis 中 #{} 和 ${} 的区别？为什么 #{} 能防 SQL 注入？
### A: #{} 是预编译占位符，MyBatis 将参数通过 PreparedStatement 的 setXxx() 安全设置，自动类型转换和转义。${} 是字符串替换，直接拼接到 SQL 中，有 SQL 注入风险。能用 #{} 的地方绝不用 ${}，除非动态表名/列名/ORDER BY 等必须拼接的场景，此时需做白名单校验。MyBatis Plus 也遵循同样原则。
### S:
- 区分了预编译占位符和字符串替换
- 解释了 PreparedStatement 防注入的机制
- 提到了必须用 ${} 的场景和白名单校验

---
<!-- id:java_011 | category:系统设计 | difficulty:3 | difficulty_label:高级 -->
### Q: 设计一个秒杀系统，需要考虑哪些技术点和防超卖方案？
### A: 1) 前端限流：按钮置灰、验证码 2) Nginx 限流：limit_req 令牌桶 3) Redis 预减库存（lua 脚本保证原子性）4) 异步下单：MQ（Kafka/RabbitMQ）削峰 5) 数据库乐观锁 `update set stock=stock-1 where stock>0 and version=old` 6) 防超卖：Redis + 数据库双重校验 7) 热点数据预热 8) 读写分离 9) 限流熔断 Sentinel 保护下游。
### S:
- 描述了从前端到后端的多层限流方案
- 提到了 Redis Lua 原子操作和 MQ 削峰
- 说明了乐观锁和双重校验防止超卖

---
<!-- id:java_012 | category:Java基础 | difficulty:1 | difficulty_label:初级 -->
### Q: 抽象类和接口的区别？Java 8 后有什么变化？
### A: 抽象类：可以有成员变量和构造函数、具体方法+抽象方法共存、单继承。接口：只能有常量（public static final）、抽象方法（无方法体）、多实现。Java 8 后接口支持 default 方法和 static 方法，Java 9 后支持 private 方法。选接口：定义行为规范。选抽象类：需要共享代码、需要非 public 成员。
### S:
- 区分了抽象类（单继承、有构造）和接口（多实现、常量）
- 提到了 Java 8/9 接口的演进（default、private 方法）
- 给出了合理的选型建议

---
<!-- id:java_013 | category:JVM | difficulty:3 | difficulty_label:高级 -->
### Q: 线上 OOM 如何排查和定位？写出完整流程。
### A: 1) JVM 参数 -XX:+HeapDumpOnOutOfMemoryError 和 -XX:HeapDumpPath 自动 dump 2) 用 jmap 手动 dump: `jmap -dump:format=b,file=heap.hprof <pid>` 3) MAT / JProfiler 分析 dump 文件，找最大对象和 GC Root 引用链 4) jstat -gc 观察 GC 回收频率和耗时 5) 查看 GC 日志分析回收情况 6) 常见原因：大对象缓存无限制、ThreadLocal 未清理、数据库查询返回过多数据、集合无限增长。代码层面排查：缓存加 size 上限、分页查询、finally 中清理资源。
### S:
- 提到了 JVM 参数自动 dump 和 jmap 手动 dump
- 说明了 MAT/JProfiler 分析 dump 的流程
- 列出了 3 个以上常见 OOM 原因和对应修复

---
<!-- id:java_014 | category:Java基础 | difficulty:2 | difficulty_label:中级 -->
### Q: Java 反射 (Reflection) 的原理和应用场景？
### A: 反射通过 Class 对象获取类的构造器、方法、字段信息并动态调用。核心入口是 Class.forName() 或 obj.getClass()。获取的信息来源于 JVM 方法区存储的类元信息。应用：Spring DI 依赖注入、MyBatis 结果映射、JUnit 测试运行、IDE 代码补全。代价：性能开销较大、破坏封装性、编译器无法做类型检查。
### S:
- 解释了反射是通过 Class 对象获取类元信息
- 给出了至少 2 个实际应用场景（Spring、MyBatis）
- 提到了性能开销和封装性代价

---
<!-- id:java_015 | category:微服务 | difficulty:3 | difficulty_label:高级 -->
### Q: 微服务架构中，如何保证服务间的数据一致性？
### A: CAP 定理下分布式系统无法同时保证强一致性和高可用性。方案：1) 最终一致性：异步消息 + 补偿机制（Seata AT/TCC, Sagas 模式）2) 分布式事务：两阶段提交 2PC（性能代价大，少用）3) 事件驱动：发事件 + 消费方做好幂等 4) CQRS 读写分离 + 事件溯源（Event Sourcing）。常用做法是消息队列 + 本地事务表确保"发消息"和"写业务数据"的原子性。
### S:
- 提到了 CAP 定理和最终一致性
- 列举了至少 2 种方案（异步消息+补偿、CQRS+事件溯源）
- 提到了消息队列+本地事务表保证原子性
