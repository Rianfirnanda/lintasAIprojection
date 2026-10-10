"""Berita lokal harian: umpan RSS, pembacaan halaman, ekstraksi harga, ringkasan, dan jadwal otomatis.

Semua uji memakai berkas tiruan (tanpa jaringan). Pengambilan halaman, Tavily, dan AI diganti fungsi palsu."""

from __future__ import annotations

import json
import urllib.error
from datetime import date, datetime, timedelta, timezone

import pytest

from pipeline import __main__ as m
from pipeline import berita
from pipeline import firestore_sinkron as fs
from pipeline import pencari_data

from .test_firestore_sinkron import DBTiruan

WIB = berita.WIB
SEKARANG = datetime(2026, 10, 9, 9, 0, tzinfo=WIB)  # Jumat

RSS_GOOGLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>harga cabai Bengkulu - Google Berita</title>
<item><title>Harga Cabai Rawit Naik di Bengkulu Tengah - RRI Bengkulu</title>
<link>https://news.google.com/rss/articles/CBMiAAA?oc=5</link>
<pubDate>Thu, 08 Oct 2026 03:00:00 GMT</pubDate>
<description>&lt;a href="https://news.google.com/x"&gt;Harga Cabai Rawit Naik di Bengkulu Tengah&lt;/a&gt;&amp;nbsp;&amp;nbsp;&lt;font&gt;RRI Bengkulu&lt;/font&gt;</description>
<source url="https://rri.co.id">RRI Bengkulu</source></item>
<item><title>Final Piala Dunia Antarklub Digelar - Bola Net</title>
<link>https://news.google.com/rss/articles/CBMiBBB?oc=5</link>
<pubDate>Thu, 08 Oct 2026 04:00:00 GMT</pubDate>
<source url="https://bola.net">Bola Net</source></item>
<item><title>Harga Beras Lama di Bengkulu - Koran Lama</title>
<link>https://news.google.com/rss/articles/CBMiCCC?oc=5</link>
<pubDate>Mon, 01 Jan 2024 03:00:00 GMT</pubDate>
<source url="https://koranlama.id">Koran Lama</source></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Portal</title>
<entry><title>Pasar murah digelar Disdag Bengkulu Tengah</title>
<link href="https://portal.example/berita/pasar-murah"/>
<updated>2026-10-07T08:30:00+07:00</updated>
<summary>Pasar murah sembako digelar.</summary></entry></feed>"""

ARTIKEL = """<html><head><title>Cabai Rawit Rp 85 Ribu | Portal Bengkulu</title>
<meta property="og:title" content="Harga Cabai Rawit Merah Tembus Rp 85.000 per Kg di Bengkulu Tengah">
<meta property="article:published_time" content="2026-10-08T10:15:00+07:00"></head>
<body><nav><p>Menu utama navigasi situs berita yang panjang sekali tetapi bukan isi artikel sama sekali.</p></nav>
<article>
<p>BENGKULU TENGAH - Harga cabai rawit merah di Pasar Karang Nanding, Bengkulu Tengah, naik menjadi Rp 85.000 per kilogram pada Kamis (8/10/2026).</p>
<p>Menurut pedagang, kenaikan sebesar Rp 10.000 per kg ini terjadi karena banjir di sentra produksi mengganggu pasokan cabai ke pasar.</p>
<p>Harga bawang merah relatif stabil di kisaran Rp32.000 - Rp35.000 per kg. Telur ayam ras dijual Rp 2.500 per butir di pasar yang sama.</p>
<p>Dinas Perdagangan menyiapkan operasi pasar untuk menahan kenaikan harga pangan di Bengkulu Tengah pekan depan.</p>
</article>
<footer><p>Hak cipta portal bengkulu, seluruh isi dilindungi, dilarang menyalin tanpa izin tertulis.</p></footer>
<script>var harga = "Rp 99.000 per kg cabai";</script></body></html>"""

ROBOTS_BEBAS = b"User-agent: *\nDisallow: /privat/\n"


class Web:
    """Pengambil halaman palsu: {url: (isi, jenis)} atau {url: kode galat HTTP}. Mencatat semua permintaan."""

    def __init__(self, halaman: dict, awalan: dict | None = None):
        self.halaman, self.awalan, self.dipanggil = halaman, awalan or {}, []

    def __call__(self, url, batas_waktu=20, maks_byte=2 * 1024 * 1024):
        self.dipanggil.append(url)
        sumber = self.halaman.get(url)
        if sumber is None:
            for a, v in self.awalan.items():
                if url.startswith(a):
                    sumber = v
        if sumber is None:
            raise urllib.error.HTTPError(url, 404, "tidak ada", {}, None)
        if isinstance(sumber, int):
            raise urllib.error.HTTPError(url, sumber, "galat", {}, None)
        isi, jenis = sumber
        return url, isi, jenis


def _jawab_gemini(objek):
    return lambda url, header, isi: {"candidates": [{"content": {"parts": [{"text": json.dumps(objek)}]}}], "modelVersion": "gemini-palsu"}


def _jawab_openai(objek):
    return lambda url, header, isi: {"choices": [{"message": {"content": json.dumps(objek)}}], "model": "groq-palsu"}


# ---------------------------------------------------------------- umpan dan tautan

def test_rss_google_berita_dibaca_dengan_sumber_dan_tanggal():
    hasil = berita.baca_rss(RSS_GOOGLE, "google_berita")
    assert len(hasil) == 3
    a = hasil[0]
    assert a["judul"] == "Harga Cabai Rawit Naik di Bengkulu Tengah" and a["sumber"] == "RRI Bengkulu"
    assert a["tanggal"] == date(2026, 10, 8) and a["cuplikan"] == ""  # deskripsi Google hanya mengulang judul
    assert a["via"] == "google_berita" and a["url"].startswith("https://news.google.com/rss/articles/")


def test_atom_dibaca():
    (a,) = berita.baca_rss(ATOM, "rss")
    assert a["url"] == "https://portal.example/berita/pasar-murah" and a["tanggal"] == date(2026, 10, 7)
    assert a["cuplikan"] == "Pasar murah sembako digelar."


def test_umpan_dengan_doctype_atau_entity_ditolak():
    jahat = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><rss><channel><item><title>&a;</title><link>https://a.id/x</link></item></channel></rss>'
    with pytest.raises(ValueError, match="DOCTYPE"):
        berita.baca_rss(jahat)


def test_tanggal_dari_berbagai_format():
    assert berita.parse_tanggal("Thu, 08 Oct 2026 20:00:00 GMT") == date(2026, 10, 9)  # sudah lewat tengah malam WIB
    assert berita.parse_tanggal("2026-10-08T10:15:00+07:00") == date(2026, 10, 8)
    assert berita.parse_tanggal("2026-10-08T23:30:00Z") == date(2026, 10, 9)
    assert berita.parse_tanggal("Diterbitkan 2026-10-05 pukul 09.00") == date(2026, 10, 5)
    assert berita.parse_tanggal("") is None and berita.parse_tanggal("kemarin") is None


def test_url_kanonik_membuang_pelacak_dan_menyatukan_berita():
    a = berita.kanonik("https://www.Portal.id/berita/cabai/?utm_source=wa&id=7&fbclid=x#komentar")
    assert a == "https://portal.id/berita/cabai?id=7"
    assert berita.id_berita("https://portal.id/berita/cabai/?id=7&utm_medium=x") == berita.id_berita("https://www.portal.id/berita/cabai?id=7")
    # tautan Google Berita: kunci artikel ada di path, query diabaikan
    assert berita.kanonik("https://news.google.com/rss/articles/CBMiX?oc=5") == "https://news.google.com/rss/articles/CBMiX"


def test_gabung_unik_menyatukan_url_dan_judul_sama():
    def b(judul, url, via, teks="", tgl=None):
        return {"judul": judul, "url": url, "sumber": "", "tanggal": tgl, "cuplikan": "", "teks": teks, "via": via}

    daftar = [b("Harga Cabai Naik di Bengkulu", "https://a.id/x?utm_source=q", "google_berita"),
              b("Harga cabai naik di Bengkulu!", "https://b.id/lain", "rss", tgl=date(2026, 10, 8)),
              b("Berita lain", "https://a.id/x", "tavily", teks="isi panjang", tgl=date(2026, 10, 7))]
    hasil = berita.gabung_unik(daftar)
    assert len(hasil) == 1
    assert hasil[0]["via"] == ["google_berita", "rss", "tavily"] and hasil[0]["teks"] == "isi panjang"
    assert hasil[0]["tanggal"] == date(2026, 10, 8)


# ---------------------------------------------------------------- robots.txt dan halaman

def test_robots_mengikuti_aturan_dan_gagal_dengan_aman():
    web = Web({"https://ok.id/robots.txt": (ROBOTS_BEBAS, "text/plain"), "https://tutup.id/robots.txt": (b"User-agent: *\nDisallow: /\n", "text/plain"),
               "https://kita.id/robots.txt": (b"User-agent: LintasBentengBot\nDisallow: /\n\nUser-agent: *\nDisallow:\n", "text/plain"),
               "https://rusak.id/robots.txt": 503, "https://tanpa.id/robots.txt": 404})
    r = berita.Robots(web)
    assert r.boleh("https://ok.id/berita/1") and not r.boleh("https://ok.id/privat/1")
    assert not r.boleh("https://tutup.id/apa-saja")
    assert not r.boleh("https://kita.id/berita")  # aturan khusus untuk bot ini menang
    assert not r.boleh("https://rusak.id/berita")  # 5xx: anggap dilarang
    assert r.boleh("https://tanpa.id/berita")  # 4xx: tidak ada aturan
    def putus(*a):
        raise OSError("jaringan putus")

    assert not berita.Robots(putus).boleh("https://mati.id/x")  # tidak bisa memastikan: anggap dilarang
    n = len(web.dipanggil)
    r.boleh("https://ok.id/berita/2")
    assert len(web.dipanggil) == n  # robots.txt per situs hanya diunduh sekali
    assert berita.Robots(web, aktif=False).boleh("https://tutup.id/x")


def test_ekstrak_halaman_hanya_isi_artikel():
    h = berita.ekstrak_halaman(ARTIKEL.encode(), "text/html; charset=utf-8")
    assert h["judul"] == "Harga Cabai Rawit Merah Tembus Rp 85.000 per Kg di Bengkulu Tengah"
    assert h["tanggal"] == date(2026, 10, 8)
    assert "Karang Nanding" in h["teks"] and "operasi pasar" in h["teks"]
    assert "navigasi" not in h["teks"] and "Hak cipta" not in h["teks"] and "99.000" not in h["teks"]


def test_ekstrak_halaman_tanpa_tag_article_memakai_semua_paragraf():
    html = "<html><body>" + "".join(f"<p>Paragraf nomor {i} berisi kalimat yang cukup panjang untuk dihitung sebagai isi.</p>" for i in range(6)) + "</body></html>"
    h = berita.ekstrak_halaman(html.encode())
    assert h["teks"].count("\n") == 5 and len(h["teks"]) > berita.MIN_TEKS_TERBACA


def _b(url="https://portal.id/a", teks=""):
    return {"judul": "Harga cabai", "url": url, "sumber": "", "tanggal": None, "cuplikan": "", "teks": teks, "via": ["rss"]}


def test_baca_halaman_berhasil_dan_melengkapi_data():
    web = Web({"https://portal.id/robots.txt": (ROBOTS_BEBAS, "text/plain"), "https://portal.id/a": (ARTIKEL.encode(), "text/html; charset=utf-8")})
    b = _b()
    assert berita.baca_halaman(b, berita.Robots(web), web) == ""
    assert "Karang Nanding" in b["teks"] and b["sumber"] == "portal.id" and b["tanggal"] == date(2026, 10, 8)


@pytest.mark.parametrize("halaman,harapan", [
    ({"https://portal.id/robots.txt": (b"User-agent: *\nDisallow: /\n", "text/plain")}, "robots.txt melarang"),
    ({"https://portal.id/robots.txt": 404, "https://portal.id/a": 403}, "gagal diunduh: HTTPError"),
    ({"https://portal.id/robots.txt": 404, "https://portal.id/a": (b"%PDF", "application/pdf")}, "bukan halaman HTML"),
    ({"https://portal.id/robots.txt": 404, "https://portal.id/a": (b"<html><body><p>Pendek.</p></body></html>", "text/html")}, "isi artikel tidak terbaca"),
])
def test_baca_halaman_gagal_dengan_catatan_jelas(halaman, harapan):
    web = Web(halaman)
    b = _b()
    assert harapan in berita.baca_halaman(b, berita.Robots(web), web)
    assert b["teks"] == ""


def test_baca_halaman_tautan_google_berita_tidak_dianggap_artikel():
    url = "https://news.google.com/rss/articles/CBMiAAA"
    web = Web({"https://news.google.com/robots.txt": 404, url: (b"<html><body>JS</body></html>", "text/html")})
    assert "Google Berita" in berita.baca_halaman(_b(url), berita.Robots(web), web)


def test_baca_halaman_yang_sudah_ada_isinya_tidak_diunduh_lagi():
    web = Web({})
    assert berita.baca_halaman(_b(teks="x" * 300), berita.Robots(web), web) == "" and web.dipanggil == []


# ---------------------------------------------------------------- relevansi dan harga

def test_relevansi_dan_tag(konf):
    a = berita.analisis_isi("Harga cabai rawit naik di Bengkulu Tengah", "Banjir mengganggu pasokan. Operasi pasar disiapkan TPID.", konf)
    assert a["relevansi"] == "tinggi" and a["wilayah"]["target"] and "Cabai Rawit" in a["komoditas"]
    assert {"harga_naik", "cuaca", "intervensi"} <= set(a["tag"])
    b = berita.analisis_isi("Harga beras di Kepahiang stabil", "Pedagang di Kepahiang menjual beras medium.", konf)
    assert b["relevansi"] in ("sedang", "rendah") and b["wilayah"]["pembanding"] == ["kepahiang"] and not b["wilayah"]["target"]
    assert berita.analisis_isi("Final sepak bola digelar", "Pertandingan berlangsung di Jakarta.", konf)["relevansi"] == "tidak"
    # Wilayah ada tetapi topiknya bukan pangan, dan topik pangan tanpa wilayah Bengkulu: dibuang
    assert berita.analisis_isi("Bupati Bengkulu Tengah membuka festival", "Acara budaya di Bengkulu Tengah.", konf)["relevansi"] == "tidak"
    assert berita.analisis_isi("Harga cabai naik di Surabaya", "Pedagang di Surabaya menaikkan harga cabai.", konf)["relevansi"] == "tidak"


def test_kata_bengkulu_di_bagian_bawah_halaman_tidak_membuat_berita_daerah_lain_relevan(konf):
    kurs = "USD/IDR 16.200 EUR/IDR 19.935 JPY/IDR 10.838 SGD/IDR 12.100 " * 30
    bawah = f"{kurs}\nDaftar provinsi: Aceh, Bengkulu, Jambi, Lampung."
    teks = f"Harga cabai merah naik menjadi Rp65.790 per kg. Harga bawang merah turun. {bawah}"
    assert berita.analisis_isi("Harga Pangan Hari Ini di Jawa Barat", teks, konf)["relevansi"] == "tidak"
    # di judul atau paragraf awal tetap dihitung
    assert berita.analisis_isi("Harga cabai di Bengkulu naik", teks, konf)["relevansi"] != "tidak"
    awal = "Harga cabai merah dan bawang merah di pasar Bengkulu naik pekan ini, kata pedagang. " + kurs
    assert berita.analisis_isi("Harga pangan pekan ini", awal, konf)["relevansi"] != "tidak"


def test_kutipan_memilih_kalimat_berita_bukan_tabel_kurs():
    kurs = "13.361 CAD/IDR 12.349 CHF/IDR 21.861 CNH/IDR 2.461 CNY/IDR 2.460 DKK/IDR 2.668 EUR/IDR 19.935"
    berita_ = "Komoditas cabai merah keriting naik paling tinggi Rp1.673 (2,61%) menjadi Rp65.790 per kg."
    assert berita.kutipan_dari(kurs, f"{kurs}\n{berita_}\nParagraf lain.") == berita_
    assert berita.kutipan_dari("Pemkab menggelar pasar murah di tiga kecamatan pekan ini.", "isi") == "Pemkab menggelar pasar murah di tiga kecamatan pekan ini."
    assert berita.kutipan_dari(kurs, kurs) == ""
    assert berita.kutipan_dari("", "") == ""


def test_workflow_manual_antre_bersama_pembaruan_harian():
    import re

    from tests.conftest import AKAR

    def kelompok(nama):
        return re.search(r"concurrency:\s+group: (\S+)", (AKAR / ".github/workflows" / nama).read_text(encoding="utf-8")).group(1)

    assert kelompok("berita.yml") == kelompok("pipeline.yml")  # keduanya menulis data/berita/berita.json


def _harga(teks, konf):
    return berita.ekstrak_harga(teks, konf)


def test_harga_dengan_satuan_varian_dan_wilayah(konf):
    (h,) = _harga("Harga cabai rawit merah di Pasar Karang Nanding, Bengkulu Tengah, naik menjadi Rp 85.000 per kilogram pada Kamis.", konf)
    assert (h["kode_varian"], h["kode_komoditas"], h["nilai"], h["satuan"], h["status"]) == ("CRW02", "CRW", 85000, "kg", "kandidat")
    assert h["peran_wilayah"] == "target" and "Rp 85.000" in h["bukti"]


def test_harga_alias_terpanjang_menang(konf):
    (h,) = _harga("Telur ayam ras dijual Rp 31.000/kg di Kota Bengkulu.", konf)
    assert h["kode_komoditas"] == "TLR" and h["peran_wilayah"] == "pembanding"
    (h,) = _harga("Harga ayam ras mencapai Rp 38.000 per kg.", konf)
    assert h["kode_komoditas"] == "DAY"


def test_harga_rentang_ribu_dan_kata_hubung(konf):
    hasil = _harga("Bawang merah Rp32.000 - Rp35.000 per kg, sedangkan beras medium Rp 14 ribu per kg di Kepahiang.", konf)
    assert [(h["kode_komoditas"], h["nilai"]) for h in hasil] == [("BWM", 32000), ("BWM", 35000), ("BRS", 14000)]
    assert [h["nilai"] for h in _harga("Gula pasir Rp 17.000 sampai Rp 18.500 per kilogram.", konf)] == [17000, 18500]


def test_harga_yang_bukan_harga_diabaikan(konf):
    teks = ("Kenaikan sebesar Rp 5.000 per kg terjadi pada cabai merah. "          # selisih
            "Telur ayam ras kini Rp 2.500 per butir. "                              # bukan kg/liter
            "Dana Rp 50 juta disiapkan untuk operasi pasar beras. "                 # bukan harga satuan
            "Rp 40.000 per kg dijual di pasar tanpa menyebut barangnya. "           # tanpa komoditas
            "Harga cabai turun, pedagang rugi.")                                    # tanpa angka
    assert _harga(teks, konf) == []


def test_harga_di_luar_batas_wajar_ditolak_bukan_dibuang(konf):
    hasil = _harga("Minyak goreng curah Rp 90 per liter. Cabai rawit merah Rp 9.000.000 per kg.", konf)
    assert [h["status"] for h in hasil] == ["ditolak: di luar batas wajar"] * 2


def test_harga_nasional_dan_tidak_jelas_diberi_label_wilayah(konf):
    assert _harga("Rata-rata nasional beras medium Rp 14.000 per kg.", konf)[0]["peran_wilayah"] == "nasional"
    assert _harga("Beras medium Rp 14.000 per kg.", konf)[0]["peran_wilayah"] == "tidak jelas"
    assert _harga("Beras medium di Provinsi Bengkulu Rp 14.000 per kg.", konf)[0]["peran_wilayah"] == "provinsi"


def test_harga_duplikat_dalam_satu_berita_digabung(konf):
    teks = "Cabai rawit merah Rp 85.000 per kg. Kemarin cabai rawit merah Rp 85.000 per kg juga."
    assert len(_harga(teks, konf)) == 1


# ---------------------------------------------------------------- pemeriksaan angka dan ringkasan

def test_ringkasan_ai_dengan_angka_karangan_dibuang():
    sumber = "Harga cabai naik menjadi Rp 85.000 per kg pada 8 Oktober."
    teks, dibuang = berita.bersihkan_angka("Cabai naik menjadi Rp 85.000 per kg. Kenaikannya 12 persen dari bulan lalu.", sumber)
    assert teks == "Cabai naik menjadi Rp 85.000 per kg." and dibuang == 1
    assert berita.bersihkan_angka("Cabai naik. Pedagang resah.", sumber) == ("Cabai naik. Pedagang resah.", 0)
    # pemisah ribuan tidak memengaruhi pencocokan
    assert berita.bersihkan_angka("Harga Rp85,000.", "Rp 85.000")[1] == 0


def test_ringkas_ekstraktif_memilih_kalimat_berisi_wilayah_dan_harga(konf):
    h = berita.ekstrak_halaman(ARTIKEL.encode())
    r = berita.ringkas_ekstraktif(h["judul"], h["teks"], konf)
    assert "Bengkulu Tengah" in r and "Rp" in r
    assert berita.ringkas_ekstraktif("Judul saja", "pendek", konf) == "Judul saja"
    ulang = "Harga beras medium di Pasar Karang Nanding, Bengkulu Tengah, stabil di Rp 13.500 per kg. " * 3
    assert berita.ringkas_ekstraktif("x", ulang, konf).count("Karang Nanding") == 1  # halaman yang mengulang kalimat


# ---------------------------------------------------------------- Tavily

def test_tavily_hasil_membawa_isi_artikel():
    isi_dikirim = []

    def kirim(url, header, isi):
        isi_dikirim.append(isi)
        return {"results": [{"url": "https://portal.id/a?utm_source=x", "title": "Harga cabai", "content": "cuplikan",
                             "raw_content": "isi " * 100, "published_date": "Thu, 08 Oct 2026 03:00:00 GMT"},
                            {"url": "ftp://aneh", "title": "x"}]}

    hasil, galat = berita.cari_tavily(["harga cabai Bengkulu"], 14, kirim)
    assert galat == [] and len(hasil) == 1 and hasil[0]["via"] == "tavily" and len(hasil[0]["teks"]) >= 200
    assert hasil[0]["tanggal"] == date(2026, 10, 8) and hasil[0]["sumber"] == "portal.id"
    assert isi_dikirim[0]["topic"] == "news" and isi_dikirim[0]["days"] == 14 and isi_dikirim[0]["include_raw_content"] is True


def test_tavily_berhenti_saat_kuota_habis_dan_dilewati_tanpa_kunci(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    assert berita.cari_tavily(["a"], 7) == ([], ["Tavily dilewati: kunci belum diisi."])
    panggilan = []

    def kirim(url, header, isi):
        panggilan.append(isi["query"])
        raise RuntimeError("HTTP 432 kuota habis")

    hasil, galat = berita.cari_tavily(["a", "b", "c"], 7, kirim)
    assert hasil == [] and len(panggilan) == 1 and "432" in galat[0]


# ---------------------------------------------------------------- satu kali jalan penuh

def _konf_uji(konf, **ubah):
    konf.pengaturan["berita"] = {"kueri": ["harga cabai Bengkulu"], "umpan_rss": [{"nama": "Portal", "url": "https://portal.id/rss.xml"}],
                                 "jeda_detik": 0, **ubah}
    return konf


def _web_lengkap():
    return Web({"https://portal.id/robots.txt": (ROBOTS_BEBAS, "text/plain"),
                "https://portal.id/rss.xml": (b"""<rss><channel>
<item><title>Harga Cabai Rawit Merah Tembus Rp 85.000 per Kg di Bengkulu Tengah</title><link>https://portal.id/a</link>
<pubDate>Thu, 08 Oct 2026 03:15:00 GMT</pubDate></item>
<item><title>Pemkab gelar lomba bendera</title><link>https://portal.id/lomba</link><pubDate>Thu, 08 Oct 2026 03:15:00 GMT</pubDate></item>
</channel></rss>""", "application/rss+xml"),
                "https://portal.id/a": (ARTIKEL.encode(), "text/html; charset=utf-8"),
                "https://news.google.com/robots.txt": 404},
               awalan={"https://news.google.com/rss/search": (RSS_GOOGLE, "application/rss+xml"),
                       "https://news.google.com/rss/articles/": (b"<html><body><script>window.location=...</script></body></html>", "text/html")})


TAVILY_HASIL = {"results": [{"url": "https://tavily.id/berita/beras", "title": "Harga beras medium di Bengkulu Tengah stabil",
                             "content": "Beras stabil.", "published_date": "Wed, 07 Oct 2026 03:00:00 GMT",
                             "raw_content": ("Harga beras medium di Pasar Karang Nanding, Bengkulu Tengah, stabil di Rp 13.500 per kg sepanjang pekan ini. "
                                             "Pedagang menyebut pasokan beras dari sentra produksi masih lancar dan stok mencukupi hingga akhir bulan. ") * 2}]}


def test_jalankan_tanpa_ai_menghasilkan_arsip_dan_kandidat(konf):
    web = _web_lengkap()
    hasil = berita.jalankan(_konf_uji(konf), klien={"tavily": lambda u, h, i: TAVILY_HASIL}, tanpa_ai=True, sekarang=SEKARANG,
                            pengambil=web, arsip={"berita": [], "kesimpulan": []})
    judul = {b["judul"]: b for b in hasil["berita"]}
    cabai = judul["Harga Cabai Rawit Merah Tembus Rp 85.000 per Kg di Bengkulu Tengah"]
    assert cabai["relevansi"] == "tinggi" and cabai["isi_terbaca"] and cabai["via"] == ["rss"]
    assert {"harga_naik", "cuaca", "intervensi"} <= set(cabai["tag"])
    assert [(h["kode_varian"], h["nilai"], h["status"]) for h in cabai["harga"]][:1] == [("CRW02", 85000, "kandidat")]
    assert len(cabai["sidik_sha256"]) == 64 and cabai["metode_ringkas"] == "ekstraktif" and cabai["dampak_harga"] == "naik"
    assert cabai["tindak_lanjut"] is True and "Karang Nanding" in cabai["ringkasan"]
    assert "teks" not in cabai and "_teks" not in cabai  # isi lengkap tidak disimpan
    beras = judul["Harga beras medium di Bengkulu Tengah stabil"]
    assert beras["via"] == ["tavily"] and beras["harga"][0]["nilai"] == 13500
    # Google Berita: tautan tidak mengarah ke artikel, jadi hanya judul; berita bola dan yang terlalu lama dibuang
    google = judul["Harga Cabai Rawit Naik di Bengkulu Tengah"]
    assert not google["isi_terbaca"] and "tidak mengarah" in google["catatan_baca"] and google["metode_ringkas"] == "judul"
    assert "Final Piala Dunia Antarklub Digelar" not in judul and "Harga Beras Lama di Bengkulu" not in judul
    assert "Pemkab gelar lomba bendera" not in judul
    st = hasil["statistik"]
    assert st["berita_baru"] == 3 and st["kandidat_harga_baru"] >= 3 and st["penyedia_ai"] == ""
    k = hasil["kesimpulan"][0]
    assert k["metode"] == "ekstraktif" and k["tanggal"] == "2026-10-09" and "kandidat harga" in k["ringkas"]
    # robots.txt diperiksa sebelum mengunduh artikel
    assert web.dipanggil.index("https://portal.id/robots.txt") < web.dipanggil.index("https://portal.id/a")


def test_jalankan_dengan_ai_memeriksa_angka_dan_cadangan_penyedia(konf):
    web = _web_lengkap()
    id_cabai = berita.id_berita("https://portal.id/a")
    ringkas = {"berita": [{"id": id_cabai, "ringkasan": "Harga cabai rawit merah naik menjadi Rp 85.000 per kg di Bengkulu Tengah. Kenaikannya 40 persen.",
                           "dampak_harga": "naik", "komoditas": ["cabai rawit"], "wilayah_disebut": "Bengkulu Tengah", "tindak_lanjut": True}]}
    kesimpulan = {"ringkas": "Harga cabai rawit naik di Bengkulu Tengah. Operasi pasar disiapkan.", "poin": ["Cabai naik", "Beras stabil 99"],
                  "perlu_dipantau": ["Pasokan cabai"]}
    permintaan = []

    def gemini(url, header, isi):
        raise pencari_data.PenyediaTidakTersedia("HTTP 429 batas pemakaian gratis tercapai")

    def groq(url, header, isi):
        permintaan.append(isi["messages"][0]["content"][:30])
        objek = ringkas if "BERITA YANG PERLU DIRINGKAS" in isi["messages"][1]["content"] else kesimpulan
        return _jawab_openai(objek)(url, header, isi)

    hasil = berita.jalankan(_konf_uji(konf), klien={"tavily": lambda u, h, i: {"results": []}, "ai": {"gemini": gemini, "groq": groq}},
                            sekarang=SEKARANG, pengambil=web, arsip={"berita": [], "kesimpulan": []})
    cabai = next(b for b in hasil["berita"] if b["id"] == id_cabai)
    assert cabai["metode_ringkas"] == "ai" and cabai["penyedia_ai"] == "groq"
    assert cabai["ringkasan"] == "Harga cabai rawit merah naik menjadi Rp 85.000 per kg di Bengkulu Tengah."  # angka 40 persen dibuang
    assert hasil["statistik"]["penyedia_ai"] == "groq" and hasil["statistik"]["model_ai"] == "groq-palsu"
    k = hasil["kesimpulan"][0]
    assert k["metode"] == "ai" and k["penyedia"] == "groq" and k["poin"] == ["Cabai naik"] and k["perlu_dipantau"] == ["Pasokan cabai"]
    assert all(p.startswith("Anda adalah analis") for p in permintaan)  # pesan sistem berita, bukan pesan AI Data Finder


def test_jalankan_semua_ai_gagal_memakai_cadangan_tanpa_ai(konf):
    def mati(url, header, isi):
        raise pencari_data.PenyediaTidakTersedia("HTTP 429 batas pemakaian gratis tercapai")

    klien = {"tavily": lambda u, h, i: {"results": []}, "ai": {n: mati for n in ("gemini", "groq", "cerebras", "openrouter", "mistral")}}
    hasil = berita.jalankan(_konf_uji(konf), klien=klien, sekarang=SEKARANG, pengambil=_web_lengkap(), arsip={"berita": [], "kesimpulan": []})
    assert hasil["kesimpulan"][0]["metode"] == "ekstraktif"
    assert {b["metode_ringkas"] for b in hasil["berita"]} <= {"ekstraktif", "judul"} and hasil["statistik"]["penyedia_ai"] == ""
    assert any("gagal" in x["teks"].lower() for x in hasil["log"] if x["jenis"] == "peringatan")


def test_jalankan_kesimpulan_ai_dengan_angka_karangan_diganti_otomatis(konf):
    def ai(url, header, isi):
        if "BERITA YANG PERLU DIRINGKAS" in isi["messages"][1]["content"]:
            return _jawab_openai({"berita": []})(url, header, isi)
        return _jawab_openai({"ringkas": "Harga cabai naik 77 persen.", "poin": [], "perlu_dipantau": []})(url, header, isi)

    klien = {"tavily": lambda u, h, i: {"results": []}, "ai": {n: ai for n in ("gemini", "groq", "cerebras", "openrouter", "mistral")}}
    klien["ai"]["gemini"] = lambda *a: (_ for _ in ()).throw(pencari_data.PenyediaTidakTersedia("HTTP 401"))
    hasil = berita.jalankan(_konf_uji(konf), klien=klien, sekarang=SEKARANG, pengambil=_web_lengkap(), arsip={"berita": [], "kesimpulan": []})
    assert hasil["kesimpulan"][0]["metode"] == "ekstraktif"
    assert any("angka yang tidak ada" in x["teks"] for x in hasil["log"])


def test_jalankan_tidak_mengulang_berita_lama_dan_membersihkan_arsip(konf):
    web = _web_lengkap()
    klien = {"tavily": lambda u, h, i: {"results": []}}
    pertama = berita.jalankan(_konf_uji(konf), klien=klien, tanpa_ai=True, sekarang=SEKARANG, pengambil=web, arsip={"berita": [], "kesimpulan": []})
    lama = {"id": "lama00000001", "url": "https://x.id/lama", "judul": "Berita sangat lama", "sumber": "x.id", "tanggal": "2026-06-01",
            "diakses": "2026-06-02T09:00:00+07:00", "skor": 5, "harga": [], "baru": False}
    kedua = berita.jalankan(_konf_uji(konf), klien=klien, tanpa_ai=True, sekarang=SEKARANG + timedelta(hours=3), pengambil=web,
                            arsip={**pertama, "berita": pertama["berita"] + [lama]})
    assert kedua["statistik"]["berita_baru"] == 0 and kedua["statistik"]["total_arsip"] == len(pertama["berita"])  # yang 60+ hari dibuang
    assert all(b["baru"] is False for b in kedua["berita"])
    assert kedua["kesimpulan"][0]["tanggal"] == "2026-10-09" and len(kedua["kesimpulan"]) == len(pertama["kesimpulan"])  # satu per hari
    assert kedua["kesimpulan"][0]["ringkas"] == "Tidak ada berita baru yang relevan hari ini."


def test_jalankan_berhenti_mengunduh_saat_batas_waktu_habis(konf, monkeypatch):
    web = _web_lengkap()
    jam = iter(range(0, 100000, 1000))  # tiap pembacaan jam maju 1000 detik
    monkeypatch.setattr(berita.time, "monotonic", lambda: next(jam))
    hasil = berita.jalankan(_konf_uji(konf, maks_menit=1), klien={"tavily": lambda u, h, i: {"results": []}}, tanpa_ai=True, sekarang=SEKARANG,
                            pengambil=web, arsip={"berita": [], "kesimpulan": []})
    assert "https://portal.id/a" not in web.dipanggil
    assert any("Batas waktu" in x["teks"] for x in hasil["log"] if x["jenis"] == "peringatan")
    b = next(b for b in hasil["berita"] if b["url"] == "https://portal.id/a")
    assert b["catatan_baca"] == "batas waktu pengunduhan habis" and not b["isi_terbaca"]


def test_jalankan_satu_sumber_rusak_tidak_menghentikan_yang_lain(konf):
    web = _web_lengkap()
    web.halaman["https://portal.id/rss.xml"] = 500
    hasil = berita.jalankan(_konf_uji(konf), klien={"tavily": lambda u, h, i: TAVILY_HASIL}, tanpa_ai=True, sekarang=SEKARANG,
                            pengambil=web, arsip={"berita": [], "kesimpulan": []})
    assert any("Portal" in g for g in hasil["galat"]) and hasil["statistik"]["berita_baru"] >= 1


def test_jalankan_robots_melarang_artikel_tidak_diunduh(konf):
    web = _web_lengkap()
    web.halaman["https://portal.id/robots.txt"] = (b"User-agent: *\nDisallow: /\n", "text/plain")
    hasil = berita.jalankan(_konf_uji(konf), klien={"tavily": lambda u, h, i: {"results": []}}, tanpa_ai=True, sekarang=SEKARANG,
                            pengambil=web, arsip={"berita": [], "kesimpulan": []})
    assert "https://portal.id/a" not in web.dipanggil
    b = next(b for b in hasil["berita"] if b["url"] == "https://portal.id/a")
    assert not b["isi_terbaca"] and b["catatan_baca"] == "robots.txt melarang" and b["harga"] == []


def test_simpan_muat_dan_data_untuk_situs(konf):
    hasil = berita.jalankan(_konf_uji(konf), klien={"tavily": lambda u, h, i: TAVILY_HASIL}, tanpa_ai=True, sekarang=SEKARANG,
                            pengambil=_web_lengkap(), arsip={"berita": [], "kesimpulan": []})
    path = berita.simpan(konf, hasil)
    tersimpan = json.loads(path.read_text(encoding="utf-8"))
    assert "log" not in tersimpan and len(tersimpan["berita"]) == len(hasil["berita"])
    situs = berita.untuk_situs(konf)
    assert situs["statistik"]["berita_baru"] == 3 and situs["label_tag"]["harga_naik"] == "Harga naik" and "belum diverifikasi" in situs["catatan"]
    path.write_text("bukan json", encoding="utf-8")
    assert berita.muat(konf) == {"berita": [], "kesimpulan": []}
    assert berita.untuk_situs(konf)["berita"] == []


# ---------------------------------------------------------------- jadwal otomatis dan pengaturan

T_PAGI = datetime(2026, 10, 9, 1, 0, tzinfo=timezone.utc)  # 08.00 WIB
T_SUBUH = datetime(2026, 10, 8, 21, 0, tzinfo=timezone.utc)  # 04.00 WIB


def test_berita_jatuh_tempo_sekali_sehari_setelah_jam_mulai(akar_sementara):
    db = DBTiruan()
    assert not fs.berita_jatuh_tempo(akar_sementara, db, T_SUBUH)  # belum jam 07.00
    assert fs.berita_jatuh_tempo(akar_sementara, db, T_PAGI)
    fs.catat_berita_harian(db, "2026-10-09")
    assert not fs.berita_jatuh_tempo(akar_sementara, db, T_PAGI)
    assert fs.berita_jatuh_tempo(akar_sementara, db, T_PAGI + timedelta(days=1))  # besok jalan lagi
    # penjaga memicu pembaruan hanya karena berita
    db.data["lbp_status"]["berita_harian"]["tanggal"] = "2026-10-08"
    db.data["lbp_status"]["ai_harian"] = {"tanggal": "2026-10-09"}
    assert fs.perlu_jalan(akar_sementara, db, T_PAGI) == (True, "berita lokal harian")


def test_berita_dimatikan_atau_jam_mulai_diubah_dari_pengaturan(akar_sementara):
    p = akar_sementara / "config" / "pengaturan.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    db = DBTiruan()
    d["berita"]["aktif"] = False
    p.write_text(json.dumps(d), encoding="utf-8")
    assert not fs.berita_jatuh_tempo(akar_sementara, db, T_PAGI)
    d["berita"].update(aktif=True, jam_mulai=10)
    p.write_text(json.dumps(d), encoding="utf-8")
    assert not fs.berita_jatuh_tempo(akar_sementara, db, T_PAGI)  # 08.00 < 10.00
    assert fs.berita_jatuh_tempo(akar_sementara, db, T_PAGI + timedelta(hours=3))


def _pasang_firestore(monkeypatch, db):
    monkeypatch.setattr(fs, "aktif", lambda: True)
    monkeypatch.setattr(fs, "klien", lambda: db)
    monkeypatch.setattr(fs, "pasang_rahasia_dari_firestore", lambda akar: [])

    class Jam(datetime):
        @classmethod
        def now(cls, tz=None):
            return T_PAGI if tz else T_PAGI.replace(tzinfo=None)

    import datetime as modul_dt
    monkeypatch.setattr(modul_dt, "datetime", Jam)


def test_berita_harian_tercatat_dan_tidak_diulang(akar_sementara, monkeypatch):
    db = DBTiruan()
    _pasang_firestore(monkeypatch, db)
    hasil = {"statistik": {"berita_baru": 4, "kandidat_harga_baru": 2, "penyedia_ai": "groq", "model_ai": "g"},
             "kesimpulan": [{"metode": "ai", "ringkas": "x"}], "berita": [{"id": "a", "baru": True}, {"id": "b", "baru": False}],
             "log": [{"waktu": "09.00.01", "teks": "Mulai", "jenis": "info"}]}
    panggil = []
    monkeypatch.setattr(berita, "jalankan", lambda konf, **k: panggil.append(1) or hasil)
    pesan = m._berita_harian(akar_sementara)
    assert pesan == ["Berita lokal harian: 4 berita baru, 2 kandidat harga (ai)."]
    assert db.data["lbp_status"]["berita_harian"]["tanggal"] == "2026-10-09" and db.data["lbp_status"]["berita_harian"]["hasil"] == "berhasil"
    assert (akar_sementara / "data/berita/berita.json").exists()
    (log,) = db.data["lbp_log_ai"].values()
    assert log["sumber"] == "berita" and log["hasil"] == "berhasil" and log["penyedia"] == "groq" and log["jumlah_kandidat"] == 1
    assert m._berita_harian(akar_sementara) == [] and len(panggil) == 1  # hari yang sama tidak diulang


def test_berita_diminta_dari_panel_jalan_walau_hari_ini_sudah_dicari(akar_sementara, monkeypatch):
    db = DBTiruan()
    _pasang_firestore(monkeypatch, db)
    fs.catat_berita_harian(db, "2026-10-09")  # sudah dicari hari ini
    hasil = {"statistik": {"berita_baru": 1, "kandidat_harga_baru": 0, "penyedia_ai": "", "model_ai": ""},
             "kesimpulan": [{"metode": "ekstraktif", "ringkas": "x"}], "berita": [], "log": []}
    panggil = []
    monkeypatch.setattr(berita, "jalankan", lambda konf, **k: panggil.append(1) or hasil)
    assert m._berita_harian(akar_sementara) == [] and not panggil
    assert m._berita_harian(akar_sementara, paksa=True) == ["Berita lokal harian: 1 berita baru, 0 kandidat harga (ekstraktif)."]
    assert len(panggil) == 1


def test_perintah_berita_dikenal_panel_aturan_dan_mesin(konf):
    """Tiap tombol Jalankan di skema harus punya jenis perintah di panel (JS), aturan Firestore, dan mesin; kalau tidak,
    panel Pengaturan gagal dimuat (dulu: 'Cannot read properties of undefined (reading indexOf)')."""
    import re

    from tests.conftest import AKAR

    js = (AKAR / "site/assets/pengaturan-firestore.js").read_text(encoding="utf-8")
    rules = (AKAR / "firestore.rules").read_text(encoding="utf-8")
    peta = dict(re.findall(r'"([\w.-]+\.yml)":\s*"(\w+)"', re.search(r"JENIS_PERINTAH = \{(.*?)\};", js, re.S).group(1)))
    skema = json.loads((AKAR / "config/skema_pengaturan.json").read_text(encoding="utf-8"))
    for a in skema["alur_kerja"]:
        assert a["berkas"] in peta, f"{a['berkas']} belum punya jenis perintah di pengaturan-firestore.js"
        assert peta[a["berkas"]] in fs.JENIS_PERINTAH, f"mesin belum mengenal perintah {peta[a['berkas']]}"
        assert f"'{peta[a['berkas']]}'" in re.search(r"jenis in \[(.*?)\]\s*&&\s*baru\(\)\.keys", rules, re.S).group(1), \
            f"aturan Firestore belum mengizinkan perintah {peta[a['berkas']]}"


def test_berita_harian_gagal_dicatat_dan_tidak_mengulang_hari_itu(akar_sementara, monkeypatch):
    db = DBTiruan()
    _pasang_firestore(monkeypatch, db)

    def rusak(konf, **k):
        raise RuntimeError("jaringan putus")

    monkeypatch.setattr(berita, "jalankan", rusak)
    (pesan,) = m._berita_harian(akar_sementara)
    assert pesan.startswith("::warning::") and "jaringan putus" in pesan
    assert db.data["lbp_status"]["berita_harian"]["hasil"] == "gagal"
    (log,) = db.data["lbp_log_ai"].values()
    assert log["hasil"] == "gagal" and log["sumber"] == "berita"
    assert m._berita_harian(akar_sementara) == []  # tidak dicoba terus-menerus sepanjang hari


def test_berita_harian_tanpa_firebase_tidak_melakukan_apa_apa(akar_sementara, monkeypatch):
    monkeypatch.setattr(fs, "aktif", lambda: False)
    assert m._berita_harian(akar_sementara) == []


def test_pengaturan_berita_ada_di_berkas_dan_skema_dan_valid(konf):
    from pipeline import pengaturan

    cfg = berita.pengaturan_berita(konf)
    assert cfg["aktif"] is True and cfg["jam_mulai"] == 7 and len(cfg["kueri"]) >= 5
    skema = json.loads((konf.akar / "config/skema_pengaturan.json").read_text(encoding="utf-8"))
    assert {k["jalur"] for k in skema["kolom"] if k["jalur"].startswith("berita.")} >= {
        "berita.aktif", "berita.jam_mulai", "berita.umur_maks_hari", "berita.maks_diringkas", "berita.pakai_ai"}
    assert any(a["berkas"] == "berita.yml" for a in skema["alur_kerja"])
    assert pengaturan.periksa_berkas(konf.akar / "config") == []


def test_pipeline_menulis_berita_json_untuk_situs(tmp_path):
    import shutil

    from pipeline import konfigurasi, proses
    from tests.conftest import AKAR, HARI_INI

    shutil.copytree(AKAR / "config", tmp_path / "config")
    (tmp_path / "data/masuk/harga").mkdir(parents=True)
    konf = konfigurasi.muat(tmp_path, hari_ini=HARI_INI)
    kosong = berita.untuk_situs(konf)  # belum pernah dicari: struktur kosong yang valid, halaman tetap bisa dibuka
    assert kosong["berita"] == [] and kosong["kesimpulan"] == [] and kosong["statistik"] == {} and "label_tag" in kosong

    hasil = berita.jalankan(_konf_uji(konf), klien={"tavily": lambda u, h, i: TAVILY_HASIL}, tanpa_ai=True, sekarang=SEKARANG,
                            pengambil=_web_lengkap(), arsip={"berita": [], "kesimpulan": []})
    berita.simpan(konf, hasil)
    keluaran = tmp_path / "site/data"
    proses.jalankan(konf, keluaran, sinkron_github=False)
    isi = json.loads((keluaran / "berita.json").read_text(encoding="utf-8"))
    assert len(isi["berita"]) == 3 and isi["kesimpulan"][0]["tanggal"] == "2026-10-09" and isi["statistik"]["berita_baru"] == 3
