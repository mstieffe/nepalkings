# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Pixel-level effects for Pygame surfaces."""


def brighten(img, brightness_factor):
    # Create a copy of the image
    image_copy = img.copy()

    # Lock the image surface to allow pixel-level access
    image_copy.lock()

    # Iterate over each pixel in the image
    for x in range(image_copy.get_width()):
        for y in range(image_copy.get_height()):
            # Get the color of the pixel
            r, g, b, a = image_copy.get_at((x, y))

            # Increase the brightness of RGB components
            r = min(int(r * brightness_factor), 255)
            g = min(int(g * brightness_factor), 255)
            b = min(int(b * brightness_factor), 255)

            # Update the pixel with the modified color
            image_copy.set_at((x, y), (r, g, b, a))

    # Unlock the image surface
    image_copy.unlock()

    # Return the modified image
    return image_copy


# Keep historical repr and pickle lookup behavior while utils.utils re-exports
# this canonical implementation.
brighten.__module__ = 'utils.utils'
