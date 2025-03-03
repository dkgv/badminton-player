"""
abandon all hope, ye who enter here, for here be dragons

this is the gem that powers badmintonplayer.dk data retrieval

raw requests dumped from network traffic -> cURL request -> python code

recommendation: leave
"""

import re
import time
from datetime import datetime
from enum import Enum
from typing import Dict, List

import cachetools.func
import pandas as pd
import requests
from bs4 import BeautifulSoup

from app.badminton_player.models import (
    Game,
    MatchMeta,
    Player,
    PlayerPerformance,
    Set,
    Standing,
    TeamMatch,
    Tournament,
)


class TableType(Enum):
    TILMELDINGSNIVEAU = 0
    STANDINGS = 1
    MATCHES = 2
    TOURNAMENTS = 3


class Client:
    def __init__(self) -> None:
        self.base_url = "https://www.badmintonplayer.dk"

    def _get_context_key(self) -> str:
        one_hour = 4 * 60 * 60
        ttl_hash = round(time.time() / one_hour)
        return self._extract_context_key(ttl_hash)

    @cachetools.func.ttl_cache(ttl=3600)
    def _extract_context_key(self, ttl_hash: int) -> str:
        r = requests.get(self.base_url)
        soup = BeautifulSoup(r.text, features="lxml")
        scripts = soup.find_all("script")
        for s in scripts:
            if "var SR_CallbackContext" not in s.text:
                continue

            part = s.text.split("SR_CallbackContext = ")[1]
            return part.split(";")[0].replace("'", "").strip()
        print("Could not find context key")
        return ""

    def get_player(self, player_id: int) -> Player | None:
        url = "http://badmintonplayer.dk/SportsResults/Components/WebService1.asmx/GetPlayerProfile"

        payload = {
            "callbackcontextkey": self._get_context_key(),
            "seasonid": "",
            "playerid": player_id,
            "getplayerdata": True,
            "showUserProfile": True,
            "showheader": False,
        }

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/111.0",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/json; charset=utf-8",
            "Origin": "http://badmintonplayer.dk",
            "DNT": "1",
            "Connection": "keep-alive",
            "Referer": "http://badmintonplayer.dk/DBF/Spiller/VisSpiller/",
        }

        response = requests.post(url, headers=headers, json=payload)
        if not response.ok:
            print("Could not get player", player_id, response.status_code)
            return None

        json_obj = response.json()

        birth_date = datetime.strptime(json_obj["d"]["playernumber"][0:6], "%y%m%d")
        player_name = json_obj["d"]["playername"].strip()

        return Player(
            id=player_id,
            club_id=json_obj["d"]["clubid"],
            birth_date=birth_date,
            name=player_name,
            club_name=json_obj["d"]["clubname"],
        )

    def search_player(self, name: str, club: str | None = None) -> List[Player]:
        json_data = {
            "callbackcontextkey": self._get_context_key(),
            "selectfunction": "SPSel1",
            "name": name,
            "clubid": "",
            "playernumber": "",
            "gender": "",
            "agegroupid": "",
            "searchteam": False,
            "licenseonly": False,
            "agegroupcontext": 0,
            "tournamentdate": "",
        }
        headers = {
            "Content-Type": "application/json; charset=utf-8",
        }

        def extract_value(string, position) -> str | None:
            s = re.findall(r"'(.*?)'", string)
            if len(s) <= position:
                return None
            return s[position]

        url = f"{self.base_url}/SportsResults/Components/WebService1.asmx"
        r = requests.post(url + "/SearchPlayer", headers=headers, json=json_data)
        if r.status_code != 200:
            return []

        players = []

        json_obj = r.json()
        soup = BeautifulSoup(json_obj["d"]["Html"], features="lxml")
        tbl = soup.find("table")

        for row in tbl.find_all("tr"):
            cells = row.find_all("td")
            player_club = cells[3].text
            if club and club.lower() != player_club.lower():
                continue

            # onclick="SPSel1('76749', '961019-09', 'Gustav V. Yde', '1666', 'Vejlby IK', 'M')"
            # get 1666
            club_id = extract_value(row["onclick"], 3)
            if not club_id:
                continue

            player_id = extract_value(row["onclick"], 0)
            birth_date = extract_value(row["onclick"], 1)[0:6]
            if birth_date != "000000":
                birth_date = datetime.strptime(birth_date, "%y%m%d")
            else:
                birth_date = None

            player_name = extract_value(row["onclick"], 2)

            players.append(
                Player(
                    id=int(player_id),
                    name=player_name,
                    club_name=player_club,
                    birth_date=birth_date,
                    club_id=int(club_id),
                )
            )

        return players

    def __parse_as_df(self, table) -> pd.DataFrame:
        columns = []
        for th in table.find_all("th"):
            columns.append(th.text)

        df = pd.DataFrame(columns=columns)

        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) == 0:
                continue

            if len(cells) == len(columns):
                df_row = {}

                for i, cell in enumerate(cells):
                    df_row[columns[i]] = cell.text
                    df_row[f"{columns[i]}_html"] = str(cell)

                df_row = pd.DataFrame(
                    df_row, index=[0]
                )  # convert the dictionary to a DataFrame with a single row
            else:
                return pd.read_html(str(table))[0]

            df = pd.concat([df, df_row], ignore_index=True)

        return df

    @cachetools.func.ttl_cache(ttl=3600)
    def get_performance_cached_1h(self, player_id: int) -> PlayerPerformance | None:
        headers = {
            "authority": "badmintonplayer.dk",
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/json; charset=UTF-8",
            "origin": "https://badmintonplayer.dk",
            "referer": "https://badmintonplayer.dk/DBF/Spiller/VisSpiller/",
            "sec-ch-ua": '"Chromium";v="105", "Not)A;Brand";v="8"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36",
            "x-requested-with": "XMLHttpRequest",
        }

        json_data = {
            "callbackcontextkey": self._get_context_key(),
            "seasonid": "",  # pass year here
            "playerid": str(player_id),
            "getplayerdata": True,
            "showUserProfile": True,
            "showheader": False,
        }

        response = requests.post(
            f"{self.base_url}/SportsResults/Components/WebService1.asmx/GetPlayerProfile",
            headers=headers,
            json=json_data,
        )
        if response.status_code != 200:
            print(
                "Could not get profile", player_id, response.status_code, response.text
            )
            return None

        json_data = response.json()
        soup = BeautifulSoup(json_data["d"]["Html"], features="lxml")

        tables = [
            t
            for t in soup.find_all("table")
            if "playerprofileuserlist" not in t.attrs.get("class", [])
            and len(t.find_all(recursive=False)) > 0
        ]

        print(f"{len(tables)} tables found in total")

        tables = [self.__parse_as_df(t) for t in tables]

        table_mapping = self.__identify_tables(tables)

        points_at_start = -1
        if TableType.TILMELDINGSNIVEAU in table_mapping:
            table = table_mapping[TableType.TILMELDINGSNIVEAU]
            points_at_start = int(table.iloc[0][1])

        if TableType.STANDINGS in table_mapping:
            standings = table_mapping[TableType.STANDINGS]

            standings = standings[standings["Rangliste"] != "Tilmeldingsniveau"]

            standings = standings.apply(
                lambda x: Standing(
                    category=x["Rangliste"],
                    tier=x["Række"],
                    num_points=int(x["Point"]) if pd.notna(x["Point"]) else None,
                    num_matches=int(x["Kampe"]) if pd.notna(x["Kampe"]) else None,
                    ranking=int(x["Placering"]) if pd.notna(x["Placering"]) else -1,
                ),
                axis=1,
            )
        else:
            standings = pd.Series()

        sort = 0

        def get_sort():
            nonlocal sort
            sort += 1
            return sort

        matches = []
        if TableType.MATCHES in table_mapping:
            matches = table_mapping[TableType.MATCHES]

            if "Kampdato" in matches.columns:
                matches = matches.apply(
                    lambda x: MatchMeta(
                        id=int(x["Kampdato_html"].split(",")[-2]),
                        date=(
                            datetime.strptime(x["Kampdato"], "%d-%m-%Y %H:%M:%S")
                            if x["Kampdato"].strip()
                            else None
                        ),
                        division=x["Række"],
                        sort=get_sort(),
                        team1=x["Hold"],
                        team2=x["Modstander"],
                    ),
                    axis=1,
                )

        tournaments = []
        if TableType.TOURNAMENTS in table_mapping:
            tournaments_df = table_mapping[TableType.TOURNAMENTS]

            def get_tournament_id(x):
                number_regex = re.compile(r"\d+")
                match = number_regex.search(x["Række_html"])
                return int(match.group())

            for row in tournaments_df.iterrows():
                row = row[1]
                if "Klub" not in row:
                    print("Could not find Klub in", tournaments_df.columns)
                    continue

                tournaments.append(
                    Tournament(
                        bp_id=get_tournament_id(row),
                        host_club=row["Klub"],
                        level=row["Række"],
                        date=datetime.strptime(row["Dato"], "%d-%m-%Y"),
                    )
                )

        return PlayerPerformance(
            season_start_points=points_at_start,
            match_metadata=matches,
            standings=standings,
            tournaments=tournaments,
        )

    def __identify_tables(
        self, tables: List[pd.DataFrame]
    ) -> Dict[TableType, pd.DataFrame]:
        result = {}
        for table in tables:
            if table.empty:
                continue

            if all([col in table.columns for col in ["Rangliste", "Række", "Point"]]):
                result[TableType.STANDINGS] = table
            elif all(
                [col in table.columns for col in ["Kampdato", "Hold", "Modstander"]]
            ):
                result[TableType.MATCHES] = table
            elif all([col in table.columns for col in ["Række", "Dato", "Klub"]]):
                result[TableType.TOURNAMENTS] = table
            elif table.apply(
                lambda row: row.astype(str)
                .str.contains("Tilmeldingsniveau ved sæsonstart:")
                .any(),
                axis=1,
            ).any():
                result[TableType.TILMELDINGSNIVEAU] = table

        return result

    def get_match(self, match_id: int) -> TeamMatch:
        print("Getting match", match_id)

        url = f"http://badmintonplayer.dk/DBF/HoldTurnering/UdskrivHoldkamp/?match={match_id}"
        response = requests.get(url)
        soup = BeautifulSoup(response.text, features="lxml")
        tables = soup.find_all("table")

        def get_details(table) -> Dict[str, str]:
            details = {}
            rows = table.find_all("tr")
            for row in rows:
                for td in row.find_all("td"):
                    span = td.find("span")
                    if not span:
                        print("Could not find span in", td)
                        continue
                    header = td.find("span").text
                    for span in td.find_all("span"):
                        span.decompose()
                    details[header] = td.text.strip()

            # Convert the "Tid" field to a more readable format
            if "Tid" in details:
                days = {
                    "lø": "sat",
                    "sø": "sun",
                    "on": "wed",
                    "ma": "mon",
                    "ti": "tue",
                    "to": "thu",
                    "fr": "fri",
                }
                details["Tid"] = details["Tid"].replace("\xa0", " ")
                for key, value in days.items():
                    details["Tid"] = details["Tid"].replace(key, value)

            return details

        details = get_details(tables[0])
        print("Match details", details)
        date = (
            datetime.strptime(details["Tid"], "%a %d-%m-%Y %H:%M")
            if details["Tid"]
            else None
        )

        def get_games(table) -> List[Game]:
            games = []
            rows = table.find_all("tr")[1:]  # Skip the first row (header)
            for row in rows:
                cells = row.find_all("td")
                if not cells:
                    continue

                category = cells[0].text.strip()

                # Extract details about the players
                if len(cells) <= 1:
                    continue

                div = cells[1].find("div")
                if div:
                    div.decompose()
                home_players = cells[1].find_all("div")
                home_player1 = home_players[0].text.strip()
                home_player2 = (
                    home_players[1].text.strip() if len(home_players) > 1 else None
                )

                cells[2].find("div").decompose()
                away_players = cells[2].find_all("div")
                away_player1 = away_players[0].text.strip()
                away_player2 = (
                    away_players[1].text.strip() if len(away_players) > 1 else None
                )

                # Extract the scores for each set
                sets = []
                for cell in cells[3:6]:
                    if cell.text.strip():
                        home_points, away_points = cell.text.split("-")
                        set_ = Set(
                            number=len(sets) + 1,
                            home_points=int(home_points.strip()),
                            away_points=int(away_points.strip()),
                        )
                        sets.append(set_)

                games.append(
                    Game(
                        category=category,
                        home_player1=home_player1,
                        home_player2=home_player2,
                        away_player1=away_player1,
                        away_player2=away_player2,
                        sets=sets,
                        date=date,
                    )
                )

            return games

        games = get_games(tables[2])
        overall_result = tables[1]

        return TeamMatch(
            id=int(details["Kampnr"]),
            division=details["Række"],
            date=date,
            home_team=overall_result.find_all("td")[0].text.strip(),
            away_team=overall_result.find_all("td")[4].text.strip(),
            games=games,
        )
