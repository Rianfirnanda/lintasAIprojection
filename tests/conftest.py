import shutil
from datetime import date
from pathlib import Path

import pytest

from pipeline import konfigurasi

AKAR = Path(__file__).resolve().parent.parent
HARI_INI = date(2026, 9, 29)


def salin_config(tujuan: Path) -> None:
    """Salin config/ ke folder uji. Sistem sungguhan sementara memakai Provinsi Bengkulu (PIHPS) sebagai target;
    uji tetap memakai skenario Kabupaten Bengkulu Tengah (pasar PSR01 dan seterusnya)."""
    import json

    shutil.copytree(AKAR / "config", tujuan)
    p = tujuan / "pengaturan.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["wilayah_target"] = "1709"
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.fixture
def akar_sementara(tmp_path: Path) -> Path:
    """Salinan config/ di folder sementara dengan folder data kosong."""
    salin_config(tmp_path / "config")
    for sub in ("masuk/harga", "masuk/konteks", "validasi", "tindak_lanjut", "sumber"):
        (tmp_path / "data" / sub).mkdir(parents=True)
    return tmp_path


@pytest.fixture
def konf(akar_sementara: Path):
    return konfigurasi.muat(akar_sementara, hari_ini=HARI_INI)


def tulis_csv(path: Path, teks: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(teks.strip() + "\n", encoding="utf-8")
    return path
