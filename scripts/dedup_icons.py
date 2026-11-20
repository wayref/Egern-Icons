#!/usr/bin/env python3
"""
Clean up Egern-Icons repo - user's approach:
1. Group by similar names (normalized: remove _, -, spaces, lowercase)
2. For each name group, check if images are the same (perceptual hash)
3. Only delete if BOTH name AND image match

Orphan cleanup: only delete files that have been orphaned for >7 days
(check git log for when file was last modified - recent files might be
in the middle of a multi-step restore, so we wait).

Usage:
    python3 dedup_icons.py [--dry-run]
"""

import sys
import json
import re
import urllib.parse
import subprocess
from datetime import datetime, timezone
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
    """Normalize name: remove _, -, spaces, lowercase."""
    return re.sub(r'[_\-\s]+', '', name.lower())

def get_file_age_days(filepath):
    """Get age in days of a file's last commit."""
    try:
        result = subprocess.run(
            ['git', 'log', '-1', '--format=%ct', '--', str(filepath)],
            capture_output=True, text=True, cwd=filepath.parent.parent
        )
        if result.returncode != 0 or not result.stdout.strip():
            return 999  # Unknown, treat as old
        timestamp = int(result.stdout.strip())
        file_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        now = datetime.now(timezone.utc)
        age = (now - file_time).total_seconds() / 86400
        return age
    except Exception:
        return 999

def main():
    dry_run = '--dry-run' in sys.argv
    repo_root = Path(__file__).parent.parent
    color_dir = repo_root / 'Color'
    json_path = repo_root / 'Egern-Icons.json'
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"Original: {len(data['icons'])} icons")
    
    # Step 1: Remove duplicate URLs and broken entries
    seen_urls = set()
    valid_icons = []
    for icon in data['icons']:
        if icon['url'] in seen_urls:
            continue
        seen_urls.add(icon['url'])
        filename = urllib.parse.unquote(icon['url'].split('/')[-1])
        if not (color_dir / filename).exists():
            continue
        valid_icons.append(icon)
    
    print(f"After removing dup URLs and broken: {len(valid_icons)}")
    
    # Step 2: Group by normalized name
    name_groups = {}
    for icon in valid_icons:
        norm = normalize_name(icon['name'])
        if norm not in name_groups:
            name_groups[norm] = []
        name_groups[norm].append(icon)
    
    # Only groups with multiple icons are candidates
    candidate_groups = {k: v for k, v in name_groups.items() if len(v) > 1}
    print(f"\nFound {len(candidate_groups)} name groups with duplicates")
    
    # Step 3: For each name group, check if images are the same
    files_to_delete = []
    names_to_remove = set()
    
    for norm_name, group in candidate_groups.items():
        print(f"\nGroup '{norm_name}' ({len(group)} icons):")
        for icon in group:
            print(f"  - {icon['name']}")
        
        # Compute hashes for all icons in this group
        hashes = {}
        for icon in group:
            filename = urllib.parse.unquote(icon['url'].split('/')[-1])
            h = perceptual_hash(color_dir / filename)
            if h:
                hashes[icon['name']] = h
        
        # Find icons with same/very similar hash (distance <= 3)
        visited = set()
        for i, icon1 in enumerate(group):
            if icon1['name'] in visited:
                continue
            if icon1['name'] not in hashes:
                continue
            
            similar = [icon1]
            visited.add(icon1['name'])
            
            for icon2 in group[i+1:]:
                if icon2['name'] in visited:
                    continue
                if icon2['name'] not in hashes:
                    continue
                
                dist = hamming_distance(hashes[icon1['name']], hashes[icon2['name']])
                if dist <= 3:
                    similar.append(icon2)
                    visited.add(icon2['name'])
            
            if len(similar) > 1:
                def sort_key(icon):
                    name = icon['name']
                    is_english = all(ord(c) < 128 for c in name)
                    has_underscore = '_' in name
                    return (0 if is_english else 1, 1 if has_underscore else 0, len(name), name)
                
                sorted_similar = sorted(similar, key=sort_key)
                keep = sorted_similar[0]
                delete = sorted_similar[1:]
                
                print(f"  -> Duplicates found (same name + same image):")
                print(f"     KEEP: {keep['name']}")
                for icon in delete:
                    filename = urllib.parse.unquote(icon['url'].split('/')[-1])
                    print(f"     DELETE: {icon['name']} ({filename})")
                    files_to_delete.append(filename)
                    names_to_remove.add(icon['name'])
            else:
                print(f"  -> No image duplicates (names similar but images different)")
    
    # Step 4: Find orphaned files - but only delete if orphaned for >7 days
    json_filenames = set(
        urllib.parse.unquote(icon['url'].split('/')[-1])
        for icon in valid_icons
    )
    all_files = set(f.name for f in color_dir.glob('*.png'))
    orphaned = all_files - json_filenames
    
    print(f"\nOrphaned files: {len(orphaned)}")
    old_orphans = []
    recent_orphans = []
    for filename in sorted(orphaned):
        age = get_file_age_days(color_dir / filename)
        if age > 7:
            old_orphans.append(filename)
            print(f"  - {filename} (orphaned {age:.1f} days, will delete)")
        else:
            recent_orphans.append(filename)
            print(f"  - {filename} (orphaned {age:.1f} days, too recent, skip)")
    
    print(f"\nWill delete {len(old_orphans)} old orphans, skip {len(recent_orphans)} recent ones")
    
    if dry_run:
        print(f"\n[DRY RUN] Would delete {len(files_to_delete)} duplicates + {len(old_orphans)} orphans")
        return 0
    
    # Delete duplicate files
    for filename in files_to_delete:
        try:
            (color_dir / filename).unlink()
        except Exception as e:
            print(f"  Failed: {filename}: {e}")
    
    # Delete old orphaned files
    for filename in old_orphans:
        try:
            (color_dir / filename).unlink()
            print(f"  Deleted orphan: {filename}")
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
    print(f"Deleted: {len(files_to_delete)} duplicates + {len(old_orphans)} orphans")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
