#!/usr/bin/env python3
"""
Clean up Egern-Icons repo - safe duplicate detection:
1. Remove duplicate JSON entries (same URL)
2. Remove name duplicates (normalize: remove _, -, spaces, lowercase)
   - Catches TencentVideo vs Tencent_Video, WeChat vs Weixin (if same normalized name)
3. Remove visually duplicate images (perceptual hash, Hamming distance <= 3)
   - Conservative threshold to avoid false positives
4. Remove orphaned files
5. Remove broken entries

Usage:
    python3 dedup_icons.py [--dry-run]
"""

import os
import sys
import json
import re
import urllib.parse
from pathlib import Path
from PIL import Image

def perceptual_hash(image_path, hash_size=8):
    """Compute perceptual hash of image."""
    try:
        with Image.open(image_path) as img:
            img = img.convert('L').resize((hash_size, hash_size), Image.LANCZOS)
            pixels = list(img.getdata())
            avg = sum(pixels) / len(pixels)
            bits = ''.join('1' if p > avg else '0' for p in pixels)
            return bits
    except Exception as e:
        return None

def hamming_distance(hash1, hash2):
    if len(hash1) != len(hash2):
        return 999
    return sum(c1 != c2 for c1, c2 in zip(hash1, hash2))

def normalize_name(name):
    """Normalize name for comparison: remove _, -, spaces, lowercase."""
    normalized = re.sub(r'[_\-\s]+', '', name.lower())
    return normalized

def main():
    dry_run = '--dry-run' in sys.argv
    repo_root = Path(__file__).parent.parent
    color_dir = repo_root / 'Color'
    json_path = repo_root / 'Egern-Icons.json'
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"Original JSON entries: {len(data['icons'])}")
    
    # Step 1: Remove duplicate URLs
    seen_urls = set()
    unique_icons = []
    dup_url_count = 0
    for icon in data['icons']:
        if icon['url'] in seen_urls:
            dup_url_count += 1
            continue
        seen_urls.add(icon['url'])
        unique_icons.append(icon)
    print(f"Step 1: Removed {dup_url_count} duplicate URLs")
    
    # Step 2: Remove broken entries
    valid_icons = []
    broken_count = 0
    for icon in unique_icons:
        filename = urllib.parse.unquote(icon['url'].split('/')[-1])
        if not (color_dir / filename).exists():
            broken_count += 1
            continue
        valid_icons.append(icon)
    print(f"Step 2: Removed {broken_count} broken entries")
    
    # Step 3: Find name duplicates (normalized)
    name_groups = {}
    for icon in valid_icons:
        norm = normalize_name(icon['name'])
        if norm not in name_groups:
            name_groups[norm] = []
        name_groups[norm].append(icon)
    
    name_dups = {k: v for k, v in name_groups.items() if len(v) > 1}
    print(f"\nStep 3: Found {len(name_dups)} name duplicate groups")
    
    # Step 4: Find visual duplicates (perceptual hash, distance <= 3 - CONSERVATIVE)
    print(f"\nStep 4: Computing perceptual hashes...")
    hashes = {}
    for icon in valid_icons:
        filename = urllib.parse.unquote(icon['url'].split('/')[-1])
        h = perceptual_hash(color_dir / filename)
        if h:
            if h not in hashes:
                hashes[h] = []
            hashes[h].append(icon)
    
    # Find exact matches and near-matches (distance <= 3)
    hash_list = list(hashes.keys())
    visual_groups = []
    visited = set()
    
    for i, h1 in enumerate(hash_list):
        if h1 in visited:
            continue
        group = [h1]
        visited.add(h1)
        for h2 in hash_list[i+1:]:
            if h2 in visited:
                continue
            if hamming_distance(h1, h2) <= 3:
                group.append(h2)
                visited.add(h2)
        if len(group) > 1:
            icons = []
            for h in group:
                icons.extend(hashes[h])
            visual_groups.append(icons)
    
    print(f"  Found {len(visual_groups)} visual duplicate groups (distance <= 3)")
    
    # Combine groups
    all_groups = list(name_dups.values()) + visual_groups
    
    # Deduplicate groups
    seen_groups = set()
    unique_groups = []
    for group in all_groups:
        key = frozenset(icon['name'] for icon in group)
        if key not in seen_groups:
            seen_groups.add(key)
            unique_groups.append(group)
    
    print(f"\nTotal unique duplicate groups: {len(unique_groups)}")
    
    # For each group, keep one
    def sort_key(icon):
        name = icon['name']
        is_english = all(ord(c) < 128 for c in name)
        has_underscore = '_' in name
        return (0 if is_english else 1, 1 if has_underscore else 0, len(name), name)
    
    files_to_delete = []
    names_to_remove = set()
    
    for group in unique_groups:
        sorted_group = sorted(group, key=sort_key)
        keep = sorted_group[0]
        delete = sorted_group[1:]
        print(f"\n  Group:")
        print(f"    KEEP: {keep['name']}")
        for icon in delete:
            filename = urllib.parse.unquote(icon['url'].split('/')[-1])
            print(f"    DELETE: {icon['name']} ({filename})")
            files_to_delete.append(filename)
            names_to_remove.add(icon['name'])
    
    # Step 5: Find orphaned files
    json_filenames = set(
        urllib.parse.unquote(icon['url'].split('/')[-1])
        for icon in valid_icons
    )
    all_files = set(f.name for f in color_dir.glob('*.png'))
    orphaned = all_files - json_filenames
    print(f"\nStep 5: Found {len(orphaned)} orphaned files")
    
    if dry_run:
        print(f"\n[DRY RUN] Would delete {len(files_to_delete)} files")
        return 0
    
    # Delete files
    for filename in files_to_delete:
        try:
            (color_dir / filename).unlink()
        except Exception as e:
            print(f"  Failed: {filename}: {e}")
    
    for filename in orphaned:
        try:
            (color_dir / filename).unlink()
        except Exception as e:
            print(f"  Failed: {filename}: {e}")
    
    # Update JSON
    final_icons = [icon for icon in valid_icons if icon['name'] not in names_to_remove]
    data['icons'] = final_icons
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
    
    print(f"\n=== Summary ===")
    print(f"Final: {len(final_icons)} entries")
    print(f"Removed: {dup_url_count} dup URLs, {broken_count} broken, {len(names_to_remove)} dup images")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
