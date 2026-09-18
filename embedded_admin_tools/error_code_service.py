# -*- coding: utf-8 -*-
"""兼容包装：统一转发到 `embedded_admin_tools.services.error_code_service`。"""

from .services.error_code_service import ErrorCodeService

__all__ = ["ErrorCodeService"]
