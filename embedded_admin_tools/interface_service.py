# -*- coding: utf-8 -*-
"""兼容包装：统一转发到 `embedded_admin_tools.services.interface_service`。"""

from .services.interface_service import InterfaceService, PLACEHOLDER_RE

__all__ = ["InterfaceService", "PLACEHOLDER_RE"]
