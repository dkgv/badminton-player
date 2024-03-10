import os

import supabase
from supabase.lib.client_options import ClientOptions

from app.badminton_player import api

badminton_player_client = api.Client()

supabase_client = supabase.create_client(
    supabase_url=os.getenv("SUPABASE_URL"),
    supabase_key=os.getenv("SUPABASE_KEY"),
    options=ClientOptions(postgrest_client_timeout=10000),
)
