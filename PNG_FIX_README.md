# Fixing libpng ICC Profile Warnings

## What the warnings mean

The warnings you're seeing indicate that some PNG image files have embedded ICC color profiles that don't match the actual image format:

```
libpng warning: iCCP: profile 'ICC Profile': 'RGB ': RGB color space not permitted on grayscale PNG
```

This happens when:
- A grayscale PNG has an RGB color profile embedded
- The profile was added incorrectly during image conversion/editing

**Impact:**
- ✅ **Functionality**: Images still display correctly
- ❌ **Performance**: Loading these images is slower
- ❌ **Console**: Clutters terminal output

## Performance Optimization

I've optimized the icon caching to reduce lag during figure operations:

### What was changed:
- **Before**: Clearing entire icon cache after upgrades → all icons regenerated
- **After**: Let `load_figures()` detect changes → only regenerate changed icons

This significantly reduces lag when building/upgrading/picking up figures.

## Fixing the PNG Files

You have two options to eliminate the warnings:

### Option 1: Python Script (Recommended)

```bash
# Install Pillow if needed
pip install pillow

# Run the fix script
python fix_png_profiles.py
```

### Option 2: Shell Script (using ImageMagick)

```bash
# Install ImageMagick
brew install imagemagick  # macOS
# or
apt-get install imagemagick  # Linux

# Make executable and run
chmod +x fix_png_profiles.sh
./fix_png_profiles.sh
```

Both scripts will:
1. Scan all PNG files in `nepal_kings/img/`
2. Remove incorrect ICC profiles
3. Report which files were fixed

### After running:
- ✅ No more libpng warnings
- ✅ Faster image loading
- ✅ Cleaner terminal output

## Technical Details

The scripts work by:
1. Opening each PNG file
2. Checking for embedded ICC profiles
3. Removing the profile if present
4. Saving the file without the profile

This is a safe, lossless operation that doesn't affect image quality or dimensions.

## Troubleshooting

**If warnings persist after running the script:**
1. Make sure you ran the script from the project root directory
2. Check that files in `nepal_kings/img/` were actually modified
3. Restart the game to clear any cached images

**If you don't want to fix the files:**
The warnings are harmless and can be ignored. The performance optimization (cache fix) will still help reduce lag.
