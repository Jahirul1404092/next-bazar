"""
Next Bazar — Lightweight Flask server
Serves the dashboard and (later) prediction API endpoints.

Run locally:
    pip install flask
    python server.py

Then open http://localhost:5000 in your browser.

For production deployment, use gunicorn:
    pip install gunicorn
    gunicorn server:app -b 0.0.0.0:5000 --workers 2
"""

import os
import json
from flask import Flask, send_file, jsonify

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, static_folder=BASE_DIR, static_url_path="")


@app.route("/")
def index():
    """Serve the main dashboard."""
    return send_file(os.path.join(BASE_DIR, "dashboard.html"))


@app.route("/dashboard_data.js")
def dashboard_data():
    """Serve the dashboard data JS file."""
    return send_file(
        os.path.join(BASE_DIR, "dashboard_data.js"),
        mimetype="application/javascript",
    )


@app.route("/api/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "service": "Next Bazar"})


@app.route("/api/predictions/<commodity>")
def get_predictions(commodity):
    """
    Placeholder: return predictions for a commodity.
    Later, load from model output files in data/ or models/ folder.
    """
    pred_file = os.path.join(BASE_DIR, "outputs", f"{commodity}_predictions.json")
    if os.path.exists(pred_file):
        with open(pred_file) as f:
            return jsonify(json.load(f))
    return jsonify({"error": "No predictions available yet", "commodity": commodity}), 404


@app.route("/api/commodities")
def list_commodities():
    """List available commodities from the clean data."""
    csv_path = os.path.join(BASE_DIR, "data", "all_prices_clean.csv")
    if os.path.exists(csv_path):
        import pandas as pd
        df = pd.read_csv(csv_path)
        commodities = sorted(df["name_en"].dropna().unique().tolist()) if "name_en" in df.columns else []
        return jsonify({"commodities": commodities, "count": len(commodities)})
    return jsonify({"commodities": [], "count": 0})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  Next Bazar Dashboard")
    print(f"  Open: http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=True)
