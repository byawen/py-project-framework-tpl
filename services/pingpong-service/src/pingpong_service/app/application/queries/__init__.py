"""Queries Package

查询处理器(查)
"""
from pingpong_service.app.application.queries.get_ping import PingQuery, PingQueryResult
from pingpong_service.app.application.queries.biz_code_test import BizCodeTestQuery, BizCodeTestResult

__all__ = ["PingQuery", "PingQueryResult", "BizCodeTestQuery", "BizCodeTestResult"]