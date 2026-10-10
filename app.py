import base64
import calendar
import hashlib
import hmac
import html as htmllib
import json
import math
import os
import re
import smtplib
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from io import BytesIO
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

# ---------------------------------------------------------------
# Config & theme
# ---------------------------------------------------------------
BASE = Path(__file__).parent
USERS_DIR = BASE / "user_data"
LOGO = BASE / "logo.png"

TEAL, TEAL_DARK, CREAM, GOLD = "#00736B", "#004F4A", "#F5E6CD", "#E0A458"
GREEN, AMBER, RED = "#2E9E5B", "#E8A317", "#D64545"

page_icon = "🎓"
if LOGO.exists():
    try:
        from PIL import Image

        page_icon = Image.open(LOGO)
    except Exception:
        pass

st.set_page_config(page_title="GITAM Smart Attendance", page_icon=page_icon, layout="wide")

CSS = f"""
<style>
.hero {{display:flex;align-items:center;gap:18px;padding:22px 26px;border-radius:20px;
  background:linear-gradient(120deg,{TEAL_DARK},{TEAL} 60%,#2a9086);color:{CREAM};
  margin-bottom:18px;box-shadow:0 8px 24px rgba(0,79,74,.25)}}
.hero img {{width:72px;height:72px;border-radius:16px}}
.hero h1 {{margin:0;font-size:1.9rem;color:{CREAM};padding:0}}
.hero p {{margin:2px 0 0;opacity:.85}}
.kpi {{background:#fff;border-radius:14px;padding:14px 16px;box-shadow:0 2px 10px rgba(0,0,0,.06)}}
.kpi-v {{font-size:1.8rem;font-weight:700;color:{TEAL_DARK};line-height:1.1}}
.kpi-l {{font-size:.85rem;color:#555;margin-top:2px}}
.kpi-s {{font-size:.75rem;color:#888}}
.card {{display:flex;gap:16px;align-items:center;background:#fff;border-radius:18px;padding:16px;
  box-shadow:0 3px 14px rgba(0,0,0,.07);margin-bottom:14px}}
.ring {{width:84px;height:84px;min-width:84px;border-radius:50%;position:relative;display:flex;
  align-items:center;justify-content:center;
  background:conic-gradient(var(--c) calc(var(--p)*1%), #e6e0d2 0)}}
.ring::before {{content:"";position:absolute;inset:9px;background:#fff;border-radius:50%}}
.ring span {{position:relative;font-weight:700;color:{TEAL_DARK}}}
.cname {{font-weight:700;font-size:1.05rem;color:{TEAL_DARK};margin-bottom:4px}}
.cinfo {{font-size:.82rem;color:#555;margin-top:6px;line-height:1.5}}
.badge {{display:inline-block;padding:2px 10px;border-radius:999px;color:#fff;font-size:.72rem;font-weight:600}}
.pill {{display:inline-block;padding:5px 14px;border-radius:999px;background:{CREAM};color:{TEAL_DARK};
  font-weight:600;font-size:.85rem;margin:0 8px 8px 0;border:1px solid {GOLD}}}
.alert {{background:#fdecea;border-left:6px solid {RED};padding:12px 16px;border-radius:10px;
  color:#7a1f1f;margin-bottom:14px}}
.ok {{background:#e7f6ee;border-left:6px solid {GREEN};padding:12px 16px;border-radius:10px;
  color:#14532d;margin-bottom:14px}}
.cal {{width:100%;border-collapse:separate;border-spacing:6px;table-layout:fixed}}
.cal th {{text-align:center;color:{TEAL_DARK};font-size:.85rem}}
.cal td {{height:54px;text-align:center;border-radius:10px;background:#fff;font-weight:600;color:#333}}
.cal td.out {{opacity:.3}}
.cal td.present {{background:{GREEN};color:#fff}}
.cal td.absent {{background:{RED};color:#fff}}
.cal td.mixed {{background:{AMBER};color:#fff}}
.cal td.today {{outline:3px solid {TEAL}}}
section[data-testid="stSidebar"] {{background:linear-gradient(180deg,{TEAL_DARK},{TEAL})}}
section[data-testid="stSidebar"] * {{color:{CREAM} !important}}
.kgrid {{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:6px}}
.cgrid {{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}}
.cgrid .card {{margin-bottom:0}}
@media (max-width: 640px) {{
  .block-container {{padding:4.5rem .8rem 3rem !important}}
  .hero {{padding:14px 16px;gap:12px;border-radius:16px}}
  .hero img {{width:52px;height:52px;border-radius:12px}}
  .hero h1 {{font-size:1.25rem}}
  .hero p {{font-size:.85rem}}
  .kpi {{padding:10px 12px}}
  .kpi-v {{font-size:1.4rem}}
  .cgrid {{grid-template-columns:1fr}}
  .card {{padding:12px;gap:12px}}
  .cal {{border-spacing:3px}}
  .cal td {{height:40px;font-size:.8rem;border-radius:8px}}
  .cal th {{font-size:.7rem}}
  .pill {{font-size:.78rem;padding:4px 10px}}
}}
</style>
"""


# ---------------------------------------------------------------
# Saved data (local JSON file)
# ---------------------------------------------------------------
DEFAULT_DATA = {
    "settings": {"req": 75, "student": ""},
    "subjects": [
        {"name": "Data Structures", "attended": 32, "total": 40, "remaining": 20, "per_week": 4},
        {"name": "DBMS", "attended": 28, "total": 40, "remaining": 20, "per_week": 4},
        {"name": "Operating Systems", "attended": 20, "total": 36, "remaining": 24, "per_week": 4},
        {"name": "Maths III", "attended": 35, "total": 38, "remaining": 22, "per_week": 4},
        {"name": "Networks", "attended": 25, "total": 30, "remaining": 30, "per_week": 3},
    ],
    "log": [],
}


def clean_username(name: str) -> str:
    return re.sub(r"[^a-z0-9_-]", "", name.strip().lower())[:30]


def user_file(user: str) -> Path:
    return USERS_DIR / f"{user}.json"


def hash_pin(pin: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), 100_000).hex()


def load_user(user: str):
    """Return the saved data for this user, or None if the account doesn't exist."""
    path = user_file(user)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def save_data():
    USERS_DIR.mkdir(exist_ok=True)
    user_file(st.session_state.user).write_text(json.dumps(st.session_state.data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------
# Attendance maths
# ---------------------------------------------------------------
def can_bunk_now(a: int, t: int, req: float) -> int:
    if t == 0:
        return 0
    return max(0, math.floor(a / req - t + 1e-9))


def must_attend(a: int, t: int, req: float) -> int:
    if t == 0 or a / t >= req:
        return 0
    return math.ceil((req * t - a) / (1 - req) - 1e-9)


def semester_plan(a: int, t: int, rem: int, req: float):
    need = max(0, math.ceil(req * (t + rem) - a - 1e-9))
    if need > rem:
        return None, None
    return need, rem - need


def subject_state(sub: dict, log: list):
    """Base numbers + everything marked in the daily log."""
    entries = [e for e in log if e["subject"] == sub["name"]]
    present = sum(e["status"] == "present" for e in entries)
    a = int(sub["attended"]) + present
    t = int(sub["total"]) + len(entries)
    rem = max(0, int(sub["remaining"]) - len(entries))
    last = sorted(entries, key=lambda e: e["date"])[-10:]
    if len(last) >= 5:
        recent = sum(e["status"] == "present" for e in last) / len(last)
    else:
        recent = a / t if t else 0.0
    return a, t, rem, recent


# ---------------------------------------------------------------
# AI layer 1: shortage-risk model (logistic regression)
# ---------------------------------------------------------------
def make_features(cur, recent, needed_rate, rem_ratio):
    return np.column_stack([cur, recent, needed_rate, rem_ratio])


@st.cache_resource
def train_risk_model():
    rng = np.random.default_rng(42)
    n = 8000
    req = rng.uniform(0.65, 0.85, n)
    total = rng.integers(20, 90, n)
    p_hist = rng.beta(6, 2, n)
    attended = rng.binomial(total, p_hist)
    remaining = rng.integers(5, 60, n)
    recent = np.clip(p_hist + rng.normal(0, 0.12, n), 0, 1)
    p_future = np.clip(0.5 * p_hist + 0.5 * recent + rng.normal(0, 0.05, n), 0, 1)
    final = (attended + rng.binomial(remaining, p_future)) / (total + remaining)
    y = (final < req).astype(int)
    needed_rate = np.clip((req * (total + remaining) - attended) / remaining, 0, 1.5)
    X = make_features(attended / total, recent, needed_rate, remaining / (total + remaining))
    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
    model.fit(X, y)
    return model


def predict_risk(model, a, t, rem, recent, req) -> float:
    if t == 0:
        return 0.0
    if rem == 0:
        return 100.0 if a / t < req else 0.0
    need = max(0.0, req * (t + rem) - a)
    if need > rem:
        return 100.0
    if need == 0:
        return 0.0
    x = make_features([a / t], [recent], [min(need / rem, 1.5)], [rem / (t + rem)])
    return float(model.predict_proba(x)[0, 1] * 100)


def build_stats(data: dict, model) -> pd.DataFrame:
    req = data["settings"]["req"] / 100
    rows = []
    for s in data["subjects"]:
        a, t, rem, recent = subject_state(s, data["log"])
        need, max_bunk = semester_plan(a, t, rem, req)
        rows.append({
            "Subject": s["name"],
            "Attended": a,
            "Total": t,
            "Remaining": rem,
            "Per week": int(s.get("per_week", 4)),
            "Current %": round(100 * a / t, 1) if t else 0.0,
            "Can bunk now": can_bunk_now(a, t, req),
            "Must attend": must_attend(a, t, req),
            "Min to attend": need,
            "Max bunks": max_bunk,
            "Risk %": round(predict_risk(model, a, t, rem, recent, req), 1),
        })
    return pd.DataFrame(rows)


def status_of(cur: float, req_pct: int, risk: float):
    if cur < req_pct:
        return "Recover now", RED
    if risk >= 65:
        return "High risk", RED
    if risk >= 30:
        return "Watch", AMBER
    return "Safe", GREEN


# ---------------------------------------------------------------
# Smart helpers
# ---------------------------------------------------------------
def current_streak(log: list) -> int:
    by = {}
    for e in log:
        by.setdefault(e["date"], []).append(e["status"] == "present")
    streak = 0
    for d in sorted(by, reverse=True):
        if all(by[d]):
            streak += 1
        else:
            break
    return streak


def get_insights(df: pd.DataFrame, data: dict) -> list:
    out = []
    if df.empty:
        return out
    best = df.sort_values("Current %", ascending=False).iloc[0]
    worst = df.sort_values("Current %").iloc[0]
    out.append(f"🏆 Strongest subject: **{best['Subject']}** at {best['Current %']:.1f}%")
    out.append(f"⚠️ Weakest subject: **{worst['Subject']}** at {worst['Current %']:.1f}%")
    out.append(f"🎟️ Total bunk budget right now: **{int(df['Can bunk now'].sum())} classes** across all subjects")
    top_risk = df.sort_values("Risk %", ascending=False).iloc[0]
    if top_risk["Risk %"] >= 30:
        out.append(f"🤖 The AI model flags **{top_risk['Subject']}** as your biggest shortage risk "
                   f"({top_risk['Risk %']:.0f}%)")
    absences = [datetime.strptime(e["date"], "%Y-%m-%d").strftime("%A")
                for e in data["log"] if e["status"] == "absent"]
    if len(absences) >= 5:
        day = max(set(absences), key=absences.count)
        out.append(f"📆 You skip most classes on **{day}s** ({absences.count(day)} absences logged)")
    return out


def get_badges(df: pd.DataFrame, data: dict, req_pct: int) -> list:
    badges = []
    streak = current_streak(data["log"])
    if streak >= 3:
        badges.append(f"🔥 {streak}-day perfect streak")
    if not df.empty and (df["Current %"] >= req_pct).all():
        badges.append("🛡️ Safe zone: all subjects above limit")
    if not df.empty and df["Attended"].sum() / max(1, df["Total"].sum()) >= 0.9:
        badges.append("🌟 Star attendee (90%+)")
    if len({e["date"] for e in data["log"]}) >= 10:
        badges.append("📒 Consistent tracker (10+ days logged)")
    return badges


def weekly_plan(data: dict, req_pct: int, buffer_pct: int) -> pd.DataFrame:
    req = req_pct / 100
    target = min(0.95, req + buffer_pct / 100)
    rows = []
    for s in data["subjects"]:
        a, t, rem, _ = subject_state(s, data["log"])
        pw = min(int(s.get("per_week", 4)), rem)
        cur = a / t if t else 0
        need = max(0, math.ceil(target * (t + rem) - a - 1e-9))
        if pw == 0:
            attend, skip, advice = 0, 0, "No classes left"
        elif cur < req or need >= rem:
            attend, skip, advice = pw, 0, "Attend every class"
        else:
            attend = min(pw, math.ceil(need / rem * pw - 1e-9))
            skip = min(pw - attend, can_bunk_now(a, t, req))
            attend = pw - skip
            advice = f"You can skip {skip}" if skip > 0 else "Attend every class"
        rows.append({"Subject": s["name"], "Classes this week": pw, "Attend": attend,
                     "Safe to skip": skip, "Advice": advice})
    return pd.DataFrame(rows)


def trend_data(data: dict):
    a = sum(int(s["attended"]) for s in data["subjects"])
    t = sum(int(s["total"]) for s in data["subjects"])
    by = {}
    for e in sorted(data["log"], key=lambda e: e["date"]):
        by.setdefault(e["date"], []).append(e)
    rows = []
    for d in sorted(by):
        for e in by[d]:
            t += 1
            a += e["status"] == "present"
        rows.append({"Date": pd.to_datetime(d), "Pct": 100 * a / t, "Type": "Actual"})
    return pd.DataFrame(rows), a, t


def forecast_data(data: dict, hist: pd.DataFrame, a: float, t: float, days: int):
    recent = sorted(data["log"], key=lambda e: e["date"])[-20:]
    p = sum(e["status"] == "present" for e in recent) / len(recent)
    per_day = max(1, round(sum(int(s.get("per_week", 4)) for s in data["subjects"]) / 5))
    d = hist["Date"].iloc[-1]
    rows = [{"Date": d, "Pct": hist["Pct"].iloc[-1], "Type": "Forecast"}]
    added = 0
    while added < days:
        d = d + timedelta(days=1)
        if d.weekday() >= 5:
            continue
        t += per_day
        a += per_day * p
        added += 1
        rows.append({"Date": d, "Pct": 100 * a / t, "Type": "Forecast"})
    return pd.DataFrame(rows), p


def month_calendar_html(year: int, month: int, log: list) -> str:
    by = {}
    for e in log:
        by.setdefault(e["date"], []).append(e["status"] == "present")
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    out = '<table class="cal"><tr>' + "".join(f"<th>{n}</th>" for n in names) + "</tr>"
    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(year, month):
        out += "<tr>"
        for d in week:
            cls = "out" if d.month != month else ""
            marks = by.get(d.isoformat())
            if marks:
                cls += " present" if all(marks) else (" absent" if not any(marks) else " mixed")
            if d == date.today():
                cls += " today"
            out += f'<td class="{cls}">{d.day}</td>'
        out += "</tr>"
    return out + "</table>"


# ---------------------------------------------------------------
# AI layer 2: chat advisor (Claude API, with offline fallback)
# ---------------------------------------------------------------
def advisor_context(df: pd.DataFrame, req_pct: int) -> str:
    lines = [
        f"- {r['Subject']}: {r['Attended']}/{r['Total']} = {r['Current %']}%, can skip now {r['Can bunk now']}, "
        f"must attend {r['Must attend']} to recover, {r['Remaining']} classes left, "
        f"shortage risk {r['Risk %']}%"
        for _, r in df.iterrows()
    ]
    return (
        "You are a friendly, practical attendance advisor for a B.Tech student at GITAM. "
        f"The required attendance is {req_pct}%. Use ONLY the numbers below, keep answers short, "
        "and use bullet points when helpful. Never help fake attendance records. If a shortage is "
        "unavoidable, suggest talking to faculty about condonation or medical leave.\n\n"
        "Student's current data:\n" + "\n".join(lines)
    )


def ask_advisor(api_key: str, history: list, system: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-5-5", max_tokens=800, system=system, messages=history
    )
    return "".join(b.text for b in msg.content if b.type == "text")


def offline_answer(q: str, df: pd.DataFrame, req_pct: int) -> str:
    if df.empty:
        return "Add your subjects in the Setup page first."
    ql = q.lower()
    if "risk" in ql or "danger" in ql or "worst" in ql:
        d = df.sort_values("Risk %", ascending=False)
        return "**Shortage risk ranking:**\n" + "\n".join(
            f"- {r['Subject']}: {r['Risk %']:.0f}% risk ({r['Current %']:.1f}% now)" for _, r in d.iterrows())
    if "skip" in ql or "bunk" in ql or "leave" in ql:
        return "**Classes you can skip right now:**\n" + "\n".join(
            f"- {r['Subject']}: {r['Can bunk now']}" for _, r in df.iterrows())
    if "recover" in ql or "below" in ql or "attend" in ql or "plan" in ql:
        low = df[df["Current %"] < req_pct]
        if low.empty:
            return f"Good news: every subject is above {req_pct}%. Keep it up!"
        return "**Attend these many classes in a row to recover:**\n" + "\n".join(
            f"- {r['Subject']}: {r['Must attend']}" for _, r in low.iterrows())
    return ("I can answer questions about **risk**, **how many classes you can skip**, and "
            "**how to recover**. Add an API key above for full AI answers.")


# ---------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------
def build_alert_message(df: pd.DataFrame, req_pct: int):
    lines = []
    for _, r in df.iterrows():
        below = r["Current %"] < req_pct
        if not (below or r["Risk %"] >= 65):
            continue
        if below and pd.isna(r["Max bunks"]):
            tip = "attendance alone can't reach the limit, talk to your faculty about condonation/medical leave"
        elif below:
            tip = f"attend the next {r['Must attend']} class(es) in a row"
        else:
            tip = "avoid skipping, you are close to the limit"
        lines.append(f"- {r['Subject']}: {r['Current %']}% (shortage risk {r['Risk %']}%). Tip: {tip}.")
    if not lines:
        return None
    return (f"Attendance alert (required: {req_pct}%)\n\n" + "\n".join(lines)
            + "\n\nSent from GITAM Smart Attendance.")


def send_email(sender, app_password, recipient, subject, body):
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = sender, recipient, subject
    msg.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, app_password)
        server.send_message(msg)


def send_whatsapp(phone, body):
    import pywhatkit

    pywhatkit.sendwhatmsg_instantly(phone, body, wait_time=20, tab_close=True, close_time=3)


# ---------------------------------------------------------------
# UI building blocks
# ---------------------------------------------------------------
def logo_b64():
    if LOGO.exists():
        return base64.b64encode(LOGO.read_bytes()).decode()
    return None


def hero(title: str, subtitle: str):
    b = logo_b64()
    img = f'<img src="data:image/png;base64,{b}"/>' if b else '<div style="font-size:3rem">🎓</div>'
    st.markdown(f'<div class="hero">{img}<div><h1>{title}</h1><p>{subtitle}</p></div></div>',
                unsafe_allow_html=True)


def kpi(label, value, sub="", color=TEAL):
    return (f'<div class="kpi" style="border-top:4px solid {color}"><div class="kpi-v">{value}</div>'
            f'<div class="kpi-l">{label}</div><div class="kpi-s">{sub}</div></div>')


def card_html(r, req_pct: int) -> str:
    label, color = status_of(r["Current %"], req_pct, r["Risk %"])
    if r["Current %"] < req_pct and pd.isna(r["Max bunks"]):
        extra = "Can't reach the limit by attendance alone. <b>Talk to your faculty</b>"
    elif r["Current %"] < req_pct:
        extra = f'Attend next <b>{int(r["Must attend"])}</b> in a row to recover'
    else:
        extra = f'Can skip <b>{int(r["Can bunk now"])}</b> class(es) now'
    name = htmllib.escape(str(r["Subject"]))
    return (
        f'<div class="card"><div class="ring" style="--p:{r["Current %"]:.0f};--c:{color}">'
        f'<span>{r["Current %"]:.0f}%</span></div><div><div class="cname">{name}</div>'
        f'<span class="badge" style="background:{color}">{label}</span>'
        f'<div class="cinfo">{extra}<br>Shortage risk: <b>{r["Risk %"]:.0f}%</b> &middot; '
        f'{int(r["Attended"])}/{int(r["Total"])} classes</div></div></div>'
    )


# ---------------------------------------------------------------
# Pages
# ---------------------------------------------------------------
def page_dashboard(data, df, req_pct):
    name = data["settings"].get("student", "").strip()
    hero("GITAM Smart Attendance", f"Welcome{', ' + name if name else ''}! Know exactly where you stand.")
    st.caption("📱 On a phone? Tap the arrow at the top-left to open the menu.")
    if df.empty:
        st.info("No subjects yet. Open **📷 Import from Portal** in the menu to load them from your "
                "college portal, add them in **⚙️ Setup**, or try the demo data.")
        if st.button("Try with demo data"):
            data["subjects"] = json.loads(json.dumps(DEFAULT_DATA["subjects"]))
            save_data()
            st.rerun()
        return

    risky = df[(df["Current %"] < req_pct) | (df["Risk %"] >= 65)]
    if len(risky):
        names = htmllib.escape(", ".join(risky["Subject"]))
        st.markdown(f'<div class="alert">⚠️ <b>{len(risky)} subject(s) need attention:</b> {names}</div>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<div class="ok">✅ <b>All clear!</b> Every subject is safe right now.</div>',
                    unsafe_allow_html=True)

    overall = 100 * df["Attended"].sum() / max(1, df["Total"].sum())
    kpis = "".join([
        kpi("Overall attendance", f"{overall:.1f}%", f"Required {req_pct}%", GREEN if overall >= req_pct else RED),
        kpi("Subjects safe", int((df["Current %"] >= req_pct).sum()), f"of {len(df)}", GREEN),
        kpi("Below limit", int((df["Current %"] < req_pct).sum()), "need recovery", RED),
        kpi("High AI risk", int((df["Risk %"] >= 65).sum()), "shortage likely", AMBER),
        kpi("Perfect streak", f"{current_streak(data['log'])} 🔥", "days in a row", GOLD),
    ])
    st.markdown(f'<div class="kgrid">{kpis}</div>', unsafe_allow_html=True)

    badges = get_badges(df, data, req_pct)
    if badges:
        st.markdown("<br>" + "".join(f'<span class="pill">{b}</span>' for b in badges), unsafe_allow_html=True)

    st.markdown("### 📚 Your subjects")
    cards = "".join(card_html(r, req_pct) for _, r in df.iterrows())
    st.markdown(f'<div class="cgrid">{cards}</div>', unsafe_allow_html=True)

    st.markdown("### 💡 Smart insights")
    for line in get_insights(df, data):
        st.markdown(f"- {line}")

    st.markdown("### 📊 Attendance vs required")
    chart_df = df[["Subject", "Current %"]].rename(columns={"Current %": "Current"})
    chart_df["Color"] = np.where(chart_df["Current"] >= req_pct, GREEN, RED)
    bars = alt.Chart(chart_df).mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6).encode(
        x=alt.X("Subject:N", sort=None, axis=alt.Axis(labelAngle=-20)),
        y=alt.Y("Current:Q", scale=alt.Scale(domain=[0, 100])),
        color=alt.Color("Color:N", scale=None),
        tooltip=["Subject", "Current"],
    )
    line = alt.Chart(pd.DataFrame({"y": [req_pct]})).mark_rule(strokeDash=[6, 4], color="#888").encode(y="y:Q")
    st.altair_chart(bars + line)

    with st.expander("📋 Full table & download"):
        show = df.drop(columns=["Per week"]).copy()
        show["Max bunks"] = show["Max bunks"].apply(lambda v: "Not possible" if pd.isna(v) else int(v))
        show["Min to attend"] = show["Min to attend"].apply(lambda v: "-" if pd.isna(v) else int(v))
        st.dataframe(show, hide_index=True)
        st.download_button("⬇️ Download report (CSV)", df.to_csv(index=False), "attendance_report.csv", "text/csv")


def page_mark(data):
    hero("Mark Today", "Log each class in seconds. Your numbers update automatically.")
    day = st.date_input("Date", value=date.today(), max_value=date.today())
    key = day.isoformat()
    existing = {e["subject"]: e["status"] for e in data["log"] if e["date"] == key}
    options = ["Present", "Absent", "No class"]

    if st.button("✅ Mark everything present for this day"):
        names = {s["name"] for s in data["subjects"]}
        data["log"] = [e for e in data["log"] if not (e["date"] == key and e["subject"] in names)]
        for n in names:
            data["log"].append({"date": key, "subject": n, "status": "present"})
        save_data()
        st.success("All subjects marked present.")
        st.rerun()

    with st.form("mark_form"):
        choices = {}
        for s in data["subjects"]:
            idx = {"present": 0, "absent": 1}.get(existing.get(s["name"]), 2)
            choices[s["name"]] = st.radio(s["name"], options, index=idx, horizontal=True,
                                          key=f"mark_{key}_{s['name']}")
        submitted = st.form_submit_button("💾 Save attendance", type="primary")

    if submitted:
        names = set(choices)
        data["log"] = [e for e in data["log"] if not (e["date"] == key and e["subject"] in names)]
        for n, c in choices.items():
            if c != "No class":
                data["log"].append({"date": key, "subject": n, "status": c.lower()})
        save_data()
        st.success(f"Saved attendance for {day.strftime('%d %b %Y')}. Check the Dashboard for updated numbers.")
        st.toast("Saved ✅")
    st.caption("Tip: marking a class also reduces that subject's 'remaining classes' by one.")


def page_calendar(data, req_pct):
    hero("Calendar & Trends", "See your attendance history and where it's heading.")
    c1, c2 = st.columns(2)
    month = c1.selectbox("Month", list(range(1, 13)), index=date.today().month - 1,
                         format_func=lambda m: calendar.month_name[m])
    year = c2.number_input("Year", 2020, 2100, date.today().year)
    st.markdown(month_calendar_html(int(year), int(month), data["log"]), unsafe_allow_html=True)
    st.caption("🟩 all present   🟥 all absent   🟧 mixed   ⬜ nothing logged")

    st.markdown("### 📈 Overall attendance trend + forecast")
    hist, a, t = trend_data(data)
    if hist.empty:
        st.info("Mark attendance for a few days and your trend line will appear here.")
        return
    days = st.slider("Forecast how many working days ahead?", 5, 60, 20)
    fc, p = forecast_data(data, hist, a, t, days)
    both = pd.concat([hist, fc], ignore_index=True)
    lo = max(0, float(both["Pct"].min()) - 8)
    chart = alt.Chart(both).mark_line(point=True).encode(
        x="Date:T",
        y=alt.Y("Pct:Q", title="Attendance %", scale=alt.Scale(domain=[lo, 100])),
        color=alt.Color("Type:N", scale=alt.Scale(domain=["Actual", "Forecast"], range=[TEAL, GOLD])),
        strokeDash=alt.StrokeDash("Type:N", scale=alt.Scale(domain=["Actual", "Forecast"],
                                                            range=[[1, 0], [6, 4]])),
        tooltip=["Date:T", alt.Tooltip("Pct:Q", format=".1f"), "Type:N"],
    )
    rule = alt.Chart(pd.DataFrame({"y": [req_pct]})).mark_rule(strokeDash=[4, 4], color="#888").encode(y="y:Q")
    st.altair_chart(chart + rule)
    end = fc["Pct"].iloc[-1]
    verdict = "above" if end >= req_pct else "below"
    st.caption(f"Forecast assumes you keep attending {p * 100:.0f}% of classes (your last 20 entries). "
               f"You would end around **{end:.1f}%**, {verdict} the {req_pct}% limit.")

    absences = [datetime.strptime(e["date"], "%Y-%m-%d").strftime("%a")
                for e in data["log"] if e["status"] == "absent"]
    if absences:
        st.markdown("### 📆 Which days do you skip most?")
        order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        counts = pd.DataFrame({"Day": order, "Absences": [absences.count(d) for d in order]})
        st.altair_chart(alt.Chart(counts).mark_bar(color=GOLD, cornerRadiusTopLeft=6,
                                                   cornerRadiusTopRight=6).encode(
            x=alt.X("Day:N", sort=order), y="Absences:Q", tooltip=["Day", "Absences"]))


def page_planner(data, df, req_pct):
    hero("Smart Planner", "AI-assisted weekly bunk budget and recovery plans.")
    if df.empty:
        st.info("Add subjects in Setup first.")
        return

    st.markdown("### 🗓️ This week's plan")
    buffer_pct = st.slider("Safety buffer (extra % above the limit)", 0, 10, 3,
                           help="A higher buffer keeps you safer in case you fall sick or get surprise absences.")
    plan = weekly_plan(data, req_pct, buffer_pct)
    st.dataframe(plan, hide_index=True)
    total_skip = int(plan["Safe to skip"].sum())
    st.success(f"You can safely skip about **{total_skip} class(es)** this week across all subjects, "
               f"with a {buffer_pct}% safety buffer.")

    st.markdown("### 🚑 Recovery plan")
    low = df[df["Current %"] < req_pct]
    if low.empty:
        st.markdown('<div class="ok">Nothing to recover. All subjects are above the limit.</div>',
                    unsafe_allow_html=True)
    for _, r in low.iterrows():
        pw = max(1, int(r["Per week"]))
        weeks = math.ceil(r["Must attend"] / pw)
        if pd.isna(r["Max bunks"]):
            st.error(f"**{r['Subject']}**: even full attendance can't reach {req_pct}% this semester. "
                     "Speak to your faculty about condonation or medical leave now.")
        else:
            st.warning(f"**{r['Subject']}**: attend the next **{int(r['Must attend'])}** classes in a row "
                       f"(about {weeks} week(s) at {pw} classes/week).")

    st.markdown("### 🎟️ Bunk budget for the rest of the semester")
    budget = df[["Subject", "Max bunks"]].copy()
    budget["Max bunks"] = budget["Max bunks"].fillna(0)
    st.altair_chart(alt.Chart(budget).mark_bar(color=TEAL, cornerRadiusTopRight=6,
                                               cornerRadiusBottomRight=6).encode(
        y=alt.Y("Subject:N", sort="-x"), x=alt.X("Max bunks:Q", title="Classes you can still skip"),
        tooltip=["Subject", "Max bunks"]))

    st.markdown("### 🔮 What-if simulator")
    w1, w2, w3 = st.columns(3)
    subj = w1.selectbox("Subject", df["Subject"])
    skip = w2.number_input("Classes I skip", 0, 100, 3)
    attend = w3.number_input("Classes I attend", 0, 100, 0)
    sel = df[df["Subject"] == subj].iloc[0]
    new_a = int(sel["Attended"]) + attend
    new_t = int(sel["Total"]) + skip + attend
    new_p = 100 * new_a / new_t if new_t else 0
    st.metric(f"{subj} after this plan", f"{new_p:.1f}%", delta=f"{new_p - sel['Current %']:+.1f}%")
    if new_p < req_pct:
        st.warning(f"That would put you below {req_pct}%.")
    else:
        st.success(f"You'd still be above {req_pct}%.")

    with st.expander("ℹ️ How the AI risk prediction works"):
        st.markdown(
            "A **logistic regression** model is trained on thousands of simulated students. Each simulation "
            "plays out the rest of a semester and records whether the student ended below the limit. "
            "Features: current attendance, recent attendance (last 10 classes you logged), the share of "
            "remaining classes you must attend, and how much of the semester is left. "
            "The output is the probability of a shortage."
        )


def page_advisor(data, df, req_pct):
    hero("AI Advisor", "Ask anything about your attendance in plain English.")
    key = api_key_input("Anthropic API key (optional, for full AI answers)")
    if "chat" not in st.session_state:
        st.session_state.chat = []

    quick = st.columns(3)
    prompts = ["Which subjects are risky?", "How many classes can I skip?", "Make me a recovery plan"]
    clicked = None
    for col, p in zip(quick, prompts):
        if col.button(p):
            clicked = p

    for m in st.session_state.chat:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    user_q = st.chat_input("e.g. Can I skip Friday's classes?") or clicked
    if user_q:
        st.session_state.chat.append({"role": "user", "content": user_q})
        with st.chat_message("user"):
            st.markdown(user_q)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    if key:
                        reply = ask_advisor(key, st.session_state.chat, advisor_context(df, req_pct))
                    else:
                        reply = offline_answer(user_q, df, req_pct)
                except Exception as e:
                    reply = f"Sorry, the AI call failed: {e}"
            st.markdown(reply)
        st.session_state.chat.append({"role": "assistant", "content": reply})

    if st.session_state.chat and st.button("🧹 Clear chat"):
        st.session_state.chat = []
        st.rerun()


def page_reminders(df, req_pct):
    hero("Reminders", "Get an email or WhatsApp alert when attendance drops.")
    alert_text = build_alert_message(df, req_pct) if not df.empty else None
    if alert_text is None:
        st.success("All subjects look fine, so there is nothing to send right now.")
        return
    st.warning("Preview of the alert:")
    st.code(alert_text, language=None)
    email_tab, wa_tab = st.tabs(["📧 Email", "💬 WhatsApp"])

    with email_tab:
        st.caption("Uses Gmail with an *app password* (Google Account → Security → 2-Step Verification → App passwords).")
        sender = st.text_input("Your Gmail address", key="em_sender")
        pw = st.text_input("Gmail app password", type="password", key="em_pw")
        to = st.text_input("Send alert to (email)", key="em_to")
        if st.button("Send email alert"):
            if not (sender and pw and to):
                st.error("Please fill all three fields.")
            else:
                try:
                    send_email(sender, pw.replace(" ", ""), to, "⚠️ Attendance alert", alert_text)
                    st.success(f"Email sent to {to}.")
                except Exception as e:
                    st.error(f"Could not send email: {e}")

    with wa_tab:
        st.caption("WhatsApp alerts only work when you run the app on your own computer: they need "
                   "`pip install pywhatkit` and WhatsApp Web logged in on your default browser. "
                   "On the shared online link, use email.")
        phone = st.text_input("Phone with country code, e.g. +919876543210", key="wa_phone")
        if st.button("Send WhatsApp alert"):
            if not phone.startswith("+"):
                st.error("Include the country code, starting with +.")
            else:
                try:
                    send_whatsapp(phone, alert_text)
                    st.success("WhatsApp message triggered. Check the browser tab.")
                except ImportError:
                    st.error("pywhatkit is not installed. Run: python -m pip install pywhatkit")
                except Exception as e:
                    st.error(f"Could not send WhatsApp message: {e}")


# ---------------------------------------------------------------
# Import from college portal (screenshot or pasted table)
# ---------------------------------------------------------------
EXTRACT_PROMPT = (
    "This is a screenshot or photo of a college attendance table. Extract EVERY subject row. "
    "Return ONLY a JSON array (no markdown, no explanation). Each item must have: "
    '"code" (string, empty if none), "name" (string, the subject name), '
    '"present" (integer, classes attended) and "total" (integer, total classes held). '
    "Ignore the percentage column and any rows that are not subjects. "
    "If a number is unreadable, use null."
)


def api_key_input(label: str) -> str:
    """API key box that remembers the key across pages (this session only)."""
    default = st.session_state.get("api_key_saved", os.environ.get("ANTHROPIC_API_KEY", ""))
    val = st.text_input(label, type="password", value=default, help="Stays in this session only.")
    st.session_state["api_key_saved"] = val
    return val.strip()


def prepare_image(uploaded) -> str:
    """Shrink the image if needed and return it as base64 JPEG."""
    from PIL import Image

    img = Image.open(BytesIO(uploaded.getvalue())).convert("RGB")
    img.thumbnail((2000, 2000))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode()


def extract_from_image(api_key: str, b64: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-5-5",
        max_tokens=2000,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
            {"type": "text", "text": EXTRACT_PROMPT},
        ]}],
    )
    return "".join(b.text for b in msg.content if b.type == "text")


def parse_json_rows(text: str):
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("The AI reply didn't contain a table. Try a clearer screenshot.")
    items = json.loads(text[start:end + 1])
    rows, skipped = [], 0
    for it in items:
        try:
            name = str(it.get("name") or it.get("code") or "").strip()
            present, total = int(it["present"]), int(it["total"])
        except (KeyError, TypeError, ValueError, AttributeError):
            skipped += 1
            continue
        if not name or present < 0 or present > total:
            skipped += 1
            continue
        rows.append({"name": name, "present": present, "total": total})
    return rows, skipped


PASTE_RE = re.compile(
    r"^(?:(?P<code>(?=[A-Za-z0-9]*\d)[A-Za-z0-9]+)\s+)?(?P<name>.+?)\s+(?P<p>\d+)\s+(?P<t>\d+)"
    r"(?:\s+\d+(?:\.\d+)?\s*%?)?$"
)


def parse_pasted_table(text: str):
    rows, skipped = [], 0
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line.strip())
        if not line:
            continue
        m = PASTE_RE.match(line)
        if not m:
            continue  # header or junk line
        present, total = int(m["p"]), int(m["t"])
        if present > total:
            skipped += 1
            continue
        rows.append({"name": m["name"].strip(), "present": present, "total": total})
    return rows, skipped


def rows_to_df(rows: list, remaining: int, per_week: int) -> pd.DataFrame:
    return pd.DataFrame({
        "Subject": [r["name"] for r in rows],
        "Attended": [r["present"] for r in rows],
        "Total": [r["total"] for r in rows],
        "Remaining": [remaining] * len(rows),
        "Per week": [per_week] * len(rows),
    })


@st.cache_resource
def get_ocr_engine():
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


def group_ocr_lines(items: list) -> list:
    """Turn scattered OCR text boxes into table rows (grouped by height, sorted left to right).
    Each item: {"x": left edge, "yc": vertical centre, "h": box height, "text": str}."""
    if not items:
        return []
    heights = sorted(i["h"] for i in items)
    tol = max(6.0, 0.6 * heights[len(heights) // 2])
    rows, current, cur_y = [], [], None
    for it in sorted(items, key=lambda i: i["yc"]):
        if cur_y is None or abs(it["yc"] - cur_y) <= tol:
            current.append(it)
            cur_y = sum(i["yc"] for i in current) / len(current)
        else:
            rows.append(current)
            current, cur_y = [it], it["yc"]
    rows.append(current)
    return [" ".join(i["text"] for i in sorted(r, key=lambda i: i["x"])) for r in rows]


def ocr_screenshot_lines(uploaded) -> list:
    """Free, offline screenshot reader (no API key)."""
    from PIL import Image

    img = Image.open(BytesIO(uploaded.getvalue())).convert("RGB")
    img.thumbnail((2600, 2600))
    result, _ = get_ocr_engine()(np.array(img))
    items = []
    for box, text, _score in (result or []):
        xs, ys = [p[0] for p in box], [p[1] for p in box]
        items.append({"x": min(xs), "yc": sum(ys) / len(ys), "h": max(ys) - min(ys), "text": str(text)})
    return group_ocr_lines(items)


def page_import(data):
    hero("Import from College Portal",
         "Upload your portal screenshot. The app reads it, and you only add the remaining classes.")
    ss = st.session_state
    ss.setdefault("import_df", None)
    ss.setdefault("import_ver", 0)

    c1, c2 = st.columns(2)
    remaining_all = c1.number_input("Remaining classes in the semester (same for all, editable later)",
                                    0, 300, 20)
    per_week_all = c2.number_input("Classes per week (default for all, editable later)", 1, 20, 4)

    def load_rows(rows, skipped):
        if not rows:
            st.error("Couldn't find any subject rows. Try a clearer screenshot or the paste option.")
            return
        ss.import_df = rows_to_df(rows, int(remaining_all), int(per_week_all))
        ss.import_ver += 1
        msg = f"Found {len(rows)} subjects. Check them below."
        if skipped:
            msg += f" ({skipped} unreadable row(s) skipped.)"
        st.success(msg)

    tab_img, tab_txt = st.tabs(["📷 Upload screenshot", "📋 Paste table text"])

    with tab_img:
        reader = st.radio(
            "How should I read it?",
            ["Free reader (no API key)", "AI reader (needs API key, best for photos)"],
            horizontal=True,
        )
        use_ai = reader.startswith("AI")
        key = api_key_input("Anthropic API key") if use_ai else ""
        up = st.file_uploader("Upload a screenshot or photo (PNG, JPG, WEBP)",
                              type=["png", "jpg", "jpeg", "webp"])
        if up:
            st.image(up, caption="Your upload", width=520)
        if use_ai:
            st.caption("Tip: crop out your name and ID number first. The image is sent to the Anthropic API.")
        else:
            st.caption("The free reader works on your own computer or server and sends nothing elsewhere. "
                       "Always double-check the numbers afterwards.")

        if st.button("🔍 Read my attendance", type="primary"):
            if not up:
                st.error("Please upload an image first.")
            elif use_ai and not key:
                st.error("Please enter your API key, or switch to the free reader.")
            elif use_ai:
                with st.spinner("Reading your screenshot..."):
                    try:
                        text = extract_from_image(key, prepare_image(up))
                        rows, skipped = parse_json_rows(text)
                        load_rows(rows, skipped)
                    except Exception as e:
                        st.error(f"Could not read the image: {e}")
            else:
                with st.spinner("Reading your screenshot (the first time can take a little longer)..."):
                    try:
                        lines = ocr_screenshot_lines(up)
                    except ImportError as e:
                        st.error("The free reader couldn't start on this server. If you run the app on your "
                                 "own computer, run `python -m pip install rapidocr-onnxruntime` and restart. "
                                 "If this is the shared link, the owner needs to add it to requirements.txt "
                                 "(see the setup notes). Meanwhile, use **Paste table text** or the AI reader.")
                        st.caption(f"Technical detail: {e}")
                        lines = None
                    except Exception as e:
                        st.error(f"Could not read the image: {e}")
                        lines = None
                if lines is not None:
                    rows, skipped = parse_pasted_table("\n".join(lines))
                    load_rows(rows, skipped)
                    with st.expander("What the reader saw (useful if rows are missing)"):
                        st.code("\n".join(lines) or "(nothing detected)", language=None)

    with tab_txt:
        st.caption("On your portal, select the whole table, copy it (Ctrl+C) and paste it here. "
                   "Each row should look like: code, subject name, present, total, percentage.")
        pasted = st.text_area("Paste the table here", height=200)
        if st.button("📥 Read pasted table"):
            rows, skipped = parse_pasted_table(pasted)
            load_rows(rows, skipped)

    if ss.import_df is not None:
        st.markdown("### ✏️ Check and complete")
        st.caption("Compare with your portal and fix any wrong number. Set the real **Remaining** classes "
                   "for each subject.")
        edited = st.data_editor(
            ss.import_df, num_rows="dynamic", key=f"import_editor_{ss.import_ver}",
            column_config={
                "Attended": st.column_config.NumberColumn(min_value=0, step=1),
                "Total": st.column_config.NumberColumn(min_value=0, step=1),
                "Remaining": st.column_config.NumberColumn(min_value=0, step=1),
                "Per week": st.column_config.NumberColumn(min_value=1, max_value=20, step=1),
            },
        )
        keep_log = st.checkbox("Keep my daily log (tick only if it has classes that are NOT yet in the portal)")
        st.warning("This will **replace** the subjects currently in the app.")
        if st.button("✅ Use this data", type="primary"):
            clean = edited.dropna(subset=["Subject"]).fillna(0)
            clean = clean[clean["Subject"].astype(str).str.strip() != ""]
            if clean.empty:
                st.error("No subjects to import.")
            elif (clean["Attended"] > clean["Total"]).any():
                st.error("Attended can't be more than Total. Please fix the table.")
            else:
                data["subjects"] = [
                    {"name": str(r["Subject"]).strip(), "attended": int(r["Attended"]),
                     "total": int(r["Total"]), "remaining": int(r["Remaining"]),
                     "per_week": int(r["Per week"]) or 4}
                    for _, r in clean.iterrows()
                ]
                if not keep_log:
                    data["log"] = []
                save_data()
                ss.import_df = None
                st.success("Imported! Open the **🏠 Dashboard** to see your attendance.")
                st.balloons()


def page_setup(data):
    hero("Setup", "Your name, subjects and starting numbers.")
    data["settings"]["student"] = st.text_input("Your name", data["settings"].get("student", ""))

    st.markdown("### 📚 Subjects (starting numbers)")
    st.caption("Enter the numbers you have *before* using daily marking. Anything you mark later is added on top.")
    base = pd.DataFrame(
        data["subjects"], columns=["name", "attended", "total", "remaining", "per_week"]
    ).rename(columns={
        "name": "Subject", "attended": "Attended", "total": "Total",
        "remaining": "Remaining", "per_week": "Per week"})
    edited = st.data_editor(
        base, num_rows="dynamic",
        column_config={
            "Attended": st.column_config.NumberColumn(min_value=0, step=1),
            "Total": st.column_config.NumberColumn(min_value=0, step=1),
            "Remaining": st.column_config.NumberColumn(min_value=0, step=1, help="Classes left in the semester"),
            "Per week": st.column_config.NumberColumn(min_value=1, max_value=20, step=1,
                                                      help="Classes of this subject per week"),
        },
    )

    if st.button("💾 Save setup", type="primary"):
        edited = edited.dropna(subset=["Subject"]).fillna(0)
        edited = edited[edited["Subject"].astype(str).str.strip() != ""]
        if (edited["Attended"] > edited["Total"]).any():
            st.error("Attended can't be more than Total. Please fix the table.")
        else:
            data["subjects"] = [
                {"name": str(r["Subject"]).strip(), "attended": int(r["Attended"]), "total": int(r["Total"]),
                 "remaining": int(r["Remaining"]), "per_week": int(r["Per week"]) or 4}
                for _, r in edited.iterrows()
            ]
            save_data()
            st.success("Saved!")
            st.rerun()

    st.markdown("### 🧰 Data tools")
    st.caption("If you use the shared online link, download a backup now and then. Hosted apps can reset "
               "their saved files when they restart.")
    backup = {k: v for k, v in data.items() if k != "auth"}
    st.download_button("⬇️ Download backup (JSON)", json.dumps(backup, indent=2), "attendance_backup.json")

    st.caption("To load attendance from a **screenshot**, use **📷 Import from Portal**. "
               "The JSON restore below is only for backups made by this app.")
    up = st.file_uploader("Restore from a backup file (.json)", type=["json"])
    if up and st.button("♻️ Restore this backup"):
        try:
            obj = json.loads(up.getvalue().decode("utf-8"))
            subjects = [
                {"name": str(s["name"]).strip(), "attended": int(s["attended"]), "total": int(s["total"]),
                 "remaining": int(s["remaining"]), "per_week": int(s.get("per_week", 4)) or 4}
                for s in obj["subjects"]
            ]
            log = [e for e in obj.get("log", []) if {"date", "subject", "status"} <= set(e)]
            data["subjects"], data["log"] = subjects, log
            data["settings"]["req"] = int(obj.get("settings", {}).get("req", data["settings"]["req"]))
            save_data()
            st.success("Backup restored!")
            st.rerun()
        except Exception as e:
            st.error(f"That doesn't look like a valid backup file: {e}")

    confirm = st.checkbox("I want to delete my daily log (this can't be undone)")
    if st.button("🗑️ Clear daily log", disabled=not confirm):
        data["log"] = []
        save_data()
        st.success("Daily log cleared.")
        st.rerun()


def page_login():
    hero("GITAM Smart Attendance By Trinay", "Sign in or create your private tracker.")
    st.markdown("Pick a **username** and a **PIN** (4 to 8 digits). A new username creates a new account. "
                "Everyone's data is separate and private.")
    with st.form("login_form"):
        username = st.text_input("Username (letters and numbers)")
        pin = st.text_input("PIN (4 to 8 digits)", type="password")
        go = st.form_submit_button("Continue", type="primary")
    st.caption("This PIN is a simple lock to keep friends out of your data, not bank-grade security. "
               "Don't reuse a PIN from your bank or phone.")
    if not go:
        return

    user = clean_username(username)
    if not user:
        st.error("Please enter a username (letters and numbers only).")
        return
    if not (pin.isdigit() and 4 <= len(pin) <= 8):
        st.error("The PIN must be 4 to 8 digits.")
        return

    existing = load_user(user)
    auth = (existing or {}).get("auth")
    if existing is not None and auth:
        if not hmac.compare_digest(hash_pin(pin, auth["salt"]), auth["hash"]):
            st.error("Wrong PIN for this username. If you're new, choose a different username.")
            return
        data = existing
    else:
        salt = os.urandom(16).hex()
        data = existing or {"settings": {"req": 75, "student": username.strip()}, "subjects": [], "log": []}
        data["auth"] = {"salt": salt, "hash": hash_pin(pin, salt)}
    st.session_state.user = user
    st.session_state.data = data
    save_data()
    st.rerun()


# ---------------------------------------------------------------
# Main
# ---------------------------------------------------------------
st.markdown(CSS, unsafe_allow_html=True)

if "user" not in st.session_state:
    page_login()
    st.stop()

data = st.session_state.data
model = train_risk_model()

with st.sidebar:
    if LOGO.exists():
        st.image(str(LOGO), width=90)
    st.markdown("## Smart Attendance")
    st.caption(f"Signed in as **{st.session_state.user}**")
    page = st.radio("Navigate", [
        "🏠 Dashboard", "📷 Import from Portal", "✅ Mark Today", "📆 Calendar & Trends", "🧠 Smart Planner",
        "🤖 AI Advisor", "🔔 Reminders", "⚙️ Setup",
    ], label_visibility="collapsed")
    req_pct = st.slider("Required attendance (%)", 50, 95, int(data["settings"]["req"]))
    if req_pct != data["settings"]["req"]:
        data["settings"]["req"] = req_pct
        save_data()
    if st.button("🚪 Log out"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

df = build_stats(data, model)

if page.endswith("Dashboard"):
    page_dashboard(data, df, req_pct)
elif page.endswith("Import from Portal"):
    page_import(data)
elif page.endswith("Mark Today"):
    page_mark(data)
elif page.endswith("Calendar & Trends"):
    page_calendar(data, req_pct)
elif page.endswith("Smart Planner"):
    page_planner(data, df, req_pct)
elif page.endswith("AI Advisor"):
    page_advisor(data, df, req_pct)
elif page.endswith("Reminders"):
    page_reminders(df, req_pct)
else:
    page_setup(data)
