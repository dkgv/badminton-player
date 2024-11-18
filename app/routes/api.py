from flask import current_app as app
from flask import jsonify, request

from app.services import player_service


@app.route("/api/player/discover", methods=["GET"])
def discover_player():
    name = request.args.get("name")
    if not name:
        return jsonify({"error": "name is required"}), 400

    club = request.args.get("club")
    if not club:
        return jsonify({"error": "club is required"}), 400

    id = player_service.get_player_id(name, club)
    if not id:
        return jsonify({"error": "player not found"}), 404

    return jsonify({"id": id})
