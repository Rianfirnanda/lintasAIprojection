"""Sementara: memeriksa alamat data BMKG, PIHPS, dan Bapanas dari mesin GitHub (bukan untuk digabung)."""
import json, sys, urllib.request, urllib.error
from datetime import date, timedelta

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128 Safari/537.36",
      "Accept": "application/json, text/plain, */*", "X-Requested-With": "XMLHttpRequest"}
hari = date.today()
d1, d0 = hari.strftime("%Y-%m-%d"), (hari - timedelta(days=7)).strftime("%Y-%m-%d")
URL = [
    "https://www.bi.go.id/hargapangan/WebSite/Home/GetRegencyAll?province_id=7",
    "https://www.bi.go.id/hargapangan/WebSite/TabelHarga/GetRegencyAll?province_id=7",
    f"https://www.bi.go.id/hargapangan/WebSite/TabelHarga/GetGridDataDaerah?price_type_id=1&comcat_id=&province_id=7&regency_id=&market_id=&tipe_laporan=1&start_date={(hari - timedelta(days=120)).isoformat()}&end_date={d1}",
    "https://panelharga.badanpangan.go.id/",
    "https://api-panelhargav2.badanpangan.go.id/",
    "https://badanpangan.go.id/",
]
for u in URL + sys.argv[1:]:
    try:
        req = urllib.request.Request(u, headers=UA)
        with urllib.request.urlopen(req, timeout=20) as r:
            isi = r.read().decode("utf-8", "replace")
            print(f"== {r.status} {u}\n{isi[:700] + ' ... ' + isi[-300:] + f' [panjang {len(isi)}]'}\n", flush=True)
    except urllib.error.HTTPError as e:
        print(f"== HTTP {e.code} {u}\n{e.read().decode('utf-8','replace')[:400]}\n", flush=True)
    except Exception as e:
        print(f"== GAGAL {u}: {e!r}\n", flush=True)
