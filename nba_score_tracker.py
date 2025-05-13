import streamlit as st
from streamlit_autorefresh import st_autorefresh
from nba_api.live.nba.endpoints import scoreboard, playbyplay, boxscore
import re

st.set_page_config(page_title="NBA Player Tracker", layout="centered")
st_autorefresh(interval=2000, limit=None, key="refresh")

st.markdown("""
<style>
    .event-box {
        animation: fadeInSlide 0.5s ease-in-out;
        background-color: #ffffff;
        padding: 1rem;
        margin-bottom: 0.5rem;
        box-shadow: 0 0 5px rgba(0,0,0,0.1);
        border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)

st.title("🏀 NBA Live Player Tracker")

def get_today_games():
    games = scoreboard.ScoreBoard().get_dict()["scoreboard"]["games"]
    return [{"label": f"{g['awayTeam']['teamTricode']} vs {g['homeTeam']['teamTricode']}", "value": g["gameId"]} for g in games]

def get_players_in_game(game_id):
    try:
        bs = boxscore.BoxScore(game_id=game_id).get_dict()
        players = []
        abbr_map = {}
        for team in ['homeTeam', 'awayTeam']:
            for player in bs['game'][team]['players']:
                full = player['name']
                parts = full.split()
                abbr = f"{parts[0][0]}. {parts[-1]}" if len(parts) > 1 else full
                players.append(full)
                abbr_map[full] = abbr
        return sorted(players), abbr_map
    except:
        return [], {}

def format_clock(clock_str):
    match = re.match(r"PT(\d+)M(\d+)\.(\d+)S", clock_str)
    if match:
        m, s, ms = match.groups()
        return f"00:{s.zfill(2)}:{ms.ljust(2, '0')}" if int(m) == 0 else f"{m.zfill(2)}:{s.zfill(2)}"
    return clock_str

def get_game_events(game_id, abbr_name):
    try:
        pbp = playbyplay.PlayByPlay(game_id=game_id).get_dict()
        actions = pbp["game"]["actions"]
        score_keywords = ["3pt", "layup", "dunk", "jump", "hook", "floater", "tip", "runner", "fadeaway", "free throw", "scores", "makes"]

        for action in actions:
            action_id = action["actionNumber"]
            if action_id <= st.session_state.last_action_id:
                continue
            st.session_state.last_action_id = max(st.session_state.last_action_id, action_id)

            desc = action.get("description", "")
            period = action["period"]
            clock = format_clock(action["clock"])
            score_home = action.get("scoreHome", "")
            score_away = action.get("scoreAway", "")
            text = f"[Q{period}] {clock} - {desc} | Score: {score_away} - {score_home}"
            st.session_state.logs.insert(0, text)

            if abbr_name.lower() in desc.lower():
                is_score = "miss" not in desc.lower() and any(kw in desc.lower() for kw in score_keywords)
                is_miss = "miss" in desc.lower()
                log_type = "score" if is_score else "miss" if is_miss else "normal"
                st.session_state.player_logs.insert(0, {"text": text, "type": log_type})
    except:
        pass

# State Init
for k in ["selected_game", "selected_player", "logs", "player_logs"]:
    if k not in st.session_state:
        st.session_state[k] = "" if "selected" in k else []
if "last_action_id" not in st.session_state:
    st.session_state.last_action_id = 0

games = get_today_games()
game_labels = [g["label"] for g in games]
game_map = {g["label"]: g["value"] for g in games}
selected_game = st.selectbox("Select Game", [""] + game_labels, index=(game_labels.index(st.session_state.selected_game)+1 if st.session_state.selected_game in game_labels else 0))

if selected_game:
    st.session_state.selected_game = selected_game
    game_id = game_map[selected_game]
else:
    st.stop()

# Get players and abbreviation map
players, abbr_map = get_players_in_game(game_id)
abbr_name = abbr_map.get(st.session_state.selected_player, st.session_state.selected_player)

# Always fetch new events before tabs, regardless of which is open
get_game_events(game_id, abbr_name)

# === TABS ===
tab1, tab2 = st.tabs(["📋 Full Play-by-Play", "🎯 Player Tracker"])

with tab1:
    for log in st.session_state.logs[:100]:
        st.markdown(f"<div class='event-box'>{log}</div>", unsafe_allow_html=True)

with tab2:
    if players:
        idx = players.index(st.session_state.selected_player)+1 if st.session_state.selected_player in players else 0
        sel = st.selectbox("Track Player", [""] + players, index=idx)
        if sel:
            if sel != st.session_state.selected_player:
                st.session_state.selected_player = sel
                st.session_state.logs = []
                st.session_state.player_logs = []
                st.session_state.last_action_id = 0
            abbr_name = abbr_map.get(sel, sel)
        else:
            st.stop()
    else:
        st.session_state.selected_player = st.text_input("Enter player name")

    # Calculate player stats from logs
    def calculate_player_stats(abbr_name):
        pts = reb = ast = 0
        for log in st.session_state.player_logs:
            txt = log["text"].lower()
            abbr = abbr_name.lower()
            if log["type"] == "score" and abbr in txt:
                match = re.search(r"\((\d+)\s*pts?\)", txt)
                if match:
                    abbr_pos = txt.find(abbr)
                    pts_pos = txt.find(match.group(0))
                    if abbr_pos != -1 and abbr_pos < pts_pos:
                        pts = max(pts, int(match.group(1)))
            if "rebound" in txt and "off:" in txt and "def:" in txt and reb == 0:
                o = re.search(r"off:(\d+)", txt)
                d = re.search(r"def:(\d+)", txt)
                reb = int(o.group(1)) + int(d.group(1)) if o and d else 0
            if "ast" in txt and ast == 0:
                a = re.search(r"(\d+)\s*ast", txt)
                if a: ast = int(a.group(1))
        return pts, reb, ast

    pts, reb, ast = calculate_player_stats(abbr_name)

    # Initialize previous values in session state
    if "prev_pts" not in st.session_state:
        st.session_state.prev_pts = 0
    if "prev_reb" not in st.session_state:
        st.session_state.prev_reb = 0
    if "prev_ast" not in st.session_state:
        st.session_state.prev_ast = 0

    # Calculate deltas
    delta_pts = pts - st.session_state.prev_pts if pts > st.session_state.prev_pts else ""
    delta_reb = reb - st.session_state.prev_reb if reb > st.session_state.prev_reb else ""
    delta_ast = ast - st.session_state.prev_ast if ast > st.session_state.prev_ast else ""

    # Store current as previous for next refresh
    st.session_state.prev_pts = pts
    st.session_state.prev_reb = reb
    st.session_state.prev_ast = ast

    # Show metrics with delta
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Player", abbr_name or "None")
    col2.metric("Points", pts, delta=delta_pts, delta_color="normal")
    col3.metric("Rebounds", reb, delta=delta_reb, delta_color="normal")
    col4.metric("Assists", ast, delta=delta_ast, delta_color="normal")

    st.markdown("### Player Events")
    for log in st.session_state.player_logs[:50]:
        txt = log["text"]
        txt_lower = txt.lower()
        abbr_lower = abbr_name.lower()

        if log["type"] == "score":
            pts_match = re.search(r"\((\d+)\s*pts?\)", txt_lower)
            if abbr_lower in txt_lower and pts_match:
                abbr_pos = txt_lower.find(abbr_lower)
                pts_pos = txt_lower.find(pts_match.group(0))
                if abbr_pos < pts_pos:
                    st.success(f"🏀 {txt} ")
                else:
                    st.markdown(f"<div class='event-box'>{txt}</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div class='event-box'>{txt}</div>", unsafe_allow_html=True)

        elif log["type"] == "miss":
            st.error(txt)

        elif "sub in" in txt_lower:
            st.info(f"{txt} 🔺")

        elif "sub out" in txt_lower:
            st.warning(f"{txt} 🔻")

        else:
            st.markdown(f"<div class='event-box'>{txt}</div>", unsafe_allow_html=True)
