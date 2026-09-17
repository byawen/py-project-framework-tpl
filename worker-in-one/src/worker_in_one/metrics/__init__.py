"""Worker-in-One 指标上报模块。

每个 Celery 消费进程（队列子进程 / prefork pool worker）启动时通过 Celery
信号挂载一个 daemon 上报线程，周期性把本地可观测状态写到共享 Redis 缓存，
供 common-gateway-service 的 /metrics 端点聚合读取。

设计要点（多实例 / 多进程稳定可靠）：
- 采集点分布：每个消费进程独立上报，无单点；任一进程在就有数据。
- active 本地直读：celery.worker.state.active_requests，零 pidbox 广播、
  零偶发不可靠。
- per-instance TTL key：进程死亡后 90s 自动过期，死进程不残留脏数据。
- 同步 redis 客户端：daemon 线程内直接用 redis.Redis，不依赖绑 loop 的
  async RedisManager，避 async 桥接。
- backlog 与 active 同一周期上报：backlog 用 LLEN 读 broker redis（db11），
  值全局相同，多进程覆盖无害。
"""
