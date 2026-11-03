# DÖSE Yönetim — Teknik Servis ve Programcı Kılavuzu

## 1. Mimari

```
depo/
  main.py                 masaüstü başlatıcı
  istemci/                Flet UI (Windows / Android / web)
  dose/                   çekirdek hesap / mevzuat / Excel-PDF / şablonlar
  supabase/               migrations + PGlite testleri (klasör adı CLI için sabit)
  tests/                  Python testleri
  docs/                   kılavuzlar

Flet istemcisi
        │  HTTPS: Supabase Auth + PostgREST (yayınlanabilir anahtar)
        ▼
Supabase (tek proje, çok okul)
  ├─ auth.users               e-posta + şifre
  ├─ dose_private.*           okul, üyelik, davet, yetki, satıcı RPC
  └─ public.*                 iş tabloları (okul_id + RLS)
```

- İstemcide sır yoktur. Yayınlanabilir anahtar herkese açık olabilir; kurallar RLS, tetikleyiciler ve
  `SECURITY DEFINER` RPC'lerdedir. **service_role ve veritabanı şifresi hiçbir istemciye konmaz.**
- Proje adresi ve anahtar [istemci/ayar.py](istemci/ayar.py); `DOSE_SUPABASE_URL` / `DOSE_SUPABASE_ANAHTAR` ile
  değiştirilebilir.
- Masaüstü ve Android'de istekler `urllib` + `certifi`, web'de (Pyodide) `pyfetch`
  ([istemci/supa.py](istemci/supa.py)).

## 2. Sunucu tarafı kurallar

| Konu | Migration |
|---|---|
| Okul, lisans, etkinleştirme, üyelik, davet | `20261030000000_okul_lisans.sql` |
| `okul_id`, sürüm, işlem kaydı, sıra no, seçenekler | `20261030000100_cok_okul_sema.sql` |
| TCKN/VKN/IBAN/tarih, sürüm çakışması, silme koruması | `20261030000200_cekirdek_dogrulama.sql` |
| RPC, tablo yetkileri, RLS | `20261030000300_cekirdek_rpc_yetki.sql` |
| Sipariş taslak / onay | `20261031000000_siparis_onay.sql` |
| Sipariş güvenliği, kesin tutarlar | `20261031000100_siparis_guvenligi.sql` |
| Manuel stok, yevmiye, okul hesapları | `20261031000200_stok_yevmiye.sql` |
| Alış / kısmi satış faturası | `20261031000300_fatura.sql` |
| Kasa/banka (açılış + fatura bağlantılı) | `20261031000400_kasa_banka.sql` |
| Merkez tahsis parametreleri | `20261031000500_merkez_mevzuat.sql` |
| 1 ay deneme lisansı | `20261101000000_deneme_lisansi.sql` |
| Parça başı | `20261102000000_parca_basi.sql` |
| Fazla çalışma | `20261103000000_fazla_calisma.sql` |
| Hazine payı | `20261104000000_hazine_payi.sql` |
| Yıl sonu / ÜTP | `20261105000000_yil_sonu.sql` |
| Görevler, maliyet, kasa genişletme, resmi/denetim, rapor | `20261106000000_gorev_mevzuat_maliyet_kasa_resmi.sql` |
| Mevzuat oranlarının PB/FC hesabına bağlanması | `20261107000000_mevzuat_hesap_baglama.sql` |
| Özel sektör/tesis peşinat, faaliyet raporu, Bakanlık mizan | `20261108000000_ozel_tesis_faaliyet_rapor.sql` |
| Alış temin usulü, gider türü, belge kontrol listesi | `20261111000000_alis_temin_belgeler.sql` |

- **Yetki:** `dose_private.sayfa_yetki` (rol × sayfa → `y`/`g`). Lisans dolunca `y` → `g`.
- **Çakışma:** istemci okuduğu `surum`'u gönderir; farklıysa `P0001` + `hint = surum_cakismasi`.
- **Canlı yenileme:** 5 sn'de bir `dose_son_degisiklik()`; kaydedilmemiş form korunur.
- **İşlem kaydı:** `islem_log` güncelleme/silme engelli.
- **Sipariş:** `dose_siparis_*` RPC; NUMERIC tutarlar; `_kesin` alanları; doğrudan PostgREST yazımı yok.
  Özel sektör / tesis esaslarında `siparis_pesinat_zorunlu` asgari peşinatı denetler.
- **Onay zinciri:** Alan Şefi → Teknik Müdür Yardımcısı → Okul Müdürü. Sipariş onayı yevmiye yazmaz.
- **Fatura / stok / kasa:** ilgili `dose_*_kaydet` / `tersle` RPC'leri atomik; GİB veya banka API’si yoktur.
  Alışta temin usulü (doğrudan temin vb.), gider türü ve zorunlu alım belgeleri `dose_alim_hazirla`
  ile `istek_id` üzerinden kayıttan hemen önce bağlanır; önizleme `dose_alim_onizle`.
- **Merkez parametreleri:** `dose_private.mevzuat_yoneticisi_ata` yalnız SQL/service_role. Okul saymanı
  `dose_mevzuat_karar` ile doğrular; oranlar `mevzuat_okul_oranlari` üzerinden PB/FC’ye bağlanır.
- **Rapor:** `dose_rapor_ozet`, `dose_faaliyet_rapor` (md.48), `dose_mizan_bakanlik` (md.47).
- Yerel PGlite canlı eşzamanlılığı kanıtlamaz; canlıya `npx supabase db push` gerekir.

## 3. İlk kurulum (bir kez)

```powershell
cd D:\DÖSE\supabase
npm install
npx supabase login
npx supabase link --project-ref bzirnfsgdswcwwutmwdi
npx supabase db push
```

Supabase paneli: Email provider + Confirm email açık; Site URL ve SMTP tanımlı olsun. Okul açma:
[SATIS_REHBERI.md](SATIS_REHBERI.md) §2.

## 4. Kaynak kod

| Dosya | Görev |
|---|---|
| `main.py` | Masaüstü giriş noktası (`ft.run` + assets) |
| `istemci/uygulama.py` | Oturum, kabuk, menü, canlı yenileme |
| `istemci/ekranlar.py` | Ana, kurum, tanımlar, sipariş/onay, kullanıcı, işlem kaydı |
| `istemci/faturalar.py` | Alış/satış fatura |
| `istemci/finans.py` | Stok, yevmiye/mizan, hesap tanımları |
| `istemci/kasa.py` | Açılış, tahsilat/ödeme, avans, virman, faturasız |
| `istemci/parca_basi.py` / `fazla_calisma.py` / `hazine_payi.py` | Bordro ve hazine |
| `istemci/yil_sonu.py` | Yıl sonu / ÜTP |
| `istemci/maliyet.py` | Ürün maliyet kalemleri |
| `istemci/raporlar.py` | Özet + faaliyet + Bakanlık mizan çıktıları |
| `istemci/resmi.py` | Resmi yazı (şablonlar) ve denetim formu |
| `istemci/mevzuat.py` | Merkez yayın / okul doğrulama |
| `istemci/belgeler.py` | PB/FC/ÜTP HTML belge gövdeleri |
| `istemci/tanimlar.py` / `takvim.py` / `supa.py` | Alanlar, yasal süreler, istemci |
| `dose/hesap.py` / `mevzuat.py` / `denetim.py` | Saf hesap ve sabitler |
| `dose/excel.py` / `pdf.py` / `belge_sablonlari.py` | Masaüstü çıktı ve üst yazı şablonları |

APK paketi `istemci/` üzerinden `apk_aab_olustur.bat` ile üretilir; Excel/PDF için APK’da HTML yeterlidir.
Masaüstünde `python main.py` `dose/` paketini de görür. Eski PySide6 / yerel sunucu / LAN kodu kaldırılmıştır.

## 5. Test

```powershell
cd supabase; npm install; npm test; cd ..
python -m pytest tests -q
```

`python -m unittest discover` klasör adındaki «Ö» yüzünden kırılabilir; pytest veya açık modül adları kullanın.
`tests/test_uctan_uca.py` Flet ekranlarını `supabase/tests/yerel_supabase.cjs` taklitine bağlar; canlı `db push`
yerine geçmez.

## 6. Derleme

```powershell
cd istemci
flet build windows
flet build web
.\apk_aab_olustur.bat
```

Sürüm: `istemci/pyproject.toml` → `version` (şu an 1.7.4). Android izinleri yalnız `INTERNET` ve
`ACCESS_NETWORK_STATE`. Çıktılar `istemci/build/`, `istemci/store/`, `*.apk` / `*.aab` — git’e eklenmez.

## 7. Sık sorunlar

| Belirti | Sebep / çözüm |
|---|---|
| «Veritabanı kurulumu tamamlanmamış» | `npx supabase db push` |
| Doğrulama e-postası gelmiyor | SMTP / saatlik sınır / gereksiz klasör |
| «E-posta adresiniz doğrulanmamış» | Bağlantıya tıklanmamış; girişte yeniden gönder |
| Davetli bağlanmıyor | Aynı e-posta; davet süresi |
| Salt okunur | Lisans dolmuş: `dose_private.lisans_ayarla` |
| «Okul lisansı kapalı» | `aktif = false` → `lisans_ayarla(kod, bitis, true)` |
| Özel sektör peşinat hatası | Bedelin asgari peşinat oranının altında; merkez parametre doğrulanmış olmalı |

## 8. Yedek

Veri Supabase'tedir. Ücretli planda günlük yedek / PITR; ek olarak `supabase db dump --data-only` şifreli saklanmalı.
