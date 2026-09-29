import shutil
from datetime import date
from pathlib import Path

import pytest

from pipeline import konfigurasi

AKAR = Path(__file__).resolve().parent.parent
HARI_INI = date(2026, 9, 29)


@pytest.fixture
def akar_sementara(tmp_path: Path) -> Path:
    """Salinan config/ di folder sementara dengan folder data kosong."""
    shutil.copytree(AKAR / "config", tmp_path / "config")
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
