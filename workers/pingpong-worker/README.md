# pingpong-worker

后台任务 worker（无 API、无端口），通过消息中间件消费任务。

## 运行

```bash
# 仓库根目录
make install-worker WORKER=pingpong-worker   # 安装依赖
make dev-worker WORKER=pingpong-worker       # 启动 worker
make migrate-worker WORKER=pingpong-worker   # 执行数据库迁移

# 或进入本目录
make install
make dev
```

## 结构

- `broker/` — 消息中间件抽象（可插拔），在 `main.py` 中显式创建实例并注册到 `BrokerManager`，在 `broker/factory.py` 注册
- `handlers/` — 任务入口层（等价于 service 的 api 层），在 `handlers/registry.py` 集中注册
- `app/` — DDD 分层（domain / application / infrastructure）
- `foundation/` — 配置、日志、依赖注入容器

依赖公共库 `workers-common`（不含 Web 框架依赖）。