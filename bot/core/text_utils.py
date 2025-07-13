from calendar import month_name
from datetime import datetime
from random import choice
from asyncio import sleep as asleep
from aiohttp import ClientSession, ClientResponseError
import xml.etree.ElementTree as ET
from anitopy import parse
from bot import Var, bot
from .ffencoder import ffargs
from .func_utils import handle_logs
from .reporter import rep

CAPTION_FORMAT = """
<blockquote><b>㊂ <i>{title}</i></b></blockquote>
<b>╔━━━━━━━━━━━━━━━━━━━━━╗</b>
<blockquote><b>‣</b> <i>Sᴇᴀsᴏɴ:</i> <i>{anime_season}</i>
<b>‣</b> <i>Eᴘɪsᴏᴅᴇ:</i> <i>{ep_no}</i></blockquote>
<blockquote><b>‣</b> <i>Aᴜᴅɪᴏ: Japanese [ESub]</i>
<b>‣</b> <i>Sᴛᴀᴛᴜs:</i> <i>{status}</i></blockquote>
<blockquote><b>‣</b> <i>Tᴏᴛᴀʟ Eᴘɪsᴏᴅᴇs:</i> <i>{t_eps}
<b>‣</b> <i>Gᴇɴʀᴇs:</i> <i>{genres}</i></blockquote>
<b>╚━━━━━━━━━━━━━━━━━━━━━╝</b>
╭┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅
⌬ <b><i>Pᴏᴡᴇʀᴇᴅ Bʏ</i></b> ~ </i></b><b><i>{cred}</i></b>
╰┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅
"""

GENRES_EMOJI = {
    "Action": "👊", "Adventure": choice(['🪂', '🧗‍♀']), "Comedy": "🤣",
    "Drama": "🎭", "Ecchi": choice(['💋', '🥵']), "Fantasy": choice(['🧞', '🧞‍♂️', '🧞‍♀️', '🌗']),
    "Hentai": "🔞", "Horror": "☠", "Mahou Shoujo": "☯", "Mecha": "🤖", "Mystery": "🔮",
    "Psychological": "♟", "Romance": "💞", "Sci-Fi": "🛸",
    "Slice of Life": choice(['☘', '🍁']), "Sports": "⚽️", "Supernatural": "🫧", "Thriller": choice(['🥶', '🔪', '🤯'])
}

GENRE_NORMALIZATION = {
    "Action & Adventure": "Action",
    "Romantic Comedy": "Comedy",
    "Shounen": "Action",
    "Shoujo": "Romance",
    "Seinen": "Drama",
    "Josei": "Drama",
    "Slice-of-Life": "Slice of Life",
    "Magical Girl": "Mahou Shoujo",
    "Science Fiction": "Sci-Fi",
    "Psychological Thriller": "Psychological",
    "Suspense": "Thriller"
}

KITSU_API = "https://kitsu.io/api/edge/anime"
ANILIST_API = "https://graphql.anilist.co"
JIKAN_API = "https://api.jikan.moe/v4/anime"
ANN_API = "https://www.animenewsnetwork.com/encyclopedia/api/xml"

ANIME_GRAPHQL_QUERY = """
query ($id: Int, $search: String, $seasonYear: Int) {
  Media(id: $id, type: ANIME, format_not_in: [MOVIE, MUSIC, MANGA, NOVEL, ONE_SHOT], search: $search, seasonYear: $seasonYear) {
    id
    idMal
    title {
      romaji
      english
      native
    }
    type
    format
    status(version: 2)
    description(asHtml: false)
    startDate {
      year
      month
      day
    }
    endDate {
      year
      month
      day
    }
    season
    seasonYear
    episodes
    duration
    chapters
    volumes
    countryOfOrigin
    source
    hashtag
    trailer {
      id
      site
      thumbnail
    }
    updatedAt
    coverImage {
      large
    }
    bannerImage
    genres
    synonyms
    averageScore
    meanScore
    popularity
    trending
    favourites
    studios {
      nodes {
        name
        siteUrl
      }
    }
    isAdult
    nextAiringEpisode {
      airingAt
      timeUntilAiring
      episode
    }
    airingSchedule {
      edges {
        node {
          airingAt
          timeUntilAiring
          episode
        }
      }
    }
    externalLinks {
      url
      site
    }
    siteUrl
  }
}
"""

def normalize_genres(genres: list) -> list:
    """Normalize API-specific genres to match GENRES_EMOJI keys."""
    normalized = []
    for genre in genres or []:
        genre_key = GENRE_NORMALIZATION.get(genre, genre)
        if genre_key in GENRES_EMOJI:
            normalized.append(genre_key)
    return normalized

class AniLister:
    def __init__(self, anime_name: str, year: int) -> None:
        self.__kitsu_api = KITSU_API
        self.__anilist_api = ANILIST_API
        self.__jikan_api = JIKAN_API
        self.__ann_api = ANN_API
        self.__ani_name = anime_name
        self.__ani_year = year
        self.__anilist_vars = {'search': self.__ani_name, 'seasonYear': self.__ani_year}
        self.__anilist_retries = 3  # Limit AniList retries to avoid floodwait loops

    async def post_data(self, api: str, params: dict = None, json: dict = None, headers: dict = None):
        try:
            async with ClientSession() as sess:
                if api == self.__anilist_api:
                    async with sess.post(api, json=json, headers=headers, timeout=15) as resp:
                        return await self._handle_response(resp)
                else:
                    async with sess.get(api, params=params, headers=headers, timeout=15) as resp:
                        return await self._handle_response(resp)
        except Exception as e:
            await rep.report(f"API Error ({api}): {str(e)}", "error")
            return (500, None, {})

    async def _handle_response(self, resp):
        if resp.status != 200:
            return (resp.status, None, resp.headers)
        if resp.content_type not in ["application/json", "text/xml", "application/vnd.api+json"]:
            raise ClientResponseError(
                resp.request_info,
                resp.history,
                status=resp.status,
                message=f"Unexpected content-type: {resp.content_type}"
            )
        if resp.content_type == "text/xml":
            return (resp.status, await resp.text(), resp.headers)
        return (resp.status, await resp.json(), resp.headers)

    @handle_logs
    async def _parse_kitsu_data(self, data):
        if not data or not data.get("data"):
            return {}
        anime = data["data"][0] if isinstance(data["data"], list) else data["data"]
        attributes = anime.get("attributes", {})
        genres = normalize_genres(attributes.get("genres", []))
        return {
            "id": anime.get("id"),
            "title": {
                "english": attributes.get("titles", {}).get("en") or attributes.get("titles", {}).get("en_jp"),
                "romaji": attributes.get("titles", {}).get("en_jp"),
                "native": attributes.get("titles", {}).get("ja_jp")
            },
            "status": attributes.get("status", "").replace("_", " ").title(),
            "description": attributes.get("synopsis"),
            "startDate": {
                "year": attributes.get("startDate", "").split("-")[0] if attributes.get("startDate") else None,
                "month": attributes.get("startDate", "").split("-")[1] if attributes.get("startDate") else None,
                "day": attributes.get("startDate", "").split("-")[2] if attributes.get("startDate") else None
            },
            "endDate": {
                "year": attributes.get("endDate", "").split("-")[0] if attributes.get("endDate") else None,
                "month": attributes.get("endDate", "").split("-")[1] if attributes.get("endDate") else None,
                "day": attributes.get("endDate", "").split("-")[2] if attributes.get("endDate") else None
            },
            "episodes": attributes.get("episodeCount"),
            "genres": genres,
            "averageScore": attributes.get("averageRating"),
            "coverImage": {"large": attributes.get("posterImage", {}).get("large")}
        }

    @handle_logs
    async def _parse_anilist_data(self, data):
        if not data or not data.get("data", {}).get("Media"):
            return {}
        anime = data["data"]["Media"]
        genres = normalize_genres(anime.get("genres", []))
        return {
            "id": anime.get("id"),
            "idMal": anime.get("idMal"),
            "title": anime.get("title", {}),
            "status": anime.get("status", "").replace("_", " ").title(),
            "description": anime.get("description"),
            "startDate": anime.get("startDate", {}),
            "endDate": anime.get("endDate", {}),
            "episodes": anime.get("episodes"),
            "genres": genres,
            "averageScore": anime.get("averageScore"),
            "coverImage": anime.get("coverImage", {})
        }

    @handle_logs
    async def _parse_jikan_data(self, data):
        if not data or not data.get("data"):
            return {}
        anime = data["data"][0] if isinstance(data["data"], list) else data["data"]
        genres = normalize_genres([g["name"] for g in anime.get("genres", [])])
        return {
            "id": anime.get("mal_id"),
            "title": {
                "english": anime.get("title_english"),
                "romaji": anime.get("title"),
                "native": anime.get("title_japanese")
            },
            "status": anime.get("status", "").replace("_", " ").title(),
            "description": anime.get("synopsis"),
            "startDate": {
                "year": anime.get("aired", {}).get("from", "").split("-")[0] if anime.get("aired", {}).get("from") else None,
                "month": anime.get("aired", {}).get("from", "").split("-")[1] if anime.get("aired", {}).get("from") else None,
                "day": anime.get("aired", {}).get("from", "").split("-")[2] if anime.get("aired", {}).get("from") else None
            },
            "endDate": {
                "year": anime.get("aired", {}).get("to", "").split("-")[0] if anime.get("aired", {}).get("to") else None,
                "month": anime.get("aired", {}).get("to", "").split("-")[1] if anime.get("aired", {}).get("to") else None,
                "day": anime.get("aired", {}).get("to", "").split("-")[2] if anime.get("aired", {}).get("to") else None
            },
            "episodes": anime.get("episodes"),
            "genres": genres,
            "averageScore": anime.get("score") * 10 if anime.get("score") else None,
            "coverImage": {"large": anime.get("images", {}).get("jpg", {}).get("large_image_url")}
        }

    @handle_logs
    async def _parse_ann_data(self, xml_data):
        try:
            root = ET.fromstring(xml_data)
            anime = root.find(".//anime")
            if not anime:
                return {}
            genres = normalize_genres([g.text for g in anime.findall("info[@type='Genres']/genre")])
            vintage = anime.findtext("info[@type='Vintage']")
            status = "Finished Airing" if vintage and "-" in vintage else "Currently Airing"
            return {
                "id": anime.get("id"),
                "title": {
                    "english": anime.findtext("name[@type='main']") or anime.findtext("name[@type='official']"),
                    "romaji": anime.findtext("name[@type='japanese']"),
                    "native": anime.findtext("name[@type='japanese']")
                },
                "status": status,
                "description": anime.findtext("info[@type='Plot Summary']"),
                "startDate": {
                    "year": vintage.split("-")[0] if vintage else None,
                    "month": vintage.split("-")[1] if vintage and len(vintage.split("-")) > 1 else None,
                    "day": None
                },
                "endDate": {"year": None, "month": None, "day": None},
                "episodes": anime.findtext("info[@type='Number of episodes']"),
                "genres": genres,
                "averageScore": float(anime.findtext("info[@type='Rating']")) * 10 if anime.findtext("info[@type='Rating']") else None,
                "coverImage": {"large": anime.findtext("info[@type='Picture']/img[@src]") or "https://cdn.animenewsnetwork.com/thumbnails/max300x300/encyc-latest.jpg"}
            }
        except Exception as e:
            await rep.report(f"ANN XML Parsing Error: {str(e)}", "error")
            return {}

    @handle_logs
    async def get_anilist_id(self, mal_id: int = None, name: str = None, year: int = None):
        """Attempt to fetch AniList ID using MAL ID or name/year."""
        if mal_id:
            variables = {'idMal': mal_id}
        else:
            variables = {'search': name, 'seasonYear': year} if year else {'search': name}
        res_code, resp_json, res_heads = await self.post_data(
            self.__anilist_api,
            json={'query': ANIME_GRAPHQL_QUERY, 'variables': variables}
        )
        if res_code == 200 and resp_json.get('data', {}).get('Media'):
            return resp_json['data']['Media']['id']
        elif res_code == 429:
            f_timer = int(res_heads.get('Retry-After', 120))
            await rep.report(f"AniList ID Fetch Rate Limit: Sleeping for {f_timer}s", "error")
            if self.__anilist_retries > 0:
                self.__anilist_retries -= 1
                await asleep(f_timer)
                return await self.get_anilist_id(mal_id, name, year)
        await rep.report(f"Failed to fetch AniList ID for {name or mal_id}", "error")
        return None

    async def get_anidata(self):
        params = {"filter[text]": self.__ani_name, "filter[seasonYear]": self.__ani_year}
        res_code, resp_data, res_heads = await self.post_data(self.__kitsu_api, params=params, headers={'Accept': 'application/vnd.api+json'})
        if res_code == 200 and resp_data.get("data"):
            await rep.report(f"Kitsu API Success: {self.__ani_name}", "info", log=False)
            return await self._parse_kitsu_data(resp_data)
        elif res_code == 429:
            f_timer = int(res_heads.get('Retry-After', 60))
            await rep.report(f"Kitsu API Rate Limit: Sleeping for {f_timer}s", "error")
            await asleep(f_timer)
            return await self.get_anidata()

        # Fallback to Jikan API (second priority)
        params = {"q": self.__ani_name, "year": self.__ani_year}
        res_code, resp_data, res_heads = await self.post_data(self.__jikan_api, params=params)
        if res_code == 200 and resp_data.get("data"):
            await rep.report(f"Jikan API Success: {self.__ani_name}", "info", log=False)
            return await self._parse_jikan_data(resp_data)
        elif res_code == 429:
            f_timer = int(res_heads.get('Retry-After', 3))
            await rep.report(f"Jikan API Rate Limit: Sleeping for {f_timer}s", "error")
            await asleep(f_timer)
            return await self.get_anidata()

        # Fallback to AniList API (third priority due to floodwait errors)
        for year in range(self.__ani_year, 2020, -1):
            self.__anilist_vars['seasonYear'] = year
            res_code, resp_json, res_heads = await self.post_data(
                self.__anilist_api,
                json={'query': ANIME_GRAPHQL_QUERY, 'variables': self.__anilist_vars}
            )
            if res_code == 200 and resp_json.get('data', {}).get('Media'):
                await rep.report(f"AniList API Success: {self.__ani_name}", "info", log=False)
                return await self._parse_anilist_data(resp_json)
            elif res_code == 429:
                f_timer = int(res_heads.get('Retry-After', 120))
                await rep.report(f"AniList API Rate Limit: Sleeping for {f_timer}s", "error")
                if self.__anilist_retries > 0:
                    self.__anilist_retries -= 1
                    await asleep(f_timer)
                    continue
                await rep.report(f"AniList Retry Limit Exhausted for {self.__ani_name}", "error")
                break
            elif res_code in [500, 501, 502]:
                await rep.report(f"AniList API Server Error: {res_code}, Waiting 5s", "error")
                await asleep(5)
                continue

        # Try AniList without year as a further attempt
        self.__anilist_vars = {'search': self.__ani_name}
        res_code, resp_json, res_heads = await self.post_data(
            self.__anilist_api,
            json={'query': ANIME_GRAPHQL_QUERY, 'variables': self.__anilist_vars}
        )
        if res_code == 200 and resp_json.get('data', {}).get('Media'):
            await rep.report(f"AniList API Success (no year): {self.__ani_name}", "info", log=False)
            return await self._parse_anilist_data(resp_json)
        elif res_code == 429:
            f_timer = int(res_heads.get('Retry-After', 120))
            await rep.report(f"AniList API Rate Limit (no year): Sleeping for {f_timer}s", "error")
            if self.__anilist_retries > 0:
                self.__anilist_retries -= 1
                await asleep(f_timer)
                return await self.get_anidata()

        # Fallback to ANN API (last priority)
        params = {"title": self.__ani_name, "type": "anime"}
        res_code, resp_data, res_heads = await self.post_data(self.__ann_api, params=params)
        if res_code == 200 and resp_data:
            parsed_data = await self._parse_ann_data(resp_data)
            if parsed_data:
                await rep.report(f"ANN API Success: {self.__ani_name}", "info", log=False)
                return parsed_data
        elif res_code == 429:
            f_timer = int(res_heads.get('Retry-After', 60))
            await rep.report(f"ANN API Rate Limit: Sleeping for {f_timer}s", "error")
            await asleep(f_timer)
            return await self.get_anidata()

        await rep.report(f"All APIs Failed for {self.__ani_name}", "error")
        return {}

class TextEditor:
    def __init__(self, name):
        self.__name = name
        self.adata = {}
        self.pdata = parse(name)
        self.anilister = AniLister(self.__name, datetime.now().year)

    async def load_anilist(self):
        cache_names = set()  # Use set to avoid duplicates
        for no_s, no_y in [(False, False), (False, True), (True, False), (True, True)]:
            ani_name = await self.parse_name(no_s, no_y)
            if not ani_name or ani_name in cache_names:
                continue
            cache_names.add(ani_name)
            self.anilister._AniLister__ani_name = ani_name  # Update AniLister's name
            self.adata = await self.anilister.get_anidata()
            if self.adata:
                break  

    @handle_logs
    async def get_id(self):
        if (ani_id := self.adata.get('id')) and str(ani_id).isdigit():
            return ani_id
        return None

    @handle_logs
    async def parse_name(self, no_s=False, no_y=False):
        anime_name = self.pdata.get("anime_title") or self.__name
        anime_season = self.pdata.get("anime_season")
        anime_year = self.pdata.get("anime_year")
        if anime_name:
            pname = anime_name
            if not no_s and self.pdata.get("episode_number") and anime_season:
                pname += f" {anime_season}"
            if not no_y and anime_year:
                pname += f" {anime_year}"
            return pname
        return anime_name

    @handle_logs
    async def get_poster(self):
        # Try to get AniList ID regardless of API source
        anime_id = None
        if self.adata.get("idMal") or "Media" in self.adata:  # AniList data
            anime_id = self.adata.get("id")
        elif self.adata.get("id"):  # Jikan, Kitsu, or ANN data
            mal_id = self.adata.get("id") if "mal_id" in self.adata else None
            name = self.adata.get("title", {}).get("romaji") or self.adata.get("title", {}).get("english") or self.__name
            year = self.adata.get("startDate", {}).get("year") or self.anilister._AniLister__ani_year
            anime_id = await self.anilister.get_anilist_id(mal_id=mal_id, name=name, year=year)
        
        if anime_id and str(anime_id).isdigit():
            return f"https://img.anili.st/media/{anime_id}"
        return "https://envs.sh/YsH.jpg"

    @handle_logs
    async def get_upname(self, qual=""):
        anime_name = self.pdata.get("anime_title")
        codec = 'HEVC' if 'libx265' in ffargs[qual] else 'AV1' if 'libaom-av1' in ffargs[qual] else ''
        lang = 'SUB' if 'sub' in self.__name.lower() else 'Sub'
        anime_season = str(ani_s[-1]) if (ani_s := self.pdata.get('anime_season', '01')) and isinstance(ani_s, list) else str(ani_s)
        if anime_name and self.pdata.get("episode_number"):
            titles = self.adata.get('title', {})
            return f"""[S{anime_season}-{'E'+str(self.pdata.get('episode_number')) if self.pdata.get('episode_number') else ''}] {titles.get('english') or titles.get('romaji') or titles.get('native')} {'['+qual+'p]' if qual else ''} {'['+codec.upper()+'] ' if codec else ''}{'['+lang+']'} {Var.BRAND_UNAME}.mkv"""
        return None

    @handle_logs
    async def get_caption(self):
        sd = self.adata.get('startDate', {})
        try:
            month_idx = int(sd.get('month')) if sd.get('month') else None
            startdate = f"{month_name[month_idx]} {sd['day']}, {sd['year']}" if sd.get('day') and sd.get('year') and month_idx else "N/A"
        except (ValueError, TypeError):
            startdate = "N/A"
        ed = self.adata.get('endDate', {})
        try:
            month_idx = int(ed.get('month')) if ed.get('month') else None
            enddate = f"{month_name[month_idx]} {ed['day']}, {ed['year']}" if ed.get('day') and ed.get('year') and month_idx else "N/A"
        except (ValueError, TypeError):
            enddate = "N/A"
        titles = self.adata.get("title", {})
        
        return CAPTION_FORMAT.format(
            title=titles.get('english') or titles.get('romaji') or titles.get('native') or "N/A",
            form=self.adata.get("format") or "N/A",
            genres=", ".join(f"{GENRES_EMOJI[x]} #{x.replace(' ', '_').replace('-', '_')}" for x in (self.adata.get('genres') or [])),
            avg_score=f"{sc}%" if (sc := self.adata.get('averageScore')) else "N/A",
            status=self.adata.get("status") or "N/A",
            start_date=startdate,
            end_date=enddate,
            t_eps=self.adata.get("episodes") or "N/A",
            anime_season=str(ani_s[-1]) if (ani_s := self.pdata.get('anime_season', '01')) and isinstance(ani_s, list) else str(ani_s),
            plot=(desc if (desc := self.adata.get("description") or "N/A") and len(desc) < 200 else desc[:200] + "...") if self.adata.get("description") else "N/A",
            ep_no=self.pdata.get("episode_number") or "N/A",
            cred=Var.BRAND_UNAME,
        )
