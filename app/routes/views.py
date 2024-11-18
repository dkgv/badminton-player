from flask import abort
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
        return abort(404)

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
        return abort(404)

    players = player_service.get_players_for_club(club_id)

    return render_template("club.html", club=club, players=players)


@app.route("/search", methods=["GET"])
def search():
    query = request.args.get("q")
    if not query:
        return render_template("search.html", players=[])

    query = query.strip()
    players = player_service.search_player(query)
    clubs = club_service.search_club(query)

    print(f"Searched for {query}, found {len(players)} players and {len(clubs)} clubs")

    return render_template("search.html", players=players, clubs=clubs, query=query)


@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404
