import time
from datetime import datetime, timezone
import requests
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Delta Crypto Scanner", layout="wide")
st.title("Delta Crypto Scanner")
st.caption("Observation-only · 15-minute completed candles · No orders or exchange API keys")

BASE_URL = "https://api.india.delta.exchange"
SYMBOLS = ["BTCUSD", "ETHUSD", "SOLUSD", "BTWUSD", "AKEUSD", "GTCUSD", "ZECUSD", "XRPUSD", "TIAUSD", "UNIUSD", "BRUSD", "STRKUSD", "DOGEUSD", "AAVEUSD", "ALTUSD", "DUSKUSD", "BNBUSD", "LTCUSD", "LINKUSD", "AVAAIUSD", "NMRUSD", "FILUSD", "BCHUSD", "ZROUSD", "XMRUSD", "LABUSD", "GRIFFAINUSD", "INJUSD"]
RS_COLS = ["15m Relative Strength %", "1h Relative Strength %", "4h Relative Strength %"]

@st.cache_data(ttl=840, show_spinner=False)
def fetch_candles(symbol, resolution, days=10):
    end = datetime.now(timezone.utc)
    start = end - pd.Timedelta(days=days)
    response = requests.get(f"{BASE_URL}/v2/history/candles", params={"symbol":symbol,"resolution":resolution,"start":int(start.timestamp()),"end":int(end.timestamp())}, headers={"Accept":"application/json"}, timeout=25)
    response.raise_for_status()
    payload=response.json()
    if not payload.get("success",False): raise RuntimeError(f"API unsuccessful response for {symbol} {resolution}")
    df=pd.DataFrame(payload.get("result",[]))
    if df.empty: raise RuntimeError(f"No candles for {symbol} {resolution}")
    df["time"]=pd.to_datetime(df["time"],unit="s",utc=True)
    for col in ["open","high","low","close","volume"]: df[col]=pd.to_numeric(df[col],errors="coerce")
    df=df.sort_values("time").drop_duplicates("time").dropna(subset=["time","open","high","low","close","volume"]).reset_index(drop=True)
    if resolution=="15m":
        now=pd.Timestamp.now(tz="UTC")
        df=df[df["time"]+pd.Timedelta(minutes=15)<=now].reset_index(drop=True)
    return df

def pivots(previous):
    H,L,C=float(previous.high),float(previous.low),float(previous.close)
    if not H>L: raise ValueError("Invalid daily candle high/low")
    P=(H+L+C)/3; rng=H-L
    R1 = 2*P-L; S1 = 2*P-H
    R2 = P+(H-L); S2 = P-(H-L)
    R3 = H+2*(P-L); S3 = L-2*(H-P)
    # Preserve the scanner's already-validated R4/S4 formulas used by entry percentages.
    R4 = 3*P+(H-3*L); S4 = 3*P-(3*H-L)
    R5 = R4+(H-L); S5 = S4-(H-L)
    return {"Pivot":P,"R1":R1,"R2":R2,"R3":R3,"R4":R4,"R5":R5,
            "S1":S1,"S2":S2,"S3":S3,"S4":S4,"S5":S5,
            "Pivot Source Date":previous.time.strftime("%Y-%m-%d")}

@st.cache_data(ttl=840, show_spinner=False)
def run_scan():
    candle_cache={}; daily_cache={}; errors=[]
    progress=st.progress(0, text="Fetching public candle data…")
    for i,symbol in enumerate(SYMBOLS,1):
        try:
            candle_cache[symbol]=fetch_candles(symbol,"15m",10)
            daily_cache[symbol]=fetch_candles(symbol,"1d",10)
            if len(candle_cache[symbol])<17: raise RuntimeError("Not enough completed 15m candles for 4h relative strength")
            if daily_cache[symbol].empty: raise RuntimeError("No daily candle data")
        except Exception as exc: errors.append({"Symbol":symbol,"Error":str(exc)})
        progress.progress(i/len(SYMBOLS),text=f"Fetching candles: {i}/{len(SYMBOLS)} — {symbol}")
    progress.empty()
    successful=[s for s in SYMBOLS if s in candle_cache and s in daily_cache]
    if "BTCUSD" not in successful: raise RuntimeError("BTCUSD data is required to calculate relative strength. Check API access and try again.")
    close_series={}
    for s in successful:
        d=candle_cache[s][["time","close"]].copy(); close_series[s]=d.drop_duplicates("time").set_index("time")["close"].sort_index()
    history=pd.concat(close_series,axis=1).sort_index().dropna(how="any")
    if len(history)<17: raise RuntimeError(f"Only {len(history)} synchronized completed candles; at least 17 are needed.")
    common=history.index[-1]
    returns={n:history.pct_change(n)*100 for n in [1,4,16]}
    rs=[]
    for s in history.columns:
        rs.append({"Symbol":s,"Close":float(history.loc[common,s]),"15m Relative Strength %":0.0 if s=="BTCUSD" else float(returns[1].loc[common,s]-returns[1].loc[common,"BTCUSD"]),"1h Relative Strength %":0.0 if s=="BTCUSD" else float(returns[4].loc[common,s]-returns[4].loc[common,"BTCUSD"]),"4h Relative Strength %":0.0 if s=="BTCUSD" else float(returns[16].loc[common,s]-returns[16].loc[common,"BTCUSD"])})
    strength=pd.DataFrame(rs)
    strength["Positive Strength Count"]=(strength[RS_COLS]>0).sum(axis=1)
    strength["Strength Category"]=strength["Positive Strength Count"].map({3:"STRONG — 3/3 PERIODS",2:"DEVELOPING — 2/3 PERIODS",1:"WEAK — 1/3 PERIODS",0:"NO POSITIVE PERIODS"})
    entries=[]; scan_errors=[]
    for s in successful:
        try:
            candles=candle_cache[s].copy(); candles=candles[candles.time<=common].sort_values("time").reset_index(drop=True)
            if len(candles)<50: raise RuntimeError("Insufficient completed 15m history")
            daily=daily_cache[s].copy(); today=pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d")
            completed=daily[daily.time.dt.strftime("%Y-%m-%d")<today]
            if completed.empty: raise RuntimeError("No previous completed UTC daily candle")
            pv=pivots(completed.iloc[-1]); candles["EMA9"]=candles.close.ewm(span=9,adjust=False).mean(); candles["EMA21"]=candles.close.ewm(span=21,adjust=False).mean()
            row=candles[candles.time==common]
            if row.empty: raise RuntimeError("No candle at synchronized timestamp")
            last=row.iloc[-1]; close=float(last.close); e9=float(last.EMA9); e21=float(last.EMA21); P=pv["Pivot"]; R4=pv["R4"]; S4=pv["S4"]
            bp=(close-P)/(R4-P)*100 if R4!=P else np.nan; sp=(P-close)/(P-S4)*100 if P!=S4 else np.nan
            bull=close>P and e9>e21 and 0<bp<=5; bear=close<P and e9<e21 and 0<sp<=5
            entries.append({"Symbol":s,"Candle UTC":common,"Pivot Source Date":pv["Pivot Source Date"],"Close":close,"EMA9":e9,"EMA21":e21,"Pivot":P,"R1":pv["R1"],"R2":pv["R2"],"R3":pv["R3"],"R4":R4,"R5":pv["R5"],"S1":pv["S1"],"S2":pv["S2"],"S3":pv["S3"],"S4":S4,"S5":pv["S5"],"Bullish %":bp,"Bearish %":sp,"Signal":"BULLISH EARLY" if bull else ("BEARISH EARLY" if bear else "NO SETUP")})
        except Exception as exc: scan_errors.append({"Symbol":s,"Error":str(exc)})
    df=pd.DataFrame(entries)
    if df.empty: raise RuntimeError("No entry results could be calculated.")
    # The entry table already contains Close; drop the duplicate Close from RS data before merging.
    strength = strength.drop(columns=["Close"], errors="ignore")
    df=df.merge(strength,on="Symbol",how="left")
    df["RS Aligned"]=(((df.Signal=="BULLISH EARLY")&(df[RS_COLS]>0).all(axis=1))|((df.Signal=="BEARISH EARLY")&(df[RS_COLS]<0).all(axis=1)))
    df["Priority"]=np.where(df["RS Aligned"]&(df.Signal!="NO SETUP"),"PRIORITY",np.where(df.Signal!="NO SETUP","ENTRY — RS NOT FULLY ALIGNED","NO SETUP"))
    df["Priority Rank"]=df.Priority.map({"PRIORITY":0,"ENTRY — RS NOT FULLY ALIGNED":1,"NO SETUP":2})
    df=df.sort_values(["Priority Rank","Positive Strength Count","15m Relative Strength %"],ascending=[True,False,False]).drop(columns="Priority Rank").reset_index(drop=True)
    return df, errors, scan_errors, common, len(history)

st.info("Free hosting can sleep or restart. This dashboard refreshes while the hosted app is active; continuous 24/7 scanning is not guaranteed on free plans.")
if st.button("Refresh scan now", type="primary"):
    st.cache_data.clear()

with st.spinner("Scanning 28 symbols using public Delta Exchange candle data…"):
    try:
        dashboard, fetch_errors, scan_errors, common_time, history_count = run_scan()
        st.caption(f"Last completed candle (UTC): {common_time} · Last page refresh (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} · Synchronized candles: {history_count}")
        c1,c2,c3,c4=st.columns(4)
        c1.metric("Symbols scanned",f"{len(dashboard)}/28")
        c2.metric("Priority",int((dashboard.Priority=="PRIORITY").sum()))
        c3.metric("Entry, RS incomplete",int((dashboard.Priority=="ENTRY — RS NOT FULLY ALIGNED").sum()))
        c4.metric("No setup",int((dashboard.Priority=="NO SETUP").sum()))
        mode=st.radio("View",["All symbols","Priority only","Entry signals"],horizontal=True)
        shown=dashboard
        if mode=="Priority only": shown=dashboard[dashboard.Priority=="PRIORITY"]
        elif mode=="Entry signals": shown=dashboard[dashboard.Signal!="NO SETUP"]
        show_rs = st.checkbox("Show Relative Strength details", value=False)
        shown = shown.copy().reset_index(drop=True)
        shown.insert(0, "S.No", range(1, len(shown) + 1))
        cols=["S.No","Symbol","Candle UTC","Close","EMA9","EMA21","Pivot",
              "R1","R2","R3","R4","R5","S1","S2","S3","S4","S5",
              "Bullish %","Bearish %","Signal"]
        if show_rs:
            cols += [*RS_COLS,"Positive Strength Count","Strength Category","RS Aligned"]
        cols += ["Priority"]
        def color_signal(row):
            signal = str(row.get("Signal", ""))
            if signal in ("BULLISH EARLY", "BEARISH EARLY"):
                return ["background-color: #d9f2df; color: #14532d"] * len(row)
            if signal == "NO SETUP":
                return ["background-color: #eeeeee; color: #555555"] * len(row)
            return [""] * len(row)
        styled = shown[cols].round(4).style.apply(color_signal, axis=1)
        st.dataframe(styled, use_container_width=True, hide_index=True)
        st.subheader("Signal counts")
        st.dataframe(dashboard.groupby(["Signal","Priority"]).size().reset_index(name="Count"),use_container_width=True,hide_index=True)
        if fetch_errors:
            with st.expander(f"Data fetch errors ({len(fetch_errors)})"): st.dataframe(pd.DataFrame(fetch_errors),use_container_width=True,hide_index=True)
        if scan_errors:
            with st.expander(f"Calculation errors ({len(scan_errors)})"): st.dataframe(pd.DataFrame(scan_errors),use_container_width=True,hide_index=True)
        st.caption("Relative strength compares each coin’s return with BTC’s return over 15m, 1h and 4h. Priority is a screening label, not a prediction. Observation only — no orders placed.")
    except Exception as exc:
        st.error(f"Scan could not complete: {exc}")
        st.warning("Try refreshing the page. If this repeats, check the hosting logs and Delta Exchange public API availability.")

# Streamlit Cloud re-runs this app on page reload; refresh_interval is handled by the browser component.
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=15*60*1000, key="delta_auto_refresh")
except Exception:
    st.caption("Automatic browser refresh component unavailable. Use ‘Refresh scan now’ or refresh the page.")
