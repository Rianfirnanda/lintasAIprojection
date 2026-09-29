"""Tindak lanjut sinyal (umpan balik TPID): buku catatan CSV + sinkronisasi opsional dengan GitHub Issues.

Status sinyal: baru -> perlu_verifikasi -> terverifikasi | false_alarm -> ditindaklanjuti -> selesai.
Label 'false_alarm' / 'terverifikasi' menjadi label kebenaran untuk mengukur precision/recall deteksi anomali.
'anomali_terlewat' dicatat analis bila ada gejolak nyata yang tidak terdeteksi (untuk menghitung recall).
"""

from __future__ import annotations

import csv
import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

STATUS_VALID = ("perlu_verifikasi", "terverifikasi", "false_alarm", "ditindaklanjuti", "selesai", "anomali_terlewat")
STATUS_BENAR = ("terverifikasi", "ditindaklanjuti", "selesai")

LABEL_SINYAL = "sinyal-harga"
LABEL_STATUS = {
    "status: perlu-verifikasi": "perlu_verifikasi",
    "status: terverifikasi": "terverifikasi",
    "status: false-alarm": "false_alarm",
    "status: ditindaklanjuti": "ditindaklanjuti",
    "status: selesai": "selesai",
}
WARNA_LABEL = {
    LABEL_SINYAL: "b60205",
    "status: perlu-verifikasi": "fbca04",
    "status: terverifikasi": "0e8a16",
    "status: false-alarm": "cccccc",
    "status: ditindaklanjuti": "1d76db",
    "status: selesai": "5319e7",
}
_PENANDA = re.compile(r"<!--\s*id_sinyal:\s*([0-9a-f]+)\s*-->")


@dataclass
class CatatanTindakLanjut:
    status: str
    catatan: str
    petugas: str
    tanggal: str
    sumber: str = "csv"
    url: str = ""
    riwayat: list[dict] = field(default_factory=list)


def baca_buku(folder: Path) -> tuple[dict[str, CatatanTindakLanjut], list[dict]]:
    """Baca data/tindak_lanjut/*.csv. Kembalikan status terkini per sinyal dan daftar anomali terlewat."""
    baris: list[dict] = []
    for p in sorted(folder.glob("*.csv")) if folder.exists() else []:
        with p.open(newline="", encoding="utf-8-sig") as f:
            for b in csv.DictReader(f):
                b = {k.strip(): (v or "").strip() for k, v in b.items() if k}
                if b.get("status") in STATUS_VALID:
                    baris.append(b)
    baris.sort(key=lambda b: b.get("tanggal", ""))
    status: dict[str, CatatanTindakLanjut] = {}
    terlewat: list[dict] = []
    for b in baris:
        if b["status"] == "anomali_terlewat":
            terlewat.append({
                "kode_varian": b.get("kode_varian", ""), "tanggal_kejadian": b.get("tanggal_kejadian", ""),
                "catatan": b.get("catatan", ""), "petugas": b.get("petugas", ""),
            })
            continue
        sid = b.get("id_sinyal", "")
        if not sid:
            continue
        entri = {"status": b["status"], "catatan": b.get("catatan", ""), "petugas": b.get("petugas", ""),
                 "tanggal": b.get("tanggal", "")}
        lama = status.get(sid)
        riwayat = (lama.riwayat if lama else []) + [entri]
        status[sid] = CatatanTindakLanjut(b["status"], entri["catatan"], entri["petugas"], entri["tanggal"], riwayat=riwayat)
    return status, terlewat


class KlienGitHub:
    def __init__(self, token: str, repo: str, api: str = "https://api.github.com"):
        self.token, self.repo, self.api = token, repo, api.rstrip("/")

    def _minta(self, metode: str, path: str, data: dict | None = None):
        url = path if path.startswith("http") else f"{self.api}{path}"
        req = urllib.request.Request(
            url, method=metode, data=json.dumps(data).encode() if data is not None else None,
            headers={
                "Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "pemantauan-harga-benteng",
                **({"Content-Type": "application/json"} if data is not None else {}),
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                isi = r.read()
                return r.status, (json.loads(isi) if isi else None), dict(r.headers)
        except urllib.error.HTTPError as e:
            isi = e.read()
            try:
                return e.code, json.loads(isi), dict(e.headers)
            except ValueError:
                return e.code, None, dict(e.headers)

    def daftar_issue(self, label: str) -> list[dict]:
        hasil, halaman = [], 1
        while True:
            kode, data, _ = self._minta("GET", f"/repos/{self.repo}/issues?labels={label}&state=all&per_page=100&page={halaman}")
            if kode != 200:
                raise RuntimeError(f"gagal membaca issue (HTTP {kode}): {data}")
            hasil.extend(i for i in data if "pull_request" not in i)
            if len(data) < 100:
                return hasil
            halaman += 1

    def pastikan_label(self) -> None:
        for nama, warna in WARNA_LABEL.items():
            kode, _, _ = self._minta("POST", f"/repos/{self.repo}/labels", {"name": nama, "color": warna})
            if kode not in (201, 422):  # 422 = label sudah ada
                log.warning("gagal membuat label %s (HTTP %s)", nama, kode)

    def buat_issue(self, judul: str, isi: str, label: list[str]) -> dict:
        kode, data, _ = self._minta("POST", f"/repos/{self.repo}/issues", {"title": judul, "body": isi, "labels": label})
        if kode != 201:
            raise RuntimeError(f"gagal membuat issue (HTTP {kode}): {data}")
        return data


def status_dari_issue(issue: dict) -> str:
    label = [lb["name"] for lb in issue.get("labels", [])]
    for nama in label:
        if nama in LABEL_STATUS:
            return LABEL_STATUS[nama]
    return "selesai" if issue.get("state") == "closed" else "perlu_verifikasi"


def isi_issue(s: dict, url_dashboard: str) -> str:
    k = s.get("konteks", {})
    baris = [
        f"**{s['judul']}**",
        "",
        f"- Jenis sinyal: `{s['jenis']}` · Keparahan: **{s['keparahan']}**",
        f"- Periode: {s['tanggal_mulai']} s.d. {s['tanggal_terakhir']}",
    ]
    if s.get("nilai_aktual") is not None:
        baris.append(f"- Harga aktual: Rp{s['nilai_aktual']:,.0f} · Baseline 28 hari: Rp{s['baseline']:,.0f} "
                     f"· Deviasi: {s['deviasi_persen']:+.1f}%".replace(",", "."))
    if s.get("narasi"):
        baris += ["", "**Konteks otomatis (perlu diverifikasi):**", s["narasi"]]
    if k:
        baris += ["", "<details><summary>Data konteks</summary>", "", "```json",
                  json.dumps(k, ensure_ascii=False, indent=2), "```", "</details>"]
    baris += [
        "",
        "### Cara menindaklanjuti",
        "1. Verifikasi ke lapangan/pasar dan sumber pendukung.",
        "2. Pasang **satu** label status: `status: terverifikasi`, `status: false-alarm`, "
        "`status: ditindaklanjuti`, atau `status: selesai` (menutup issue = selesai).",
        "3. Tulis ringkasan temuan & tindakan di komentar. Status akan tampil di dashboard pada pembaruan berikutnya.",
        "",
        f"Dashboard: {url_dashboard}" if url_dashboard else "",
        "",
        f"<!-- id_sinyal: {s['id']} -->",
    ]
    return "\n".join(baris)


def sinkronisasi_github(sinyal: list[dict], pengaturan: dict, token: str | None, repo: str | None,
                        boleh_buat: bool, url_dashboard: str = "") -> tuple[dict[str, dict], str]:
    """Baca status dari issue yang ada; buat issue baru untuk sinyal prioritas. Tidak pernah menggagalkan pipeline."""
    tl = pengaturan["tindak_lanjut"]
    if not tl.get("github_issues") or not token or not repo:
        return {}, "sinkronisasi GitHub Issues nonaktif (token/repo tidak tersedia atau dimatikan di pengaturan)"
    klien = KlienGitHub(token, repo)
    peta: dict[str, dict] = {}
    try:
        for issue in klien.daftar_issue(LABEL_SINYAL):
            m = _PENANDA.search(issue.get("body") or "")
            if m:
                peta[m.group(1)] = {
                    "status": status_dari_issue(issue), "url": issue["html_url"], "nomor": issue["number"],
                    "diperbarui": issue.get("updated_at", ""),
                }
        if not boleh_buat:
            return peta, f"{len(peta)} issue terbaca; pembuatan issue dilewati (mode demo)"
        tingkat = {"rendah": 0, "sedang": 1, "tinggi": 2}
        minimal = tingkat[tl["keparahan_minimal_issue"]]
        calon = [
            s for s in sinyal
            if s["id"] not in peta and s["jenis"] == "anomali_harga" and s.get("aktif")
            and tingkat[s["keparahan"]] >= minimal
        ]
        if calon:
            klien.pastikan_label()
        dibuat = 0
        for s in calon[: tl["maks_issue_baru_per_jalan"]]:
            issue = klien.buat_issue(f"[Sinyal harga] {s['judul']}", isi_issue(s, url_dashboard),
                                     [LABEL_SINYAL, "status: perlu-verifikasi"])
            peta[s["id"]] = {"status": "perlu_verifikasi", "url": issue["html_url"], "nomor": issue["number"],
                             "diperbarui": issue.get("created_at", "")}
            dibuat += 1
        return peta, f"{len(peta)} issue tersinkron; {dibuat} issue baru dibuat"
    except Exception as e:  # jaringan/izin: catat, jangan gagalkan publikasi dashboard
        log.warning("sinkronisasi GitHub gagal: %s", e)
        return peta, f"sinkronisasi GitHub gagal: {e}"
