#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test if overwrite works"""
content = "OVERWRITE TEST\n"
with open(r"F:\phpstudy_pro\WWW\ServerTimeDemo\_test_overwrite.txt", "w", encoding="utf-8") as f:
    f.write(content)
print("written")
