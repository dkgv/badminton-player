import os
from collections import defaultdict
from datetime import datetime, timedelta
from threading import Thread
from typing import Dict, List, Optional

import supabase
from postgrest.exceptions import APIError
from pyjarowinkler import distance

from app.badminton_player import api
from app.badminton_player.models import Game, Match, Player, PlayerMeta, Standing
from app.services.models import PlayerProfile
from app.utils import supabase_utils

badminton_player_client = api.Client()
supabase_client = supabase.create_client(
    supabase_url=os.getenv("SUPABASE_URL"),
    supabase_key=os.getenv("SUPABASE_KEY"),
)


def search_player(name: str, club: str = None) -> List[Player]:
    query = " | ".join(name.split(" "))
    fuzzy_players = supabase_utils.from_resp(
        supabase_client.from_("players")
        .select("*, clubs (name)")
        .text_search("bp_name", query)
        .execute(),
        Player,
    )

    visited = set()
    players = []
    for f in fuzzy_players:
        if f.id in visited:
            continue
        visited.add(f.id)
        players.append(f)

    bp_players = badminton_player_client.search_player(name, club)
    for p in bp_players:
        if p.id in visited:
            continue
        visited.add(p.id)
        players.append(p)

        _upsert_player_async(p)

    query = name.lower().replace(" ", "")

    players.sort(
        key=lambda p: distance.get_jaro_distance(
            p.name.lower().replace(" ", ""),
            query,
            winkler=True,
            scaling=0.2,
        ),
        reverse=True,
    )

    return players


def get_player_profile(player_id: int) -> Optional[PlayerProfile]:
    player_id = int(player_id)

    player = _try_find_player(player_id)
    if not player:
        print(f"Could not find player with id {player_id}")
        return None

    standings = _try_find_standings(player_id)
    if not standings:
        print(f"Could not find standing for player with id {player_id}")

    matches = _try_find_matches(player_id)
    if not matches:
        print(f"Could not find matches for player with id {player_id}")

    games = _try_find_games(player.name, matches)
    if not games:
        print(f"Could not find games for player with id {player_id}")

    meta = badminton_player_client.get_profile(player_id)
    if not meta:
        print(f"Could not find meta for player with id {player_id}")
        return None

    return PlayerProfile(
        player=player,
        metadata=PlayerMeta(
            standings=standings,
            season_start_points=meta.season_start_points,
            match_metadata=[],
        ),
        games=games,
        matches=matches,
        standings=standings,
    )


def group_games_by_category(games: List[Game]) -> Dict[str, List[Game]]:
    streak = defaultdict(list)
    for game in games:
        category = game.category
        if category != "MD":
            category = category[2:].strip()
        streak[category].append(game)

    if "D" in streak:
        if "HD" in streak:
            streak["HD"].extend(streak["D"])
        else:
            streak["DD"].extend(streak["D"])

        del streak["D"]

    mapping = {
        "HS": "Rangliste Single",
        "DS": "Rangliste Single",
        "MD": "Rangliste Mix",
        "HD": "Rangliste Double",
        "DD": "Rangliste Double",
    }

    return {mapping[k]: v for k, v in streak.items() if k in mapping}


def _try_find_standings(player_id: int) -> Optional[List[Standing]]:
    one_day_ago = datetime.now() - timedelta(days=1)
    standings = supabase_utils.from_resp(
        supabase_client.from_("standings")
        .select("*")
        .eq("bp_player_id", player_id)
        .gte("updated_at", one_day_ago)
        .execute(),
        Standing,
    )
    if standings:
        return standings

    profile = badminton_player_client.get_profile(player_id)
    if not profile or not profile.standings.any():
        return None

    supabase_client.from_("standings").insert(
        [s.to_dict(player_id) for s in profile.standings]
    ).execute()

    return list(profile.standings)


def _try_find_player(player_id: int) -> Optional[Player]:
    player = supabase_utils.from_resp(
        supabase_client.from_("players")
        .select("*, clubs (name)")
        .eq("bp_id", player_id)
        .execute(),
        Player,
    )
    if player:
        return player[0]

    player = badminton_player_client.get_player(player_id)
    if not player:
        return None

    _upsert_player_async(player)

    return player


def _upsert_player_async(player: Player) -> None:
    def _upsert_player_job():
        if not player.club_id:
            return

        supabase_client.from_("clubs").upsert(
            {
                "bp_id": player.club_id,
                "name": player.club_name,
            },
            on_conflict="bp_id",
        ).execute()

        supabase_client.from_("players").upsert(
            player.to_dict(), on_conflict="bp_id"
        ).execute()

    t = Thread(target=_upsert_player_job)
    t.start()


def _try_find_matches(player_id: int) -> Optional[List[Match]]:
    profile = badminton_player_client.get_profile(player_id)
    if not profile:
        return []

    matches = []
    sort_for_match = {}
    for meta in profile.match_metadata:
        if not meta:
            continue

        match = badminton_player_client.get_match(meta.id)
        if not match:
            continue

        sort_for_match[match.id] = meta.sort
        matches.append(match)

    matches.sort(key=lambda m: sort_for_match[m.id], reverse=True)

    return matches


def _try_find_games(player_name: str, matches: List[Match]):
    if not matches:
        return []

    games = []
    for match in matches:
        for game in match.games:
            if game and game.date and game.contains(player_name):
                games.append(game)

    games.sort(key=lambda g: g.date if g.date is not None else 0, reverse=True)

    return games
