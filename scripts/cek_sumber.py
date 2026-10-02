"""Sementara: memeriksa alamat data BMKG, PIHPS, dan Bapanas dari mesin GitHub (bukan untuk digabung)."""
import json, sys, urllib.request, urllib.error
from datetime import date, timedelta

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128 Safari/537.36",
      "Accept": "application/json, text/plain, */*", "X-Requested-With": "XMLHttpRequest"}
hari = date.today()
d1, d0 = hari.strftime("%Y-%m-%d"), (hari - timedelta(days=7)).strftime("%Y-%m-%d")
URL = [
    "https://api.bmkg.go.id/publik/prakiraan-cuaca?adm4=17.09.01.2001",
    "https://api.bmkg.go.id/publik/prakiraan-cuaca?adm4=17.09.01.1001",
    "https://api.bmkg.go.id/publik/prakiraan-cuaca?adm4=17.09.06.2001",
    "https://api.bmkg.go.id/publik/prakiraan-cuaca?adm4=17.71.01.1001",
    "https://www.bi.go.id/hargapangan/WebSite/Home/GetProvinceAll",
    "https://www.bi.go.id/hargapangan/WebSite/Home/GetRegencyAll",
    "https://www.bi.go.id/hargapangan/WebSite/Home/GetCommoditiesTree",
    f"https://www.bi.go.id/hargapangan/WebSite/TabelHarga/GetGridDataDaerah?price_type_id=1&comcat_id=&province_id=7&regency_id=&market_id=&tipe_laporan=1&start_date={d0}&end_date={d1}",
    f"https://www.bi.go.id/hargapangan/WebSite/Home/GetGridData1?tanggal={d1}&commodity=&priceType=1&isPasokan=1&jenis=1&periode=1&provId=7",
    "https://api-panelhargav2.badanpangan.go.id/api/province",
    "https://api-panelhargav2.badanpangan.go.id/api/city?province_id=",
    "https://api-panelhargav2.badanpangan.go.id/api/front/harga-pangan-informasi?province_id=&city_id=&level_harga_id=3",
    "https://api-panelhargav2.badanpangan.go.id/api/front/komoditas",
    "https://api-panelhargav2.badanpangan.go.id/api/front/harga-pangan-table-provinsi?province_id=&level_harga_id=3",
]
for u in URL + sys.argv[1:]:
    try:
        req = urllib.request.Request(u, headers=UA)
        with urllib.request.urlopen(req, timeout=40) as r:
            isi = r.read().decode("utf-8", "replace")
            print(f"== {r.status} {u}\n{isi[:1500]}\n", flush=True)
    except urllib.error.HTTPError as e:
        print(f"== HTTP {e.code} {u}\n{e.read().decode('utf-8','replace')[:400]}\n", flush=True)
    except Exception as e:
        print(f"== GAGAL {u}: {e!r}\n", flush=True)
