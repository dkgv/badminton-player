from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Thread
from typing import Dict, List, Optional

from pyjarowinkler import distance

from app.badminton_player.models import (
    Game,
    Player,
    PlayerPerformance,
    Standing,
    TeamMatch,
    Tournament,
)
from app.services import badminton_player_client, supabase_client
from app.utils import supabase_utils


@dataclass
class AggregatePlayerProfile:
    metadata: PlayerPerformance
    player: Player
    games: List[Game]
    matches: List[TeamMatch]
    standings: List[Standing]
    tournaments: List[Tournament]


def get_players_for_club(club_id: int) -> List[Player]:
    players = supabase_utils.from_resp(
        supabase_client.from_("players")
        .select("*")
        .eq("bp_club_id", club_id)
        .order("bp_name")
        .execute(),
        Player,
    )
    return players


def get_player_id(name: str, club_name: str) -> Optional[int]:
    players = search_player(name, club_name)
    if not players:
        return None

    return players[0].id


def search_player(name: str, club: str = None) -> List[Player]:
    parts = name.split(" ")
    query = " | ".join([p for p in parts if p])

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
        if f.id not in visited:
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


def build_player_profile(player_id: int) -> Optional[AggregatePlayerProfile]:
    player_id = int(player_id)

    player = _try_find_player(player_id)
    if not player:
        print(f"Could not find player with id {player_id}")
        return None

    standings = _try_find_standings(player_id)
    if not standings:
        print(f"Could not find standing for player with id {player_id}")

    matches = _try_find_team_matches(player_id)
    if not matches:
        print(f"Could not find matches for player with id {player_id}")

    games = _try_find_games(player.name, matches)
    if not games:
        print(f"Could not find games for player with id {player_id}")

    performance = badminton_player_client.get_performance_cached_1h(player_id)
    if not performance:
        print(f"Could not find meta for player with id {player_id}")
        return None

    tournaments = _try_find_tournaments(player_id)
    if not tournaments:
        print(f"Could not find tournaments for player with id {player_id}")

    return AggregatePlayerProfile(
        player=player,
        metadata=performance,
        games=games,
        matches=matches,
        standings=standings,
        tournaments=tournaments,
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


def group_matches_by_division(matches: List[TeamMatch]) -> List[List[TeamMatch]]:
    grouped_matches = []
    curr_group = []
    prev_division = None
    for m in matches:
        if m.division == prev_division:
            m.division = None
            curr_group.append(m)
        else:
            if curr_group:
                grouped_matches.append(curr_group)
            curr_group = [m]
            prev_division = m.division

    if curr_group:
        grouped_matches.append(curr_group)

    return grouped_matches


def _try_find_standings(player_id: int) -> Optional[List[Standing]]:
    def sort_standings(standings: List[Standing]) -> List[Standing]:
        return sorted(
            standings,
            key=lambda s: s.category,
            reverse=True,
        )

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
        print(f"Found existing standings for player with id {player_id}")
        return sort_standings(standings)

    print(f"Retrieving standings for player with id {player_id}")
    profile = badminton_player_client.get_performance_cached_1h(player_id)
    if not profile or len(profile.standings) == 0:
        return None

    standings_data = [s.to_dict(player_id) for s in profile.standings]
    for standing in standings_data:
        standing["updated_at"] = "now()"

    supabase_client.from_("standings").upsert(
        standings_data,
        on_conflict="bp_player_id,category",
    ).execute()

    standings = list(profile.standings)
    return sort_standings(standings)


def _try_find_player(player_id: int) -> Optional[Player]:
    def _getter() -> Optional[Player]:
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

    player = _getter()
    if not player:
        return None

    player.name = player.name.strip()

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


def _try_find_team_matches(player_id: int) -> Optional[List[TeamMatch]]:
    profile = badminton_player_client.get_performance_cached_1h(player_id)
    if not profile:
        return []

    player = _try_find_player(player_id)
    if not player:
        return []

    matches = []
    sort_for_match = {}
    for i, meta in enumerate(profile.match_metadata):
        if not meta:
            continue

        games: List[Game] = supabase_utils.from_resp(
            supabase_client.from_("games")
            .select("*")
            .eq("bp_match_id", meta.id)
            .execute(),
            Game,
        )
        if games:
            # Order: 1. MD, 2. MD, 1. DS, 2. DS, 1. HS, 2. HS, 3. HS, 4. HS, 1. DD, 2. DD
            # Sort by type (last two chars): MD, DS, HS, DD
            # Sort by number (first char): 1, 2, 3, 4
            order = {
                "MD": 0,
                "DS": 1,
                "HS": 2,
                "DD": 3,
                "HD": 4,
                "S": 5,
                "D": 6,
            }
            games.sort(
                key=lambda g: (
                    (
                        order[g.category[3:]]
                        if g.category[0].isdigit()
                        else order[g.category]
                    ),
                    int(g.category.strip()[0]) if g.category[0].isdigit() else 0,
                )
            )

            for g in games:
                g.date = g.date.replace(tzinfo=None)

            print(f"Found games for match id={meta.id}")

            match = TeamMatch(
                id=meta.id,
                date=meta.date,
                division=meta.division.strip(),
                games=games,
            )

            sort_for_match[match.id] = i
        else:
            print("Retrieving games for match with id", meta.id)
            match = badminton_player_client.get_match(meta.id)
            if not match:
                continue

            for game in match.games:
                # TODO: are we persisting games correctly?
                _upsert_game_async(meta.id, game)

            sort_for_match[match.id] = meta.sort

        home_players, away_players = [], []
        for g in match.games:
            home_players.append(g.home_player1)
            away_players.append(g.away_player1)

            if g.home_player2:
                home_players.append(g.home_player2)
            if g.away_player2:
                away_players.append(g.away_player2)

        home_team, away_team = meta.team1, meta.team2
        home_club, away_club = "", ""

        if player.name not in home_players:
            home_team, away_team = away_team, home_team
            home_club = _identify_club_name(home_players)
            away_club = player.club_name
        else:
            home_club = player.club_name
            away_club = _identify_club_name(away_players)

        match.home_team = home_team
        match.away_team = away_team
        match.home_club = home_club
        match.away_club = away_club

        matches.append(match)

    matches.sort(key=lambda m: sort_for_match[m.id], reverse=True)
    
    return matches


def _identify_club_name(player_names: List[str]) -> str:
    players = supabase_utils.from_resp(
        supabase_client.from_("players")
        .select("*, clubs (name)")
        .in_("bp_name", player_names)
        .execute(),
        Player,
    )
    if not players:
        return "unknown"

    print("Found players:", players, "for names:", player_names)
    club_buckets = defaultdict(int)
    for player in players:
        club_buckets[player.club_name] += 1

    print(club_buckets)

    club_name = max(club_buckets, key=club_buckets.get)
    return club_name


def _upsert_game_async(match_id: str, game: Game) -> None:
    if not game.category:
        return

    def upsert_game():
        row = game.to_dict()
        row["bp_match_id"] = match_id
        supabase_client.from_("games").upsert(row).execute()

    t = Thread(target=upsert_game)
    t.start()


def _try_find_games(player_name: str, matches: List[TeamMatch]) -> List[Game]:
    if not matches:
        return []

    games = []
    for match in matches:
        for game in match.games:
            if game and game.date and game.contains(player_name):
                games.append(game)

    games.sort(
        key=lambda g: g.date.timestamp() if g.date is not None else 0, reverse=True
    )

    return games


def _upsert_tournaments_async(player_id: int, tournaments: List[Tournament]) -> None:
    if not tournaments:
        return

    def upsert_tournaments():
        for tournament in tournaments:
            row = tournament.to_dict()
            row["bp_player_id"] = player_id
            supabase_client.from_("tournaments").upsert(row).execute()

    t = Thread(target=upsert_tournaments)
    t.start()


def _try_find_tournaments(player_id: int) -> List[Tournament]:
    profile = badminton_player_client.get_performance_cached_1h(player_id)
    if not profile:
        return []

    if not profile.tournaments:
        return []

    _upsert_tournaments_async(player_id, profile.tournaments)

    profile.tournaments.sort(key=lambda t: t.date, reverse=True)

    return profile.tournaments
