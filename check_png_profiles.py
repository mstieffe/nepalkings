#!/usr/bin/env python3
"""
Check which PNG files still have problematic ICC profiles.
This helps identify which images are causing libpng warnings.
"""

from PIL import Image
import os
from pathlib import Path

def check_png_profiles(directory):
    """
    Check all PNG files in directory for ICC profile issues.
    Returns list of problematic files.
    """
    problematic_files = []
    total_checked = 0
    
    # Walk through all subdirectories
    for root, dirs, files in os.walk(directory):
        for filename in files:
            if filename.lower().endswith('.png'):
                filepath = os.path.join(root, filename)
                total_checked += 1
                
                try:
                    with Image.open(filepath) as img:
                        # Check if image has ICC profile
                        if 'icc_profile' in img.info:
                            mode = img.mode
                            profile = img.info.get('icc_profile')
                            
                            # Check for the specific problem: RGB profile on grayscale PNG
                            if mode in ('L', 'LA', 'P'):  # Grayscale or palette modes
                                # This is problematic - grayscale image with color profile
                                rel_path = os.path.relpath(filepath, directory)
                                problematic_files.append({
                                    'path': rel_path,
                                    'mode': mode,
                                    'profile_size': len(profile)
                                })
                                print(f"❌ {rel_path}")
                                print(f"   Mode: {mode}, Profile size: {len(profile)} bytes")
                            
                except Exception as e:
                    print(f"⚠️  Error checking {filepath}: {e}")
    
    return problematic_files, total_checked

def main():
    img_dir = os.path.join(os.path.dirname(__file__), 'nepal_kings', 'img')
    
    print("=" * 80)
    print("PNG ICC Profile Checker")
    print("=" * 80)
    print(f"\nScanning directory: {img_dir}\n")
    
    problematic_files, total_checked = check_png_profiles(img_dir)
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total PNG files checked: {total_checked}")
    print(f"Files with problematic ICC profiles: {len(problematic_files)}")
    
    if problematic_files:
        print("\n" + "=" * 80)
        print("PROBLEMATIC FILES (Grayscale PNGs with RGB ICC profiles)")
        print("=" * 80)
        
        # Group by directory for easier reading
        by_dir = {}
        for file_info in problematic_files:
            dir_name = os.path.dirname(file_info['path'])
            if dir_name not in by_dir:
                by_dir[dir_name] = []
            by_dir[dir_name].append(file_info)
        
        for dir_name in sorted(by_dir.keys()):
            print(f"\n{dir_name}/")
            for file_info in by_dir[dir_name]:
                filename = os.path.basename(file_info['path'])
                print(f"  - {filename} (mode: {file_info['mode']})")
        
        print("\n" + "=" * 80)
        print("RECOMMENDED ACTION")
        print("=" * 80)
        print("Run fix_png_profiles.py again on these specific directories,")
        print("or use ImageMagick with: mogrify -strip nepal_kings/img/**/*.png")
    else:
        print("\n✅ All PNG files are clean! No problematic ICC profiles found.")
    
    print("=" * 80)

if __name__ == '__main__':
    main()
