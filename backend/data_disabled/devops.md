# 运维工程师面试题库

---
<!-- id:dvops_001 | category:Linux | difficulty:1 | difficulty_label:初级 -->
### Q: 线上服务突然变慢, 你会用哪些 Linux 命令排查?
### A: 先用 top/htop 看CPU和负载, 定位高CPU进程; free -m 看内存是否不足或swap占用; iostat -x 看磁盘IO是否打满; netstat/ss -tnp 或 iftop 看网络连接和流量; df -h 看磁盘是否写满; 用 ps aux、strace、pidstat 定位具体进程; dmesg 看内核日志。结合日志 tail -f / journalctl -u 找错误。
### S:
- 提到 top/htop 排查CPU负载
- 提到 free/iostat/df 排查内存/IO/磁盘
- 提到 netstat/ss 排查网络
- 提到查看应用日志或dmesg

---
<!-- id:dvops_002 | category:容器 | difficulty:2 | difficulty_label:中级 -->
### Q: Docker 的核心原理是什么? 镜像和容器的关系?
### A: Docker 基于 Linux 内核的 namespaces(隔离: pid/net/mnt/uts/ipc/user) 和 cgroups(资源限制: CPU/内存/IO) 实现轻量隔离。镜像(Image)是只读的分层文件系统(UnionFS叠加, 如Overlay2), 包含运行所需的所有依赖; 容器(Container)是镜像运行时的可读写实例, 在镜像顶层加一层可写层。镜像是模板, 容器是实例。
### S:
- 提到 namespaces 做隔离
- 提到 cgroups 做资源限制
- 说明了镜像是分层只读模板
- 说明了容器是镜像的可写运行实例

---
<!-- id:dvops_003 | category:Kubernetes | difficulty:2 | difficulty_label:中级 -->
### Q: 解释 Kubernetes 中 Pod、Deployment、Service 的概念和关系。
### A: Pod 是 K8s 最小调度单元, 包含一个或多个共享网络/存储的容器; Deployment 管理 Pod 副本集, 声明期望副本数并保证实际状态趋近期望(自愈、滚动更新、回滚); Service 提供固定访问入口和负载均衡, 通过 Label Selector 关联 Pod, 解决 Pod IP 易变问题(类型 ClusterIP/NodePort/LoadBalancer)。Deployment 管"跑多少", Service 管"怎么访问"。
### S:
- 正确描述 Pod 是最小调度单元(可含多容器)
- 说明了 Deployment 的副本管理与滚动更新能力
- 说明了 Service 提供固定入口+负载均衡+Label关联
- 阐明了三者关系(Deployment管Pod, Service暴露Pod)

---
<!-- id:dvops_004 | category:CI/CD | difficulty:2 | difficulty_label:中级 -->
### Q: 描述一个典型的 CI/CD 流程, 包含哪些关键环节?
### A: 典型流程: 1) 开发提交代码到Git仓库; 2) CI触发: 代码检查(lint)、单元测试、构建产物(镜像/包); 3) 推送镜像到仓库; 4) CD部署到测试环境做集成/验收测试; 5) 审批后灰度发布到生产; 6) 健康检查通过后全量滚动更新; 7) 监控告警持续观测。工具: Jenkins/GitLab CI/GitHub Actions + ArgoCD/Helm。核心是自动化+可回滚。
### S:
- 提到代码提交触发CI
- 提到lint/单测/构建/镜像推送
- 提到多环境部署(测试→灰度→生产)
- 提到健康检查/监控/可回滚

---
<!-- id:dvops_005 | category:网络 | difficulty:2 | difficulty_label:中级 -->
### Q: Nginx 反向代理和负载均衡的区别与配置思路?
### A: 反向代理是 Nginx 作为前置服务接收客户端请求, 转发给后端真实服务, 对客户端隐藏后端; 负载均衡是反向代理的特例, 后端为多台, 按策略分发请求(轮询/加权/IP hash/最少连接)。配置: upstream 块定义后端池及策略, location 块 proxy_pass 指向 upstream。还可做健康检查、缓存、限流。正向代理代理客户端, 反向代理代理服务端。
### S:
- 区分了反向代理(隐藏后端)与负载均衡(多后端分发)
- 提到 upstream 和 proxy_pass 配置
- 提到至少2种负载策略(轮询/加权/IP hash)
- 区分了正向代理与反向代理

---
<!-- id:dvops_006 | category:监控 | difficulty:3 | difficulty_label:高级 -->
### Q: 如何设计一个监控告警体系? Prometheus + Grafana 的角色?
### A: 监控分层: 基础设施(CPU/内存/磁盘/网络)、中间件(数据库/缓存/队列)、应用(JVM/接口RT/QPS/错误率)、业务(订单/支付)。Prometheus 是时序数据库+拉取式采集(targets/metrics), 用 PromQL 查询, Alertmanager 做告警路由和通知(分级、收敛、静默); Grafana 做可视化看板。告警需设合理阈值(避免噪声)、分级(P0~P3)、值班对接on-call。
### S:
- 提到监控分层(基础设施/中间件/应用/业务)
- 说明了 Prometheus 拉取采集+PromQL+Alertmanager
- 说明了 Grafana 可视化角色
- 提到告警阈值/分级/收敛/on-call
