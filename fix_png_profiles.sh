#!/bin/bash

# Script to fix ICC profile warnings in PNG files using ImageMagick
#
# This removes incorrect ICC profiles from PNG files, eliminating
# libpng warnings and improving loading performance.
#
# Requirements:
#   brew install imagemagick  (on macOS)
#   or
#   apt-get install imagemagick  (on Linux)
#
# Usage:
#   chmod +x fix_png_profiles.sh
#   ./fix_png_profiles.sh

# Check if ImageMagick is installed
if ! command -v magick &> /dev/null && ! command -v convert &> /dev/null; then
    echo "Error: ImageMagick is not installed."
    echo "Install with: brew install imagemagick"
    exit 1
fi

# Determine the correct command
if command -v magick &> /dev/null; then
    CONVERT_CMD="magick convert"
else
    CONVERT_CMD="convert"
fi

echo "Fixing ICC profiles in PNG files..."
echo "This may take a few minutes..."

cd nepal_kings/img || exit 1

fixed=0
total=0

# Find all PNG files and strip ICC profiles
while IFS= read -r -d '' file; do
    ((total++))
    
    # Strip ICC profile by converting without profile
    $CONVERT_CMD "$file" +profile "icc" "$file.tmp" 2>/dev/null
    
    if [ $? -eq 0 ] && [ -f "$file.tmp" ]; then
        mv "$file.tmp" "$file"
        ((fixed++))
        echo "Fixed: $file"
    else
        rm -f "$file.tmp"
    fi
done < <(find . -name "*.png" -type f -print0)

echo ""
echo "Done! Processed $total PNG files."
echo "Fixed ICC profiles in $fixed files."
echo "The libpng warnings should now be eliminated."
