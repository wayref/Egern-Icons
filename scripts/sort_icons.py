#!/usr/bin/env python3
"""
Egern Icons 自动排序脚本（仓库版）
按以下顺序排序：
1. 透明 Logo 在前（不透明像素 < 70%）
2. 圆角方块在中（不透明像素 >= 70%）
3. 国旗在最后（19 个固定国旗名）

用法：
  python3 sort_icons.py
"""

import json
import urllib.parse
from pathlib import Path
from PIL import Image

# 国旗列表（固定）
FLAG_NAMES = {"AU", "CA", "CN", "China", "DE", "FR", "HK", "JP", "KR", "MO", "RU", "SG", "TH", "TR", "TW", "UK", "UN", "US", "VN"}

def get_opacity_percent(image_path):
    """计算图片的不透明像素百分比"""
    try:
        with Image.open(image_path) as img:
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            alpha = img.split()[3]
            pixels = list(alpha.getdata())
            opaque = sum(1 for p in pixels if p > 128)
            return opaque / len(pixels) * 100
    except Exception as e:
        print(f"  Warning: Could not read {image_path}: {e}")
        return 100  # Default to rounded square

def main():
    repo_root = Path(__file__).parent.parent
    color_dir = repo_root / 'Color'
    json_path = repo_root / 'Egern-Icons.json'
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"Total icons: {len(data['icons'])}")
    
    # Categorize icons
    transparent = []
    rounded = []
    flags = []
    
    for icon in data['icons']:
        name = icon['name']
        filename = urllib.parse.unquote(icon['url'].split('/')[-1])
        filepath = color_dir / filename
        
        if name in FLAG_NAMES:
            flags.append(icon)
        elif not filepath.exists():
            print(f"  Warning: {filename} not found, treating as rounded")
            rounded.append(icon)
        else:
            opacity = get_opacity_percent(filepath)
            if opacity < 70:
                transparent.append(icon)
            else:
                rounded.append(icon)
    
    print(f"Transparent: {len(transparent)}")
    print(f"Rounded: {len(rounded)}")
    print(f"Flags: {len(flags)}")
    
    # Sort each category by name
    transparent.sort(key=lambda x: x['name'])
    rounded.sort(key=lambda x: x['name'])
    flags.sort(key=lambda x: x['name'])
    
    # Combine: transparent + rounded + flags
    data['icons'] = transparent + rounded + flags
    
    # Write back
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
    
    print(f"\nSorted: {len(transparent)} transparent + {len(rounded)} rounded + {len(flags)} flags")
    print(f"Total: {len(data['icons'])}")

if __name__ == '__main__':
    main()
