# 🚴‍♀️ Boston BlueBikes Live Dashboard

A real-time BlueBikes station finder with walking distance calculations and directional search capabilities.

## 🚀 Try the App
[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://boston-bluebikes-walker.streamlit.app/?embed_options=dark_theme)


## ✨ Features

### **Location Search**
- **Address input**: Enter any Boston area address
- **Intersection search**: Find stations near intersections (e.g., "Mass Ave and Newbury St")
- **Separate pickup/dropoff**: Independent addresses for finding bikes vs docks
- **8-direction search**: Filter by compass direction (N, NE, E, SE, S, SW, W, NW)

### 🚶‍♀️ **Real Walking Distance**
- **Actual route calculation**: Uses OpenStreetMap routing to find real walking paths
- **Barrier filtering**: Excludes stations across rivers, highways, or other obstacles
- **Configurable radius**: 0.1 to 2.0 mile search radius
- **Smart caching**: Fast refreshes for same location (updates bike counts only)

### **Interactive Map**
- **Live station data**: Real-time bike and dock availability
- **Color-coded stations**: Green (plenty), Orange (few), Red (empty), Blue (moderate)
- **Click to search**: Click anywhere on map to search from that location
- **Station details**: Hover/click for walking distance and availability

### **Persistent Settings**
- **Favorite searches**: Save common locations with all parameters
- **Local storage**: Settings saved to `~/.bluebikes_config.json`
- **Separate tabs**: Pickup and dropoff remember different addresses
- **Weather API**: Optional OpenWeatherMap integration with saved API key

### **Smart Refresh**
- **Fast updates**: Cached stations update in 1-2 seconds
- **Full recalculation**: Only when location/parameters change
- **Auto-refresh**: Optional periodic updates (30s to 5min intervals)
- **Manual refresh**: Update bike/dock availability on demand

## Installation

### Prerequisites
```bash
pip install polars requests streamlit folium plotly streamlit-folium geopy
```

### Run the App
```bash
streamlit run bluebike.py
```

The app will open in your browser at `http://localhost:8501`

## Usage

### Basic Search
1. Choose **"Find bikes"** or **"Find docks"**
2. Enter an address (e.g., "123 Main St" or "Harvard Sq")
3. Set search radius (0.1 - 2.0 miles)
4. Choose direction (All or specific compass direction)
5. View results on interactive map

### Extra Notes
- **Intersection search**: "Mass Ave and Boylston St"
- **Save favorites**: Click "Save as Favorite" for common searches
- **Load favorites**: Select from dropdown in sidebar
- **Weather data**: Add OpenWeatherMap API key in sidebar settings
- **Map interaction**: Click empty areas to search from new location

### Separate Pickup/Dropoff
- **Find bikes tab**: Enter your starting location
- **Find docks tab**: Enter your destination
- **Independent memory**: Each tab remembers its own address and settings
- **No interference**: Settings don't affect each other

## ⚙️ Configuration

### Weather API (Optional)
1. Get free API key from [OpenWeatherMap](https://openweathermap.org/api)
2. Enter in sidebar settings
3. Check "Remember API key" to save locally
4. View temperature, humidity, wind, and biking conditions

### Local Storage
Settings are automatically saved to:
- **macOS/Linux**: `~/.bluebikes_config.json`
- **Windows**: `C:\Users\{username}\.bluebikes_config.json`

Contains:
- Weather API key (if saved)
- Favorite searches
- User preferences

## 🏗️ Technical Details

### Data Sources
- **BlueBikes**: Live GBFS feed (no API key required)
- **Routing**: OpenStreetMap Routing Machine (OSRM)
- **Geocoding**: Nominatim (OpenStreetMap)
- **Weather**: OpenWeatherMap (optional)

### Smart Caching
- **Route caching**: Expensive walking calculations cached by location/radius/direction
- **Fast refreshes**: Same location updates bike counts in 1-2 seconds
- **Cache invalidation**: New searches when parameters change
- **Memory efficient**: Caches only essential station data

### Walking Distance Algorithm
1. **Straight-line filter**: Pre-filter stations within radius
2. **Route calculation**: Get actual walking path from OSRM
3. **Barrier detection**: Reject routes >3x straight-line distance
4. **Direction filtering**: Apply compass direction constraints
5. **Results caching**: Store for fast future updates

## 🎨 Map Legend

### Your Location
- 🏠 **Red home icon**: Pickup location (finding bikes)
- 🏁 **Blue flag icon**: Dropoff location (finding docks)

### Station Colors
- 🟢 **Green**: Plenty available (5+ bikes/docks)
- 🔵 **Blue**: Moderate availability
- 🟠 **Orange**: Few available (1-4 bikes/docks)
- 🔴 **Red**: None available (empty/full)

### Station Icons
- ⚡ **Lightning**: E-bikes available
- 🚲 **Bicycle**: Regular bikes only
- 🏠 **Home**: Docks available
- 🚫 **Ban**: Empty/full station

## 🔧 Troubleshooting

### Common Issues
- **"No stations found"**: Try increasing radius or changing direction
- **Slow initial search**: Walking route calculation takes 30-60 seconds first time
- **Weather not showing**: Add OpenWeatherMap API key in sidebar
- **Favorites not saving**: Check file permissions for home directory

### Performance Tips
- **Use cached results**: Same location refreshes are much faster
- **Smaller radius**: Reduces calculation time
- **Specific directions**: Fewer stations to process

## 📝 License

MIT License - Feel free to use and modify for personal or commercial projects.

## 🤝 Contributing

Contributions welcome! Areas for improvement:
- Additional transit integration
- Mobile app version
- Route planning between stations
- Historical availability data
- Bike lane routing preferences

## Support

For issues or questions, please open a GitHub issue with:
- Error messages (if any)
- Steps to reproduce
- Your operating system
- Python/Streamlit versions