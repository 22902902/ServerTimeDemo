# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'F:\phpstudy_pro\WWW\ServerTimeDemo')

import importlib
import embedded_admin_tools.services.error_code_service as ecs
importlib.reload(ecs)
import embedded_admin_tools.services.interface_service as iface
importlib.reload(iface)
import embedded_admin_tools.services.icon_service as icns
importlib.reload(icns)

e = ecs.ErrorCodeService()
s = iface.InterfaceService()
i = icns.get_icon_bytes()

print('ErrorCodeService keys:', len(e._RETURN_CODE_MAP))
print('InterfaceService envs:', list(s.config['environments'].keys()))
print('Icon bytes:', len(i))
print('Test msg 998200010001:', e.get_message('998200010001'))
print('Test msg -998310000001:', e.get_message('-998310000001'))
print('InterfaceService login endpoint:', s.get_endpoint(s.get_default_environment_key()))
