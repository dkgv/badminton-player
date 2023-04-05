from app.services import player_service
from flask import current_app as app
from flask import render_template, request


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/player/<player_id>", methods=["GET"])
def player(player_id: int):
    profile = player_service.get_player_profile(player_id)
    if not profile:
        return "Not found", 404

    return render_template(
        "player.html",
        profile=profile.metadata,
        games=profile.games,
        player=profile.player,
        matches=profile.matches,
        standings=profile.standings,
    )


@app.route("/search", methods=["GET"])
def search():
    query = request.args.get("q")
    if not query:
        return render_template("search.html", players=[])

    players = player_service.search_player(query)
    return render_template("search.html", players=players, query=query)
