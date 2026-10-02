import csv
import json
from types import SimpleNamespace

import pytest

from pipeline import konektor_cuaca, pencari_data


def respons_cuaca(tanggal, hujan, suhu):
    return {"daily": {"time": tanggal, "precipitation_sum": hujan, "temperature_2m_mean": suhu}}


def test_ubah_respons_membuang_nilai_kosong_dan_masa_depan():
    from datetime import date
    baris = konektor_cuaca.ubah_respons(
        respons_cuaca(["2026-09-27", "2026-09-28", "2026-09-29"], [1.5, None, 3.0], [26.0, 27.0, 28.0]), "1709", date(2026, 9, 28))
    assert {(b["tanggal"], b["indikator"]) for b in baris} == {
        ("2026-09-27", "curah_hujan_mm"), ("2026-09-27", "suhu_rata_c"), ("2026-09-28", "suhu_rata_c")}
    assert all(b["kode_sumber"] == "BD-CUACA" for b in baris)


def test_perbarui_cuaca_menulis_dan_menggabung(konf, akar_sementara):
    dipanggil = []

    def pengambil(url):
        dipanggil.append(url)
        if "archive" in url:
            return respons_cuaca(["2025-12-31", "2026-01-01"], [5.0, 6.0], [25.0, 25.5])
        return respons_cuaca(["2026-09-27", "2026-09-28"], [2.0, 4.0], [26.0, 26.5])

    hasil = konektor_cuaca.perbarui(konf, pengambil=pengambil)
    assert hasil["galat"] == [] and hasil["baris_baru"] == 3 * 8
    folder = akar_sementara / "data/masuk/konteks"
    assert sorted(p.name for p in folder.glob("cuaca_*.csv")) == ["cuaca_openmeteo_2025.csv", "cuaca_openmeteo_2026.csv"]
    assert any("latitude=-3.72" in u for u in dipanggil)
    # jalan kedua: arsip tidak diambil ulang untuk wilayah yang sudah punya riwayat panjang? (riwayat pendek -> diambil lagi)
    hasil2 = konektor_cuaca.perbarui(konf, pengambil=pengambil)
    assert hasil2["baris_baru"] == 0
    with (folder / "cuaca_openmeteo_2026.csv").open() as f:
        baris = list(csv.DictReader(f))
    assert len(baris) == 3 * 6  # tidak ada duplikat kunci


def test_perbarui_cuaca_galat_jaringan_tidak_menghentikan(konf):
    def gagal(url):
        raise OSError("jaringan putus")
    hasil = konektor_cuaca.perbarui(konf, pengambil=gagal)
    assert len(hasil["galat"]) == 3


class KlienPalsu:
    def __init__(self, respons):
        self.respons = list(respons)
        self.panggilan = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.panggilan.append(kw)
        return self.respons.pop(0)


def blok(tipe, **kw):
    return SimpleNamespace(type=tipe, **kw)


HASIL_JSON = {
    "kandidat": [
        {"nama_sumber": "Panel Harga Pangan", "penyedia": "Bapanas", "url": "https://panelharga.badanpangan.go.id/tabel",
         "wilayah": "Kab. Bengkulu Tengah", "peran_wilayah": "target", "periode_data": "harian", "komoditas_varian": "cabai rawit merah",
         "satuan": "Rp/kg", "frekuensi_pembaruan": "harian", "metode_akses": "web", "lisensi_atau_ketentuan": "tidak diketahui",
         "perlu_izin": True, "relevansi": "tinggi", "catatan_keandalan": "resmi"},
        {"nama_sumber": "Situs karangan", "penyedia": "?", "url": "https://contoh-palsu.example/data", "wilayah": "?",
         "peran_wilayah": "tidak diketahui", "periode_data": "?", "komoditas_varian": "?", "satuan": "?",
         "frekuensi_pembaruan": "?", "metode_akses": "tidak diketahui", "lisensi_atau_ketentuan": "?", "perlu_izin": True,
         "relevansi": "?", "catatan_keandalan": "?"},
    ],
    "tidak_ditemukan": [], "catatan": "uji",
}


def cek_palsu(url):
    return (url.startswith("https://panelharga"), "HTTP 200" if url.startswith("https://panelharga") else "HTTP 404")


def test_pencari_data_claude_menandai_url_dan_melanjutkan_pause_turn(konf):
    hasil_cari = blok("web_search_tool_result", content=[SimpleNamespace(url="https://panelharga.badanpangan.go.id/")])
    r1 = SimpleNamespace(stop_reason="pause_turn", content=[blok("server_tool_use"), hasil_cari], model="claude-opus-5-5")
    r2 = SimpleNamespace(stop_reason="end_turn", content=[blok("text", text=json.dumps(HASIL_JSON))], model="claude-opus-5-5",
                         _request_id="req_1")
    klien = KlienPalsu([r1, r2])
    catatan = pencari_data.cari(konf, "cabai rawit merah", "September 2026", penyedia="anthropic",
                                klien={"anthropic": klien}, pemeriksa_url=cek_palsu)
    assert len(klien.panggilan) == 2
    assert klien.panggilan[1]["messages"][1]["role"] == "assistant"
    p = klien.panggilan[0]
    assert p["model"] == "claude-opus-5-5" and p["fallbacks"] == "default"
    assert p["output_config"]["format"]["type"] == "json_schema"
    assert p["tools"][0]["type"] == "web_search_20260209"
    k = catatan["hasil"]["kandidat"]
    assert k[0]["url_ada_di_hasil_pencarian"] is True and k[1]["url_ada_di_hasil_pencarian"] is False
    assert k[0]["url_dapat_diakses"] is True and k[1]["url_dapat_diakses"] is False
    assert all(x["status_verifikasi"] == "kandidat" for x in k)
    assert catatan["penyedia"] == "anthropic"
    path = pencari_data.simpan(konf, catatan)
    assert json.loads(path.read_text())["pencarian"][0]["request_id"] == "req_1"


def test_pencari_data_claude_penolakan_model(konf):
    r = SimpleNamespace(stop_reason="refusal", content=[], stop_details=SimpleNamespace(explanation="kebijakan"))
    with pytest.raises(RuntimeError, match="ditolak"):
        pencari_data.cari(konf, "x", "y", penyedia="anthropic", klien={"anthropic": KlienPalsu([r])}, pemeriksa_url=None)


def test_pencari_data_gemini_grounding(konf):
    dikirim = []

    def kirim(url, header, isi):
        dikirim.append((url, isi))
        teks = "Berikut hasilnya:\n```json\n" + json.dumps(HASIL_JSON) + "\n```"
        return {
            "candidates": [{"content": {"parts": [{"text": teks}]},
                            "groundingMetadata": {"groundingChunks": [
                                {"web": {"uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc",
                                         "title": "badanpangan.go.id"}}]}}],
            "modelVersion": "gemini-flash-latest", "responseId": "resp-1",
        }

    catatan = pencari_data.cari(konf, "cabai rawit merah", "September 2026", penyedia="gemini",
                                klien={"gemini": kirim}, pemeriksa_url=cek_palsu)
    url, isi = dikirim[0]
    assert "gemini-flash-latest:generateContent" in url
    assert isi["tools"] == [{"google_search": {}}]
    k = catatan["hasil"]["kandidat"]
    assert k[0]["url_ada_di_hasil_pencarian"] is True  # subdomain dari domain rujukan grounding
    assert k[1]["url_ada_di_hasil_pencarian"] is False
    assert catatan["penyedia"] == "gemini" and catatan["punya_pencarian_web"] is True


SEMUA_KUNCI = ("GEMINI_API_KEY", "GROQ_API_KEY", "CEREBRAS_API_KEY", "OPENROUTER_API_KEY", "MISTRAL_API_KEY",
               "ANTHROPIC_API_KEY", "GITHUB_TOKEN", "TAVILY_API_KEY")


@pytest.fixture
def tanpa_kunci(monkeypatch):
    for kunci in SEMUA_KUNCI:
        monkeypatch.delenv(kunci, raising=False)


def jawaban_chat(isi, **lain):
    return {"choices": [{"message": {"content": isi}}], **lain}


def test_pencari_data_otomatis_jatuh_ke_github_models(konf, tanpa_kunci):

    def kirim_github(url, header, isi):
        assert url == pencari_data.URL_GITHUB_MODELS and isi["model"] == "openai/gpt-4.1-mini"
        assert "TIDAK memiliki akses internet" in isi["messages"][0]["content"]
        return {"choices": [{"message": {"content": json.dumps({"kandidat": [HASIL_JSON["kandidat"][0]]})}}], "id": "gh-1"}

    catatan = pencari_data.cari(konf, "cabai", "Oktober 2026", klien={"github_models": kirim_github}, pemeriksa_url=cek_palsu)
    assert catatan["penyedia"] == "github_models"
    # AI yang kuncinya belum diisi dilewati satu per satu, alasannya dicatat
    assert [d.split(":")[0] for d in catatan["penyedia_dilewati"]] == ["gemini", "groq", "cerebras", "openrouter", "mistral"]
    assert "GROQ_API_KEY belum diisi" in catatan["penyedia_dilewati"][1]
    k = catatan["hasil"]["kandidat"][0]
    assert k["url_ada_di_hasil_pencarian"] is None and k["url_dapat_diakses"] is True
    assert catatan["hasil"]["tidak_ditemukan"] == [] and catatan["hasil"]["catatan"] == ""


def test_pencari_data_kuota_habis_lanjut_penyedia_berikutnya(konf, tanpa_kunci):
    def gemini_habis(url, header, isi):
        raise pencari_data.PenyediaTidakTersedia("HTTP 429: kuota habis")

    def github_ok(url, header, isi):
        return {"choices": [{"message": {"content": json.dumps({"kandidat": []})}}]}

    catatan = pencari_data.cari(konf, "x", "y", klien={"gemini": gemini_habis, "github_models": github_ok}, pemeriksa_url=None)
    assert catatan["penyedia"] == "github_models" and "429" in catatan["penyedia_dilewati"][0]


def test_pencari_data_semua_penyedia_gagal(konf, tanpa_kunci):
    with pytest.raises(RuntimeError, match="tidak ada penyedia AI"):
        pencari_data.cari(konf, "x", "y", pemeriksa_url=None)


def test_pencari_data_ai_gratis_bergantian_sampai_berhasil(konf, monkeypatch, tanpa_kunci):
    for kunci in ("GROQ_API_KEY", "CEREBRAS_API_KEY", "OPENROUTER_API_KEY", "MISTRAL_API_KEY"):
        monkeypatch.setenv(kunci, f"kunci-uji-{kunci.lower()}")
    dikirim = {}

    def catat(nama, jawab):
        def kirim(url, header, isi):
            dikirim[nama] = (url, header, isi)
            if isinstance(jawab, Exception):
                raise jawab
            return jawab
        return kirim

    klien = {
        "gemini": catat("gemini", pencari_data.PenyediaTidakTersedia("HTTP 429 (batas pemakaian gratis tercapai): kuota")),
        "groq": catat("groq", pencari_data.PenyediaTidakTersedia("HTTP 429 (batas pemakaian gratis tercapai): rate limit")),
        "cerebras": catat("cerebras", jawaban_chat("maaf, saya tidak bisa")),  # bukan JSON: lanjut, jangan berhenti
        "openrouter": catat("openrouter", {"error": {"message": "Provider returned error", "code": 502}}),
        "mistral": catat("mistral", jawaban_chat([{"type": "text", "text": json.dumps({"kandidat": [HASIL_JSON["kandidat"][0]]})}],
                                                 model="mistral-small-2603", id="mis-1")),
        "github_models": catat("github_models", AssertionError("tidak boleh dipanggil karena Mistral sudah berhasil")),
    }
    catatan = pencari_data.cari(konf, "cabai", "Oktober 2026", klien=klien, pemeriksa_url=None)
    assert catatan["penyedia"] == "mistral" and catatan["model"] == "mistral-small-2603" and catatan["request_id"] == "mis-1"
    assert catatan["punya_pencarian_web"] is False and len(catatan["hasil"]["kandidat"]) == 1
    assert [d.split(":")[0] for d in catatan["penyedia_dilewati"]] == ["gemini", "groq", "cerebras", "openrouter"]
    assert "JSON" in catatan["penyedia_dilewati"][2] and "Provider returned error" in catatan["penyedia_dilewati"][3]
    assert "github_models" not in dikirim
    # alamat, kunci, dan model tiap layanan
    assert dikirim["groq"][0] == "https://api.groq.com/openai/v1/chat/completions"
    assert dikirim["groq"][1]["Authorization"] == "Bearer kunci-uji-groq_api_key"
    assert dikirim["groq"][2]["model"] == "openai/gpt-oss-120b"
    assert dikirim["cerebras"][0] == "https://api.cerebras.ai/v1/chat/completions" and dikirim["cerebras"][2]["model"] == "gpt-oss-120b"
    assert dikirim["openrouter"][0] == "https://openrouter.ai/api/v1/chat/completions"
    assert dikirim["openrouter"][2]["model"] == "openrouter/free"
    assert dikirim["mistral"][0] == "https://api.mistral.ai/v1/chat/completions"
    assert dikirim["mistral"][2]["model"] == "mistral-small-latest"
    assert "TIDAK memiliki akses internet" in dikirim["mistral"][2]["messages"][0]["content"]


def test_pencari_data_pilihan_tunggal_tidak_pindah(konf, monkeypatch, tanpa_kunci):
    monkeypatch.setenv("GROQ_API_KEY", "kunci-uji-groq-1234567890")

    def habis(url, header, isi):
        raise pencari_data.PenyediaTidakTersedia("HTTP 429 (batas pemakaian gratis tercapai)")

    with pytest.raises(RuntimeError, match="groq: HTTP 429"):
        pencari_data.cari(konf, "x", "y", penyedia="groq", klien={"groq": habis, "github_models": habis}, pemeriksa_url=None)


def test_post_json_semua_galat_http_membuat_ai_dilewati(monkeypatch):
    import io
    import urllib.error

    def tolak(kode, badan):
        def urlopen(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, kode, "galat", {}, io.BytesIO(badan.encode()))
        return urlopen

    # Gemini menjawab 400 untuk kunci yang salah; dulu ini menghentikan mode otomatis
    monkeypatch.setattr(pencari_data.urllib.request, "urlopen", tolak(400, '{"error": "API key not valid"}'))
    with pytest.raises(pencari_data.PenyediaTidakTersedia, match="HTTP 400 .*API key not valid"):
        pencari_data._post_json("https://contoh.example/x", {}, {})
    monkeypatch.setattr(pencari_data.urllib.request, "urlopen", tolak(429, "rate\nlimit"))
    with pytest.raises(pencari_data.PenyediaTidakTersedia, match="batas pemakaian gratis"):
        pencari_data._post_json("https://contoh.example/x", {}, {})

    def lambat(req, timeout=None):
        raise TimeoutError("timed out")
    monkeypatch.setattr(pencari_data.urllib.request, "urlopen", lambat)
    with pytest.raises(pencari_data.PenyediaTidakTersedia, match="jaringan"):
        pencari_data._post_json("https://contoh.example/x", {}, {})


def test_ambil_json_dan_normalisasi():
    assert pencari_data.ambil_json_dari_teks('ok {"a": 1} selesai') == {"a": 1}
    assert pencari_data.ambil_json_dari_teks('```json\n{"a": [1]}\n```') == {"a": [1]}
    with pytest.raises(RuntimeError):
        pencari_data.ambil_json_dari_teks("tidak ada json")
    h = pencari_data.normalisasi_hasil({"kandidat": [{"nama_sumber": "BPS", "url": "https://bps.go.id"}, "x", {"url": "y"}],
                                        "tidak_ditemukan": "tidak ada"})
    assert len(h["kandidat"]) == 1 and h["kandidat"][0]["metode_akses"] == "tidak diketahui"
    assert h["kandidat"][0]["perlu_izin"] is True and h["tidak_ditemukan"] == ["tidak ada"]


def test_cek_url_tidak_valid():
    assert pencari_data.cek_url("bukan-url")[0] is False
    assert pencari_data.cek_url("")[0] is False


def test_urutan_penyedia(konf):
    gratis = ["gemini", "groq", "cerebras", "openrouter", "mistral", "github_models"]
    assert pencari_data.urutan_penyedia(konf) == gratis
    assert pencari_data.urutan_penyedia(konf, "anthropic") == ["anthropic"]
    assert pencari_data.urutan_penyedia(konf, "cerebras") == ["cerebras"]
    # urutan lama yang tersimpan tetap didahulukan, AI gratis lain menyusul sebagai cadangan
    konf.pengaturan["ai"]["urutan_otomatis"] = ["github_models", "gemini"]
    assert pencari_data.urutan_penyedia(konf) == ["github_models", "gemini", "groq", "cerebras", "openrouter", "mistral"]
    konf.pengaturan["ai"]["urutan_otomatis"] = ["gemini", "anthropic"]
    assert pencari_data.urutan_penyedia(konf) == ["gemini", "anthropic", "groq", "cerebras", "openrouter", "mistral", "github_models"]
    with pytest.raises(ValueError):
        pencari_data.urutan_penyedia(konf, "entah")


def tavily_palsu(dikirim, gagal_kode=None):
    def kirim(url, header, isi):
        dikirim.append(isi)
        assert url == pencari_data.URL_TAVILY and header["Authorization"].startswith("Bearer ")
        if gagal_kode:
            raise pencari_data.PenyediaTidakTersedia(f"HTTP {gagal_kode}: kuota habis")
        return {"results": [
            {"title": "Panel Harga Pangan", "url": "https://panelharga.badanpangan.go.id/tabel", "content": "harga  cabai\nharian"},
            {"title": "BPS Bengkulu", "url": "https://bengkulu.bps.go.id/statistics-table", "content": "tabel harga"}]}
    return kirim


def test_tavily_hasil_web_diberikan_ke_ai_dan_url_dicocokkan(konf, tanpa_kunci):
    cari_web, dikirim_ai = [], []

    def groq(url, header, isi):
        dikirim_ai.append(isi)
        return jawaban_chat(json.dumps(HASIL_JSON))

    catatan = pencari_data.cari(konf, "cabai rawit merah", "Oktober 2026", penyedia="groq",
                                klien={"tavily": tavily_palsu(cari_web), "groq": groq}, pemeriksa_url=None)
    assert len(cari_web) == 3 and cari_web[1]["include_domains"] == pencari_data.DOMAIN_RESMI
    sistem, pengguna = dikirim_ai[0]["messages"][0]["content"], dikirim_ai[0]["messages"][1]["content"]
    assert "HASIL PENCARIAN WEB" in pengguna and "https://bengkulu.bps.go.id/statistics-table" in pengguna
    assert "HANYA dari hasil itu" in sistem and "TIDAK memiliki akses internet" not in sistem
    k = catatan["hasil"]["kandidat"]
    assert k[0]["url_ada_di_hasil_pencarian"] is True and k[1]["url_ada_di_hasil_pencarian"] is False
    assert catatan["punya_pencarian_web"] is True and catatan["pencarian_web"] == "Tavily, 2 hasil"


def test_tavily_kuota_habis_ai_tetap_jalan_tanpa_pencarian(konf, tanpa_kunci):
    cari_web = []
    catatan = pencari_data.cari(konf, "x", "y", penyedia="groq", pemeriksa_url=None,
                                klien={"tavily": tavily_palsu(cari_web, 432), "groq": lambda u, h, i: jawaban_chat('{"kandidat": []}')})
    assert len(cari_web) == 1  # berhenti setelah kuota habis, tidak membuang permintaan
    assert catatan["penyedia"] == "groq" and catatan["punya_pencarian_web"] is False and catatan["pencarian_web"] is None
    assert catatan["penyedia_dilewati"][0].startswith("tavily: HTTP 432")


def test_gemini_memakai_hasil_tavily_tanpa_pencarian_google(konf, tanpa_kunci):
    isi_gemini = []

    def gemini(url, header, isi):
        isi_gemini.append(isi)
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(HASIL_JSON)}]}}]}

    catatan = pencari_data.cari(konf, "cabai", "Okt", penyedia="gemini", pemeriksa_url=None,
                                klien={"tavily": tavily_palsu([]), "gemini": gemini})
    assert "tools" not in isi_gemini[0] and "HANYA dari hasil itu" in isi_gemini[0]["system_instruction"]["parts"][0]["text"]
    assert catatan["hasil"]["kandidat"][0]["url_ada_di_hasil_pencarian"] is True


def test_gemini_tanpa_tavily_pencarian_google_ditolak_dicoba_tanpa_pencarian(konf, tanpa_kunci):
    isi_gemini = []

    def gemini(url, header, isi):
        isi_gemini.append(isi)
        if "tools" in isi:
            raise pencari_data.PenyediaTidakTersedia("HTTP 400 (permintaan ditolak): grounding tidak tersedia di free tier")
        return {"candidates": [{"content": {"parts": [{"text": '{"kandidat": []}'}]}}]}

    catatan = pencari_data.cari(konf, "x", "y", penyedia="gemini", klien={"gemini": gemini}, pemeriksa_url=None)
    assert len(isi_gemini) == 2 and "tools" not in isi_gemini[1]
    assert "TIDAK memiliki akses internet" in isi_gemini[1]["system_instruction"]["parts"][0]["text"]
    assert catatan["penyedia"] == "gemini" and catatan["punya_pencarian_web"] is False
