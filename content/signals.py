"""
Django signals for content app
"""
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from content.models import Course
from content.utils.image_optimizer import optimize_image, get_image_size_mb


@receiver(pre_save, sender=Course)
def optimize_course_thumbnail(sender, instance, **kwargs):
    """
    Automatically optimize course thumbnail before saving.
    Only optimize if thumbnail is being updated (not just loaded from DB).
    """
    # Check if thumbnail field has been changed
    if instance.pk:  # Update case
        try:
            old_instance = Course.objects.get(pk=instance.pk)
            # If thumbnail hasn't changed, skip optimization
            if old_instance.thumbnail == instance.thumbnail:
                return
        except Course.DoesNotExist:
            pass
    
    # Only optimize if thumbnail exists and is a new file
    if instance.thumbnail and hasattr(instance.thumbnail, 'file'):
        # Check file size - only optimize if > 500KB
        file_size_mb = get_image_size_mb(instance.thumbnail)
        
        if file_size_mb > 0.5:  # Only optimize if > 500KB
            # Optimize the image
            optimized = optimize_image(
                instance.thumbnail,
                max_width=1200,
                max_height=800,
                quality=85,
                format='JPEG'
            )
            
            if optimized:
                # Replace the original with optimized version
                instance.thumbnail = optimized
                print(f"Optimized course thumbnail: {file_size_mb:.2f}MB -> reduced")

