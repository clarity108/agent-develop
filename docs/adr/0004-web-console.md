# ADR-0004: Web Console 前端架构

## 日期
2026-09-02

## 背景
agent 需要浏览器界面，让开发者通过网页提交任务、观看执行过程、管理会话历史。

## 决策
采用 **FastAPI + Jinja2 + SSE** 架构：

1. **FastAPI** 作为 HTTP 层，提供 HTML 路由和 JSON API
2. **Jinja2** 服务端渲染 HTML 模板
3. **Server-Sent Events (SSE)** 实现执行状态的实时推送
4. **agent 在后台线程执行**，通过事件队列向 SSE 客户端推送

页面设计采用"execution trace"概念：垂直时间线，每步展示 `thought → tool_call → tool_result`，等宽字体（JetBrains Mono）作为主字体，深板岩灰底色配琥珀色信号和钢蓝色结构。

## 后果

### 正面
- SSE 比 WebSocket 简单，无需额外协议库，浏览器原生支持
- 服务端渲染（Jinja2）无需构建步骤，开发快
- agent 线程隔离，HTTP 响应不被阻塞
- 前端 JS 仅 200 行，逻辑集中在事件渲染

### 负面
- SSE 是单向通信（服务端→客户端），不支持双向交互
- agent 执行状态存储在内存中，重启丢失
- 后台线程没有优雅终止机制
- 目前仅支持 rule-based agent 模式

## 相关文件
- `src/web/app.py` — FastAPI app, routes, SSE streaming
- `templates/base.html` — 基础模板
- `templates/execute.html` — 执行追踪页面
- `static/styles.css` — 设计系统 CSS
- `static/app.js` — 前端 JS
