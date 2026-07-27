"""API Layer Package

API Layer - 展示层 / 接口层

包含:
- v1/router.py: 所有路由聚合点 prefix="/v1"
- v1/dependencies.py: 接口层依赖（可选：限流、权限等）
- v1/endpoints/: Handler / Controller
- v1/schemas/: Pydantic DTO（入参/出参）
"""
