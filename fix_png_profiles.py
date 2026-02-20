#!/usr/bin/env python3
"""
Script to fix ICC profile warnings in PNG files.

This script removes ICC color profiles from PNG files that have incorrect profiles
(e.g., RGB profiles on grayscale images). This eliminates libpng warnings and
improves image loading performance.

Usage:
    python fix_png_profiles.py

Requirements:
    pip install pillow
"""

import os
from pathlib import Path
from PIL import Image

def fix_png_icc_profile(image_path):
    """Remove ICC profile from a PNG file."""
    try:
        with Image.open(image_path) as img:
            # Check if image has an ICC profile
            has_profile = 'icc_profile' in img.info
            
            if has_profile:
                print(f"Fixing: {image_path}")
                
                # Create a completely new image from pixel data
                # This strips ALL metadata including ICC profiles
                img_copy = img.copy()
                
                # Save with explicit parameters to ensure no ICC profile
                img_copy.save(image_path, 'PNG', optimize=False, icc_profile=None)
                
                return True
        
        return False
    except Exception as e:
        print(f"Error processing {image_path}: {e}")
        return False

def main():
    # Start from the nepal_kings/img directory
    img_dir = Path(__file__).parent / 'nepal_kings' / 'img'
    
    if not img_dir.exists():
        print(f"Error: {img_dir} not found")
        return
    
    print(f"Scanning PNG files in {img_dir}...")
    
    fixed_count = 0
    total_count = 0
    
    # Walk through all directories
    for png_file in img_dir.rglob('*.png'):
        total_count += 1
        if fix_png_icc_profile(png_file):
            fixed_count += 1
    
    print(f"\nDone! Fixed {fixed_count} out of {total_count} PNG files.")
    print("The libpng warnings should now be eliminated.")

if __name__ == '__main__':
    main()
