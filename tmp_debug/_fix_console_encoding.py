# -*- coding: utf-8 -*-
"""修复 console_page.py 中的全角字符（Python 3.12 tokenizer 不接受）"""
path = r'F:\phpstudy_pro\WWW\ServerTimeDemo\console_page.py'
with open(path, 'rb') as f:
    data = f.read()

fixed = data.decode('utf-8').translate({
    0xFF01: 0x0021,  # ！ -> !
    0xFF02: 0x0022,  #  " -> "
    0xFF03: 0x0023,  #  # -> #
    0xFF04: 0x0024,  #  $ -> $
    0xFF05: 0x0025,  #  % -> %
    0xFF06: 0x0026,  #  & -> &
    0xFF07: 0x0027,  #  ' -> '
    0xFF08: 0x0028,  #  ( -> (
    0xFF09: 0x0029,  #  ) -> )
    0xFF0A: 0x002A,  #  * -> *
    0xFF0B: 0x002B,  #  + -> +
    0xFF0C: 0x002C,  #  , -> ,
    0xFF0D: 0x002D,  #  - -> -
    0xFF0E: 0x002E,  #  . -> .
    0xFF0F: 0x002F,  #  / -> /
    0xFF1A: 0x003A,  #  : -> :
    0xFF1B: 0x003B,  #  ; -> ;
    0xFF1C: 0x003C,  #  < -> <
    0xFF1D: 0x003D,  #  = -> =
    0xFF1E: 0x003E,  #  > -> >
    0xFF1F: 0x003F,  #  ? -> ?
    0xFF20: 0x0040,  #  @ -> @
    0xFF3B: 0x005B,  #  [ -> [
    0xFF3C: 0x005C,  #  \ -> \
    0xFF3D: 0x005D,  #  ] -> ]
    0xFF3E: 0x005E,  #  ^ -> ^
    0xFF3F: 0x005F,  #  _ -> _
    0xFF40: 0x0060,  #  ` -> `
    0xFF5B: 0x007B,  #  { -> {
    0xFF5C: 0x007C,  #  | -> |
    0xFF5D: 0x007D,  #  } -> }
    0xFF5E: 0x007E,  #  ~ -> ~
}).encode('utf-8')

changed = data != fixed
with open(path, 'wb') as f:
    f.write(fixed)
print('Fixed fullwidth chars:', changed)
