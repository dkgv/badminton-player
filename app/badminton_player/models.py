from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from markupsafe import Markup


@dataclass
class Standing:
    # e.g. Rangliste, Rangliste Single
    category: str
    # e.g. U15 B
    tier: str
    num_points: int
    num_matches: int
    ranking: int

    def to_dict(self, player_id: int) -> dict:
        return {
            "category": self.category,
            "tier": self.tier,
            "num_points": self.num_points,
            "num_matches": self.num_matches,
            "ranking": self.ranking,
            "bp_player_id": player_id,
        }

    @staticmethod
    def from_json(d: dict) -> "Standing":
        return Standing(
            category=d["category"],
            tier=d["tier"],
            num_points=d["num_points"],
            num_matches=d["num_matches"],
            ranking=d["ranking"],
        )


@dataclass
class Set:
    home_points: int
    away_points: int

    def to_dict(self) -> dict:
        return {
            "home_points": self.home_points,
            "away_points": self.away_points,
        }

    def to_html(self, winner: str) -> Markup:
        if winner == "home":
            html = f"<b>{self.home_points}</b> - {self.away_points}"
        else:
            html = f"{self.home_points} - <b>{self.away_points}</b>"
        return Markup(html)


@dataclass
class Game:
    date: datetime
    category: str
    sets: List[Set]
    home_player1: str
    home_player2: Optional[str]
    away_player1: str
    away_player2: Optional[str]

    def contains(self, player_name: str) -> bool:
        return player_name in [
            self.home_player1,
            self.home_player2,
            self.away_player1,
            self.away_player2,
        ]

    def get_winner(self) -> str:
        if not self.home_player1 and not self.home_player2:
            return "away"
        if not self.away_player1 and not self.away_player2:
            return "home"
        home = sum([1 for s in self.sets if s.home_points > s.away_points])
        away = sum([1 for s in self.sets if s.home_points < s.away_points])
        return "home" if home > away else "away"

    def won_by(self, player_name: str) -> bool:
        if self.get_winner() == "home":
            return player_name in [self.home_player1, self.home_player2]
        else:
            return player_name in [self.away_player1, self.away_player2]

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "sets": [s.to_dict() for s in self.sets],
            "home_player1": self.home_player1,
            "home_player2": self.home_player2,
            "away_player1": self.away_player1,
            "away_player2": self.away_player2,
        }


@dataclass
class MatchMeta:
    id: int
    sort: int
    date: datetime
    group: str
    home_team: str
    away_team: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "date": self.date,
            "group": self.group,
            "home_team": self.home_team,
            "away_team": self.away_team,
        }


@dataclass
class Match:
    id: int
    date: datetime
    group: str
    home_team: str
    home_team_points: int
    away_team: str
    away_team_points: int
    games: List[Game]
    location: str

    def get_winner(self) -> str:
        return "home" if self.home_team_points > self.away_team_points else "away"

    def is_tie(self) -> bool:
        return self.home_team_points == self.away_team_points

    def on_winning_team(self, player_name: str) -> bool:
        home_players = []
        away_players = []
        for g in self.games:
            home_players.append(g.home_player1)
            if g.home_player2:
                home_players.append(g.home_player2)

            away_players.append(g.away_player1)
            if g.away_player2:
                away_players.append(g.away_player2)

        home_players = [p for p in home_players if p]
        away_players = [p for p in away_players if p]

        if not self.date:
            players = home_players if home_players else away_players
            return player_name in players

        if self.get_winner() == "home":
            return player_name in self.home_team
        else:
            return player_name in self.away_team


@dataclass
class Player:
    id: int
    name: str
    club_name: str
    club_id: int
    birth_date: datetime

    def get_age(self) -> int:
        today = datetime.today()
        return (
            today.year
            - self.birth_date.year
            - ((today.month, today.day) < (self.birth_date.month, self.birth_date.day))
        )

    def to_dict(self) -> dict:
        return {
            "bp_id": self.id,
            "bp_name": self.name,
            "bp_club_id": self.club_id,
            "birthdate": self.birth_date.isoformat()
            if self.birth_date
            else "1970-01-01T00:00:00+00:00",
        }

    @staticmethod
    def from_json(d: dict) -> "Player":
        return Player(
            id=d["bp_id"],
            name=d["bp_name"],
            club_name=d["clubs"]["name"],
            club_id=d["bp_club_id"],
            birth_date=datetime.strptime(d["birthdate"], "%Y-%m-%dT%H:%M:%S%z"),
        )


@dataclass
class PlayerMeta:
    season_start_points: int
    standings: List[Standing]
    match_metadata: List[MatchMeta]
