"""Pemuatan master data dan pengaturan dari folder config/."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import pengaturan as modul_pengaturan

AKAR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Varian:
    kode: str
    nama: str
    kode_komoditas: str
    komoditas: str
    satuan: str
    kelompok: str
    paket: str
    aktif: bool
    batas_bawah: float
    batas_atas: float


@dataclass(frozen=True)
class Wilayah:
    kode: str
    nama: str
    peran: str
    lat: float
    lon: float


@dataclass(frozen=True)
class Pasar:
    kode: str
    nama: str
    kode_wilayah: str
    kecamatan: str
    lat: float | None
    lon: float | None
    blank_spot: bool
    koordinat_terverifikasi: bool
    aktif: bool


@dataclass(frozen=True)
class Sumber:
    kode: str
    nama: str
    kelompok: str
    metode_akses: str
    frekuensi: str
    url: str
    lisensi: str
    status: str
    prioritas: int
    catatan: str


@dataclass(frozen=True)
class Acara:
    tanggal: date
    nama: str
    jenis: str
    status: str


@dataclass
class Konfigurasi:
    akar: Path
    pengaturan: dict
    varian: dict[str, Varian]
    wilayah: dict[str, Wilayah]
    pasar: dict[str, Pasar]
    sumber: dict[str, Sumber]
    kalender: list[Acara]
    hari_ini: date = field(default_factory=date.today)

    @property
    def wilayah_target(self) -> str:
        return self.pengaturan["wilayah_target"]

    @property
    def wilayah_cadangan(self) -> str | None:
        """Wilayah yang deretnya dipakai bila varian tidak punya harga di wilayah target (mis. Provinsi Bengkulu)."""
        kode = self.pengaturan.get("wilayah_cadangan")
        return kode if kode and kode != self.wilayah_target else None

    @property
    def varian_aktif(self) -> list[Varian]:
        return [v for v in self.varian.values() if v.aktif]

    @property
    def komoditas_aktif(self) -> list[str]:
        urut: list[str] = []
        for v in self.varian_aktif:
            if v.kode_komoditas not in urut:
                urut.append(v.kode_komoditas)
        return urut

    def pasar_di(self, kode_wilayah: str, hanya_aktif: bool = True) -> list[Pasar]:
        return [
            p for p in self.pasar.values()
            if p.kode_wilayah == kode_wilayah and (p.aktif or not hanya_aktif)
        ]

    def prioritas_sumber(self, kode: str) -> int:
        s = self.sumber.get(kode)
        return s.prioritas if s else 99

    def hari_raya(self) -> list[Acara]:
        return [a for a in self.kalender if a.jenis == "hari_raya"]


def _baca_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return [
            {k.strip(): (v or "").strip() for k, v in baris.items() if k}
            for baris in csv.DictReader(f)
        ]


def _float_atau_none(nilai: str) -> float | None:
    return float(nilai) if nilai not in ("", None) else None


def hari_ini_wib(zona: str = "Asia/Jakarta") -> date:
    return datetime.now(ZoneInfo(zona)).date()


def muat(akar: Path | str | None = None, hari_ini: date | None = None) -> Konfigurasi:
    akar = Path(akar) if akar else AKAR
    folder = akar / "config"
    pengaturan = json.loads((folder / "pengaturan.json").read_text(encoding="utf-8"))
    modul_pengaturan.pastikan_sah(pengaturan, modul_pengaturan.muat_skema(folder))

    varian = {}
    for b in _baca_csv(folder / "komoditas.csv"):
        varian[b["kode_varian"]] = Varian(
            kode=b["kode_varian"],
            nama=b["varian"],
            kode_komoditas=b["kode_komoditas"],
            komoditas=b["komoditas"],
            satuan=b["satuan"],
            kelompok=b["kelompok"],
            paket=b["paket"],
            aktif=b["aktif"] == "1",
            batas_bawah=float(b["batas_bawah"]),
            batas_atas=float(b["batas_atas"]),
        )

    wilayah = {
        b["kode_wilayah"]: Wilayah(
            kode=b["kode_wilayah"], nama=b["nama_wilayah"], peran=b["peran"],
            lat=float(b["lat"]), lon=float(b["lon"]),
        )
        for b in _baca_csv(folder / "wilayah.csv")
    }

    pasar = {}
    for b in _baca_csv(folder / "pasar.csv"):
        if b["kode_wilayah"] not in wilayah:
            raise ValueError(f"Pasar {b['kode_pasar']} merujuk wilayah tak dikenal {b['kode_wilayah']}")
        pasar[b["kode_pasar"]] = Pasar(
            kode=b["kode_pasar"], nama=b["nama_pasar"], kode_wilayah=b["kode_wilayah"],
            kecamatan=b.get("kecamatan", ""),
            lat=_float_atau_none(b.get("lat", "")), lon=_float_atau_none(b.get("lon", "")),
            blank_spot=b.get("blank_spot") == "1",
            koordinat_terverifikasi=b.get("koordinat_terverifikasi") == "1",
            aktif=b.get("aktif", "1") == "1",
        )

    sumber = {
        b["kode_sumber"]: Sumber(
            kode=b["kode_sumber"], nama=b["nama_sumber"], kelompok=b["kelompok"],
            metode_akses=b["metode_akses"], frekuensi=b["frekuensi"], url=b["url"],
            lisensi=b["lisensi"], status=b["status"],
            prioritas=int(b["prioritas_rekonsiliasi"] or 99), catatan=b["catatan"],
        )
        for b in _baca_csv(folder / "sumber.csv")
    }

    kalender = sorted(
        (
            Acara(
                tanggal=date.fromisoformat(b["tanggal"]), nama=b["nama_acara"],
                jenis=b["jenis"], status=b["status"],
            )
            for b in _baca_csv(folder / "kalender.csv")
        ),
        key=lambda a: a.tanggal,
    )

    if pengaturan["wilayah_target"] not in wilayah:
        raise ValueError("wilayah_target pada pengaturan.json tidak ada di wilayah.csv")
    if pengaturan.get("wilayah_cadangan") and pengaturan["wilayah_cadangan"] not in wilayah:
        raise ValueError("wilayah_cadangan pada pengaturan.json tidak ada di wilayah.csv")

    return Konfigurasi(
        akar=akar, pengaturan=pengaturan, varian=varian, wilayah=wilayah, pasar=pasar,
        sumber=sumber, kalender=kalender,
        hari_ini=hari_ini or hari_ini_wib(pengaturan.get("zona_waktu", "Asia/Jakarta")),
    )
