#!/usr/bin/env python3

import polars as pl
import requests
import numpy as np
from datetime import datetime
import streamlit as st
import folium
from streamlit_folium import st_folium
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
import warnings
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
import time
import math
import json
import os
warnings.filterwarnings('ignore')

BOSTON_LAT, BOSTON_LON = 42.3601, -71.0589

class RoutingService:
    def __init__(self):
        self.base_url = "https://router.project-osrm.org/route/v1/walking"
        self.cache = {}
    
    def get_walking_distance(self, lat1, lon1, lat2, lon2):
        cache_key = f"{lat1:.6f},{lon1:.6f}->{lat2:.6f},{lon2:.6f}"
        
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            url = f"{self.base_url}/{lon1},{lat1};{lon2},{lat2}"
            params = {
                'overview': 'false',
                'geometries': 'geojson',
                'steps': 'false',
                'annotations': 'false'
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data['code'] == 'Ok' and data['routes'] and len(data['routes']) > 0:
                distance_meters = data['routes'][0]['distance']
                distance_miles = distance_meters * 0.000621371
                
                straight_distance = self.get_straight_distance(lat1, lon1, lat2, lon2)
                if distance_miles > straight_distance * 3.0:
                    self.cache[cache_key] = None
                    return None
                
                self.cache[cache_key] = distance_miles
                return distance_miles
            else:
                self.cache[cache_key] = None
                return None
                
        except Exception as e:
            print(f"Routing error: {e}")
            self.cache[cache_key] = None
            return None
    
    def get_straight_distance(self, lat1, lon1, lat2, lon2):
        R = 3959
        lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
        c = 2 * np.arcsin(np.sqrt(a))
        return R * c

class GeocodeService:
    def __init__(self):
        self.geolocator = Nominatim(user_agent="bluebikes_dashboard")
        self.cache = {}
    
    def geocode_address(self, address):
        if address in self.cache:
            return self.cache[address]
        
        try:
            intersection_keywords = [' and ', ' & ', ' @ ', ' at ']
            is_intersection = any(keyword in address.lower() for keyword in intersection_keywords)
            
            if is_intersection:
                search_addresses = []
                
                normalized_address = address.lower()
                for keyword in intersection_keywords:
                    normalized_address = normalized_address.replace(keyword, ' and ')
                
                if "boston" not in normalized_address and "ma" not in normalized_address:
                    search_addresses.append(f"{normalized_address}, Boston, MA")
                    search_addresses.append(f"{address}, Boston, MA")
                else:
                    search_addresses.append(normalized_address)
                    search_addresses.append(address)
                
                if ' and ' in normalized_address:
                    streets = normalized_address.split(' and ')
                    if len(streets) == 2:
                        street1 = streets[0].strip()
                        street2 = streets[1].strip()
                        
                        base_location = ", Boston, MA" if "boston" not in normalized_address else ""
                        search_addresses.extend([
                            f"{street1} & {street2}{base_location}",
                            f"{street1} at {street2}{base_location}",
                            f"intersection of {street1} and {street2}{base_location}",
                            f"{street1}/{street2}{base_location}"
                        ])
            else:
                if "boston" not in address.lower() and "ma" not in address.lower():
                    search_addresses = [f"{address}, Boston, MA"]
                else:
                    search_addresses = [address]
            
            for search_address in search_addresses:
                for attempt in range(2):
                    try:
                        location = self.geolocator.geocode(search_address, timeout=10)
                        if location:
                            result = {
                                'lat': location.latitude,
                                'lon': location.longitude,
                                'formatted_address': location.address,
                                'success': True,
                                'error': None
                            }
                            self.cache[address] = result
                            return result
                            
                    except GeocoderTimedOut:
                        if attempt < 1:
                            time.sleep(1)
                            continue
                        else:
                            break
                
        except Exception as e:
            pass
        
        result = {
            'lat': None,
            'lon': None,
            'formatted_address': None,
            'success': False,
            'error': f"Could not find location for: {address}"
        }
        self.cache[address] = result
        return result

class WeatherService:
    def __init__(self, api_key=None):
        self.api_key = api_key
        self.base_url = "http://api.openweathermap.org/data/2.5"
    
    def get_current_weather(self, lat=BOSTON_LAT, lon=BOSTON_LON):
        if not self.api_key or self.api_key == "your_openweathermap_api_key_here":
            return None
        
        try:
            url = f"{self.base_url}/weather"
            params = {
                'lat': lat,
                'lon': lon,
                'appid': self.api_key,
                'units': 'imperial'
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            return {
                'temperature': data['main']['temp'],
                'feels_like': data['main']['feels_like'],
                'humidity': data['main']['humidity'],
                'wind_speed': data['wind']['speed'] if 'wind' in data else 0,
                'description': data['weather'][0]['description'].title(),
                'icon': data['weather'][0]['icon']
            }
            
        except Exception:
            return None

class BlueBikesService:
    def __init__(self):
        self.stations_df = None
        self.last_update = None
    
    def fetch_station_data(self):
        print("Fetching live BlueBikes data...")
        
        try:
            gbfs_url = "http://gbfs.bluebikes.com/gbfs/gbfs.json"
            response = requests.get(gbfs_url, timeout=15)
            response.raise_for_status()
            gbfs_data = response.json()
            
            station_info_url = None
            station_status_url = None
            
            for feed in gbfs_data['data']['en']['feeds']:
                if feed['name'] == 'station_information':
                    station_info_url = feed['url']
                elif feed['name'] == 'station_status':
                    station_status_url = feed['url']
            
            if not station_info_url or not station_status_url:
                raise Exception("Could not find station data URLs")
            
            station_info_response = requests.get(station_info_url, timeout=15)
            station_info_response.raise_for_status()
            station_info = station_info_response.json()
            
            station_status_response = requests.get(station_status_url, timeout=15)
            station_status_response.raise_for_status()
            station_status = station_status_response.json()
            
            stations_df = pl.DataFrame(station_info['data']['stations'])
            status_df = pl.DataFrame(station_status['data']['stations'])
            
            combined_df = stations_df.join(status_df, on='station_id', how='left')
            
            self.stations_df = combined_df
            self.last_update = datetime.now()
            
            print(f"Fetched data for {len(combined_df)} BlueBikes stations!")
            return combined_df
            
        except Exception as e:
            print(f"Error fetching BlueBikes data: {e}")
            return pl.DataFrame()
    
    def haversine_distance(self, lat1, lon1, lat2, lon2):
        R = 3959
        lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
        c = 2 * np.arcsin(np.sqrt(a))
        return R * c
    
    def get_bearing(self, lat1, lon1, lat2, lon2):
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dlon = lon2 - lon1
        y = math.sin(dlon) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
        bearing = math.atan2(y, x)
        bearing = math.degrees(bearing)
        bearing = (bearing + 360) % 360
        return bearing
    
    def is_in_direction(self, bearing, direction):
        direction_ranges = {
            'north': (337.5, 22.5),
            'northeast': (22.5, 67.5),
            'east': (67.5, 112.5),
            'southeast': (112.5, 157.5),
            'south': (157.5, 202.5),
            'southwest': (202.5, 247.5),
            'west': (247.5, 292.5),
            'northwest': (292.5, 337.5),
        }
        
        if direction not in direction_ranges:
            return True
        
        start, end = direction_ranges[direction]
        
        if start > end:
            return bearing >= start or bearing <= end
        else:
            return start <= bearing <= end
    
    def get_stations_near_location(self, location_name, lat, lon, radius_miles, direction=None, force_refresh=False):
        if self.stations_df is None or self.stations_df.is_empty():
            return pl.DataFrame()
        
        cache_key = f"{lat:.6f}_{lon:.6f}_{radius_miles}_{direction or 'all'}"
        
        if not force_refresh and cache_key in st.session_state.cached_stations:
            cached_data = st.session_state.cached_stations[cache_key]
            
            updated_stations = []
            station_lookup = {station.get('station_id'): station for station in self.stations_df.iter_rows(named=True)}
            
            for cached_station in cached_data:
                station_id = cached_station.get('station_id')
                current_station = station_lookup.get(station_id)
                
                if current_station:
                    updated_station = dict(cached_station)
                    updated_station['num_bikes_available'] = current_station.get('num_bikes_available', 0)
                    updated_station['num_ebikes_available'] = current_station.get('num_ebikes_available', 0)
                    updated_station['num_docks_available'] = current_station.get('num_docks_available', 0)
                    updated_station['is_renting'] = current_station.get('is_renting', 1)
                    updated_station['is_returning'] = current_station.get('is_returning', 1)
                    updated_stations.append(updated_station)
            
            if updated_stations:
                st.success("✅ Updated bike/dock availability using cached locations")
                return pl.DataFrame(updated_stations).sort('distance_miles')
            else:
                st.warning("Cache expired, recalculating routes...")
                del st.session_state.cached_stations[cache_key]
        
        progress_bar = st.progress(0)
        progress_text = st.empty()
        progress_text.text("🚶‍♀️ Calculating walking routes...")
        
        straight_line_candidates = []
        total_stations = len(self.stations_df)
        
        progress_text.text("Finding nearby stations...")
        
        for i, station in enumerate(self.stations_df.iter_rows(named=True)):
            progress = i / total_stations
            progress_bar.progress(progress)
            
            try:
                station_lat = float(station.get('lat', 0))
                station_lon = float(station.get('lon', 0))
                straight_distance = self.haversine_distance(lat, lon, station_lat, station_lon)
                
                if straight_distance <= radius_miles:
                    if direction and direction != 'all':
                        bearing = self.get_bearing(lat, lon, station_lat, station_lon)
                        if not self.is_in_direction(bearing, direction):
                            continue
                    
                    station_copy = dict(station)
                    station_copy['straight_distance'] = straight_distance
                    straight_line_candidates.append(station_copy)
                    
            except (ValueError, TypeError):
                continue
        
        progress_bar.progress(1.0)
        progress_text.text(f"Found {len(straight_line_candidates)} nearby stations")
        
        if not straight_line_candidates:
            time.sleep(1)
            progress_bar.empty()
            progress_text.empty()
            return pl.DataFrame()
        
        walkable_stations = []
        routing_service = RoutingService()
        routing_failures = 0
        excluded_by_walking = 0
        
        progress_text.text("Calculating walking routes...")
        
        for i, station in enumerate(straight_line_candidates):
            progress = i / len(straight_line_candidates)
            progress_bar.progress(progress)
            
            station_lat = float(station.get('lat', 0))
            station_lon = float(station.get('lon', 0))
            
            walking_distance = routing_service.get_walking_distance(lat, lon, station_lat, station_lon)
            
            if walking_distance is None:
                routing_failures += 1
                continue
            
            if walking_distance > radius_miles:
                excluded_by_walking += 1
                continue
            
            station['distance_miles'] = walking_distance
            station['area'] = location_name
            walkable_stations.append(station)
        
        progress_bar.progress(1.0)
        progress_text.text(f"Found {len(walkable_stations)} walkable stations")
        
        time.sleep(1)
        progress_bar.empty()
        progress_text.empty()
        
        if routing_failures > 0 or excluded_by_walking > 0:
            summary_parts = []
            if routing_failures > 0:
                summary_parts.append(f"{routing_failures} blocked by barriers")
            if excluded_by_walking > 0:
                summary_parts.append(f"{excluded_by_walking} too far to walk")
            st.caption(f"Filtered out: {', '.join(summary_parts)}")
        
        if walkable_stations:
            st.session_state.cached_stations[cache_key] = walkable_stations
            return pl.DataFrame(walkable_stations).sort('distance_miles')
        else:
            return pl.DataFrame()

def save_config(api_key, favorites, save_api_key):
    try:
        config = {
            'api_key': api_key if save_api_key else '',
            'favorites': favorites,
            'save_api_key': save_api_key
        }
        config_file = os.path.expanduser("~/.bluebikes_config.json")
        with open(config_file, 'w') as f:
            json.dump(config, f)
    except Exception:
        pass

def load_config():
    try:
        config_file = os.path.expanduser("~/.bluebikes_config.json")
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {'api_key': '', 'favorites': {}, 'save_api_key': False}

def create_streamlit_app():
    st.set_page_config(
        page_title="BlueBikes",
        page_icon="🚴‍♀️",
        layout="wide"
    )
    
    st.title("🚴‍♀️ BlueBikes")
    
    if 'bluebikes_service' not in st.session_state:
        st.session_state.bluebikes_service = BlueBikesService()
    if 'weather_service' not in st.session_state:
        st.session_state.weather_service = WeatherService()
    if 'geocode_service' not in st.session_state:
        st.session_state.geocode_service = GeocodeService()
    if 'routing_service' not in st.session_state:
        st.session_state.routing_service = RoutingService()
    if 'locations' not in st.session_state:
        st.session_state.locations = {}
    if 'favorites' not in st.session_state:
        st.session_state.favorites = {}
    if 'map_interaction' not in st.session_state:
        st.session_state.map_interaction = None
    if 'saved_api_key' not in st.session_state:
        st.session_state.saved_api_key = ""
    if 'save_api_key' not in st.session_state:
        st.session_state.save_api_key = False
    if 'pickup_address' not in st.session_state:
        st.session_state.pickup_address = ""
    if 'dropoff_address' not in st.session_state:
        st.session_state.dropoff_address = ""
    if 'pickup_radius' not in st.session_state:
        st.session_state.pickup_radius = 0.5
    if 'dropoff_radius' not in st.session_state:
        st.session_state.dropoff_radius = 0.5
    if 'pickup_direction' not in st.session_state:
        st.session_state.pickup_direction = 'all'
    if 'dropoff_direction' not in st.session_state:
        st.session_state.dropoff_direction = 'all'
    if 'last_search_params' not in st.session_state:
        st.session_state.last_search_params = {}
    if 'cached_stations' not in st.session_state:
        st.session_state.cached_stations = {}
    
    if 'storage_loaded' not in st.session_state:
        config = load_config()
        st.session_state.saved_api_key = config.get('api_key', '')
        st.session_state.favorites = config.get('favorites', {})
        st.session_state.save_api_key = config.get('save_api_key', False)
        st.session_state.storage_loaded = True
    
    with st.sidebar:
        st.header("Settings")
        
        save_api_key = st.checkbox("Remember API key", value=st.session_state.save_api_key)
        
        weather_api_key = st.text_input(
            "Weather API Key (optional):",
            value=st.session_state.saved_api_key if save_api_key else "",
            placeholder="Enter OpenWeatherMap API key",
            help="Get free API key at openweathermap.org",
            type="password"
        )
        
        if save_api_key != st.session_state.save_api_key or (save_api_key and weather_api_key != st.session_state.saved_api_key):
            st.session_state.save_api_key = save_api_key
            if save_api_key:
                st.session_state.saved_api_key = weather_api_key
            else:
                st.session_state.saved_api_key = ""
            
            save_config(st.session_state.saved_api_key, st.session_state.favorites, st.session_state.save_api_key)
        
        if weather_api_key:
            st.session_state.weather_service = WeatherService(weather_api_key)
        
        if st.session_state.favorites:
            selected_favorite = st.selectbox(
                "Load Favorite:",
                options=[''] + list(st.session_state.favorites.keys()),
                format_func=lambda x: "Select..." if x == '' else x
            )
            
            if selected_favorite and selected_favorite != '':
                if st.button("Load"):
                    fav = st.session_state.favorites[selected_favorite]
                    if fav['search_type'] == 'pickup':
                        st.session_state.pickup_address = fav['address']
                        st.session_state.pickup_radius = fav['radius']
                        st.session_state.pickup_direction = fav['direction']
                    else:
                        st.session_state.dropoff_address = fav['address']
                        st.session_state.dropoff_radius = fav['radius']
                        st.session_state.dropoff_direction = fav['direction']
                    
                    location_key = f"{fav['address']}_{fav['search_type']}"
                    st.session_state.locations[location_key] = fav['location_result']
            
            if st.button("Delete Selected"):
                if selected_favorite and selected_favorite != '':
                    del st.session_state.favorites[selected_favorite]
                    save_config(st.session_state.saved_api_key, st.session_state.favorites, st.session_state.save_api_key)
        
        auto_refresh = st.checkbox("Auto-refresh", value=False)
        if auto_refresh:
            refresh_interval = st.selectbox("Interval:", [30, 60, 120, 300], index=2,
                format_func=lambda x: f"{x//60}min" if x >= 60 else f"{x}s")
            time.sleep(refresh_interval)
            st.rerun()
    
    search_type = st.radio(
        "",
        options=['pickup', 'dropoff'],
        format_func=lambda x: 'Find bikes' if x == 'pickup' else 'Find docks',
        horizontal=True,
        key="search_type_radio"
    )
    
    current_address = st.session_state.pickup_address if search_type == 'pickup' else st.session_state.dropoff_address
    current_radius_index = 2
    current_direction_index = 0
    
    radius_options = [0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0]
    current_radius_value = st.session_state.pickup_radius if search_type == 'pickup' else st.session_state.dropoff_radius
    try:
        current_radius_index = radius_options.index(current_radius_value)
    except ValueError:
        current_radius_index = 2
    
    direction_options = ['all', 'north', 'northeast', 'east', 'southeast', 'south', 'southwest', 'west', 'northwest']
    current_direction_value = st.session_state.pickup_direction if search_type == 'pickup' else st.session_state.dropoff_direction
    try:
        current_direction_index = direction_options.index(current_direction_value)
    except ValueError:
        current_direction_index = 0
    
    col1, col2, col3 = st.columns([3, 1, 1])
    
    with col1:
        current_saved_address = st.session_state.pickup_address if search_type == 'pickup' else st.session_state.dropoff_address
        
        address = st.text_input(
            f"{'Pickup' if search_type == 'pickup' else 'Dropoff'} Address:",
            value=current_saved_address,
            placeholder="e.g., 123 Main St or Ruggles Ave and Huntington Ave",
            key=f"address_input_{search_type}"
        )
        
        if search_type == 'pickup':
            st.session_state.pickup_address = address
        else:
            st.session_state.dropoff_address = address
    
    with col2:
        radius = st.selectbox(
            "Radius:",
            options=radius_options,
            index=current_radius_index,
            format_func=lambda x: f"{x} mi",
            key=f"radius_select_{search_type}"
        )
        if search_type == 'pickup':
            st.session_state.pickup_radius = radius
        else:
            st.session_state.dropoff_radius = radius
    
    with col3:
        direction = st.selectbox(
            "Direction:",
            options=direction_options,
            index=current_direction_index,
            format_func=lambda x: {
                'all': 'All', 'north': 'N', 'northeast': 'NE', 'east': 'E',
                'southeast': 'SE', 'south': 'S', 'southwest': 'SW', 'west': 'W', 'northwest': 'NW'
            }[x],
            key=f"direction_select_{search_type}"
        )
        if search_type == 'pickup':
            st.session_state.pickup_direction = direction
        else:
            st.session_state.dropoff_direction = direction
    
    location_result = None
    if address:
        location_key = f"{address}_{search_type}"
        if location_key not in st.session_state.locations:
            with st.spinner("Finding location..."):
                location_result = st.session_state.geocode_service.geocode_address(address)
                st.session_state.locations[location_key] = location_result
        else:
            location_result = st.session_state.locations[location_key]
    
    if address and location_result:
        if location_result['success']:
            save_col1, save_col2, refresh_col = st.columns([2, 2, 1])
            with save_col1:
                st.success(f"Found: {location_result['formatted_address']}")
            with save_col2:
                if st.button("Save as Favorite"):
                    favorite_name = f"{search_type}: {address[:15]}..."
                    st.session_state.favorites[favorite_name] = {
                        'address': address,
                        'search_type': search_type,
                        'radius': radius,
                        'direction': direction,
                        'location_result': location_result
                    }
                    save_config(st.session_state.saved_api_key, st.session_state.favorites, st.session_state.save_api_key)
                    st.success("Saved!")
            with refresh_col:
                if st.button("Refresh"):
                    st.session_state.bluebikes_service.fetch_station_data()
                    st.success("✅ Updated bike/dock availability!")
                    st.rerun()
            
            weather = st.session_state.weather_service.get_current_weather(location_result['lat'], location_result['lon'])
            
            if weather is not None:
                w_col1, w_col2, w_col3, w_col4 = st.columns(4)
                with w_col1:
                    st.metric("Temperature", f"{weather['temperature']:.0f}°F")
                with w_col2:
                    st.metric("Humidity", f"{weather['humidity']:.0f}%")
                with w_col3:
                    st.metric("Wind", f"{weather['wind_speed']:.0f} mph")
                with w_col4:
                    temp = weather['temperature']
                    wind = weather['wind_speed']
                    if 65 <= temp <= 80 and wind < 15:
                        st.metric("Conditions", "Perfect")
                    elif 50 <= temp <= 85 and wind < 20:
                        st.metric("Conditions", "Good")
                    else:
                        st.metric("Conditions", "OK")
            
        else:
            st.error(f"Error: {location_result['error']}")
            return
    elif address:
        return
    
    if not location_result or not location_result['success']:
        st.info("Enter an address to find BlueBikes stations")
        return
    
    if st.session_state.bluebikes_service.stations_df is None:
        with st.spinner("Loading BlueBikes data..."):
            st.session_state.bluebikes_service.fetch_station_data()
    
    bluebikes = st.session_state.bluebikes_service
    
    if bluebikes.stations_df is not None and not bluebikes.stations_df.is_empty():
        nearby_stations = bluebikes.get_stations_near_location(
            "Search Location",
            location_result['lat'],
            location_result['lon'],
            radius,
            direction if direction != 'all' else None,
            force_refresh=False
        )
        
        if not nearby_stations.is_empty():
            total_stations = len(nearby_stations)
            
            if search_type == 'pickup':
                total_bikes = sum(s.get('num_bikes_available', 0) for s in nearby_stations.iter_rows(named=True))
                total_ebikes = sum(s.get('num_ebikes_available', 0) for s in nearby_stations.iter_rows(named=True))
                total_regular = total_bikes - total_ebikes
                stations_with_bikes = sum(1 for s in nearby_stations.iter_rows(named=True) if s.get('num_bikes_available', 0) > 0)
                
                metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
                with metric_col1:
                    st.metric("Stations", total_stations)
                with metric_col2:
                    st.metric("With Bikes", stations_with_bikes)
                with metric_col3:
                    st.metric("Regular", total_regular)
                with metric_col4:
                    st.metric("E-bikes", total_ebikes)
                
            else:
                total_docks = sum(s.get('num_docks_available', 0) for s in nearby_stations.iter_rows(named=True))
                stations_with_docks = sum(1 for s in nearby_stations.iter_rows(named=True) if s.get('num_docks_available', 0) > 0)
                stations_full = total_stations - stations_with_docks
                
                metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
                with metric_col1:
                    st.metric("Stations", total_stations)
                with metric_col2:
                    st.metric("With Docks", stations_with_docks)
                with metric_col3:
                    st.metric("Full", stations_full)
                with metric_col4:
                    st.metric("Free Docks", total_docks)
            
            zoom_levels = {0.1: 17, 0.25: 16, 0.5: 15, 0.75: 14, 1.0: 14, 1.5: 13, 2.0: 13}
            zoom_level = zoom_levels.get(radius, 14)
            
            m = folium.Map(
                location=[location_result['lat'], location_result['lon']],
                zoom_start=zoom_level,
                tiles='OpenStreetMap'
            )
            
            search_icon = 'home' if search_type == 'pickup' else 'flag'
            search_color = 'red' if search_type == 'pickup' else 'blue'
            
            folium.Marker(
                location=[location_result['lat'], location_result['lon']],
                popup=f"Your Location: {address}",
                icon=folium.Icon(color=search_color, icon=search_icon, prefix='fa'),
                tooltip="Your Location"
            ).add_to(m)
            
            folium.Circle(
                location=[location_result['lat'], location_result['lon']],
                radius=radius * 1609.34,
                popup=f"{radius} mile radius",
                color=search_color,
                fill=True,
                fillColor=search_color,
                fillOpacity=0.1,
                opacity=0.5
            ).add_to(m)
            
            for station in nearby_stations.iter_rows(named=True):
                try:
                    lat = float(station.get('lat', 0))
                    lon = float(station.get('lon', 0))
                    name = station.get('name', 'Unknown')
                    distance = station.get('distance_miles', 0)
                    
                    if search_type == 'pickup':
                        bikes = station.get('num_bikes_available', 0)
                        ebikes = station.get('num_ebikes_available', 0)
                        regular = bikes - ebikes if bikes >= ebikes else 0
                        
                        if bikes == 0:
                            color = 'red'
                            icon = 'ban'
                        elif ebikes > 0:
                            color = 'green'
                            icon = 'bolt'
                        elif bikes >= 5:
                            color = 'blue'
                            icon = 'bicycle'
                        else:
                            color = 'orange'
                            icon = 'bicycle'
                        
                        popup_html = f"""
                        <div style="width: 180px;">
                            <b>{name}</b><br>
                            Walk: {distance:.1f} mi<br>
                            E-bikes: {ebikes}<br>
                            Regular: {regular}
                        </div>
                        """
                        
                        tooltip_text = f"{name} | {bikes} bikes"
                    
                    else:
                        docks = station.get('num_docks_available', 0)
                        
                        if docks == 0:
                            color = 'red'
                            icon = 'ban'
                        elif docks >= 5:
                            color = 'green'
                            icon = 'home'
                        else:
                            color = 'orange'
                            icon = 'home'
                        
                        popup_html = f"""
                        <div style="width: 180px;">
                            <b>{name}</b><br>
                            Walk: {distance:.1f} mi<br>
                            Free docks: {docks}
                        </div>
                        """
                        
                        tooltip_text = f"{name} | {docks} docks"
                    
                    folium.Marker(
                        location=[lat, lon],
                        popup=folium.Popup(popup_html, max_width=200),
                        icon=folium.Icon(color=color, icon=icon, prefix='fa'),
                        tooltip=tooltip_text
                    ).add_to(m)
                    
                except (ValueError, TypeError):
                    continue
            
            map_data = st_folium(m, width=1000, height=500, key="stations_map")
            
            if map_data['last_clicked'] is not None:
                clicked_lat = map_data['last_clicked']['lat']
                clicked_lng = map_data['last_clicked']['lng']
                clicked_distance = st.session_state.bluebikes_service.haversine_distance(
                    location_result['lat'], location_result['lon'], clicked_lat, clicked_lng
                )
                
                if clicked_distance > 0.05:
                    if st.button(f"Search here ({clicked_distance:.1f}mi away)"):
                        new_address = f"Map Location {clicked_lat:.4f}, {clicked_lng:.4f}"
                        location_key = f"{new_address}_{search_type}"
                        st.session_state.locations[location_key] = {
                            'lat': clicked_lat, 'lon': clicked_lng,
                            'formatted_address': f"Map Location ({clicked_lat:.4f}, {clicked_lng:.4f})",
                            'success': True, 'error': None
                        }
                        if search_type == 'pickup':
                            st.session_state.pickup_address = new_address
                        else:
                            st.session_state.dropoff_address = new_address
                        st.rerun()
        
        else:
            direction_text = "all directions" if direction == 'all' else f"the {direction} direction"
            st.warning(f"No stations found within {radius} mi walking distance in {direction_text}")
    
    else:
        st.error("Could not load BlueBikes data. Please try refreshing.")

def main():
    create_streamlit_app()

if __name__ == "__main__":
    main()