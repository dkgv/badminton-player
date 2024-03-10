from flask import current_app as app
from flask import render_template, request

from app.services import club_service, player_service


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/player/<player_id>", methods=["GET"])
def player(player_id: int):
    profile = player_service.get_player_profile(player_id)
    if not profile:
        return "Not found", 404

    name_to_ids = player_service.get_player_ids(profile.matches)
    streak = player_service.group_games_by_category(profile.games)

    return render_template(
        "player.html",
        profile=profile.metadata,
        games=profile.games,
        streak=streak,
        player=profile.player,
        matches=profile.matches,
        standings=profile.standings,
        name_to_ids=name_to_ids,
    )


@app.route("/club/<club_id>", methods=["GET"])
def club(club_id: int):
    club = club_service.get_club(club_id)
    if not club:
        return "Not found", 404

    players = player_service.get_players_for_club(club_id)

    print(club)
    return render_template("club.html", club=club, players=players)


@app.route("/search", methods=["GET"])
def search():
    query = request.args.get("q")
    if not query:
        return render_template("search.html", players=[])

    players = player_service.search_player(query)
    clubs = club_service.search_club(query)

    print(players, clubs)

    return render_template("search.html", players=players, clubs=clubs, query=query)
