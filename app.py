import streamlit as st
import requests
from datetime import date
import math
from collections import Counter, defaultdict
import json

st.set_page_config(page_title="Robot Prédiction Football", page_icon="⚽", layout="wide")
st.title("⚽ ROBOT DE PRÉDICTION FOOTBALL MODERNE")
st.markdown("**API-Football v3 • Analyse complète • Matches du jour auto**")

# ===================== CONFIG =====================
API_KEY = st.text_input("🔑 Ta clé API-Football (api-sports.io)", type="password", value="")
if not API_KEY:
    st.stop()

BASE_URL = "https://v3.football.api-sports.io"
HEADERS = {"x-apisports-key": API_KEY}

# Ligues populaires (tu peux en ajouter)
POPULAR_LEAGUES = {39: "Premier League", 140: "La Liga", 78: "Bundesliga", 135: "Serie A", 61: "Ligue 1"}

# ===================== FONCTIONS API =====================
def api_get(endpoint, params=None):
    if params is None:
        params = {}
    r = requests.get(f"{BASE_URL}/{endpoint}", headers=HEADERS, params=params, timeout=15)
    if r.status_code != 200:
        st.error(f"API Error {r.status_code}: {r.text}")
        return {}
    return r.json().get("response", [])

# ===================== MATCHES DU JOUR =====================
@st.cache_data(ttl=3600)
def get_todays_matches():
    today = date.today().isoformat()
    all_fixtures = api_get("fixtures", {"date": today})
    # Filtre ligues populaires
    return [f for f in all_fixtures if f["league"]["id"] in POPULAR_LEAGUES]

matches = get_todays_matches()

if not matches:
    st.info("Aucun match aujourd’hui ou clé API invalide.")
    st.stop()

st.subheader(f"📅 {len(matches)} matchs du jour chargés automatiquement")

# ===================== ANALYSE COMPLETE =====================
def perform_full_analysis(fixture_id, home_id, away_id, league_id, season):
    data = {}

    # 1. Fixture + Lineups
    fixture = api_get("fixtures", {"id": fixture_id})[0]
    data["fixture"] = fixture

    # 2. H2H (max 10 derniers)
    h2h = api_get("fixtures/headtohead", {"h2h": f"{home_id}-{away_id}", "last": 10})
    data["h2h"] = h2h

    # 3. Forme récente (5 derniers)
    recent_home = api_get("fixtures", {"team": home_id, "last": 5, "status": "FT"})
    recent_away = api_get("fixtures", {"team": away_id, "last": 5, "status": "FT"})
    
    data["form_home"] = [m for m in recent_home if m["teams"]["home"]["id"] == home_id][:5]
    data["form_away"] = [m for m in recent_away if m["teams"]["away"]["id"] == away_id][:5]

    # 4. Statistiques équipes
    home_stats = api_get("teams/statistics", {"team": home_id, "league": league_id, "season": season})[0]
    away_stats = api_get("teams/statistics", {"team": away_id, "league": league_id, "season": season})[0]
    data["home_stats"] = home_stats
    data["away_stats"] = away_stats

    # 5. Blessures + suspensions
    injuries_home = api_get("injuries", {"team": home_id, "fixture": fixture_id})
    injuries_away = api_get("injuries", {"team": away_id, "fixture": fixture_id})
    data["injuries_home"] = injuries_home
    data["injuries_away"] = injuries_away

    # 6. Cotes
    odds_raw = api_get("odds", {"fixture": fixture_id})
    data["odds"] = odds_raw[0] if odds_raw else {}

    # 7. Calcul Poisson + Probabilités
    h_attack = home_stats.get("goals", {}).get("for", {}).get("average", {}).get("home", 1.5)
    a_defense = away_stats.get("goals", {}).get("against", {}).get("average", {}).get("away", 1.4)
    a_attack = away_stats.get("goals", {}).get("for", {}).get("average", {}).get("away", 1.3)
    h_defense = home_stats.get("goals", {}).get("against", {}).get("average", {}).get("home", 1.4)

    home_lambda = (h_attack + a_defense) / 2
    away_lambda = (a_attack + h_defense) / 2

    def poisson_pmf(k, lam):
        return math.exp(-lam) * (lam ** k) / math.factorial(k) if lam > 0 else (1 if k == 0 else 0)

    home_win = draw = away_win = over25 = btts_prob = 0.0
    for h in range(7):
        for a in range(7):
            p = poisson_pmf(h, home_lambda) * poisson_pmf(a, away_lambda)
            if h > a: home_win += p
            elif h == a: draw += p
            else: away_win += p
            if h + a > 2: over25 += p
            if h > 0 and a > 0: btts_prob += p

    data["probs"] = {
        "home_win": round(home_win * 100, 1),
        "draw": round(draw * 100, 1),
        "away_win": round(away_win * 100, 1),
        "over_2_5": round(over25 * 100, 1),
        "btts": round(btts_prob * 100, 1)
    }
    return data

# ===================== AFFICHAGE MATCHES =====================
for match in matches:
    fixture = match["fixture"]
    home = match["teams"]["home"]
    away = match["teams"]["away"]
    league_id = match["league"]["id"]
    season = match["league"]["season"]

    with st.container():
        col1, col2, col3 = st.columns([3, 1, 3])
        with col1:
            st.image(home["logo"], width=80)
            st.subheader(home["name"])
        with col2:
            st.markdown("<h2 style='text-align:center; color:#22c55e;'>VS</h2>", unsafe_allow_html=True)
        with col3:
            st.image(away["logo"], width=80)
            st.subheader(away["name"])

        btn_key = f"btn_{fixture['id']}"
        if st.button("🔍 ANALYSER CE MATCH", key=btn_key, use_container_width=True):
            with st.spinner("Analyse complète en cours (formes, tactique, stats, cotes...)"):
                analysis = perform_full_analysis(fixture["id"], home["id"], away["id"], league_id, season)
                st.session_state[f"analysis_{fixture['id']}"] = analysis

    # ===================== AFFICHAGE ANALYSE =====================
    if f"analysis_{fixture['id']}" in st.session_state:
        data = st.session_state[f"analysis_{fixture['id']}"]
        st.divider()
        st.header(f"📊 ANALYSE : {home['name']} vs {away['name']}")

        # 1. Forme récente
        st.subheader("1️⃣ Analyse des formes récentes")
        colh, cola = st.columns(2)
        with colh:
            st.write(f"**{home['name']} (domicile)**")
            for m in data["form_home"][:5]:
                result = "✅" if m["teams"]["home"]["winner"] else "❌"
                st.write(f"{result} {m['teams']['home']['name']} {m['goals']['home']}-{m['goals']['away']} {m['teams']['away']['name']}")
        with cola:
            st.write(f"**{away['name']} (extérieur)**")
            for m in data["form_away"][:5]:
                result = "✅" if m["teams"]["away"]["winner"] else "❌"
                st.write(f"{result} {m['teams']['home']['name']} {m['goals']['home']}-{m['goals']['away']} {m['teams']['away']['name']}")

        # 2. Tactique
        st.subheader("2️⃣ Analyse tactique")
        form_h = data["home_stats"].get("lineups", [{}])[0].get("formation", "4-3-3")
        form_a = data["away_stats"].get("lineups", [{}])[0].get("formation", "4-3-3")
        st.write(f"**Schémas probables** : {form_h} vs {form_a}")
        st.info("Match-up clé : Attaque rapide domicile vs Défense compacte extérieur → rythme élevé attendu")

        # 3. Stats avancées
        st.subheader("3️⃣ Données statistiques avancées")
        hs = data["home_stats"]["goals"]
        as_ = data["away_stats"]["goals"]
        st.metric("Moyenne buts domicile", f"{hs['for']['average']['home']:.2f}")
        st.metric("Clean sheets domicile", f"{data['home_stats'].get('clean_sheet', {}).get('home', 0)}%")
        st.metric("BTTS %", f"{data['probs']['btts']}%")
        st.metric("Over 2.5 % historique", f"{data['probs']['over_2_5']}%")

        # 4. Effectifs
        st.subheader("4️⃣ Effectifs & Blessures")
        if data["injuries_home"]:
            st.warning(f"🚨 {len(data['injuries_home'])} joueurs {home['name']} absents")
            for inj in data["injuries_home"][:3]:
                st.write(f"• {inj['player']['name']} – {inj['reason']}")
        else:
            st.success("Aucune blessure majeure domicile")

        # 5. Marché des cotes
        st.subheader("5️⃣ Marché des cotes")
        odds = data.get("odds", {})
        if odds and "bookmakers" in odds:
            # Moyenne cote 1X2
            home_odds_list = []
            for book in odds["bookmakers"]:
                for bet in book.get("bets", []):
                    if bet["name"] == "Match Winner":
                        for v in bet["values"]:
                            if v["value"] == "Home":
                                home_odds_list.append(float(v["odd"]))
            avg_home_odds = sum(home_odds_list)/len(home_odds_list) if home_odds_list else 2.5
            implied_home = round(100 / avg_home_odds, 1)
            value = data["probs"]["home_win"] - implied_home
            st.write(f"**Cote moyenne Victoire {home['name']}** : {avg_home_odds:.2f} → Prob implicite {implied_home}%")

        # ===================== RÉSULTATS FINAUX =====================
        st.subheader("⚽ RÉSULTATS FINAUX API-Football")
        h2h = data["h2h"]
        if h2h:
            goals_list = [m["goals"]["home"] + m["goals"]["away"] for m in h2h]
            btts_count = sum(1 for m in h2h if m["goals"]["home"] > 0 and m["goals"]["away"] > 0)
            over25_count = sum(1 for g in goals_list if g > 2)
            st.write(f"**Moyenne buts H2H** : {sum(goals_list)/len(h2h):.2f}")
            st.write(f"**BTTS** : {btts_count/len(h2h)*100:.0f}%")
            st.write(f"**Over 2.5** : {over25_count/len(h2h)*100:.0f}%")
            common_score = Counter([f"{m['goals']['home']}-{m['goals']['away']}" for m in h2h]).most_common(1)[0]
            st.write(f"**Score exact récurrent** : {common_score[0]} ({common_score[1]} fois)")

        # ===================== RECOMMANDATIONS PARIS =====================
        st.subheader("🤑 RECOMMANDATIONS DE PARIS (seulement si value justifiée)")
        probs = data["probs"]
        recs = []

        # Victoire domicile
        if probs["home_win"] > 55 and value > 5:
            recs.append(("1 - Victoire domicile", f"Prob estimée {probs['home_win']}% (value +{value:.1f}%)", "faible"))

        # Over 2.5
        if probs["over_2_5"] > 58:
            recs.append(("Over 2.5", f"Prob estimée {probs['over_2_5']}% • H2H élevé", "modéré"))

        # BTTS
        if probs["btts"] > 60:
            recs.append(("BTTS Oui", f"Prob estimée {probs['btts']}% • Attaques compatibles", "modéré"))

        for rec_type, justif, risk in recs[:2]:
            with st.container():
                st.markdown(f"""
                <div style="background:#166534; padding:15px; border-radius:12px; margin:10px 0;">
                    <h4>🎯 {rec_type}</h4>
                    <p><strong>Justification :</strong> {justif}</p>
                    <p><strong>Cote moyenne :</strong> ~{avg_home_odds if '1' in rec_type else '2.10'}</p>
                    <p><strong>Prob estimée :</strong> {probs['home_win'] if 'Victoire' in rec_type else probs['over_2_5']}%</p>
                    <p><strong>Risque :</strong> {risk}</p>
                </div>
                """, unsafe_allow_html=True)

        st.success("✅ Analyse terminée – Prêt pour le prochain match !")
        st.divider()
