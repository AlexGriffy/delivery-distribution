"""U.S. cities offered in the "add from city list" picker and used to name map clicks."""

import math

CITIES = {
    "Albert Lea, MN": (43.6480, -93.3683),
    "Albuquerque, NM": (35.0844, -106.6504),
    "Atlanta, GA": (33.7490, -84.3880),
    "Austin, TX": (30.2672, -97.7431),
    "Baltimore, MD": (39.2904, -76.6122),
    "Bellingham, WA": (48.7519, -122.4787),
    "Billings, MT": (45.7833, -108.5007),
    "Birmingham, AL": (33.5186, -86.8104),
    "Boise, ID": (43.6150, -116.2023),
    "Boston, MA": (42.3601, -71.0589),
    "Buffalo, NY": (42.8864, -78.8784),
    "Charlotte, NC": (35.2271, -80.8431),
    "Chicago, IL": (41.8781, -87.6298),
    "Cincinnati, OH": (39.1031, -84.5120),
    "Cleveland, OH": (41.4993, -81.6944),
    "Columbus, OH": (39.9612, -82.9988),
    "Dallas, TX": (32.7767, -96.7970),
    "Denver, CO": (39.7392, -104.9903),
    "Des Moines, IA": (41.5868, -93.6250),
    "Detroit, MI": (42.3314, -83.0458),
    "El Paso, TX": (31.7619, -106.4850),
    "Eugene, OR": (44.0521, -123.0868),
    "Fargo, ND": (46.8772, -96.7898),
    "Fresno, CA": (36.7378, -119.7871),
    "Houston, TX": (29.7604, -95.3698),
    "Indianapolis, IN": (39.7684, -86.1581),
    "Jacksonville, FL": (30.3322, -81.6557),
    "Kansas City, MO": (39.0997, -94.5786),
    "Las Vegas, NV": (36.1699, -115.1398),
    "Little Rock, AR": (34.7465, -92.2896),
    "Los Angeles, CA": (34.0522, -118.2437),
    "Louisville, KY": (38.2527, -85.7585),
    "Memphis, TN": (35.1495, -90.0490),
    "Miami, FL": (25.7617, -80.1918),
    "Milwaukee, WI": (43.0389, -87.9065),
    "Minneapolis, MN": (44.9778, -93.2650),
    "Nashville, TN": (36.1627, -86.7816),
    "New Orleans, LA": (29.9511, -90.0715),
    "New York, NY": (40.7128, -74.0060),
    "Oklahoma City, OK": (35.4676, -97.5164),
    "Omaha, NE": (41.2565, -95.9345),
    "Philadelphia, PA": (39.9526, -75.1652),
    "Phoenix, AZ": (33.4484, -112.0740),
    "Pittsburgh, PA": (40.4406, -79.9959),
    "Portland, OR": (45.5152, -122.6784),
    "Raleigh, NC": (35.7796, -78.6382),
    "Rapid City, SD": (44.0805, -103.2310),
    "Reno, NV": (39.5296, -119.8138),
    "Richmond, VA": (37.5407, -77.4360),
    "Sacramento, CA": (38.5816, -121.4944),
    "St. Louis, MO": (38.6270, -90.1994),
    "Salt Lake City, UT": (40.7608, -111.8910),
    "San Antonio, TX": (29.4241, -98.4936),
    "San Diego, CA": (32.7157, -117.1611),
    "San Francisco, CA": (37.7749, -122.4194),
    "Seattle, WA": (47.6062, -122.3321),
    "Spokane, WA": (47.6588, -117.4260),
    "Tampa, FL": (27.9506, -82.4572),
    "Tucson, AZ": (32.2226, -110.9747),
    "Washington, DC": (38.9072, -77.0369),
}


def haversine_miles(lat1, lon1, lat2, lon2):
    """Great-circle ("as the crow flies") distance in miles."""
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_city(lat, lon, max_miles=60):
    """Name of the closest listed city within max_miles, or None."""
    name, dist = min(
        ((n, haversine_miles(lat, lon, *ll)) for n, ll in CITIES.items()),
        key=lambda t: t[1],
    )
    return name.split(",")[0] if dist <= max_miles else None
