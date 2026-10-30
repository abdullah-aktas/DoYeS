"""Satıcıya özel, komut satırından lisans üretme aracı.

Özel anahtarı kullanarak okul lisansını imzalar, .lic dosyası oluşturur ve satış kaydına ekler.
"""
import argparse
import csv
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from cryptography.hazmat.primitives import serialization

KLASOR = Path(__file__).resolve().parent
sys.path.insert(0, str(KLASOR.parent))

from dose import lisans  # noqa: E402

OZEL = KLASOR / "ozel_anahtar.pem"
KAYIT = KLASOR / "lisanslar.csv"
LIC_KLASORU = KLASOR / "lisanslar"
KOLONLAR = ["no", "tarih", "okul", "kurum_kodu", "tur", "bitis", "ucret", "fatura_no", "iletisim", "not", "anahtar"]
SUREKLI = lisans.SUREKLI


def yil_ekle(t: date, n: int) -> date:
    try:
        return t.replace(year=t.year + n)
    except ValueError:
        return t.replace(year=t.year + n, day=28)


def kayitlari_oku() -> list[dict]:
    if not KAYIT.exists():
        return []
    with KAYIT.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def kayit_ekle(satir: dict):
    yeni = not KAYIT.exists()
    with KAYIT.open("a", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=KOLONLAR, delimiter=";")
        if yeni:
            w.writeheader()
        w.writerow(satir)


def sonraki_no() -> str:
    yil = date.today().year
    onek = f"L-{yil}-"
    sayilar = [int(k["no"][len(onek):]) for k in kayitlari_oku() if k.get("no", "").startswith(onek)
               and k["no"][len(onek):].isdigit()]
    return f"{onek}{max(sayilar, default=0) + 1:04d}"


def lisans_uret(okul: str, kurum_kodu: str, sure: str, bitis: date | None, ucret: Decimal,
                fatura_no: str = "", iletisim: str = "", notlar: str = "") -> tuple[str, Path]:
    if not OZEL.exists():
        raise FileNotFoundError(f"{OZEL} bulunamadı. Önce 'python satici/anahtar_olustur.py' çalıştırın.")
    ozel = serialization.load_pem_private_key(OZEL.read_bytes(), password=None)
    acik = lisans._b64(ozel.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
    if acik != lisans.ACIK_ANAHTAR:
        raise ValueError("Özel anahtar, dose/lisans.py içindeki açık anahtarla eşleşmiyor.")

    okul = okul.strip()
    kod = lisans.kurum_kodu_normalize(kurum_kodu)
    if not okul or not kod:
        raise ValueError("Okul adı ve geçerli kurum kodu zorunludur.")
    if not ucret.is_finite() or ucret < 0:
        raise ValueError("Ücret sonlu ve sıfır veya daha büyük olmalıdır.")
    if sure == "0":
        tur, bitis = SUREKLI, None
    else:
        if bitis is None or bitis <= date.today():
            raise ValueError("Bitiş tarihi bugünden sonra olmalıdır.")
        tur = "Özel tarih" if sure == "özel" else f"{sure} yıl"

    no = sonraki_no()
    anahtar = lisans.imzala(ozel, okul, kod, bitis, no, tur)
    lisans.coz(anahtar, acik)
    LIC_KLASORU.mkdir(exist_ok=True)
    dosya = LIC_KLASORU / f"{kod}_{no}.lic"
    dosya.write_text(anahtar + "\n", encoding="utf-8")
    kayit_ekle({
        "no": no,
        "tarih": date.today().strftime("%d.%m.%Y"),
        "okul": okul,
        "kurum_kodu": kod,
        "tur": tur,
        "bitis": bitis.strftime("%d.%m.%Y") if bitis else SUREKLI,
        "ucret": f"{ucret:.2f}",
        "fatura_no": fatura_no.strip(),
        "iletisim": iletisim.strip(),
        "not": notlar.strip(),
        "anahtar": anahtar,
    })
    return anahtar, dosya


def _interaktif(parser: argparse.ArgumentParser) -> argparse.Namespace:
    print("DÖSE lisans üretimi (süre: 1, 2, 3 yıl; 0=süresiz; özel=özel bitiş tarihi)")
    okul = input("Okul adı: ").strip()
    kurum_kodu = input("MEB kurum kodu: ").strip()
    sure = input("Süre [1]: ").strip() or "1"
    if sure not in ("1", "2", "3", "0", "özel"):
        parser.error("Süre 1, 2, 3, 0 veya özel olmalıdır.")
    bitis = None
    if sure == "özel":
        try:
            bitis = date.fromisoformat(input("Bitiş tarihi (YYYY-MM-DD): ").strip())
        except ValueError:
            parser.error("Bitiş tarihi YYYY-MM-DD biçiminde olmalıdır.")
    ucret_metin = input("Ücret (TL) [0]: ").strip() or "0"
    try:
        ucret = Decimal(ucret_metin)
    except InvalidOperation:
        parser.error("Ücret sayısal olmalıdır.")
    return argparse.Namespace(
        okul=okul, kurum_kodu=kurum_kodu, sure=sure, bitis=bitis, ucret=ucret,
        fatura_no=input("Fatura no [boş]: ").strip(),
        iletisim=input("İletişim [boş]: ").strip(),
        notlar=input("Not [boş]: ").strip(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Okul adına imzalı DÖSE lisansı üretir.")
    parser.add_argument("--okul", help="Okulun tam adı")
    parser.add_argument("--kurum-kodu", help="MEB kurum kodu")
    parser.add_argument("--sure", choices=("1", "2", "3", "0", "özel"), default="1",
                        help="Lisans süresi: yıl, 0=süresiz, özel=--bitis")
    parser.add_argument("--bitis", type=date.fromisoformat, help="Özel süre için YYYY-MM-DD bitiş tarihi")
    parser.add_argument("--ucret", type=Decimal, default=Decimal("0"), help="Satış ücreti (TL)")
    parser.add_argument("--fatura-no", default="")
    parser.add_argument("--iletisim", default="")
    parser.add_argument("--not", dest="notlar", default="")
    args = _interaktif(parser) if argv is None and len(sys.argv) == 1 else parser.parse_args(argv)
    if not args.okul or not args.kurum_kodu:
        parser.error("--okul ve --kurum-kodu gereklidir.")

    if args.sure == "özel":
        if args.bitis is None:
            parser.error("--sure özel seçildiğinde --bitis gereklidir.")
        bitis = args.bitis
    elif args.sure == "0":
        if args.bitis is not None:
            parser.error("Süresiz lisansta --bitis kullanılamaz.")
        bitis = None
    else:
        if args.bitis is not None:
            parser.error("--bitis yalnız --sure özel için kullanılabilir.")
        bitis = yil_ekle(date.today(), int(args.sure))

    try:
        anahtar, dosya = lisans_uret(args.okul, args.kurum_kodu, args.sure, bitis, args.ucret,
                                     args.fatura_no, args.iletisim, args.notlar)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Lisans üretilemedi: {exc}\n")
    print(f"Lisans üretildi: {dosya}")
    print(f"Anahtar: {anahtar}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
