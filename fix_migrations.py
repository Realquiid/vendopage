# fix_migrations.py
import psycopg2
import os

# Paste your Railway DATABASE_URL here
DATABASE_URL = "postgresql://postgres:IfkXDUwBtAnkZhPLFpLQbmjVXLydOvml@postgres.railway.internal:5432/railway"
# Or use: DATABASE_URL = os.environ.get('DATABASE_URL')

try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    print("✅ Connected to database")
    
    # Delete conflicting migrations
    cur.execute("""
        DELETE FROM django_migrations 
        WHERE app = 'products' 
        AND name LIKE '0002%';
    """)
    print(f"✅ Deleted {cur.rowcount} '0002' migrations")
    
    cur.execute("""
        DELETE FROM django_migrations 
        WHERE app = 'products' 
        AND name LIKE '0003%';
    """)
    print(f"✅ Deleted {cur.rowcount} '0003' migrations")
    
    cur.execute("""
        DELETE FROM django_migrations 
        WHERE app = 'products' 
        AND name LIKE '0004%';
    """)
    print(f"✅ Deleted {cur.rowcount} '0004' migrations")
    
    # Check if image_url column exists
    cur.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'products_productimage'
        AND column_name = 'image_url';
    """)
    
    if cur.fetchone():
        print("✅ image_url column already exists")
    else:
        print("⚠️ image_url column missing, adding it...")
        cur.execute("""
            ALTER TABLE products_productimage 
            ADD COLUMN image_url VARCHAR(500) DEFAULT '';
        """)
        print("✅ Added image_url column")
    
    conn.commit()
    print("✅ All fixes applied successfully!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    
finally:
    if conn:
        cur.close()
        conn.close()