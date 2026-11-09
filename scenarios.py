"""Built-in scenarios and scenario (de)serialization."""

import copy
import json

from cities import CITIES


def _node(prefix, k, city, qty_field, qty, name=None):
    lat, lon = CITIES[city]
    return {"id": f"{prefix}{k}", "name": name or city.split(",")[0], "lat": lat, "lon": lon, qty_field: qty}


def _scenario(warehouses, stores, rate, overrides=None, note=""):
    return {
        "cost_per_mile": rate,
        "warehouses": [_node("W", k + 1, c, "supply", q) for k, (c, q) in enumerate(warehouses)],
        "stores": [_node("S", k + 1, c, "demand", q) for k, (c, q) in enumerate(stores)],
        "cost_overrides": overrides or {},
        "note": note,
    }


def _pt_company():
    # Hillier & Lieberman, "Introduction to Operations Research": P&T Company.
    # Canneries ship truckloads of peas to warehouses; cost is $ per truckload.
    costs = [
        [464, 513, 654, 867],
        [352, 416, 690, 791],
        [995, 682, 388, 685],
    ]
    overrides = {f"W{i + 1}|S{j + 1}": float(c) for i, row in enumerate(costs) for j, c in enumerate(row)}
    return _scenario(
        [("Bellingham, WA", 75), ("Eugene, OR", 125), ("Albert Lea, MN", 100)],
        [("Sacramento, CA", 80), ("Salt Lake City, UT", 65), ("Rapid City, SD", 70), ("Albuquerque, NM", 85)],
        rate=0.5,
        overrides=overrides,
        note="Textbook example (Hillier & Lieberman, P&T Company). Costs are the book's $/truckload "
             "values, entered as manual overrides. Known optimal cost: $152,535.",
    )


PRESETS = {
    "National retail network (4 warehouses, 8 stores)": lambda: _scenario(
        [("Los Angeles, CA", 900), ("Dallas, TX", 1100), ("Chicago, IL", 1200), ("Atlanta, GA", 1000)],
        [("Seattle, WA", 450), ("Denver, CO", 400), ("Phoenix, AZ", 380), ("Houston, TX", 520),
         ("Minneapolis, MN", 350), ("New York, NY", 700), ("Miami, FL", 480), ("Boston, MA", 400)],
        rate=0.10,
        note="Costs are distance-based estimates: $0.10 per unit per mile. Supply exceeds demand.",
    ),
    "Textbook check: P&T Company (3 × 4)": _pt_company,
    "Shortage: demand exceeds supply": lambda: _scenario(
        [("Denver, CO", 500), ("Kansas City, MO", 400)],
        [("Seattle, WA", 300), ("Phoenix, AZ", 250), ("Chicago, IL", 300), ("Dallas, TX", 250)],
        rate=0.10,
        note="Total demand (1,100) exceeds total supply (900), so the plain model is infeasible. "
             "Turn on 'Balance with a dummy node' in the sidebar to see the textbook fix.",
    ),
    "Blank (build your own on the map)": lambda: _scenario([], [], rate=0.10),
}


def load_preset(name):
    return PRESETS[name]()


def to_json(scn):
    return json.dumps(scn, indent=2)


def from_json(text):
    """Parse and sanity-check an uploaded scenario. Raises ValueError on bad input."""
    data = json.loads(text)
    scn = copy.deepcopy(PRESETS["Blank (build your own on the map)"]())
    scn["cost_per_mile"] = float(data.get("cost_per_mile", scn["cost_per_mile"]))
    scn["note"] = str(data.get("note", ""))
    for kind, prefix, qty in [("warehouses", "W", "supply"), ("stores", "S", "demand")]:
        for k, n in enumerate(data.get(kind, []), start=1):
            try:
                scn[kind].append({
                    "id": str(n.get("id") or f"{prefix}{k}"),
                    "name": str(n["name"]),
                    "lat": float(n["lat"]),
                    "lon": float(n["lon"]),
                    qty: max(0.0, float(n[qty])),
                })
            except (KeyError, TypeError, ValueError) as e:
                raise ValueError(f"Bad entry in '{kind}' #{k}: {e}") from e
    scn["cost_overrides"] = {str(k): float(v) for k, v in data.get("cost_overrides", {}).items()}
    return scn
