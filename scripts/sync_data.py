# -*- coding: utf-8 -*-
"""同步中美宏观数据到 data/sync.json（本地与 GitHub Actions 通用）
FRED(圣路易斯联储) 22 系列 + 东方财富数据中心 12 报表 + 外汇 4 项
+ 历史K线（东财美股/A股/港股 + 新浪外汇 + 新浪全球期货，2020 起）
"""
import urllib.request, urllib.parse, json, time, sys, os, datetime, re

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) doubao-sync/1.0'}
FRED_KEY = "3bfcf47458e7e97a5a4ad69174d28fe0"

def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')

def fetch_json(url, timeout=30):
    return json.loads(fetch(url, timeout))

# ---------- FRED ----------
FRED_SERIES = {
  "DGS10": {"name":"美债10年期收益率", "unit":"%"},
  "DGS2":  {"name":"美债2年期收益率", "unit":"%"},
  "DGS30": {"name":"美债30年期收益率", "unit":"%"},
  "VIXCLS": {"name":"VIX恐慌指数", "unit":"点"},
  "GACDFSA066MSFRBPHI": {"name":"美国制造业景气(费城联储)", "unit":""},
  "M2SL": {"name":"美国M2货币供应量", "unit":"十亿美元"},
  "CPIAUCSL": {"name":"美国CPI(指数)", "unit":"1982-84=100"},
  "CPILFESL": {"name":"美国核心CPI(指数)", "unit":"1982-84=100"},
  "PPIFIS": {"name":"美国PPI(指数)", "unit":"1982=100"},
  "UNRATE": {"name":"美国失业率", "unit":"%"},
  "PAYEMS": {"name":"美国非农就业(万人)", "unit":"千人"},
  "HOUST": {"name":"美国新屋开工", "unit":"千套"},
  "RSAFS": {"name":"美国零售销售(百万美元)", "unit":"百万美元"},
  "TCU": {"name":"美国产能利用率", "unit":"%"},
  "PCEPILFE": {"name":"美国核心PCE(指数)", "unit":"2017=100"},
  "UMCSENT": {"name":"美国消费者信心", "unit":""},
  "FEDFUNDS": {"name":"美国联邦基金利率(月均)", "unit":"%"},
  "A191RL1Q225SBEA": {"name":"美国GDP环比年化", "unit":"%"},
  "INDPRO": {"name":"美国工业产出(指数)", "unit":"2017=100"},
  "BOPGSTB": {"name":"美国贸易逆差(货物服务)", "unit":"百万美元"},
  "MORTGAGE30US": {"name":"美国30年房贷利率", "unit":"%"},
  "ICSA": {"name":"美国当周初请失业金", "unit":"千人"},
  "CP0000EZ19M086NEST": {"name":"欧元区HICP(指数)", "unit":"2015=100"}
}

def pull_fred():
    out = {}
    for sid in FRED_SERIES:
        try:
            url = f"https://api.stlouisfed.org/fred/series/observations?series_id={sid}&api_key={FRED_KEY}&file_type=json&sort_order=asc&observation_start=2016-01-01&limit=100000"
            d = fetch_json(url)
            obs = d.get("observations", [])
            dates, values = [], []
            for o in obs:
                if o.get("value") not in (".", "", None):
                    v = float(o["value"])
                    if not (v != v):  # not NaN
                        dates.append(o["date"]); values.append(v)
            if dates:
                # 最多保留 1300 点
                if len(dates) > 1300:
                    dates = dates[-1300:]; values = values[-1300:]
                out[sid] = {"dates": dates, "values": values}
                print("  FRED", sid, len(dates), dates[0], "~", dates[-1], values[-1])
            else:
                print("  FRED", sid, "EMPTY")
        except Exception as e:
            print("  FRED", sid, "ERR", e)
        time.sleep(0.6)  # FRED 限流 120/min
    return out

# ---------- 东方财富数据中心 ----------
def emdc(report, filter=None, len_=360):
    params = {
        "reportName": report, "columns": "ALL", "pageSize": str(len_),
        "pageNumber": "1", "sortColumns": "REPORT_DATE", "sortTypes": "-1",
        "source": "WEB", "client": "WEB"
    }
    if filter: params["filter"] = filter
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get?" + urllib.parse.urlencode(params)
    d = fetch_json(url)
    if d.get("result") and d["result"].get("data"):
        return d["result"]["data"]
    return []

def pull_emdc():
    out = {}
    specs = [
        ("china_pmi", "RPT_ECONOMY_PMI", None, "MAKE_INDEX", 1),
        ("china_cpi", "RPT_ECONOMY_CPI", None, "NATIONAL_SAME", 1),
        ("china_ppi", "RPT_ECONOMY_PPI", None, "BASE_SAME", 1),
        ("china_m2", "RPT_ECONOMY_CURRENCY_SUPPLY", None, "BASIC_CURRENCY", 10000),
        ("china_exports", "RPT_ECONOMY_CUSTOMS", None, "EXIT_BASE_SAME", 1),
        ("china_imports", "RPT_ECONOMY_CUSTOMS", None, "IMPORT_BASE_SAME", 1),
        ("china_loan", "RPT_ECONOMY_RMB_LOAN", None, "RMB_LOAN", 1),
        ("china_gdp", "RPT_ECONOMY_GDP", None, "SUM_SAME", 1),
        ("bdi", "RPT_INDUSTRY_INDEX", '(INDICATOR_ID="EMI00107664")', "INDICATOR_VALUE", 1),
        ("bdti", "RPT_INDUSTRY_INDEX", '(INDICATOR_ID="EMI00107668")', "INDICATOR_VALUE", 1),
        ("bci", "RPT_INDUSTRY_INDEX", '(INDICATOR_ID="EMI00107666")', "INDICATOR_VALUE", 1),
        ("bcti", "RPT_INDUSTRY_INDEX", '(INDICATOR_ID="EMI00107669")', "INDICATOR_VALUE", 1),
    ]
    for key, report, filt, field, div in specs:
        try:
            rows = emdc(report, filt, 400)
            dates, values = [], []
            for r in reversed(rows):
                try:
                    v = float(r.get(field))
                except (TypeError, ValueError):
                    continue
                dates.append(str(r.get("REPORT_DATE", ""))[:10])
                values.append(round(v / div, 2))
            if dates:
                if len(dates) > 1300:
                    dates = dates[-1300:]; values = values[-1300:]
                out[key] = {"dates": dates, "values": values}
                print("  EMDC", key, len(dates), dates[0], "~", dates[-1], values[-1])
            else:
                print("  EMDC", key, "EMPTY")
        except Exception as e:
            print("  EMDC", key, "ERR", e)
        time.sleep(0.3)
    return out

# ---------- 外汇/指数（新浪行情，Python 伪造 Referer） ----------
def pull_fx():
    codes = {
        "DINIW": "dxy",        # 美元指数
        "fx_susdcny": "usdcny", # 美元/人民币(在岸)
        "fx_seurusd": "eurusd", # 欧元/美元
        "fx_susdcnh": "usdcnh"  # 美元/离岸人民币
    }
    out = {}
    list_str = ",".join(codes.keys())
    try:
        url = f"https://hq.sinajs.cn/list={list_str}"
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn/'
        })
        with urllib.request.urlopen(req, timeout=20) as r:
            text = r.read().decode('gbk', 'replace')
        for code, key in codes.items():
            m = text.split(f'var hq_str_{code}="')[1].split('"')[0]
            parts = m.split(",")
            if len(parts) >= 3:
                try:
                    price = float(parts[1])
                    chg = float(parts[12]) if len(parts) > 12 and parts[12] not in ("", "-") else float('nan')
                except ValueError:
                    price = float('nan'); chg = float('nan')
                out[key] = {"value": price, "chg": chg if chg == chg else None,
                            "time": int(time.time() * 1000)}
                print("  FX", key, out[key]["value"])
            else:
                print("  FX", key, "BAD_FORMAT")
    except Exception as e:
        print("  FX ERR", e)
    return out

# ---------- 历史K线（东财美股/A股/港股 + 新浪外汇 + 新浪全球期货） ----------
# 备源：美股失败切雅虎(Yahoo Finance)，A股/港股失败切腾讯K线（海外Actions环境东财中国链路易被风控）
def pull_yahoo_hist(key, sym):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?range=8y&interval=1d"
    d = fetch_json(url)
    r = (d.get("chart") or {}).get("result") or []
    if not r:
        return None
    ts = r[0].get("timestamp") or []
    quotes = ((r[0].get("indicators") or {}).get("quote") or [{}])
    closes = (quotes[0].get("close") if quotes else None) or []
    dates, values = [], []
    for i in range(len(ts)):
        c = closes[i] if i < len(closes) else None
        if c is None:
            continue
        try:
            v = float(c)
        except (TypeError, ValueError):
            continue
        if v == v:
            dstr = datetime.datetime.utcfromtimestamp(int(ts[i])).strftime("%Y-%m-%d")
            dates.append(dstr); values.append(v)
    if not dates:
        return None
    if len(dates) > 1300:
        dates = dates[-1300:]; values = values[-1300:]
    return {"dates": dates, "values": values}

def pull_tx_hist(key, code):
    param = f"{code},day,2020-01-01,2026-12-31,3200,qfq"
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={param}"
    d = fetch_json(url)
    data = d.get("data") or {}
    node = data.get(code)
    if not node and data:
        node = data[list(data.keys())[0]]
    if not node:
        return None
    arr = None
    for k in node:
        if isinstance(node[k], list) and node[k]:
            arr = node[k]; break
    if not arr:
        return None
    dates, values = [], []
    for row in arr:
        try:
            dates.append(row[0]); values.append(float(row[2]))
        except (IndexError, TypeError, ValueError):
            continue
    if not dates:
        return None
    if len(dates) > 1300:
        dates = dates[-1300:]; values = values[-1300:]
    return {"dates": dates, "values": values}

YAHOO_MAP = {"ndx": "%5EIXIC", "spx": "%5EGSPC", "djia": "%5EDJI"}
TX_MAP = {"sh000001": "sh000001", "sh000905": "sh000905", "sh000300": "sh000300",
          "sz399006": "sz399006", "hsi": "hkHSI"}

def pull_hist():
    out = {}
    em_secids = {
        "ndx": "100.NDX", "spx": "100.SPX", "djia": "100.DJIA",
        "sh000001": "1.000001", "sh000905": "1.000905", "sh000300": "1.000300",
        "sz399006": "0.399006", "hsi": "100.HSI",
    }
    for i, (key, secid) in enumerate(em_secids.items()):
        host = "push2his.eastmoney.com"
        for attempt in range(4):
            try:
                url = (f"https://{host}/api/qt/stock/kline/get?secid={secid}"
                       f"&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58"
                       f"&klt=101&fqt=1&beg=20200101&end=20261231")
                req = urllib.request.Request(url, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36',
                    'Referer': 'https://quote.eastmoney.com/'
                })
                with urllib.request.urlopen(req, timeout=25) as r:
                    d = json.loads(r.read().decode('utf-8', 'replace'))
                klines = (d.get("data") or {}).get("klines") or []
                dates, values = [], []
                for k in klines:
                    p = k.split(",")
                    if len(p) >= 3:
                        try:
                            dates.append(p[0]); values.append(float(p[2]))
                        except ValueError:
                            continue
                if dates:
                    if len(dates) > 1300:
                        dates = dates[-1300:]; values = values[-1300:]
                    out[key] = {"dates": dates, "values": values}
                    print("  HIST-EM", key, len(dates), dates[0], "~", dates[-1], values[-1])
                else:
                    print("  HIST-EM", key, "EMPTY")
                break
            except Exception as e:
                if attempt < 3:
                    time.sleep([3, 6, 10][attempt])
                    continue
                print("  HIST-EM", key, "ERR", str(e)[:80])
        time.sleep(2.5)
    # 第二轮补拉缺失的东财历史（风控偶发打掉单个key）
    for key in [k for k in em_secids if k not in out]:
        secid = em_secids[key]
        for attempt in range(3):
            try:
                url = (f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={secid}"
                       f"&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58"
                       f"&klt=101&fqt=1&beg=20200101&end=20261231")
                req = urllib.request.Request(url, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36',
                    'Referer': 'https://quote.eastmoney.com/'
                })
                with urllib.request.urlopen(req, timeout=25) as r:
                    d = json.loads(r.read().decode('utf-8', 'replace'))
                klines = (d.get("data") or {}).get("klines") or []
                dates, values = [], []
                for k in klines:
                    p = k.split(",")
                    if len(p) >= 3:
                        try:
                            dates.append(p[0]); values.append(float(p[2]))
                        except ValueError:
                            continue
                if dates:
                    if len(dates) > 1300:
                        dates = dates[-1300:]; values = values[-1300:]
                    out[key] = {"dates": dates, "values": values}
                    print("  HIST-EM-RETRY", key, len(dates), dates[0], "~", dates[-1], values[-1])
                break
            except Exception as e:
                if attempt < 2:
                    time.sleep(8)
                    continue
                print("  HIST-EM-RETRY", key, "ERR", str(e)[:80])
        time.sleep(2)
    # 第三轮：东财仍缺失的键走备源（美股→雅虎，A股/港股→腾讯K线）
    for key in [k for k in em_secids if k not in out]:
        h = None
        try:
            if key in YAHOO_MAP:
                h = pull_yahoo_hist(key, YAHOO_MAP[key])
                print("  HIST-YH", key, "OK" if h else "EMPTY", h and len(h["dates"]))
            elif key in TX_MAP:
                h = pull_tx_hist(key, TX_MAP[key])
                print("  HIST-TX", key, "OK" if h else "EMPTY", h and len(h["dates"]))
        except Exception as e:
            print("  HIST-FALLBACK", key, "ERR", str(e)[:80])
        if h and h["dates"]:
            out[key] = h
        time.sleep(1)
    fx_syms = {"diniw": "DINIW", "usdcny": "USDCNY", "usdcnh": "USDCNH", "eurusd": "EURUSD"}
    for key, sym in fx_syms.items():
        try:
            cb = "_h" + str(int(time.time() * 1000))
            url = (f"https://vip.stock.finance.sina.com.cn/forex/api/jsonp.php/var%20{cb}="
                   f"/NewForexService.getDayKLine?symbol={sym}&_={int(time.time() * 1000)}")
            t = fetch(url)
            m = re.search(r'=\s*\((.*)\)\s*;?\s*$', t, re.S)
            if not m:
                print("  HIST-FX", key, "BAD", t[:100]); continue
            dates, values = [], []
            for row in m.group(1).split("|"):
                p = row.split(",")
                if len(p) >= 5 and p[0].strip():
                    try:
                        v = float(p[4])
                    except ValueError:
                        continue
                    if p[0].strip() >= "2020-01-01":
                        dates.append(p[0].strip()); values.append(v)
            if dates:
                if len(dates) > 1300:
                    dates = dates[-1300:]; values = values[-1300:]
                out[key] = {"dates": dates, "values": values}
                print("  HIST-FX", key, len(dates), dates[0], "~", dates[-1], values[-1])
            else:
                print("  HIST-FX", key, "EMPTY")
        except Exception as e:
            print("  HIST-FX", key, "ERR", e)
        time.sleep(0.4)
    fut_syms = {"gc": "GC", "si": "SI", "oil": "OIL", "cl": "CL", "hg": "HG", "c": "C", "s": "S"}
    for key, sym in fut_syms.items():
        try:
            cb = "_f" + str(int(time.time() * 1000))
            url = (f"https://stock.finance.sina.com.cn/futures/api/jsonp.php/var%20{cb}="
                   f"/GlobalFuturesService.getGlobalFuturesDailyKLine?symbol={sym}")
            t = fetch(url)
            m = re.search(r'=\s*\(?(\[.*\])\s*\)?\s*;?\s*$', t, re.S)
            if not m:
                print("  HIST-FUT", key, "BAD", t[:100]); continue
            arr = json.loads(m.group(1))
            dates, values = [], []
            for o in arr:
                d = str(o.get("date", ""))
                if d >= "2020-01-01":
                    try:
                        dates.append(d); values.append(float(o.get("close", 0)))
                    except (TypeError, ValueError):
                        continue
            if dates:
                if len(dates) > 1300:
                    dates = dates[-1300:]; values = values[-1300:]
                out[key] = {"dates": dates, "values": values}
                print("  HIST-FUT", key, len(dates), dates[0], "~", dates[-1], values[-1])
            else:
                print("  HIST-FUT", key, "EMPTY")
        except Exception as e:
            print("  HIST-FUT", key, "ERR", e)
        time.sleep(0.4)
    return out

def main():
    print("== pull FRED ==")
    fred = pull_fred()
    print("== pull EMDC ==")
    emdc = pull_emdc()
    print("== pull FX ==")
    fx = pull_fx()
    print("== pull HIST ==")
    hist = pull_hist()
    payload = {
        "updated": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z"),
        "fred": fred, "emdc": emdc, "fx": fx, "hist": hist
    }
    if sys.platform == "win32":
        out_path = r"D:\豆包工作文件\宏观金融指标看板\data\sync.json"
    else:
        out_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "sync.json"))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    print("WROTE", out_path, os.path.getsize(out_path), "bytes")
    print("FRED series:", len(fred), "| EMDC:", len(emdc), "| FX:", len(fx), "| HIST:", len(hist))

if __name__ == "__main__":
    main()
