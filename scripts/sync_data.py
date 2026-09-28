# -*- coding: utf-8 -*-
"""同步中美宏观数据到 data/sync.json（本地与 GitHub Actions 通用）
FRED(圣路易斯联储) 22 系列 + 东方财富数据中心 12 报表 + 外汇 4 项
"""
import urllib.request, urllib.parse, json, time, sys, os, datetime

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
  "PAYEMS": {"name":"美国非农就业(千人)", "unit":"千人"},
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
                    if not (v != v):
                        dates.append(o["date"]); values.append(v)
            if dates:
                if len(dates) > 1300:
                    dates = dates[-1300:]; values = values[-1300:]
                out[sid] = {"dates": dates, "values": values}
                print("  FRED", sid, len(dates), dates[0], "~", dates[-1], values[-1])
            else:
                print("  FRED", sid, "EMPTY")
        except Exception as e:
            print("  FRED", sid, "ERR", e)
        time.sleep(0.6)
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
        "DINIW": "dxy",
        "fx_susdcny": "usdcny",
        "fx_seurusd": "eurusd",
        "fx_susdcnh": "usdcnh"
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

def main():
    print("== pull FRED ==")
    fred = pull_fred()
    print("== pull EMDC ==")
    emdc = pull_emdc()
    print("== pull FX ==")
    fx = pull_fx()
    payload = {
        "updated": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z"),
        "fred": fred, "emdc": emdc, "fx": fx
    }
    if sys.platform == "win32":
        out_path = r"D:\豆包工作文件\宏观金融指标看板\data\sync.json"
    else:
        out_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "sync.json"))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    print("WROTE", out_path, os.path.getsize(out_path), "bytes")
    print("FRED series:", len(fred), "| EMDC:", len(emdc), "| FX:", len(fx))

if __name__ == "__main__":
    main()
