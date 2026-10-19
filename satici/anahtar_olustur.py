"""Satıcı imza anahtarını bir kez oluşturur ve açık anahtarı dose/lisans.py dosyasına yazar.

ozel_anahtar.pem dosyası lisans üretmenin tek yoludur: kaybederseniz yeni lisans üretemezsiniz, başkasının eline
geçerse o kişi de lisans üretebilir. Yedeğini şifreli bir USB belleğe alın, programla birlikte asla dağıtmayın.
"""
import re
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

KLASOR = Path(__file__).resolve().parent
OZEL = KLASOR / "ozel_anahtar.pem"
LISANS_PY = KLASOR.parent / "dose" / "lisans.py"
sys.path.insert(0, str(KLASOR.parent))

from dose.lisans import _b64  # noqa: E402


def acik_anahtar_metni(ozel) -> str:
    return _b64(ozel.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))


def main():
    if OZEL.exists():
        ozel = serialization.load_pem_private_key(OZEL.read_bytes(), password=None)
        print(f"Mevcut özel anahtar kullanılıyor: {OZEL}")
    else:
        ozel = Ed25519PrivateKey.generate()
        OZEL.write_bytes(ozel.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                            serialization.NoEncryption()))
        print(f"Yeni özel anahtar oluşturuldu: {OZEL}")
    acik = acik_anahtar_metni(ozel)
    metin = LISANS_PY.read_text(encoding="utf-8")
    yeni = re.sub(r'^ACIK_ANAHTAR = ".*"$', f'ACIK_ANAHTAR = "{acik}"', metin, count=1, flags=re.M)
    if yeni != metin:
        LISANS_PY.write_text(yeni, encoding="utf-8")
        print("Açık anahtar dose/lisans.py dosyasına yazıldı. EXE paketini yeniden oluşturun.")
    else:
        print("dose/lisans.py zaten bu açık anahtarı içeriyor.")
    print("\nÖNEMLİ: ozel_anahtar.pem dosyasının yedeğini alın ve kimseyle paylaşmayın.")


if __name__ == "__main__":
    main()
