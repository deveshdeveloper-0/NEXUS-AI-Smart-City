from datetime import datetime, timezone

# Clearly labelled demonstration data. Replace with verified city/IoT data
# when a real data source is available.
DEMO_CITY = {
    "city": "NEXUS Demo City",
    "data_mode": "synthetic_demo",
    "traffic_index": 78,
    "air_quality_index": 142,
    "energy_load_percent": 71,
    "water_level_percent": 64,
    "traffic_history": [42, 48, 53, 61, 67, 72, 78],
    "aqi_history": [91, 98, 105, 112, 121, 135, 142],
}

def get_dashboard():
    return {
        **DEMO_CITY,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "indicators": [
            {"name": "Traffic", "value": DEMO_CITY["traffic_index"], "unit": "/100"},
            {"name": "Air Quality Index", "value": DEMO_CITY["air_quality_index"], "unit": "AQI"},
            {"name": "Energy Load", "value": DEMO_CITY["energy_load_percent"], "unit": "%"},
            {"name": "Water Level", "value": DEMO_CITY["water_level_percent"], "unit": "%"},
        ],
    }

def analyze_city():
    traffic = DEMO_CITY["traffic_index"]
    aqi = DEMO_CITY["air_quality_index"]
    energy = DEMO_CITY["energy_load_percent"]
    agents = []

    # Transparent rule-based agents for the first prototype.
    if traffic >= 70:
        agents.append({
            "agent": "Traffic Intelligence Agent",
            "status": "alert",
            "finding": f"Traffic index is {traffic}/100 (high in this demo scenario).",
            "recommendation": "Review congestion hotspots and consider signal-timing optimization."
        })
    else:
        agents.append({
            "agent": "Traffic Intelligence Agent",
            "status": "normal",
            "finding": f"Traffic index is {traffic}/100.",
            "recommendation": "Continue monitoring traffic conditions."
        })

    if aqi >= 100:
        agents.append({
            "agent": "Air Quality Agent",
            "status": "alert",
            "finding": f"AQI is {aqi} in the synthetic demo dataset.",
            "recommendation": "Investigate likely emission sources and consult local air-quality advisories."
        })
    else:
        agents.append({
            "agent": "Air Quality Agent",
            "status": "normal",
            "finding": f"AQI is {aqi}.",
            "recommendation": "Continue air-quality monitoring."
        })

    agents.append({
        "agent": "Energy Intelligence Agent",
        "status": "watch" if energy >= 70 else "normal",
        "finding": f"Energy load is {energy}%.",
        "recommendation": "Review peak-load periods and assess demand-management options."
    })

    alerts = sum(1 for item in agents if item["status"] == "alert")
    return {
        "data_mode": "synthetic_demo",
        "method": "transparent rule-based analysis (not a trained predictive model)",
        "summary": f"{alerts} high-priority alert(s) identified from the demo indicators.",
        "agents": agents,
        "limitations": [
            "Values are synthetic demonstration data, not live city telemetry.",
            "Recommendations are rule-based and require human review.",
            "This prototype does not control real-world infrastructure."
        ]
    }
