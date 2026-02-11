import asyncio
import asyncpg
from dotenv import load_dotenv
import os
from urllib.parse import urlparse, unquote

load_dotenv()

async def test_connection():
    db_url = os.getenv('DATABASE_URL')
    
    # Parse the URL
    parsed = urlparse(db_url)
    host = parsed.hostname
    port = parsed.port or 5432
    database = parsed.path.lstrip('/')
    user = parsed.username
    # Ensure password is properly decoded from URL encoding
    password = unquote(parsed.password) if parsed.password else None
    
    print(f'Testing connection to: {host}:{port}/{database}')
    print(f'User: {user}')
    
    try:
        conn = await asyncpg.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            timeout=10
        )
        
        version = await conn.fetchval('SELECT version()')
        print(f'\n✅ Connection successful!')
        print(f'PostgreSQL version: {version.split(",")[0]}')
        
        # Check for required extensions
        extensions = await conn.fetch(
            "SELECT extname FROM pg_extension WHERE extname IN ('pgcrypto', 'vector')"
        )
        
        ext_names = [row['extname'] for row in extensions]
        if ext_names:
            print(f'✅ Installed extensions: {", ".join(ext_names)}')
        else:
            print('⚠️  Extensions pgcrypto and vector not yet installed')
            print('   (They will be added by migrations)')
        
        # Check current schema
        tables = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )
        
        table_names = [row['tablename'] for row in tables]
        if table_names:
            print(f'\n📊 Existing tables ({len(table_names)}): {", ".join(table_names)}')
        else:
            print('\n📊 No tables yet (run migrations to create schema)')
        
        await conn.close()
        print('\n✅ Database validation complete!')
        return True
        
    except Exception as e:
        print(f'\n❌ Connection failed: {e}')
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = asyncio.run(test_connection())
    exit(0 if success else 1)
