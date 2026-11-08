import streamlit as st
import pandas as pd
import random
import os
import math
import re
import difflib

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="Trivia Night",
    page_icon="🎯",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# --- STYLING (Dark Theme CSS) ---
st.markdown("""
<style>
    .stApp {
        background-color: #111827;
        color: #F9FAFB;
    }
    .card {
        background-color: #1F2937;
        padding: 20px;
        border-radius: 10px;
        margin-bottom: 20px;
    }
    .gold-header {
        color: #FBBF24;
        font-weight: 800;
        text-align: center;
    }
    .score-box {
        background-color: #374151;
        padding: 10px;
        border-radius: 8px;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# --- CONFIGURATION ---
SHEET_NAME = "Trivia"
MC_ROUNDS = ((1, 5), (2, 10), (3, 20))
FIB_ROUND = (4, 40)
QUESTIONS_PER_ROUND = 4
DD_THRESHOLD = 0.78
FIB_THRESHOLD = 0.82

STOP = frozenset("""a an the of in on at to for and or is are was were be been it its this that these those
what which who whom whose when where why how with as by from into than then there their they he she his her
him you your we our not no do does did has have had can could would should will shall may might one two
name called known better term word most first last also only many much any some all both each other""".split())
ARTICLES = frozenset(("the", "a", "an"))
NUMWORDS = {w: str(i) for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve "
    "thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}
SMALL_WORDS = frozenset("of the and a an in on at to for de la von van".split())
VAGUE_ANSWERS = frozenset(("yes", "no", "true", "false", "none", "nothing", "all", "both", "nan"))
CAT_ALIASES = {"tech & video games": "Technology & Video Games", "mathematics & geometry": "Mathematics"}
GENERIC_CATS = {"", "general", "nan", "none", "misc", "other"}

CAT_KEYWORDS = {
    "Music": "song songs album albums band singer sang singing guitar piano violin orchestra opera symphony beatles rapper lyrics concert composer drummer grammy billboard melody musical jazz bassist vocalist trumpet saxophone",
    "Geography": "capital country countries river mountain mountains island islands ocean lake continent border desert sea currency peninsula bay population province volcano canyon strait gulf",
    "Science & Nature": "element atom atoms chemical planet species animal animals bird birds mammal plant tree flower gas bone bones blood disease gene cell cells moon star galaxy physics biology fish insect insects temperature energy vitamin organ acid mineral metal reptile dinosaur",
    "History & Holidays": "war king queen emperor president century battle empire revolution ancient treaty christmas easter halloween thanksgiving holiday independence assassinated dynasty pharaoh roman medieval civil colony colonial",
    "Sports & Leisure": "football baseball basketball soccer tennis golf olympic olympics nfl nba boxing cricket rugby hockey wimbledon marathon athlete medal stadium champion racing swimming skating quarterback touchdown",
    "Food & Drink": "food dish cheese wine beer cocktail recipe ingredient cuisine fruit vegetable sauce chocolate coffee tea bread pasta spice soup cooked whisky vodka restaurant eaten drink dessert",
    "Entertainment": "film films movie movies actor actress tv television sitcom oscar director hollywood episode cartoon starring broadway disney sequel",
    "Art & Literature": "novel novels author poet poem poems painter painting paintings artist sculptor wrote playwright shakespeare literature museum gallery sculpture",
    "Religion & Mythology": "god gods goddess bible biblical mythology myth church pope saint temple zeus jesus apostle prophet angel heaven hindu buddhist islam jewish mythological",
    "Toys & Games": "toy toys chess monopoly lego dice puzzle poker doll scrabble cluedo",
    "Technology & Video Games": "computer software internet nintendo playstation xbox console smartphone website programming microsoft google robot arcade",
    "Language": "spelled spelling language latin translates synonym grammar alphabet pronounced idiom vocabulary",
    "Mathematics": "square root triangle angle equation fraction geometry algebra percent hexagon polygon multiply integer",
}
CAT_KW = {c: frozenset(w.split()) for c, w in CAT_KEYWORDS.items()}

# --- HELPER FUNCTIONS ---
def clean(x):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return ""
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return re.sub(r"\s+", " ", str(x).replace("\xa0", " ")).strip()

def strip_accents(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))

def norm(s):
    s = strip_accents(s).lower().replace("&", " and ")
    s = s.replace("'", "").replace("’", "")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return " ".join(NUMWORDS.get(t, t) for t in s.split() if t not in ARTICLES)

def tokens(s):
    return frozenset(t for t in norm(s).split() if t not in STOP and len(t) > 2)

def pretty_answer(a):
    if a and (a.islower() or a.isupper() or a == a.capitalize()):
        words = a.split(" ")
        out = []
        for i, w in enumerate(words):
            lw = w.lower()
            out.append(lw if (i and lw in SMALL_WORDS) else re.sub(r"(^|[-/])([a-z])", lambda m: m.group(1) + m.group(2).upper(), lw))
        return " ".join(out)
    return a

def pretty_question(q):
    return q[:1].upper() + q[1:] if q else q

def is_close(guess, answer, threshold=DD_THRESHOLD):
    g = norm(guess)
    if not g:
        return False
    alts = [answer] + re.split(r"\s+or\s+|/|;", answer) if re.search(r"\sor\s|/|;", answer) else [answer]
    for alt in alts:
        a = norm(alt)
        if not a:
            continue
        gc, ac = g.replace(" ", ""), a.replace(" ", "")
        if g == a or gc == ac:
            return True
        if ac.isdigit() or gc.isdigit() or len(ac) <= 4:
            continue
        if difflib.SequenceMatcher(None, gc, ac).ratio() >= threshold:
            return True
        gt, at = g.split(), a.split()
        if sorted(gt) == sorted(at):
            return True
        if len(at) >= 2 and len(gt) <= len(at) + 1 and all(
                any(difflib.SequenceMatcher(None, w, x).ratio() >= max(threshold, .8) for x in gt)
                for w in at if w not in STOP):
            return True
    return False

def normalise_category(raw):
    c = clean(raw)
    return CAT_ALIASES.get(c.lower(), c)

def infer_category(question):
    toks = set(re.findall(r"[a-z]+", question.lower()))
    toks |= {t[:-1] for t in toks if t.endswith("s")}
    scores = sorted(((len(toks & kws), cat) for cat, kws in CAT_KW.items()), reverse=True)
    (top, best), (second, _) = scores[0], scores[1]
    return best if top >= 2 and top > second else "General"

NUM_RE = re.compile(r"^([$£€]?)(\d[\d,]*\.?\d*|\.\d+)(%?)$")
BAD_Q = re.compile(r"\b(either|any of|name two|name three|name the two|following|above|below|picture|pictured)\b", re.I)
BAD_A = re.compile(r"[;()\[\]{}:?\"]|\s/\s|\sor\s|\*")

def answer_shape(a):
    m = NUM_RE.match(a)
    if not m:
        return "txt", 0.0
    val = float(m.group(2).replace(",", ""))
    kind = "year" if (re.fullmatch(r"\d{4}", m.group(2)) and 1000 <= val <= 2100) else "num"
    return kind + m.group(1) + m.group(3), val

class Bank:
    def __init__(self, uploaded_file):
        self.entries = []
        self.load(uploaded_file)
        self._index()

    def load(self, path):
        raw = pd.read_excel(path, sheet_name=SHEET_NAME, header=None, dtype=object)
        header = [clean(h).lower() for h in raw.iloc[0].tolist()]
        starts = [i for i, h in enumerate(header) if h == "category" and i + 2 < len(header)
                  and header[i + 1] == "question" and header[i + 2] == "answer"]
        if not starts:
            raise ValueError("Could not find 'Category / Question / Answer' columns on the Trivia tab.")
        seen_q = set()
        for s in starts:
            block = raw.iloc[1:, s:s + 3].values.tolist()
            for cat_raw, q_raw, a_raw in block:
                q, a = clean(q_raw), clean(a_raw)
                if q.startswith('"') and q.endswith('"') and '""' in q:
                    q = q[1:-1].replace('""', '"')
                if len(q) < 12 or not a:
                    continue
                qn = norm(q)
                if qn in seen_q:
                    continue
                seen_q.add(qn)
                cat = normalise_category(cat_raw)
                if cat.lower() in GENERIC_CATS or cat.lower().startswith("question needs"):
                    cat = infer_category(q)
                self._add(cat, q, a, qn)

    def _add(self, cat, q, a, qn):
        a_disp = pretty_answer(a)
        an = norm(a_disp)
        if not an or an in VAGUE_ANSWERS or BAD_A.search(a_disp) or len(a_disp) > 34:
            return
        if len(an) >= 3 and re.search(r"\b" + re.escape(an) + r"\b", qn):
            return
        words = len(a_disp.split())
        shape, val = answer_shape(a_disp)
        e = type('Entry', (), {
            'i': len(self.entries), 'cat': cat, 'q': pretty_question(q), 'a': a_disp,
            'qn': qn, 'an': an, 'toks': tokens(q), 'shape': shape, 'value': val,
            'qtype': "other"
        })()
        e.mc = words <= 5 and 18 <= len(q) <= 170 and not q.endswith(":")
        e.fib = (words <= 3 and len(a_disp) <= 24 and 22 <= len(q) <= 150 and not BAD_Q.search(q)
                 and bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .'&\-]*", a_disp)) and " and " not in a_disp.lower())
        if e.mc or e.fib:
            self.entries.append(e)

    def _index(self):
        self.by_cat = {"mc": {}, "fib": {}}
        self.tok_index = {}
        self.by_shape = {}
        for e in self.entries:
            if e.mc:
                self.by_cat["mc"].setdefault(e.cat, []).append(e.i)
                self.by_shape.setdefault(e.shape, []).append(e.i)
                for t in e.toks:
                    self.tok_index.setdefault(t, []).append(e.i)
            if e.fib:
                self.by_cat["fib"].setdefault(e.cat, []).append(e.i)
        self.cat_list = {k: [c for c, v in d.items() if len(v) >= 10] for k, d in self.by_cat.items()}
        if not self.cat_list['mc']:
            self.cat_list = {k: list(d.keys()) for k, d in self.by_cat.items()}

    def _draw(self, kind, used, avoid=()):
        cats = [c for c in self.cat_list[kind] if c not in avoid] or self.cat_list[kind]
        for _ in range(400):
            pool = self.by_cat[kind][random.choice(cats)]
            e = self.entries[random.choice(pool)]
            if e.i in used or ("a", e.an) in used:
                continue
            used.update((e.i, ("a", e.an)))
            return e
        raise RuntimeError("Not enough usable questions in the workbook.")

    def new_game(self):
        used, steps = set(), []
        pic_round = random.choice([1, 2, 3])
        for rnd, pts in MC_ROUNDS:
            cats = set()
            for n in range(QUESTIONS_PER_ROUND):
                e = self._draw("mc", used, cats)
                cats.add(e.cat)
                opts = [e.a] + self.distractors(e, 3)
                random.shuffle(opts)
                steps.append({'kind': 'mc', 'round': rnd, 'pts': pts, 'e': e, 'options': opts, 'first': (n == 0)})
            steps.append({'kind': 'dd', 'round': rnd, 'pts': 0, 'e': self._draw("fib", used), 'pic': (rnd == pic_round)})
        rnd, pts = FIB_ROUND
        cats = set()
        for n in range(QUESTIONS_PER_ROUND):
            e = self._draw("fib", used, cats)
            cats.add(e.cat)
            steps.append({'kind': 'fib', 'round': rnd, 'pts': pts, 'e': e, 'first': (n == 0), 'threshold': FIB_THRESHOLD})
        steps.append({'kind': 'final', 'round': 5, 'pts': 0, 'e': self._draw("fib", used)})
        return steps

    def distractors(self, e, k=3):
        cand = set()
        for t in e.toks:
            lst = self.tok_index.get(t)
            if lst:
                cand.update(lst if len(lst) <= 40 else random.sample(lst, 40))
        same_cat = self.by_cat["mc"].get(e.cat, [])
        cand.update(random.sample(same_cat, min(250, len(same_cat))))
        cand.discard(e.i)
        top, picked_an = [], []
        for ci in cand:
            c = self.entries[ci]
            if c.shape != e.shape or c.an in picked_an or c.an == e.an:
                continue
            top.append(c.a)
            picked_an.append(c.an)
            if len(top) >= 8:
                break
        out = random.sample(top, min(k, len(top)))
        while len(out) < k:
            out.append("Alternative " + str(random.randint(10, 99)))
        return out

# --- SESSION STATE INITIALIZATION ---
if 'game_state' not in st.session_state:
    st.session_state.game_state = 'WELCOME'
    st.session_state.bank = None
    st.session_state.steps = []
    st.session_state.step_idx = 0
    st.session_state.score = 0
    st.session_state.round_pts = 0
    st.session_state.report = {}
    st.session_state.feedback = None

# --- UI VIEWS ---

if st.session_state.game_state == 'WELCOME':
    st.markdown("<h1 class='gold-header'>🎯 TRIVIA NIGHT</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #9CA3AF;'>DJ Trivia style mobile-friendly web app</p>", unsafe_allow_html=True)
    
    with st.container():
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("### Game Rules")
        st.markdown("* **Rounds 1–3:** 4 Multiple Choice questions each (5, 10, 20 pts).")
        st.markdown("* **Double Down:** After each round, risk your points or pass safely.")
        st.markdown("* **Round 4:** 4 Fill-in-the-blank questions (40 pts each).")
        st.markdown("* **Final Showdown:** Double your entire score or lose it all!")
        st.markdown("</div>", unsafe_allow_html=True)
        
    excel_path = "Trivia Questions.xlsx"
    
    if os.path.exists(excel_path):
        try:
            if st.session_state.bank is None:
                st.session_state.bank = Bank(excel_path)
            
            st.success(f"Successfully loaded {len(st.session_state.bank.entries):,} questions from cloud storage!")
            
            if st.button("START GAME", type="primary", use_container_width=True):
                st.session_state.steps = st.session_state.bank.new_game()
                st.session_state.step_idx = 0
                st.session_state.score = 0
                st.session_state.round_pts = 0
                st.session_state.report = {}
                st.session_state.game_state = 'PLAYING'
                st.rerun()
        except Exception as e:
            st.error(f"Error loading workbook: {e}")
    else:
        st.error(f"Could not find '{excel_path}' in the repository. Please make sure it is uploaded to your GitHub folder alongside app.py.")

elif st.session_state.game_state == 'PLAYING':
    steps = st.session_state.steps
    idx = st.session_state.step_idx
    
    if idx >= len(steps):
        st.session_state.game_state = 'GAMEOVER'
        st.rerun()
        
    st.sidebar.metric("Current Score", st.session_state.score)
    st.progress(idx / len(steps))
    
    st_item = steps[idx]
    
    if st_item['first'] and st_item['kind'] in ('mc', 'fib') and 'intro_shown' not in st_item:
        st_item['intro_shown'] = True
        st.session_state.round_pts = 0
        st.markdown(f"<h1 class='gold-header'>ROUND {st_item['round']}</h1>", unsafe_allow_html=True)
        kind_name = "Multiple Choice" if st_item['kind'] == 'mc' else "Fill-in-the-Blank"
        st.markdown(f"<p style='text-align: center;'>{kind_name} • {st_item['pts']} Points per Question</p>", unsafe_allow_html=True)
        if st.button("Continue to Round", type="primary", use_container_width=True):
            st.rerun()
        st.stop()

    st.markdown(f"**Category:** `{st_item['e'].cat.upper()}`")
    
    if st_item['kind'] == 'mc':
        n = sum(1 for s in steps[:idx + 1] if s['kind'] == 'mc' and s['round'] == st_item['round'])
        st.markdown(f"### Round {st_item['round']} • Question {n}/{QUESTIONS_PER_ROUND} ({st_item['pts']} pts)")
        st.markdown(f"<div class='card'><h4>{st_item['e'].q}</h4></div>", unsafe_allow_html=True)
        
        for opt in st_item['options']:
            if st.button(opt, use_container_width=True):
                ok = (opt == st_item['e'].a)
                if ok:
                    st.session_state.score += st_item['pts']
                    st.session_state.round_pts += st_item['pts']
                st.session_state.feedback = {'ok': ok, 'correct': st_item['e'].a, 'chosen': opt, 'pts': st_item['pts'] if ok else 0}
                st.session_state.game_state = 'FEEDBACK'
                st.rerun()

    elif st_item['kind'] == 'fib' or st_item['kind'] == 'final':
        is_final = (st_item['kind'] == 'final')
        title = "FINAL SHOWDOWN" if is_final else f"Round 4 • Fill in the Blank ({st_item['pts']} pts)"
        st.markdown(f"### {title}")
        if is_final:
            st.warning(f"Everything on the line! Your current score: {st.session_state.score}")
            
        st.markdown(f"<div class='card'><h4>{st_item['e'].q}</h4></div>", unsafe_allow_html=True)
        
        with st.form(key=f"fib_form_{idx}"):
            user_ans = st.text_input("Type your answer:")
            submitted = st.form_submit_button("Submit Answer", use_container_width=True)
            if submitted:
                if not user_ans.strip():
                    st.warning("Please type an answer.")
                else:
                    ok = is_close(user_ans, st_item['e'].a, FIB_THRESHOLD)
                    if is_final:
                        before = st.session_state.score
                        st.session_state.score = before * 2 if ok else 0
                        delta = f"Score doubled to {st.session_state.score}" if ok else "Score dropped to 0"
                    else:
                        if ok:
                            st.session_state.score += st_item['pts']
                            st.session_state.round_pts += st_item['pts']
                        delta = f"+{st_item['pts']} points" if ok else "+0 points"
                        
                    st.session_state.feedback = {'ok': ok, 'correct': st_item['e'].a, 'chosen': user_ans, 'pts_text': delta}
                    st.session_state.game_state = 'FEEDBACK'
                    st.rerun()

    elif st_item['kind'] == 'dd':
        risk = st.session_state.round_pts
        st.markdown(f"### ⚡ DOUBLE DOWN (After Round {st_item['round']})")
        st.markdown(f"<div class='score-box'><b>Points at stake: {risk}</b><br>Right: +{risk} (Doubled) | Wrong: -{risk} | Pass: Keep points safe</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='card'><h4>{st_item['e'].q}</h4></div>", unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🛡️ PASS (Keep Safe)", use_container_width=True):
                st.session_state.report[st_item['round']] = f"Passed (kept {risk})"
                st.session_state.feedback = {'ok': None, 'correct': st_item['e'].a, 'chosen': 'Passed', 'pts_text': f"Kept {risk} points"}
                st.session_state.game_state = 'FEEDBACK'
                st.rerun()
        with col2:
            pass_dd = st.button("🔥 RISK IT (Double Down)", type="primary", use_container_width=True)
            
        user_dd_ans = st.text_input("Type your answer (Required if risking):")
        if pass_dd:
            if not user_dd_ans.strip():
                st.warning("Type an answer to risk points, or click Pass.")
            else:
                ok = is_close(user_dd_ans, st_item['e'].a, DD_THRESHOLD)
                rep = st.session_state.report.setdefault(st_item['round'], {})
                if ok:
                    st.session_state.score += risk
                    delta = f"+{risk} bonus points"
                else:
                    st.session_state.score -= risk
                    delta = f"-{risk} points"
                st.session_state.feedback = {'ok': ok, 'correct': st_item['e'].a, 'chosen': user_dd_ans, 'pts_text': delta}
                st.session_state.game_state = 'FEEDBACK'
                st.rerun()

elif st.session_state.game_state == 'FEEDBACK':
    fb = st.session_state.feedback
    if fb['ok'] is True:
        st.success("### Correct! 🎉")
    elif fb['ok'] is False:
        st.error("### Not Quite! ❌")
    else:
        st.info("### Round Safe")
        
    st.markdown(f"**Correct Answer:** {fb['correct']}")
    if 'chosen' in fb:
        st.markdown(f"**Your Answer:** {fb['chosen']}")
    if 'pts_text' in fb:
        st.markdown(f"**Result:** {fb['pts_text']}")
        
    if st.button("Continue", type="primary", use_container_width=True):
        st.session_state.step_idx += 1
        st.session_state.game_state = 'PLAYING'
        st.rerun()

elif st.session_state.game_state == 'GAMEOVER':
    st.markdown("<h1 class='gold-header'>GAME OVER</h1>", unsafe_allow_html=True)
    st.markdown(f"<h1 style='text-align: center; font-size: 80px; color: #FBBF24;'>{st.session_state.score}</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>Final Score</p>", unsafe_allow_html=True)
    
    if st.button("PLAY AGAIN", type="primary", use_container_width=True):
        st.session_state.game_state = 'WELCOME'
        st.rerun()
