# -*- coding: utf-8 -*-
"""Find broken string patterns in main.py."""
with open(r'F:\phpstudy_pro\WWW\ServerTimeDemo\main.py', 'rb') as f:
    lines = f.read().split(b'\n')

print(f'Total: {len(lines)} lines')

# Pattern: line contains an unclosed string (more double quotes opened than closed)
# AND next line doesn't start with quote
import re

for i in range(len(lines) - 1):
    line = lines[i]
    next_line = lines[i+1]
    
    # Count quotes on this line
    # A string is properly closed if it has even number of double quotes (or odd with trailing comma/close paren)
    # Simple heuristic: if line has " but doesn't end with closing patterns
    stripped = line.strip()
    
    # Skip comment lines
    if stripped.startswith(b'#'):
        continue
    
    # Count unclosed strings: if number of " on this line is odd
    dq_count = stripped.count(b'"')
    
    if dq_count % 2 == 1:  # odd = unclosed string
        # Check if next line is NOT a continuation (starts with quote, comma+close, def/class, empty)
        next_stripped = next_line.strip()
        if (next_stripped and 
            not next_stripped.startswith(b'"') and 
            not next_stripped.startswith(b"'") and
            not next_stripped.startswith(b'#') and
            not next_stripped.startswith(b'def ') and
            not next_stripped.startswith(b'class ') and
            not next_stripped.startswith(b'if ') and
            not next_stripped.startswith(b'for ') and
            not next_stripped.startswith(b'with ') and
            not next_stripped.startswith(b'return ') and
            not next_stripped.startswith(b'raise ') and
            not next_stripped.startswith(b'except ') and
            not next_stripped.startswith(b'else:') and
            not next_stripped.startswith(b'except:') and
            not next_stripped.startswith(b'and ') and
            not next_stripped.startswith(b'or ') and
            not next_stripped.startswith(b'\\') and  # backslash continuation
            not next_stripped.startswith(b')') and
            not next_stripped.startswith(b',')):
            print(f'UNCLOSED STRING at line {i+1}: {repr(stripped[:80])}')
            print(f'  Next line {i+2}: {repr(next_stripped[:80])}')
            print()
