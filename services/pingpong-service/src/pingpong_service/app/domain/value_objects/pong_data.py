"""PongData 值对象模块

PongData 值对象 - 不可变
"""
from pydantic import field_validator


class PongData:
    """PongData 值对象"""
    
    def __init__(self, value: str):
        self._value = value
    
    @property
    def value(self) -> str:
        return self._value
    
    def __str__(self) -> str:
        return self._value
    
    def __repr__(self) -> str:
        return f"PongData('{self._value}')"
    
    def __eq__(self, other: object) -> bool:
        if isinstance(other, PongData):
            return self._value == other._value
        return False
    
    def __hash__(self) -> int:
        return hash(self._value)
