
import requests
import json
import time
from database import save_road_data, get_cached_api_response, cache_api_response

def fetch_osm_roads(road_type, bbox_str, timeout=30):
    """
    Fetch road data from OpenStreetMap using Overpass API

    Args:
        road_type: Type of road (motorway, trunk, primary, secondary)
        bbox_str: Bounding box string "south,west,north,east"
        timeout: Request timeout in seconds

    Returns:
        Dictionary containing OSM data or None if failed
    """

    # Overpass API endpoint
    overpass_url = "https://overpass-api.de/api/interpreter"

    # Build Overpass query for specific road type within bounding box
    overpass_query = f"""
    [out:json][timeout:{timeout}][bbox:{bbox_str}];
    (
      way["highway"="{road_type}"];
    );
    out geom;
    """

    try:
        print(f"Fetching {road_type} roads from OpenStreetMap...")

        response = requests.post(
            overpass_url,
            data={'data': overpass_query},
            timeout=timeout,
            headers={'User-Agent': 'Toledo-Roads-Visualizer/1.0'}
        )

        if response.status_code == 200:
            data = response.json()
            print(f"Successfully fetched {len(data.get('elements', []))} {road_type} roads from OSM")
            return data
        else:
            print(f"OSM API request failed with status {response.status_code}: {response.text}")
            return None

    except requests.exceptions.Timeout:
        print(f"OSM API request timed out after {timeout} seconds")
        return None
    except requests.exceptions.RequestException as e:
        print(f"OSM API request failed: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Failed to parse OSM API response: {e}")
        return None

print("OSM data fetch_osm_roads loaded successfully")

def update_roads_from_osm(bbox_str="41.4,-83.8,41.9,-83.2", road_types=None):
    """
    Update road data by fetching from OpenStreetMap

    Args:
        bbox_str: Bounding box for Toledo area "south,west,north,east"
        road_types: List of road types to fetch, defaults to all types

    Returns:
        Dictionary with update statistics
    """
    if road_types is None:
        road_types = ['motorway', 'trunk', 'primary', 'secondary']

    stats = {
        'total_fetched': 0,
        'total_saved': 0,
        'by_type': {},
        'errors': []
    }
    # print("Starting OSM roads update...")
    for road_type in road_types:
        try:
            # Check cache first
            cache_key = f"osm_{road_type}_{bbox_str}"
            cached_data = get_cached_api_response(cache_key)

            if cached_data:
                print(f"Using cached data for {road_type} roads")
                osm_data = cached_data
            else:
                # Fetch from OSM API
                osm_data = fetch_osm_roads(road_type, bbox_str)

                if osm_data:
                    # Cache the response for 1 hour
                    cache_api_response(cache_key, osm_data, ttl_hours=1)
                else:
                    stats['errors'].append(f"Failed to fetch {road_type} roads from OSM")
                    continue

            # Save to database
            if osm_data and 'elements' in osm_data:
                fetched_count = len(osm_data['elements'])
                saved_count = save_road_data(osm_data, road_type, bbox_str)

                stats['total_fetched'] += fetched_count
                stats['total_saved'] += saved_count
                stats['by_type'][road_type] = {
                    'fetched': fetched_count,
                    'saved': saved_count
                }

                print(f"Updated {saved_count}/{fetched_count} {road_type} roads")

                # Rate limiting - be nice to the API
                time.sleep(1)

        except Exception as e:
            error_msg = f"Error updating {road_type} roads: {str(e)}"
            stats['errors'].append(error_msg)
            print(error_msg)

    return stats

print("OSM roads update_roads_from_osm loaded successfully")

def fetch_roads_by_name(road_name, bbox_str="41.4,-83.8,41.9,-83.2", timeout=30):
    """
    Fetch specific roads by name from OpenStreetMap

    Args:
        road_name: Name of the road to search for
        bbox_str: Bounding box string "south,west,north,east"
        timeout: Request timeout in seconds

    Returns:
        Dictionary containing OSM data or None if failed
    """

    overpass_url = "https://overpass-api.de/api/interpreter"

    # Build Overpass query to search for roads by name
    overpass_query = f"""
    [out:json][timeout:{timeout}][bbox:{bbox_str}];
    (
      way["highway"]["name"~"{road_name}",i];
    );
    out geom;
    """

    try:
        print(f"Searching for roads named '{road_name}' in OpenStreetMap...")

        response = requests.post(
            overpass_url,
            data={'data': overpass_query},
            timeout=timeout,
            headers={'User-Agent': 'Toledo-Roads-Visualizer/1.0'}
        )

        if response.status_code == 200:
            data = response.json()
            found_count = len(data.get('elements', []))
            print(f"Found {found_count} roads matching '{road_name}'")
            return data
        else:
            print(f"OSM search request failed with status {response.status_code}")
            return None

    except Exception as e:
        print(f"Error searching for road '{road_name}': {e}")
        return None

print("OSM road fetch_roads_by_name loaded successfully")

def get_available_road_types(bbox_str="41.4,-83.8,41.9,-83.2", timeout=30):
    """
    Get all available road types in the specified area

    Args:
        bbox_str: Bounding box string "south,west,north,east"
        timeout: Request timeout in seconds

    Returns:
        List of available highway types
    """

    overpass_url = "https://overpass-api.de/api/interpreter"

    # Query to get unique highway types in the area
    overpass_query = f"""
    [out:json][timeout:{timeout}][bbox:{bbox_str}];
    (
      way["highway"];
    );
    out tags;
    """

    try:
        print("Fetching available road types from OpenStreetMap...")

        response = requests.post(
            overpass_url,
            data={'data': overpass_query},
            timeout=timeout,
            headers={'User-Agent': 'Toledo-Roads-Visualizer/1.0'}
        )

        if response.status_code == 200:
            data = response.json()
            highway_types = set()

            for element in data.get('elements', []):
                highway_type = element.get('tags', {}).get('highway')
                if highway_type:
                    highway_types.add(highway_type)

            road_types = sorted(list(highway_types))
            print(f"Found {len(road_types)} different road types: {road_types}")
            return road_types
        else:
            print(f"Road types query failed with status {response.status_code}")
            return []

    except Exception as e:
        print(f"Error fetching road types: {e}")
        return []

print("OSM road get_available_road_types loaded successfully")
