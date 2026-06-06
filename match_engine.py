"""
Match Engine – Real 90-minute matches with PostgreSQL
"""
import random, threading, time, json, os, psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from contextlib import contextmanager

# Database connection helper
def get_db_conn():
    database_url = os.environ.get('DATABASE_URL')
    if database_url and database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    return psycopg2.connect(database_url, cursor_factory=RealDictCursor)

@contextmanager
def get_cursor():
    conn = get_db_conn()
    try:
        yield conn.cursor()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# League and team data (same as before)
LEAGUES = {
    'english': {
        'name': 'English League',
        'flag': '🏴󠁧󠁢󠁥󠁮󠁧󠁿',
        'teams': [
            ('ARS','Arsenal'),('AVL','Aston Villa'),('BHA','Brighton'),
            ('BOU','Bournemouth'),('BRE','Brentford'),('BUR','Burnley'),
            ('CHE','Chelsea'),('CRY','Crystal Palace'),('EVE','Everton'),
            ('FUL','Fulham'),('LEE','Leeds Utd'),('LEI','Leicester'),
            ('LIV','Liverpool'),('MCI','Man City'),('MUN','Man United'),
            ('NEW','Newcastle'),('NOT','Nott\'m Forest'),('SHU','Sheffield Utd'),
            ('SUN','Sunderland'),('TOT','Tottenham'),('WHU','West Ham'),
            ('WOL','Wolves'),('SOT','Southampton'),('LUT','Luton'),
        ]
    },
    'spanish': {
        'name': 'Spanish League',
        'flag': '🇪🇸',
        'teams': [
            ('ALM','Almeria'),('ATH','Athletic Bilbao'),('ATM','Atletico Madrid'),
            ('BAR','Barcelona'),('BET','Real Betis'),('CAD','Cadiz'),
            ('CEL','Celta Vigo'),('GET','Getafe'),('GIR','Girona'),
            ('GRA','Granada'),('LAS','Las Palmas'),('MAL','Mallorca'),
            ('OSA','Osasuna'),('RAY','Rayo Vallecano'),('RMA','Real Madrid'),
            ('RSO','Real Sociedad'),('SEV','Sevilla'),('VAL','Valencia'),
            ('VIL','Villarreal'),('ALV','Alaves'),
        ]
    },
    'italian': {
        'name': 'Italian League',
        'flag': '🇮🇹',
        'teams': [
            ('ATA','Atalanta'),('BOL','Bologna'),('CAG','Cagliari'),
            ('EMP','Empoli'),('FIO','Fiorentina'),('FRO','Frosinone'),
            ('GEN','Genoa'),('HEL','Hellas Verona'),('INT','Inter Milan'),
            ('JUV','Juventus'),('LAZ','Lazio'),('LEC','Lecce'),
            ('MIL','AC Milan'),('MON','Monza'),('NAP','Napoli'),
            ('ROM','Roma'),('SAL','Salernitana'),('SAS','Sassuolo'),
            ('TOR','Torino'),('UDI','Udinese'),
        ]
    }
}

PLAYERS = {
    'ARS':['Saka','Martinelli','Odegaard','Havertz','Trossard'],
    'LIV':['Salah','Nunez','Diaz','Szoboszlai','Mac Allister'],
    'MCI':['Haaland','De Bruyne','Foden','Doku','Bernardo'],
    'MUN':['Rashford','Fernandes','Hojlund','Antony','Mainoo'],
    'CHE':['Palmer','Jackson','Sterling','Mudryk','Gallagher'],
    'TOT':['Son','Richarlison','Maddison','Kulusevski','Bissouma'],
    'NEW':['Isak','Wilson','Almiron','Trippier','Joelinton'],
    'BHA':['Mitoma','Welbeck','Gross','March','Baleba'],
    'RMA':['Vinicius','Bellingham','Rodrygo','Valverde','Kroos'],
    'BAR':['Yamal','Lewandowski','Pedri','Gavi','Raphinha'],
    'ATM':['Griezmann','Morata','Correa','Felix','Llorente'],
    'JUV':['Vlahovic','Chiesa','Kean','Yildiz','Kostic'],
    'INT':['Lautaro','Thuram','Calhanoglu','Barella','Dimarco'],
    'MIL':['Giroud','Leao','Pulisic','Theo','Reijnders'],
    'NAP':['Osimhen','Kvaratskhelia','Politano','Zielinski','Di Lorenzo'],
}

active_simulations = {}

def get_player(code):
    return random.choice(PLAYERS.get(code, ['Player A','Player B','Player C']))

# Odds generation (unchanged)
def generate_odds(home_code, away_code):
    home_bias = random.uniform(0.35, 0.55)
    draw_prob  = random.uniform(0.22, 0.30)
    away_prob  = max(0.10, 1 - home_bias - draw_prob)
    mg = 1.08

    def o(p): return round(max(1.10, (1/p)/mg * mg), 2)

    h, d, a = o(home_bias), o(draw_prob), o(away_prob)

    ou = {
        'over_1.5':  round(random.uniform(1.08,1.25),2),
        'under_1.5': round(random.uniform(4.00,7.00),2),
        'over_2.5':  round(random.uniform(1.35,1.70),2),
        'under_2.5': round(random.uniform(2.20,2.90),2),
        'over_3.5':  round(random.uniform(2.00,2.60),2),
        'under_3.5': round(random.uniform(1.50,1.75),2),
    }
    btts = {'yes': round(random.uniform(1.45,1.75),2), 'no': round(random.uniform(1.90,2.50),2)}
    dc   = {
        '1X': round(max(1.05, 1/(home_bias+draw_prob)*0.93),2),
        'X2': round(max(1.05, 1/(draw_prob+away_prob)*0.93),2),
        '12': round(max(1.05, 1/(home_bias+away_prob)*0.93),2),
    }
    htft = {
        '1/1': round(random.uniform(1.90,3.20),2), '1/X': round(random.uniform(14,22),2),
        '1/2': round(random.uniform(40,65),2),      'X/1': round(random.uniform(4,6),2),
        'X/X': round(random.uniform(6.5,9),2),      'X/2': round(random.uniform(11,16),2),
        '2/1': round(random.uniform(22,35),2),       '2/X': round(random.uniform(18,26),2),
        '2/2': round(random.uniform(8,12),2),
    }
    cs = {}
    for hg in range(6):
        for ag in range(6):
            base = 6 + (hg+ag)*4 + abs(hg-ag)*2
            cs[f'{hg}-{ag}'] = round(random.uniform(base*0.8, base*1.3), 2)
    cs['other'] = round(random.uniform(55,80),2)

    return {'1x2':{'1':h,'X':d,'2':a}, 'ou':ou, 'btts':btts, 'dc':dc, 'htft':htft, 'cs':cs}

# Fixture generation
def make_pairs(league_key):
    teams = LEAGUES[league_key]['teams'].copy()
    random.shuffle(teams)
    pairs, used = [], set()
    for t in teams:
        if t[0] in used: continue
        for t2 in teams:
            if t2[0] not in used and t2[0] != t[0]:
                pairs.append((t, t2))
                used.add(t[0]); used.add(t2[0])
                break
        if len(pairs) == 10: break
    return pairs

def create_next_matchday(app):
    with app.app_context():
        with get_cursor() as cur:
            now = datetime.utcnow()
            base_offset = random.randint(3, 8)

            for league_key in LEAGUES:
                cur.execute(
                    "SELECT MAX(matchday_number) as mn FROM matchdays WHERE league=%s",
                    (league_key,)
                )
                row = cur.fetchone()
                next_num = (row['mn'] or 0) + 1

                league_base = now + timedelta(minutes=base_offset + random.randint(0,5))
                starts_at = league_base.strftime('%Y-%m-%d %H:%M:%S')
                
                cur.execute(
                    "INSERT INTO matchdays (matchday_number, league, starts_at) VALUES (%s,%s,%s) RETURNING id",
                    (next_num, league_key, starts_at)
                )
                md_id = cur.fetchone()['id']

                pairs = make_pairs(league_key)
                offset_mins = 0
                for (hcode, hname), (acode, aname) in pairs:
                    kickoff_dt = league_base + timedelta(minutes=offset_mins)
                    kickoff_str = kickoff_dt.strftime('%Y-%m-%d %H:%M:%S')
                    odds = generate_odds(hcode, acode)
                    cur.execute(
                        """INSERT INTO matches
                           (matchday_id,home_code,away_code,home_team,away_team,
                            league,odds_json,kickoff_time,preset_home,preset_away)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (md_id, hcode, acode, hname, aname,
                         league_key, json.dumps(odds), kickoff_str,
                         None, None)
                    )
                    offset_mins += random.randint(8, 20)

def build_goal_events(home_code, away_code, home_team, away_team,
                      target_home, target_away):
    total = target_home + target_away
    if total == 0:
        return []

    all_mins = sorted(random.sample(range(3, 90), min(total, 87)))
    while len(all_mins) < total:
        all_mins.append(random.randint(3, 89))
    all_mins = sorted(all_mins[:total])

    home_goals = target_home
    away_goals = target_away
    sides = ['home']*home_goals + ['away']*away_goals
    random.shuffle(sides)

    events = []
    for i, minute in enumerate(all_mins):
        side = sides[i]
        team = home_team if side == 'home' else away_team
        code = home_code if side == 'home' else away_code
        player = get_player(code)
        events.append({
            'minute': minute, 'type': 'goal', 'side': side,
            'desc': f'GOAL! {player} scores for {team}!', 'team': team
        })
    return events

def build_other_events(home_team, away_team, home_code, away_code):
    events = []
    for m in sorted(random.sample(range(2,90), random.randint(6,14))):
        team = random.choice([home_team, away_team])
        events.append({'minute':m,'type':'corner','desc':f'Corner for {team}','team':team})
    for m in sorted(random.sample(range(5,90), random.randint(2,6))):
        team = random.choice([home_team, away_team])
        code = home_code if team==home_team else away_code
        p = get_player(code)
        events.append({'minute':m,'type':'yellow_card','desc':f'Yellow card: {p} ({team})','team':team})
    if random.random() < 0.10:
        m = random.randint(35,88)
        team = random.choice([home_team, away_team])
        code = home_code if team==home_team else away_code
        p = get_player(code)
        events.append({'minute':m,'type':'red_card','desc':f'Red card! {p} sent off!','team':team})
    return events

def simulate_match(match_id):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM matches WHERE id=%s", (match_id,))
        m = cur.fetchone()
        if not m:
            return
        
        home_team = m['home_team']
        away_team = m['away_team']
        home_code = m['home_code']
        away_code = m['away_code']

        if m['preset_home'] is not None and m['preset_away'] is not None:
            target_home = int(m['preset_home'])
            target_away = int(m['preset_away'])
        else:
            target_home = random.choices([0,1,2,3,4,5], weights=[15,30,28,15,8,4])[0]
            target_away = random.choices([0,1,2,3,4,5], weights=[18,30,26,14,8,4])[0]

        cur.execute(
            "UPDATE matches SET status='live',current_minute=0,home_score=0,away_score=0 WHERE id=%s",
            (match_id,)
        )

    goal_events = build_goal_events(home_code, away_code, home_team, away_team,
                                    target_home, target_away)
    other_events = build_other_events(home_team, away_team, home_code, away_code)
    all_events = sorted(goal_events + other_events, key=lambda x: x['minute'])
    ev_idx = 0
    home_score = 0
    away_score = 0
    ht_home = 0
    ht_away = 0

    for minute in range(1, 91):
        if not active_simulations.get(match_id, False):
            break

        time.sleep(1)

        with get_cursor() as cur:
            # Check for admin updates to preset score
            cur.execute("SELECT preset_home, preset_away FROM matches WHERE id=%s", (match_id,))
            row = cur.fetchone()
            if row and row['preset_home'] is not None:
                new_th = int(row['preset_home'])
                new_ta = int(row['preset_away'])
                if (new_th, new_ta) != (target_home, target_away):
                    target_home = new_th
                    target_away = new_ta
                    future_others = [e for e in all_events[ev_idx:] if e['type'] != 'goal']
                    remaining_home = max(0, target_home - home_score)
                    remaining_away = max(0, target_away - away_score)
                    new_goals = build_goal_events(
                        home_code, away_code, home_team, away_team,
                        remaining_home, remaining_away
                    )
                    if new_goals:
                        mins_left = list(range(minute+1, 90))
                        sample_size = min(len(new_goals), len(mins_left))
                        new_mins = sorted(random.sample(mins_left, sample_size)) if sample_size else []
                        for i, g in enumerate(new_goals[:len(new_mins)]):
                            g['minute'] = new_mins[i]
                    remaining = sorted(new_goals + future_others, key=lambda x: x['minute'])
                    all_events = all_events[:ev_idx] + remaining

            while ev_idx < len(all_events) and all_events[ev_idx]['minute'] <= minute:
                ev = all_events[ev_idx]
                cur.execute(
                    """INSERT INTO match_events
                       (match_id,minute,event_type,description,team,is_home)
                       VALUES (%s,%s,%s,%s,%s,%s)""",
                    (match_id, ev['minute'], ev['type'], ev['desc'],
                     ev['team'], 1 if ev['team']==home_team else 0)
                )
                if ev['type'] == 'goal':
                    if ev['side'] == 'home':
                        home_score += 1
                    else:
                        away_score += 1
                ev_idx += 1

            if minute == 45:
                ht_home, ht_away = home_score, away_score
                cur.execute("UPDATE matches SET ht_home=%s,ht_away=%s WHERE id=%s",
                           (ht_home, ht_away, match_id))

            cur.execute(
                "UPDATE matches SET current_minute=%s,home_score=%s,away_score=%s WHERE id=%s",
                (minute, home_score, away_score, match_id)
            )

    # Full Time
    with get_cursor() as cur:
        cur.execute(
            "UPDATE matches SET status='finished',current_minute=90,home_score=%s,away_score=%s WHERE id=%s",
            (home_score, away_score, match_id)
        )
        settle_match_bets(cur, match_id, home_score, away_score, ht_home, ht_away)

    active_simulations.pop(match_id, None)

def settle_match_bets(cur, match_id, hs, as_, ht_h, ht_a):
    cur.execute(
        "SELECT * FROM bet_selections WHERE match_id=%s AND result='pending'",
        (match_id,)
    )
    sels = cur.fetchall()
    
    for sel in sels:
        won = eval_market(sel['market'], sel['selection'], hs, as_, ht_h, ht_a)
        cur.execute("UPDATE bet_selections SET result=%s WHERE id=%s",
                   ('won' if won else 'lost', sel['id']))

    for bid in set(s['bet_id'] for s in sels):
        cur.execute("SELECT result FROM bet_selections WHERE bet_id=%s", (bid,))
        all_s = cur.fetchall()
        if any(s['result'] == 'pending' for s in all_s):
            continue
        if all(s['result'] == 'won' for s in all_s):
            cur.execute("SELECT * FROM bets WHERE id=%s", (bid,))
            bet = cur.fetchone()
            cur.execute("UPDATE bets SET status='won',settled_at=CURRENT_TIMESTAMP WHERE id=%s", (bid,))
            cur.execute("UPDATE users SET balance=balance+%s WHERE id=%s",
                       (bet['potential_win'], bet['user_id']))
            cur.execute(
                "INSERT INTO transactions (user_id,type,amount,status,note) VALUES (%s,%s,%s,%s,%s)",
                (bet['user_id'], 'winnings', bet['potential_win'], 'confirmed', f'Bet #{bid} won')
            )
        else:
            cur.execute("UPDATE bets SET status='lost',settled_at=CURRENT_TIMESTAMP WHERE id=%s", (bid,))

def eval_market(market, selection, hs, as_, ht_h, ht_a):
    total = hs + as_
    if market == '1x2':
        return {'1': hs>as_, 'X': hs==as_, '2': as_>hs}.get(selection, False)
    elif market == 'ou':
        line = float(selection.split('_')[1])
        return (total > line) if selection.startswith('over') else (total < line)
    elif market == 'btts':
        return (hs>0 and as_>0) if selection=='yes' else not(hs>0 and as_>0)
    elif market == 'dc':
        return {'1X': hs>=as_, 'X2': as_>=hs, '12': hs!=as_}.get(selection, False)
    elif market == 'htft':
        ht = '1' if ht_h>ht_a else ('X' if ht_h==ht_a else '2')
        ft = '1' if hs>as_ else ('X' if hs==as_ else '2')
        return selection == f'{ht}/{ft}'
    elif market == 'cs':
        return selection == f'{hs}-{as_}'
    return False

def start_single_match(match_id):
    active_simulations[match_id] = True
    t = threading.Thread(target=simulate_match, args=(match_id,), daemon=True)
    t.start()

def scheduler_loop(app):
    time.sleep(4)
    while True:
        try:
            with get_cursor() as cur:
                now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
                
                cur.execute(
                    """SELECT * FROM matches
                       WHERE status='upcoming' AND kickoff_time <= %s""",
                    (now_str,)
                )
                due = cur.fetchall()
                
                for m in due:
                    cur.execute("UPDATE matches SET status='live' WHERE id=%s", (m['id'],))
                    cur.execute(
                        "UPDATE matchdays SET status='live' WHERE id=%s AND status='upcoming'",
                        (m['matchday_id'],)
                    )
                    start_single_match(m['id'])
                
                cur.execute("SELECT id FROM matchdays WHERE status='live'")
                live_mds = cur.fetchall()
                for md in live_mds:
                    cur.execute(
                        "SELECT COUNT(*) as c FROM matches WHERE matchday_id=%s AND status!='finished'",
                        (md['id'],)
                    )
                    pending = cur.fetchone()['c']
                    if pending == 0:
                        cur.execute("UPDATE matchdays SET status='finished' WHERE id=%s", (md['id'],))
                
                cur.execute("SELECT COUNT(*) as c FROM matchdays WHERE status='upcoming'")
                upcoming_count = cur.fetchone()['c']
                
            if upcoming_count < 2:
                with app.app_context():
                    create_next_matchday(app)
                    
        except Exception as e:
            print(f"Scheduler error: {e}")
        
        time.sleep(15)

def start_scheduler(app):
    t = threading.Thread(target=scheduler_loop, args=(app,), daemon=True)
    t.start()

def admin_set_score(match_id, home, away):
    with get_cursor() as cur:
        cur.execute(
            "UPDATE matches SET preset_home=%s, preset_away=%s WHERE id=%s",
            (home, away, match_id)
        )

def admin_force_start(match_id):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM matches WHERE id=%s", (match_id,))
        m = cur.fetchone()
        if m and m['status'] == 'upcoming':
            cur.execute(
                "UPDATE matches SET status='live', kickoff_time=CURRENT_TIMESTAMP WHERE id=%s",
                (match_id,)
            )
            cur.execute(
                "UPDATE matchdays SET status='live' WHERE id=%s AND status='upcoming'",
                (m['matchday_id'],)
            )
            start_single_match(match_id)

def admin_force_finish(match_id):
    active_simulations[match_id] = False
    time.sleep(1.2)
    with get_cursor() as cur:
        cur.execute("SELECT * FROM matches WHERE id=%s", (match_id,))
        m = cur.fetchone()
        if m:
            cur.execute(
                "UPDATE matches SET status='finished',current_minute=90 WHERE id=%s",
                (match_id,)
            )
            settle_match_bets(cur, match_id,
                            m['home_score'], m['away_score'],
                            m['ht_home'], m['ht_away'])