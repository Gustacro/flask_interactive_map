from flask import Flask, render_template, jsonify
from osm_data import update_roads_from_osm
import json
import os
from database import (
    init_database, get_cached_roads, cleanup_expired_cache,
    get_database_stats, search_roads_by_name
)

app = Flask(__name__)

# Initialize database on startup
try:
    init_database()
    cleanup_expired_cache()
    print("Database initialized successfully")
except Exception as e:
    print(f"Database initialization failed: {e}")

# Define the main route to serve the HTML page
@app.route('/')
def index():
    """Serve the main HTML page with Leaflet map"""
    return render_template('index.html')

# Define API endpoints, including data retrieval and updates
@app.route('/data')
def get_data():
    """Serve GeoJSON data from database or static file"""
    try:
        # Try to get data from database first
        # Define bounding box for Toledo area
        bbox_str = "41.4,-83.8,41.9,-83.2"

        # Try to get cached roads from database
        all_roads = []
        road_types = ['motorway', 'trunk', 'primary', 'secondary']
        # Iterate through each road type and fetch from cache
        for road_type in road_types:
            try:
                cached_roads = get_cached_roads(road_type, bbox_str)
                if cached_roads and 'elements' in cached_roads:
                    for road in cached_roads['elements']:
                        # Convert to GeoJSON format
                        if 'geometry' in road and road['geometry']: # Ensure geometry exists, and not empty
                            coordinates = [[node['lat'], node['lon']] for node in road['geometry']]
                            if len(coordinates) > 1: # Ensure at least two points for a LineString
                                # Create GeoJSON feature
                                feature = {
                                    "type": "Feature",
                                    "properties": {
                                        "name": road.get('tags', {}).get('name', f'{road_type.title()} Road'),
                                        "highway": road_type,
                                        "osm_id": road.get('id', '')
                                    },
                                    "geometry": {
                                        "type": "LineString",
                                        "coordinates": [[coord[1], coord[0]] for coord in coordinates]  # [lon, lat]
                                    }
                                }
                                all_roads.append(feature)
            except Exception as road_error:
                print(f"Error getting {road_type} roads: {road_error}")
                continue
        # If we have roads from the database, return them
        if all_roads:
            geojson_data = {
                "type": "FeatureCollection",
                "features": all_roads
            }
            print(f"Serving {len(all_roads)} roads from database")
            return jsonify(geojson_data)

        # Fallback to static file if database is empty
        print("Database returned no roads, falling back to static file")
        static_file_path = os.path.join('static', 'data', 'toledo_roads.geojson')
        if os.path.exists(static_file_path):
            with open(static_file_path, 'r') as f:
                data = json.load(f)
            print(f"Serving {len(data.get('features', []))} roads from static file")
            return jsonify(data)

        # Return empty GeoJSON if no data available
        return jsonify({
            "type": "FeatureCollection",
            "features": []
        })

    except Exception as e:
        print(f"Error serving data: {e}")
        # Return empty GeoJSON on error
        return jsonify({
            "type": "FeatureCollection",
            "features": []
        })

# Define additional API endpoints for stats
@app.route('/stats')
def get_stats():
    """Get database statistics"""
    try:
        stats = get_database_stats()
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)})

# Define API endpoint for searching roads by name, which can be used for autocomplete or filtering
@app.route('/search/<query>')
def search_roads(query):
    """Search roads by name"""
    try:
        results = search_roads_by_name(query)
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)})

# Define API endpoint to trigger OSM data update manually
@app.route('/update-data')
def update_data():
    """Trigger OSM data update manually"""
    try:
        stats = update_roads_from_osm()
        return jsonify({
            "status": "success",
            "message": "Data update completed",
            "stats": stats
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=4000, debug=True)
