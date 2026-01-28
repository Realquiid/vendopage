# sellers/tasks.py
from celery import shared_task
from django.core.files.base import ContentFile
from products.models import Product, ProductImage
import logging
import base64
import traceback

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def upload_product_images_async(self, product_id, images_data):
    """
    Upload images to Cloudinary in background.
    
    Args:
        product_id: ID of the product
        images_data: List of dicts with {'filename', 'content', 'order'}
    
    Returns:
        dict: {'success': bool, 'uploaded': int, 'failed': int}
    """
    try:
        logger.info(f"Starting background upload for product {product_id} with {len(images_data)} images")
        
        product = Product.objects.get(id=product_id)
        uploaded_count = 0
        failed_count = 0
        
        for img_data in images_data:
            try:
                # Decode base64 image
                image_content = base64.b64decode(img_data['content'])
                
                # Create Django file object
                image_file = ContentFile(
                    image_content,
                    name=img_data['filename']
                )
                
                # Upload to Cloudinary (happens automatically)
                ProductImage.objects.create(
                    product=product,
                    image=image_file,
                    order=img_data['order']
                )
                
                uploaded_count += 1
                logger.info(f"✅ Uploaded image {img_data['order'] + 1}/{len(images_data)} for product {product_id}")
                
            except Exception as img_error:
                failed_count += 1
                logger.error(f"❌ Failed to upload image {img_data['order']}: {str(img_error)}")
                continue
        
        # Check results
        if uploaded_count == 0:
            # All uploads failed - delete product
            logger.error(f"All images failed for product {product_id}. Deleting product.")
            product.delete()
            return {
                'success': False,
                'error': 'All images failed to upload',
                'uploaded': 0,
                'failed': failed_count
            }
        
        logger.info(f"✅ Upload complete for product {product_id}: {uploaded_count} uploaded, {failed_count} failed")
        
        return {
            'success': True,
            'uploaded': uploaded_count,
            'failed': failed_count,
            'product_id': product_id
        }
        
    except Product.DoesNotExist:
        logger.error(f"Product {product_id} not found")
        return {'success': False, 'error': 'Product not found'}
        
    except Exception as exc:
        logger.error(f"Task failed for product {product_id}: {str(exc)}\n{traceback.format_exc()}")
        
        # Retry up to 3 times
        try:
            raise self.retry(exc=exc, countdown=60)
        except self.MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for product {product_id}")
            # Delete product after max retries
            try:
                Product.objects.filter(id=product_id).delete()
            except:
                pass
            return {'success': False, 'error': 'Max retries exceeded'}


@shared_task
def cleanup_failed_products():
    """
    Cleanup products with no images (created but upload failed).
    Run this periodically via Celery Beat.
    """
    from django.utils import timezone
    from datetime import timedelta
    
    # Find products older than 1 hour with no images
    one_hour_ago = timezone.now() - timedelta(hours=1)
    
    failed_products = Product.objects.filter(
        created_at__lt=one_hour_ago,
        images__isnull=True
    )
    
    count = failed_products.count()
    if count > 0:
        failed_products.delete()
        logger.info(f"🧹 Cleaned up {count} failed products with no images")
    
    return {'cleaned': count}