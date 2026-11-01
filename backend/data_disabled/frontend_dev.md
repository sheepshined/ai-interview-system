# 前端开发工程师面试题库

---
<!-- id:fe_001 | category:JavaScript | difficulty:1 | difficulty_label:初级 -->
### Q: 解释 JavaScript 的事件循环 (Event Loop) 机制？
### A: JS 是单线程语言，通过事件循环实现异步非阻塞。机制：调用栈执行同步代码 → 异步任务（setTimeout/Promise/事件）交给 Web API → 回调进入任务队列 → 调用栈空闲时取任务执行。微任务（Promise.then/MutationObserver）优先级高于宏任务（setTimeout/setInterval/I/O），每个宏任务执行完后会清空微任务队列中的所有微任务。
### S:
- 解释了调用栈、Web API、任务队列的协作
- 区分了微任务（Promise）和宏任务（setTimeout）
- 说明了微任务在每个宏任务后清空的机制

---
<!-- id:fe_002 | category:CSS | difficulty:1 | difficulty_label:初级 -->
### Q: CSS 中 flex 和 grid 分别适用于什么布局场景？
### A: Flex 是一维布局模型，适合：导航栏、卡片列表、居中布局、等分空间（space-between/stretch）。Grid 是二维布局模型，适合：整体页面布局、复杂行列网格、不规则布局。快速判断：单行或单列排列用 flex，需要同时控制行和列用 grid。两者可组合使用：外层 grid 划分区域，内层 flex 处理区域内元素的对齐。
### S:
- 准确区分了一维(flex)和二维(grid)布局
- 给出了具体适用场景的例子
- 提到了两者可以组合使用

---
<!-- id:fe_003 | category:Vue | difficulty:2 | difficulty_label:中级 -->
### Q: Vue 3 的响应式系统原理？和 Vue 2 的区别在哪里？
### A: Vue 2 用 Object.defineProperty 劫持属性 getter/setter，无法检测新增/删除属性（需 Vue.set/delete），且初始化时需递归遍历所有属性。Vue 3 用 Proxy 代理整个对象，可检测属性增删、数组索引变化、length 变化，且惰性响应——只有被访问到的嵌套对象才会转为 Proxy。配合 Reflect API 保证 this 指向正确。Vue 3 的响应式对数组更友好。
### S:
- 区分了 defineProperty 和 Proxy 两种方案
- 提到了 Proxy 可检测属性增删而 defineProperty 不能
- 提到了惰性响应和 Reflect API

---
<!-- id:fe_004 | category:React | difficulty:2 | difficulty_label:中级 -->
### Q: React 的虚拟 DOM 和 Diff 算法原理是什么？
### A: 虚拟 DOM 是 JS 对象树，描述真实 DOM 结构，用于减少直接操作真实 DOM 的开销。Diff 策略：1) 同层比较（不跨层）O(n) 复杂度 2) 不同类型节点直接替换整棵子树 3) key 属性标识列表元素，key 相同则复用。React 18 引入并发渲染，Fiber 架构支持可中断的 Reconciliation，优先级更高的更新可打断低优先级渲染。
### S:
- 解释了虚拟 DOM 减少真实 DOM 操作的目的
- 描述了同层比较和 key 策略
- 提到了 Fiber 架构和并发渲染

---
<!-- id:fe_005 | category:前端工程化 | difficulty:2 | difficulty_label:中级 -->
### Q: 前端性能优化有哪些方向？首屏加载优化怎么做？
### A: 1) 资源优化：代码分割 (lazy import)、Tree Shaking 死代码消除、Gzip/Brotli 压缩、图片 WebP + 懒加载 2) 加载优化：CDN 加速、预加载 (preload/prefetch)、SSR/SSG 服务端渲染 3) 渲染优化：减少重排重绘、虚拟长列表、防抖节流 4) 缓存策略：HTTP 缓存 + Service Worker + localStorage。首屏优化：关键 CSS 内联、JS 异步 defer、骨架屏、SSR、资源按需加载。
### S:
- 至少覆盖了资源、加载、渲染三个方向
- 提到了代码分割和 Tree Shaking
- 首屏优化提到了 SSR、骨架屏、关键 CSS 内联

---
<!-- id:fe_006 | category:JavaScript | difficulty:1 | difficulty_label:初级 -->
### Q: var、let、const 的区别？暂时性死区 (TDZ) 是什么？
### A: var：函数作用域、变量提升（初始化为 undefined）、可重复声明。let/const：块级作用域、存在暂时性死区——在声明前访问会抛 ReferenceError、不可重复声明。const 声明常量必须初始化且不可重新赋值（但对象内容仍可变）。暂时性死区：从块开始到 let/const 声明语句之间的区域，变量在此区间不可访问，这是 JS 引擎的规范行为。
### S:
- 区分了函数作用域(var)和块级作用域(let/const)
- 解释了变量提升和暂时性死区
- 说明了 const 不可重新赋值但对象内容可变

---
<!-- id:fe_007 | category:TypeScript | difficulty:2 | difficulty_label:中级 -->
### Q: TypeScript 的泛型 (Generics) 是什么？举一个实际的例子。
### A: 泛型让函数/类/接口在定义时不指定具体类型，使用时才确定。如 `function identity<T>(arg: T): T { return arg }`。实际应用：1) API 响应类型封装 `axios.get<User[]>(url)` 2) React 组件泛型 `React.FC<Props>` 3) 工具类型 Partial<T>/Pick<T,K>/Omit<T,K>/Record<K,V> 4) 通用 hook `function useRequest<T>(url: string): Result<T>`。泛型让代码既灵活又类型安全。
### S:
- 解释了泛型的延迟确定类型
- 给出了至少 2 个实际应用场景
- 提到了常用工具类型

---
<!-- id:fe_008 | category:Vue | difficulty:2 | difficulty_label:中级 -->
### Q: Vue Router 的三种路由模式？Hash 和 History 的区别？
### A: 1) Hash 模式：URL 带 # 号，# 后内容不发送到服务器，hashchange 事件监听路由变化，无需服务端配置 2) History 模式：利用 HTML5 History API (pushState/replaceState)，URL 干净无 #，但需要服务器配置（所有路由返回 index.html）否则刷新 404 3) Abstract 模式：非浏览器环境（Node 或 SSR）使用。选 History 需要干净 URL 时，选 Hash 无法配置服务器时。
### S:
- 区分了 Hash 和 History 两种模式
- 说明了 Hash 不需要服务端配置而 History 需要
- 解释了 History 模式 404 的原因和解决方案

---
<!-- id:fe_009 | category:网络 | difficulty:2 | difficulty_label:中级 -->
### Q: 跨域问题如何产生？解决跨域有哪些主流方案？
### A: 浏览器同源策略：协议、域名、端口任一不同即跨域。方案：1) CORS（服务器设 Access-Control-Allow-Origin 响应头），最标准最常用 2) 开发环境 Proxy（webpack devServer proxy / vite server.proxy）3) Nginx 反向代理（同域转发到不同后端）4) JSONP（利用 script 标签绕过同源，只支持 GET，古老方案）5) WebSocket（不受同源策略限制）。生产环境推荐 CORS + Nginx 反向代理组合。
### S:
- 解释了同源策略的定义（协议+域名+端口）
- 列举了至少 3 种跨域方案
- 区分了开发环境 Proxy 和生产环境 Nginx/CORS

---
<!-- id:fe_010 | category:CSS | difficulty:1 | difficulty_label:初级 -->
### Q: CSS 的 position 属性有哪些值？sticky 的失效条件？
### A: static（默认，正常流）、relative（相对自身偏移，保留原位）、absolute（相对最近非 static 祖先定位，脱离文档流）、fixed（视口定位，脱离文档流）、sticky（relative+fixed 混合，滚动到阈值后固定）。sticky 失效常见原因：没有设置 top/left 等阈值、父元素 overflow 设为 hidden/auto/scroll、父元素高度不大于 sticky 元素高度、浏览器不支持。
### S:
- 列举了 5 种 position 值
- 说明了每种值的定位参照和文档流关系
- 准确指出了 sticky 失效的常见原因

---
<!-- id:fe_011 | category:前端工程化 | difficulty:3 | difficulty_label:高级 -->
### Q: 如何设计一个前端组件库？需要考虑哪些方面？
### A: 1) 组件设计：原子→分子→组合结构，TypeScript 泛型保证 Props 类型 2) 样式方案：CSS Variables 做主题化、Scoped/CSS Modules/BEM 避免样式冲突 3) 按需加载：Tree Shaking + ES Module 导出 4) 无障碍 (a11y)：ARIA 标签、键盘导航支持 5) 测试策略：Vitest 单元测试 + Playwright 集成测试 6) 文档：Storybook 交互式文档 7) 版本管理：语义化版本 + Changelog + CI 自动发布。
### S:
- 提到了组件分层设计（原子→分子→组合）
- 涉及了样式隔离和主题化方案
- 涵盖了测试、文档、版本、无障碍的工程化要点

---
<!-- id:fe_012 | category:前端工程化 | difficulty:2 | difficulty_label:中级 -->
### Q: Webpack 和 Vite 的核心区别？为什么 Vite 开发启动更快？
### A: Webpack 是打包型构建工具：开发时将所有模块打包成 bundle，项目变大后冷启动慢。Vite 是 ESM 型：开发时直接利用浏览器原生 ES Module 的 import，按需编译，只处理当前访问的页面。Vite 用 esbuild（Go 语言）预构建依赖，速度快 10-100 倍，用 Rollup 做生产打包。新项目优先 Vite，旧项目/复杂 webpack 插件场景可继续 Webpack。
### S:
- 区分了打包型 (Webpack) 和 ESM 型 (Vite)
- 解释了浏览器原生 ESM + 按需编译
- 提到了 esbuild 预构建依赖的性能优势

---
<!-- id:fe_013 | category:前端工程化 | difficulty:3 | difficulty_label:高级 -->
### Q: 实现一个前端监控 SDK，需要收集哪些数据？如何设计上报策略？
### A: 1) 错误监控：JS Error (window.onerror + unhandledrejection)、Promise 异常、资源加载错误 2) 性能监控：FCP/LCP/TTI/CLS (PerformanceObserver API)、接口耗时 3) 用户行为：PV/UV、点击流、页面停留时长 4) 网络监控：API 请求耗时+状态码+错误信息。上报策略：sendBeacon 保证页面关闭前发送、批量聚合上报减少请求数、采样率控制（按百分比/按错误类型）、敏感数据脱敏。
### S:
- 覆盖了错误、性能、用户行为三个监控维度
- 提到了 PerformanceObserver 和 sendBeacon
- 说明了批量上报和采样率控制

---
<!-- id:fe_014 | category:网络 | difficulty:1 | difficulty_label:初级 -->
### Q: HTTP 缓存策略：强缓存和协商缓存的区别？
### A: 强缓存：命中后直接返回本地缓存，不发送请求到服务器。响应头 Cache-Control: max-age=3600（秒级精度）、Expires（HTTP/1.0 绝对时间）。协商缓存：发送请求到服务器，服务器返回 304 Not Modified 则用本地缓存。Etag/If-None-Match（内容哈希，精确）、Last-Modified/If-Modified-Since（修改时间，秒精度）。策略：HTML 用协商缓存，JS/CSS/图片用强缓存 + 文件名哈希实现更新。
### S:
- 区分了强缓存（不请求）和协商缓存（304）
- 解释了 Cache-Control 和 Etag 的区别
- 给出了合理的缓存策略（HTML 协商，静态资源强缓存+哈希）

---
<!-- id:fe_015 | category:JavaScript | difficulty:2 | difficulty_label:中级 -->
### Q: Promise 链式调用和 async/await 的区别？如何正确处理 async/await 错误？
### A: async/await 是 Promise 的语法糖，用同步写法写异步代码，可读性和可维护性更好。Promise 适合需要并行执行多个异步操作的场景（Promise.all/allSettled/race）。async/await 错误处理：用 try/catch 包裹；或者在调用时 `.catch()`；top-level await 需要 ES2022+ 或模块环境。注意：async 函数始终返回 Promise。多个独立请求用 `await Promise.all([...])` 不要逐个 await（避免串行等待）。
### S:
- 说明了 async/await 是 Promise 的语法糖
- 提到了 try/catch 错误处理方式
- 强调了 Promise.all 并行和逐个 await 串行的区别
