import os
import sqlalchemy as sa
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import pandas as pd
import json
from datetime import datetime
# Import local development config
from config import LOCAL_DATABASE

# Database configuration
DATABASE_URL = os.getenv('DATABASE_URL')
# If not available, fall back to local PostgreSQL 
if not DATABASE_URL:
    print("Warning: DATABASE_URL not found. Falling back to local Posgresql.")
    
    # Construct SQLAlchemy connection string for local PostgreSQL
    engine_string = (
        f"postgresql+psycopg2://{LOCAL_DATABASE['USER']}:{LOCAL_DATABASE['PASSWORD']}"
        f"@{LOCAL_DATABASE['HOST']}:{LOCAL_DATABASE['PORT']}/{LOCAL_DATABASE['NAME']}"
    )

    # Create SQLAlchemy engine
    engine = create_engine(engine_string, pool_pre_ping=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
else:
    # Use the cloud/database URL from environment with optional SSL and timeout config
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={
            "sslmode": "prefer",
            "connect_timeout": 10
        }
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_database():
    """Initialize database tables for storing road data"""
    if not engine:
        print("Database not configured, skipping initialization")
        return

    with engine.connect() as conn:
        # Create roads table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS roads (
                id SERIAL PRIMARY KEY,
                osm_id BIGINT UNIQUE,
                road_type VARCHAR(50) NOT NULL,
                name VARCHAR(255),
                geometry TEXT NOT NULL,
                tags TEXT,
                bbox VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Create index for faster queries
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_roads_type ON roads(road_type);
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_roads_bbox ON roads(bbox);
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_roads_osm_id ON roads(osm_id);
        """))

        # Create cache table for API responses
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS api_cache (
                id SERIAL PRIMARY KEY,
                cache_key VARCHAR(255) UNIQUE NOT NULL,
                data TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_cache_key ON api_cache(cache_key);
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_cache_expires ON api_cache(expires_at);
        """))

        conn.commit()
        # Print success message
        print("Databse shcema initialized successfully")

def save_road_data(road_data, road_type, bbox_str):
    """Save road data to database"""
    if not engine or not road_data or 'elements' not in road_data:
        return 0

    saved_count = 0
    with engine.connect() as conn:
        for element in road_data['elements']:
            if element['type'] == 'way' and 'geometry' in element:
                try:
                    # Extract data
                    osm_id = element.get('id')
                    if osm_id is None:
                        continue

                    name = element.get('tags', {}).get('name', '')
                    geometry = json.dumps(element['geometry'])
                    tags = json.dumps(element.get('tags', {}))

                    # Insert or update road data
                    conn.execute(text("""
                        INSERT INTO roads (osm_id, road_type, name, geometry, tags, bbox)
                        VALUES (:osm_id, :road_type, :name, :geometry, :tags, :bbox)
                        ON CONFLICT (osm_id) DO UPDATE SET
                            road_type = EXCLUDED.road_type,
                            name = EXCLUDED.name,
                            geometry = EXCLUDED.geometry,
                            tags = EXCLUDED.tags,
                            bbox = EXCLUDED.bbox,
                            updated_at = CURRENT_TIMESTAMP
                    """), {
                        'osm_id': osm_id,
                        'road_type': road_type,
                        'name': name,
                        'geometry': geometry,
                        'tags': tags,
                        'bbox': bbox_str
                    })
                    saved_count += 1
                except Exception as e:
                    st.error(f"Error saving road {osm_id if 'osm_id' in locals() else 'unknown'}: {str(e)}")
                    continue

        conn.commit()

    return saved_count

def get_cached_roads(road_type, bbox_str):
    """Get roads from database cache with retry logic for sleeping database"""
    if not engine:
        return None

    import time
    max_retries = 3
    retry_delay = 2

    for attempt in range(max_retries):
        try:
            with engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT osm_id, name, geometry, tags
                    FROM roads 
                    WHERE road_type = :road_type AND bbox = :bbox
                """), {'road_type': road_type, 'bbox': bbox_str})

                roads = []
                for row in result:
                    # Parse JSON strings from TEXT fields
                    tags = json.loads(row[3]) if row[3] else {}
                    geometry = json.loads(row[2])

                    roads.append({
                        'id': row[0],
                        'type': 'way',
                        'tags': tags,
                        'geometry': geometry
                    })

                if roads:
                    return {'elements': roads}
                return None

        except Exception as e:
            print(f"Database connection attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                print(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                print("All database connection attempts failed")
                raise e

def cache_api_response(cache_key, data, ttl_hours=1):
    """Cache API response in database"""
    from datetime import datetime, timedelta

    expires_at = datetime.now() + timedelta(hours=ttl_hours)

    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO api_cache (cache_key, data, expires_at)
            VALUES (:cache_key, :data, :expires_at)
            ON CONFLICT (cache_key) DO UPDATE SET
                data = EXCLUDED.data,
                expires_at = EXCLUDED.expires_at
        """), {
            'cache_key': cache_key,
            'data': json.dumps(data),  # Store as JSON string in TEXT field
            'expires_at': expires_at
        })
        conn.commit()

def get_cached_api_response(cache_key):
    """Get cached API response from database"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT data FROM api_cache 
            WHERE cache_key = :cache_key AND expires_at > CURRENT_TIMESTAMP
        """), {'cache_key': cache_key})

        row = result.fetchone()
        if row:
            # Parse JSON string from TEXT field
            return json.loads(row[0])
        return None

def cleanup_expired_cache():
    """Remove expired cache entries"""
    with engine.connect() as conn:
        conn.execute(text("""
            DELETE FROM api_cache WHERE expires_at < CURRENT_TIMESTAMP
        """))
        conn.commit()

def get_database_stats():
    """Get database statistics"""
    with engine.connect() as conn:
        # Count roads by type
        road_stats = conn.execute(text("""
            SELECT road_type, COUNT(*) as count
            FROM roads
            GROUP BY road_type
            ORDER BY count DESC
        """)).fetchall()

        # Total roads
        total_roads = conn.execute(text("""
            SELECT COUNT(*) FROM roads
        """)).scalar()

        # Cache stats
        cache_count = conn.execute(text("""
            SELECT COUNT(*) FROM api_cache
        """)).scalar()

        return {
            'total_roads': total_roads,
            'roads_by_type': {road_type: count for road_type, count in road_stats},
            'cached_responses': cache_count
        }

def search_roads_by_name(search_term, limit=10):
    """Search roads by name"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT road_type, name, geometry
            FROM roads
            WHERE name ILIKE :search_term
            ORDER BY name
            LIMIT :limit
        """), {
            'search_term': f'%{search_term}%',
            'limit': limit
        })

        return [{'type': row[0], 'name': row[1], 'geometry': json.loads(row[2])} for row in result]