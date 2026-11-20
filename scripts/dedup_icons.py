#!/usr/bin/env python3
"""
Find and remove duplicate icons in Egern-Icons repo by comparing image content.
Keeps one copy per unique image (prefers English name, then shortest name).
Updates Egern-Icons.json accordingly.

Usage:
    python3 dedup_icons.py [--dry-run]

- Without --dry-run: deletes duplicate PNG files and updates JSON
- With --dry-run: only reports what would be deleted
"""

import os
import sys
import json
import hashlib
from pathlib import Path

def compute_hash(filepath):
    """Compute MD5 hash of file content."""
    with open(filepath, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

def main():
    dry_run = '--dry-run' in sys.argv
    repo_root = Path(__file__).parent.parent
    color_dir = repo_root / 'Color'
    json_path = repo_root / 'Egern-Icons.json'
    
    # Load JSON
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"Total icons in JSON: {len(data['icons'])}")
    
    # Group by content hash
    hashes = {}  # hash -> list of (name, filename)
    for icon in data['icons']:
        name = icon['name']
        url = icon['url']
        filename = url.split('/')[-1]
        filepath = color_dir / filename
        
        if not filepath.exists():
            print(f"  WARNING: {filename} not found, skipping")
            continue
        
        h = compute_hash(filepath)
        if h not in hashes:
            hashes[h] = []
        hashes[h].append((name, filename))
    
    # Find duplicates
    duplicates = {h: v for h, v in hashes.items() if len(v) > 1}
    print(f"\nDuplicate groups: {len(duplicates)}")
    total_dup = sum(len(v) for v in duplicates.values())
    to_delete = sum(len(v) - 1 for v in duplicates.values())
    print(f"Total duplicate files: {total_dup}")
    print(f"Files to delete: {to_delete}")
    
    if not duplicates:
        print("\nNo duplicates found.")
        return 0
    
    # For each group, decide which to keep and which to delete
    # Preference: English name > Chinese name, shorter name > longer name
    def sort_key(item):
        name, filename = item
        # English names (ASCII only) come first
        is_english = all(ord(c) < 128 for c in name)
        return (0 if is_english else 1, len(name), name)
    
    files_to_delete = []
    names_to_remove = set()
    
    for h, group in duplicates.items():
        sorted_group = sorted(group, key=sort_key)
        keep = sorted_group[0]
        delete = sorted_group[1:]
        
        print(f"\nGroup (hash {h[:8]}):")
        print(f"  KEEP: {keep[0]} ({keep[1]})")
        for name, filename in delete:
            print(f"  DELETE: {name} ({filename})")
            files_to_delete.append(filename)
            names_to_remove.add(name)
    
    if dry_run:
        print(f"\n[DRY RUN] Would delete {len(files_to_delete)} files")
        return 0
    
    # Delete files
    print(f"\nDeleting {len(files_to_delete)} files...")
    for filename in files_to_delete:
        filepath = color_dir / filename
        try:
            filepath.unlink()
            print(f"  Deleted {filename}")
        except Exception as e:
            print(f"  Failed to delete {filename}: {e}")
    
    # Update JSON (remove deleted entries)
    original_count = len(data['icons'])
    data['icons'] = [icon for icon in data['icons'] if icon['name'] not in names_to_remove]
    new_count = len(data['icons'])
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
    
    print(f"\nJSON updated: {original_count} -> {new_count} icons")
    print(f"Removed {original_count - new_count} entries")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
