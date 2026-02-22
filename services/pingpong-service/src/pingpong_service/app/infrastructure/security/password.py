"""密码安全工具模块

密码哈希和验证
"""
import bcrypt
import re


class PasswordHandler:
    """密码处理器"""
    
    MIN_LENGTH = 8
    
    @staticmethod
    def hash_password(password: str) -> str:
        """哈希密码"""
        return bcrypt.hashpw(
            password.encode("utf-8"),
            bcrypt.gensalt(),
        ).decode("utf-8")
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """验证密码"""
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    
    @staticmethod
    def validate_password_strength(password: str) -> tuple[bool, str]:
        """验证密码强度
        
        Returns:
            tuple: (是否有效, 错误消息)
        """
        if len(password) < PasswordHandler.MIN_LENGTH:
            return False, f"Password must be at least {PasswordHandler.MIN_LENGTH} characters"
        
        if not re.search(r"[A-Za-z]", password):
            return False, "Password must contain at least one letter"
        
        if not re.search(r"[0-9]", password):
            return False, "Password must contain at least one number"
        
        return True, ""
