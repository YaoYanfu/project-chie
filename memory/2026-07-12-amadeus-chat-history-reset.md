# Amadeus 定时更新与聊天历史丢失

- 状态：DONE_WITH_CONCERNS
- 现象：Amadeus 界面周期性发生视觉更新，页面或连接重建后聊天记录消失。
- 根因：前端每 5 秒轮询状态并无条件写入 React 状态；当前聊天 Hook 只保存内存消息，重连时又会用远端历史整体覆盖，空历史会清空窗口；旧连接清理与新连接启动之间还存在重复重连竞态。
- 修复：完整消息写入本机 `data/amadeus/amadeus.db`；新增历史读取/清空 API；启动时恢复本机历史；远端历史改为合并且按 ID/内容时间窗口去重；空历史不再覆盖；重连计时器按 Hook 生命周期隔离；轮询结果无可见变化时复用旧状态，减少界面跳动。
- 验证：`uv run pytest pytests/amadeus -q` 为 21 passed；Amadeus 前端回归测试 3 passed；`ruff`、Dashboard 生产构建和 Electron 构建通过。
- 关注项：完整前端套件另有 14 个既有失败，位于动态表单和长期记忆页面旧断言/超时，与本次 Amadeus 改动无关。
