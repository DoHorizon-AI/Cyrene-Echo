"""
┌─────────────────────────────────────────────────────────────────────┐
│  📄 __init__.py                                                     │
│  Module: cyrene_echo                                                │
│  Role: Public Echo Product API construction surface.                 │
│                                                                     │
│  模块职责：导出 Echo 产品 API 创建入口。                                │
└─────────────────────────────────────────────────────────────────────┘
"""

from cyrene_echo.api import create_app

__all__ = ["create_app"]
