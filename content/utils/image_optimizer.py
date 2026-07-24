"""
Utility functions for optimizing images (compression, resizing, format conversion)
"""
import os
from io import BytesIO
from PIL import Image
from django.core.files.uploadedfile import InMemoryUploadedFile
import sys


def optimize_image(image_file, max_width=1200, max_height=800, quality=85, format='JPEG'):
    """
    Optimize an uploaded image by resizing and compressing it.
    
    Args:
        image_file: The uploaded image file
        max_width: Maximum width in pixels (default: 1200)
        max_height: Maximum height in pixels (default: 800)
        quality: JPEG quality (1-100, default: 85)
        format: Output format ('JPEG', 'PNG', 'WEBP')
    
    Returns:
        Optimized InMemoryUploadedFile or None if optimization fails
    """
    try:
        # Open the image
        img = Image.open(image_file)
        
        # Convert RGBA to RGB if necessary (for JPEG)
        if format == 'JPEG' and img.mode in ('RGBA', 'LA', 'P'):
            # Create a white background
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Calculate new dimensions while maintaining aspect ratio
        original_width, original_height = img.size
        ratio = min(max_width / original_width, max_height / original_height)
        
        # Only resize if image is larger than max dimensions
        if ratio < 1:
            new_width = int(original_width * ratio)
            new_height = int(original_height * ratio)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        else:
            # Image is already smaller, keep original size
            new_width, new_height = original_width, original_height
        
        # Save to BytesIO
        output = BytesIO()
        
        # Use WebP if supported and format is not specified, otherwise use specified format
        save_format = format
        if format == 'WEBP':
            img.save(output, format='WEBP', quality=quality, method=6)
            content_type = 'image/webp'
        elif format == 'PNG':
            # PNG doesn't support quality parameter
            img.save(output, format='PNG', optimize=True)
            content_type = 'image/png'
        else:  # JPEG
            img.save(output, format='JPEG', quality=quality, optimize=True)
            content_type = 'image/jpeg'
        
        output.seek(0)
        
        # Get original filename
        filename = image_file.name if hasattr(image_file, 'name') else 'image.jpg'
        # Change extension based on format
        if format == 'WEBP':
            filename = os.path.splitext(filename)[0] + '.webp'
        elif format == 'PNG':
            filename = os.path.splitext(filename)[0] + '.png'
        else:
            filename = os.path.splitext(filename)[0] + '.jpg'
        
        # Create InMemoryUploadedFile
        optimized_file = InMemoryUploadedFile(
            output,
            'ImageField',
            filename,
            content_type,
            sys.getsizeof(output),
            None
        )
        
        return optimized_file
    
    except Exception as e:
        # If optimization fails, return None (will use original)
        print(f"Image optimization failed: {str(e)}")
        return None


def create_thumbnail(image_file, width=400, height=300, quality=80):
    """
    Create a thumbnail version of an image.
    
    Args:
        image_file: The uploaded image file
        width: Thumbnail width in pixels (default: 400)
        height: Thumbnail height in pixels (default: 300)
        quality: JPEG quality (1-100, default: 80)
    
    Returns:
        Optimized InMemoryUploadedFile for thumbnail or None if fails
    """
    return optimize_image(image_file, max_width=width, max_height=height, quality=quality, format='JPEG')


def get_image_size_mb(image_file):
    """
    Get the size of an image file in MB.
    
    Args:
        image_file: The image file
    
    Returns:
        Size in MB (float)
    """
    try:
        if hasattr(image_file, 'size'):
            return image_file.size / (1024 * 1024)
        elif hasattr(image_file, 'read'):
            # Read the file to get size
            image_file.seek(0, os.SEEK_END)
            size = image_file.tell()
            image_file.seek(0)
            return size / (1024 * 1024)
        return 0
    except Exception:
        return 0

