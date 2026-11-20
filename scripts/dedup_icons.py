#!/usr/bin/env python3
"""
Clean up Egern-Icons repo using perceptual hashing:
1. Remove duplicate JSON entries (same URL)
2. Remove visually duplicate images (perceptual hash, catches same-looking icons with different files)
3. Remove orphaned files (in Color/ but not in JSON)
4. Remove broken JSON entries (URL points to non-existent file)

Usage:
    python3 dedup_icons.py [--dry-run]
"""

import os
import sys
import json
import urllib.parse
from pathlib import Path
from PIL import Image

def perceptual_hash(image_path, hash_size=8):
    """Compute perceptual hash of image. Returns hash string."""
    try:
        with Image.open(image_path) as img:
            # Convert to grayscale and resize to hash_size x hash_size
            img = img.convert('L').resize((hash_size, hash_size), Image.LANCZOS)
            pixels = list(img.getdata())
            avg = sum(pixels) / len(pixels)
            # Create binary hash: 1 if pixel > avg, else 0
            bits = ''.join('1' if p > avg else '0' for p in pixels)
            return bits
    except Exception as e:
        print(f"  Warning: Could not hash {image_path}: {e}")
        return None

def hamming_distance(hash1, hash2):
    """Calculate Hamming distance between two hashes."""
    if len(hash1) != len(hash2):
        return 999
    return sum(c1 != c2 for c1, c2 in zip(hash1, hash2))

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
            continue
        seen_urls.add(url)
        unique_icons.append(icon)
    
    print(f"\nStep 1: Removed {dup_url_count} duplicate URL entries")
    
    # Step 2: Check for broken entries
    valid_icons = []
    broken_count = 0
    for icon in unique_icons:
        filename = urllib.parse.unquote(icon['url'].split('/')[-1])
        filepath = color_dir / filename
        if not filepath.exists():
            broken_count += 1
            continue
        valid_icons.append(icon)
    
    print(f"Step 2: Removed {broken_count} broken entries")
    
    # Step 3: Find visually duplicate images using perceptual hash
    print(f"\nStep 3: Computing perceptual hashes for {len(valid_icons)} icons...")
    hashes = {}
    for icon in valid_icons:
        filename = urllib.parse.unquote(icon['url'].split('/')[-1])
        filepath = color_dir / filename
        h = perceptual_hash(filepath)
        if h is None:
            continue
        if h not in hashes:
            hashes[h] = []
        hashes[h].append(icon)
    
    # Find exact hash matches
    exact_dups = {h: v for h, v in hashes.items() if len(v) > 1}
    print(f"  Found {len(exact_dups)} groups with identical perceptual hash")
    
    # Also check for near-duplicates (Hamming distance <= 2)
    # This catches icons that look the same but have minor differences
    hash_list = list(hashes.keys())
    near_dup_groups = []
    visited = set()
    
    for i, h1 in enumerate(hash_list):
        if h1 in visited:
            continue
        group = [h1]
        visited.add(h1)
        for h2 in hash_list[i+1:]:
            if h2 in visited:
                continue
            if hamming_distance(h1, h2) <= 2:
                group.append(h2)
                visited.add(h2)
        if len(group) > 1:
            near_dup_groups.append(group)
    
    print(f"  Found {len(near_dup_groups)} groups with near-identical perceptual hash")
    
    # Combine all duplicate groups
    all_dup_groups = []
    for h, icons in exact_dups.items():
        all_dup_groups.append(icons)
    
    for group_hashes in near_dup_groups:
        icons = []
        for h in group_hashes:
            icons.extend(hashes[h])
        all_dup_groups.append(icons)
    
    # For each group, keep one (prefer English name, shortest name)
    def sort_key(icon):
        name = icon['name']
        is_english = all(ord(c) < 128 for c in name)
        return (0 if is_english else 1, len(name), name)
    
    files_to_delete = []
    names_to_remove = set()
    
    for group in all_dup_groups:
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
    
    print(f"\nStep 3: Found {len(files_to_delete)} visually duplicate files to delete")
    
    # Step 4: Find orphaned files
    json_filenames = set(
        urllib.parse.unquote(icon['url'].split('/')[-1])
        for icon in valid_icons
    )
    all_files = set(f.name for f in color_dir.glob('*.png'))
    orphaned = all_files - json_filenames
    print(f"Step 4: Found {len(orphaned)} orphaned files")
    
    if dry_run:
        print(f"\n[DRY RUN] Would delete:")
        print(f"  - {len(files_to_delete)} duplicate image files")
        print(f"  - {len(orphaned)} orphaned files")
        print(f"  - {len(names_to_remove)} JSON entries")
        return 0
    
    # Delete files
    print(f"\nDeleting {len(files_to_delete)} duplicate files...")
    for filename in files_to_delete:
        filepath = color_dir / filename
        try:
            filepath.unlink()
        except Exception as e:
            print(f"  Failed: {filename}: {e}")
    
    print(f"Deleting {len(orphaned)} orphaned files...")
    for filename in orphaned:
        filepath = color_dir / filename
        try:
            filepath.unlink()
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
    print(f"Deleted files: {len(files_to_delete)} duplicates + {len(orphaned)} orphaned")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
