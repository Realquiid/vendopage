from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from sellers.models import Seller
from products.models import Product, ProductImage
from django.core.files.base import ContentFile
import base64
import json

@csrf_exempt
@require_http_methods(["GET"])
def get_vendor_by_phone(request, phone):
    """Get vendor details by phone number"""
    try:
        print(f"🔍 API: Looking for vendor with phone: {phone}")
        
        # Clean phone number (remove country code, spaces, dashes)
        clean_phone = phone.replace('+', '').replace('-', '').replace(' ', '').replace('234', '0').strip()
        
        print(f"🔍 API: Cleaned phone: {clean_phone}")
        
        # Try exact match first
        try:
            seller = Seller.objects.get(
                whatsapp_number=clean_phone,
                is_active=True
            )
            print(f"✅ API: Found vendor by exact match: {seller.business_name}")
        except Seller.DoesNotExist:
            # Try partial match (last 10 digits)
            last_10 = clean_phone[-10:] if len(clean_phone) >= 10 else clean_phone
            seller = Seller.objects.get(
                whatsapp_number__contains=last_10,
                is_active=True
            )
            print(f"✅ API: Found vendor by partial match: {seller.business_name}")
        
        return JsonResponse({
            'id': seller.id,
            'business_name': seller.business_name,
            'slug': seller.slug,
            'weekly_page_views': seller.weekly_page_views,
            'weekly_whatsapp_clicks': seller.weekly_whatsapp_clicks,
        })
        
    except Seller.DoesNotExist:
        print(f"❌ API: Vendor not found for phone: {phone}")
        return JsonResponse({'error': 'Vendor not found'}, status=404)
    except Seller.MultipleObjectsReturned:
        print(f"⚠️ API: Multiple vendors found for phone: {phone}")
        # If multiple, get first one
        seller = Seller.objects.filter(
            whatsapp_number__contains=clean_phone[-10:],
            is_active=True
        ).first()
        
        return JsonResponse({
            'id': seller.id,
            'business_name': seller.business_name,
            'slug': seller.slug,
            'weekly_page_views': seller.weekly_page_views,
            'weekly_whatsapp_clicks': seller.weekly_whatsapp_clicks,
        })
    except Exception as e:
        print(f"❌ API: Error: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def create_product_from_whatsapp(request):
    """Create product from WhatsApp bot"""
    try:
        print("📦 API: Creating product from WhatsApp...")
        
        data = json.loads(request.body)
        
        vendor_id = data.get('vendor_id')
        description = data.get('description')
        price = data.get('price')
        images_data = data.get('images', [])
        
        print(f"📦 API: Vendor ID: {vendor_id}")
        print(f"📦 API: Description: {description[:50]}...")
        print(f"📦 API: Price: {price}")
        print(f"📦 API: Images: {len(images_data)}")
        
        # Get vendor
        seller = Seller.objects.get(id=vendor_id, is_active=True)
        print(f"✅ API: Found vendor: {seller.business_name}")
        
        # Create product
        product = Product.objects.create(
            seller=seller,
            description=description,
            price=price if price else None
        )
        print(f"✅ API: Product created with ID: {product.id}")
        
        # Save images
        for index, img_data in enumerate(images_data):
            try:
                # The data is already base64 encoded string from whatsapp-web.js
                # We need to decode it
                image_bytes = base64.b64decode(img_data['data'])
                
                # Determine file extension
                mimetype = img_data.get('mimetype', 'image/jpeg')
                if 'jpeg' in mimetype or 'jpg' in mimetype:
                    ext = 'jpg'
                elif 'png' in mimetype:
                    ext = 'png'
                elif 'webp' in mimetype:
                    ext = 'webp'
                else:
                    ext = 'jpg'
                
                # Create image
                ProductImage.objects.create(
                    product=product,
                    image=ContentFile(image_bytes, name=f'whatsapp_{product.id}_{index}.{ext}'),
                    order=index
                )
                print(f"✅ API: Image {index + 1} saved")
                
            except Exception as e:
                print(f"❌ API: Error saving image {index}: {str(e)}")
                # Continue with other images even if one fails
        
        print(f"✅ API: Product created successfully!")
        
        return JsonResponse({
            'success': True,
            'product_id': product.id,
            'message': f'Product created with {len(images_data)} images'
        })
        
    except Seller.DoesNotExist:
        print(f"❌ API: Vendor not found with ID: {vendor_id}")
        return JsonResponse({'error': 'Vendor not found'}, status=404)
    except Exception as e:
        print(f"❌ API: Error creating product: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=400)