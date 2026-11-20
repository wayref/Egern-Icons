#!/usr/bin/env python3
"""
Clean up Egern-Icons repo:
1. Remove duplicate JSON entries (same URL)
2. Remove duplicate images (same content, different files)
3. Remove orphaned files (in Color/ but not in JSON)
4. Remove broken JSON entries (URL points to non-existent file)
5. Fix URL encoding issues (+ should be %2B in URL, but filename has +)

Usage:
    python3 dedup_icons.py [--dry-run]
"""

import os
import sys
import json
import hashlib
import urllib.parse
from pathlib import Path

def compute_hash(filepath):
    with open(filepath, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

def main():
    dry_run = '--dry-run' in sys.argv
    repo_root = Path(__file__).parent.parent
    color_dir = repo_root / 'Color'
    json_path = repo_root / 'Egern-Icons.json'
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"Original JSON entries: {len(data['icons'])}")
    
    # Step 1: Remove duplicate JSON entries (same URL)
    seen_urls = set()
    unique_icons = []
    dup_url_count = 0
    for icon in data['icons']:
        url = icon['url']
        if url in seen_urls:
            dup_url_count += 1
            print(f"  Duplicate URL: {icon['name']} -> {url}")
            continue
        seen_urls.add(url)
        unique_icons.append(icon)
    
    print(f"\nStep 1: Removed {dup_url_count} duplicate URL entries")
    print(f"  Remaining: {len(unique_icons)}")
    
    # Step 2: Check for broken entries (file doesn't exist)
    valid_icons = []
    broken_count = 0
    for icon in unique_icons:
        filename = icon['url'].split('/')[-1]
        # URL decode filename (+ is %2B in URL)
        filename = urllib.parse.unquote(filename)
        filepath = color_dir / filename
        if not filepath.exists():
            broken_count += 1
            print(f"  Broken link: {icon['name']} -> {filename} (file not found)")
            continue
        valid_icons.append(icon)
    
    print(f"\nStep 2: Removed {broken_count} broken entries")
    print(f"  Remaining: {len(valid_icons)}")
    
    # Step 3: Find duplicate images by content
    hashes = {}
    for icon in valid_icons:
        filename = urllib.parse.unquote(icon['url'].split('/')[-1])
        filepath = color_dir / filename
        h = compute_hash(filepath)
        if h not in hashes:
            hashes[h] = []
        hashes[h].append(icon)
    
    duplicates = {h: v for h, v in hashes.items() if len(v) > 1}
    print(f"\nStep 3: Found {len(duplicates)} duplicate image groups")
    
    # For each group, keep one (prefer English name, shortest name)
    def sort_key(icon):
        name = icon['name']
        is_english = all(ord(c) < 128 for c in name)
        return (0 if is_english else 1, len(name), name)
    
    files_to_delete = []
    names_to_remove = set()
    
    for h, group in duplicates.items():
        sorted_group = sorted(group, key=sort_key)
        keep = sorted_group[0]
        delete = sorted_group[1:]
        print(f"\n  Group (hash {h[:8]}):")
        print(f"    KEEP: {keep['name']}")
        for icon in delete:
            filename = urllib.parse.unquote(icon['url'].split('/')[-1])
            print(f"    DELETE: {icon['name']} ({filename})")
            files_to_delete.append(filename)
            names_to_remove.add(icon['name'])
    
    # Step 4: Find orphaned files (in Color/ but not in JSON)
    json_filenames = set(
        urllib.parse.unquote(icon['url'].split('/')[-1])
        for icon in valid_icons
    )
    all_files = set(f.name for f in color_dir.glob('*.png'))
    orphaned = all_files - json_filenames
    print(f"\nStep 4: Found {len(orphaned)} orphaned files (not in JSON)")
    for f in sorted(orphaned)[:10]:
        print(f"  - {f}")
    if len(orphaned) > 10:
        print(f"  ... and {len(orphaned) - 10} more")
    
    if dry_run:
        print(f"\n[DRY RUN] Would delete:")
        print(f"  - {len(files_to_delete)} duplicate image files")
        print(f"  - {len(orphaned)} orphaned files")
        print(f"  - {len(names_to_remove)} JSON entries")
        return 0
    
    # Delete duplicate files
    print(f"\nDeleting {len(files_to_delete)} duplicate files...")
    for filename in files_to_delete:
        filepath = color_dir / filename
        try:
            filepath.unlink()
            print(f"  Deleted {filename}")
        except Exception as e:
            print(f"  Failed: {filename}: {e}")
    
    # Delete orphaned files
    print(f"\nDeleting {len(orphaned)} orphaned files...")
    for filename in orphaned:
        filepath = color_dir / filename
        try:
            filepath.unlink()
            print(f"  Deleted {filename}")
        except Exception as e:
            print(f"  Failed: {filename}: {e}")
    
    # Update JSON
    final_icons = [icon for icon in valid_icons if icon['name'] not in names_to_remove]
    data['icons'] = final_icons
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
    
    print(f"\n=== Summary ===")
    print(f"Original: {len(data['icons']) + dup_url_count + broken_count + len(names_to_remove)} entries")
    print(f"Final: {len(final_icons)} entries")
    print(f"Removed: {dup_url_count} dup URLs, {broken_count} broken, {len(names_to_remove)} dup images")
    print(f"Deleted files: {len(files_to_delete)} duplicates + {len(orphaned)} orphaned")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
