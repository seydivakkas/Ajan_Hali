# Ajan Halı — Fotoğraftan CAD ve İplik Reçetesi

[![License: All Rights Reserved](https://img.shields.io/badge/license-All%20Rights%20Reserved-red?style=flat-square)](LICENSE)

React/Tailwind stüdyosu ve FastAPI görüntü işleme motoru. **Yeni kurulum boş fabrika envanteriyle başlar**; demo palet ve sentetik stok/fiyat yalnız açık kullanıcı isteğiyle yüklenir ve DEMO olarak etiketlenir. Şirket değerleri bilinmiyorsa kullanıcıdan istenir.

## Kurulum (Windows / Python 3.11 ve Node.js 22)

Proje kökünde PowerShell:

```powershell
py -3.11 -m venv .venv
.\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt
cd frontend
npm ci
npm run build
cd ..
.\\.venv\\Scripts\\python.exe -m uvicorn api.server:app --host 127.0.0.1 --port 8001
```

Tarayıcıda `http://127.0.0.1:8001` açılır. İsteğe bağlı FastSAM modeli için uygun PyTorch kurulumu ardından `pip install ultralytics` gerekir; bu paket olmadan segmentasyonun diğer yöntemleri kullanılabilir. Ayrı React geliştirme sunucusu için backend çalışırken `cd frontend; npm run dev` kullanın: `/api` ve `/static` istekleri 8001 portuna yönlenir.

**Güvenlik sınırı:** API halen kullanıcı kimlik doğrulaması içermez. Yalnız `127.0.0.1` üzerinde çalıştırın; ağ/İnternet erişimine açmayın. Tarayıcı kökeni kısıtlaması kullanıcı kimlik doğrulamasının yerine geçmez. `factory_settings.json` ve `supplier_catalog.json` yerel çalışma verileridir, Git'e eklenmez. Daha önce bu dosyaları özelleştirdiyseniz güncelleme yapmadan önce yedekleyin.

## Kullanıcı oturumları ve yetki modeli (yerel beta)

Varsayılan `AJAN_HALI_AUTH_MODE=local`: mevcut tek kullanıcılı yerel stüdyo çalışır,
ancak gerçek bir oturum/rol kontrolü etkin **değildir**. Uygulama DNS-rebinding
kontrolüyle yalnızca loopback adresinden ve `localhost`/`127.0.0.1`
Host değeriyle kullanılabilir. **Firmaya açılacak bir sunucu için bu mod uygun
değildir.**

Yerel cihazda oturum koruması etkinleştirmek için PowerShell'de:

```powershell
.\\.venv\\Scripts\\python.exe -m core.access_control add-user yonetici --role ADMIN
$env:AJAN_HALI_AUTH_MODE = "session"
.\\.venv\\Scripts\\python.exe -m uvicorn api.server:app --host 127.0.0.1 --port 8001
```

Komut parolayı ekranda göstermeden ister (en az 12 karakter). Diğer rolleri
`--role DESIGNER` veya `--role OPERATOR` ile oluşturabilirsiniz.
Bir hesabı ve tüm oturumlarını kapatmak için:
`python -m core.access_control disable-user <kullanici>`.

`ADMIN`: fabrika ayarları, katalog, analiz, stüdyo ve kayıt yönetimi.
`DESIGNER`: kayıtları okur, analiz yapar, stüdyo revizyonu/inceleme oluşturur;
fabrika ayarlarını değiştiremez.
`OPERATOR`: analiz/ön kontrol kayıtlarını salt okunur açabilir; üretim sevki
için yetki veya doğrulanmış tezgâh adaptörü verilmez.

Oturumlar 8 saatlik sunucu tarafı SQLite kayıtlarıdır (`output/auth.sqlite3`);
parolalar rastgele tuzlanmış scrypt özetiyle tutulur. Tarayıcıda HttpOnly,
SameSite=Strict çerezi ve yazma işlemlerinde sunucu doğrulamalı CSRF kullanılır.
Oturum kapatılabilir, kullanıcı devre dışı bırakılınca aktif oturumlar iptal olur.
Aynı kullanıcı adıyla 15 dakikada 5 başarısız giriş sonrasında, doğru parola
verilse bile 15 dakikalık geçici kilit uygulanır (HTTP 429, Retry-After).
Başarısız deneme sayaçları SQLite içinde tutulur; bu temel koruma, çok
kullanıcılı/İnternet erişimli kurulumda IP bazlı hız sınırı, WAF ve
izleme gereksinimlerinin yerine geçmez.

**Sınırlar:** Bu ilk sürüm tek şirket/tek cihaz içindir. TLS'li uzaktan erişim,
çok şirketli veri ayrımı, ağ kenarı IP hız sınırı, merkezi kullanıcı/kimlik
yönetimi ve ayrıntılı nesne düzeyi yetkiler henüz yoktur. 0.0.0.0/LAN/İnternet
üzerine yayınlamak yasaktır; `session` modu bunları güvenli kılmaz. Bu çalışmalar
Issue #2 kapsamında açık kalır.

## Başlatma

`start_studio.bat` veya proje kökünde:

```powershell
python -m uvicorn api.server:app --host 127.0.0.1 --port 8001
```

Stüdyo: http://127.0.0.1:8001 — API dokümanı: http://127.0.0.1:8001/docs

Frontend değişikliklerinden sonra `frontend` klasöründe `npm run build` çalıştırın. Çalışan Python sunucusunu backend değişikliklerinde yeniden başlatın.

## Şirket verisiyle ilk kurulum

1. **Fabrika ayarları** bölümüne şirket adını girin.
2. Her iplik için benzersiz stok kodu, ad, malzeme, dtex, TL/kg fiyat, net bobin ağırlığı, kullanılabilir stok ve Lab ölçümünü girin. Sıfır fiyat/stok ancak açıkça girilirse kabul edilir; boş alan sıfır sayılmaz. Ekran rengi Lab'dan türetilen önizlemedir.
3. QTX/CXF dosyasından yalnızca açık Lab üçlüleri taslağa alınabilir. Eksik ölçüm veya yalnız spektrum bulunan dosyalara varsayılan değer üretilmez. Ölçüm koşullarını cihaz kaydınızla kontrol edin; içe aktarım D65/10° uyumluluk doğrulaması değildir.
4. İsteğe bağlı tezgâh adı, kontrolör modeli, IP, port ve protokol ekleyin. ERP adı ve Attio şirket kayıt ID alanları yalnız bağlantı referansıdır.
5. Kaydedin. Bilgiler `factory_settings.json` dosyasında tarih ve revizyonla tutulur; aynı eski revizyonun üzerine yazılması engellenir.
6. Analiz stüdyosunda fotoğrafı seçin. Ebat, tarak/atkı sıklığı, hav yüksekliği, renk kapasitesi, sipariş adedi, fire, dokuma uzama faktörü ve düğüm altı payını girin. Bu şirket/üretim alanları boş başlar.

### Tedarikçi kataloğundan seçim

Fabrika Ayarları içindeki **Tedarikçi kataloğu ve ölçümlü kartela** bölümünde gerçek teknik föy ve ölçüm kayıtlarını elle ekleyin veya JSON dosyası yükleyin. Katalog boş başlar. Alan açıklamaları: [katalog dosyası biçimi](samples/SUPPLIER_CATALOG_FORMAT.md).

Envantere iplik ekledikten sonra **Tedarikçi kataloğundan iplik seç** alanı malzemeyi ve dtex değerini doldurur. Ardından yalnız o ürüne bağlı renk/parti kayıtları listelenir. Kartela seçimi Lab değerlerini ve renk adını doldurur; tedarikçi, özgün numara/birim, kaynak belge, renk kodu, boya partisi, cihaz, ölçüm tarihi, aydınlatıcı ve gözlemci açısı görüntülenir. Fiyat, stok ve bobin ağırlığı kullanıcı tarafından ayrıca girilir.

Bağlı alanlar katalogla tutarlı kalır; düzenlemek için ilgili seçimi Manuel girişe alın. Kaynak kopyası sunucuda oluşturulur ve analiz raporunun palet kopyasında saklanır. Farklı aydınlatıcı/gözlemci koşulları mevcut D65/2° fotoğraf motoruyla doğrudan karşılaştırılmaz; analiz öncesinde açıklayıcı hata döner.

Fiyat, stok ve bobin alanlarını istediğiniz zaman değiştirebilirsiniz. Ayarlarda kaydedilmeyen değişiklikler sekme geçişinde korunur; tarayıcı yenilenirse kaybolur. Kaydedilen değerler yeni analizlerde kullanılır.

## Analiz ve inceleme

- Otomatik segmentasyon veya fotoğraf üzerinde dört köşe seçimi: sol üst → sağ üst → sağ alt → sol alt. Geçersiz/kesişen köşeler reddedilir.
- İki karşı köşeye dokunarak dikdörtgen onarım bölgeleri seçme, geri alma ve temizleme. Maske fotoğrafla aynı homografiden geçirilir; manuel maske otomatik maskenin yerini alır.
- Parlama düzeltme, simetri/doku tamamlama, CIEDE2000 palet eşleme ve gerçek tezgâh matrisine yeniden örnekleme.
- Ham fotoğraf, işlem aşamaları, onarım maskesi, renk dağılımları ve audit sonuçlarını inceleme.
- Son 100 kaynak kayıtlı analizi açma. Raporlarda şirket ayar revizyonu, palet/fiyat/stok kopyası, üretim parametreleri ve kaynak fotoğraf saklanır.
- Yerel desinatör inceleme günlüğü: isim, karar, not, tarih ve rapor SHA-256 izi SQLite içinde saklanır. İsim beyana dayanır; kimliği doğrulanmış imza veya üretim izni değildir.

## Maliyet ve veri kapsamı

İplik başına düğüm sayısı gerçek yeniden örneklenmiş matristen gelir:

`uzunluk_m = düğüm_sayısı × (2 × hav_mm / 1000 × dokuma_faktörü + düğüm_altı_mm / 1000)`

`net_kg = uzunluk_m × dtex / 10^7 × sipariş_adedi`

`brüt_kg = net_kg × (1 + fire)`

`bobin = ceil(brüt_kg / net_bobin_ağırlığı)`

`iplik_maliyeti_TL = brüt_kg × TL/kg`

Bobin hesabı **tüketim için gereken toplam bobin** miktarıdır; aynı anda cağlığa bağlanacak bobin sayısı değildir. Maliyet yalnız iplik tahminidir: işçilik, enerji, vergi ve makine maliyeti dahil değildir. Toplam TL, iki ondalığa yuvarlanmış renk satırlarının toplamıdır. Kullanıcı stok girişi ERP'den doğrulanmış canlı stok değildir.

İplik reçetesi sekmesindeki **Güncel reçeteyi hesapla**, aynı desen ve siparişi güncel fiyat/dtex/stok/bobin değerleriyle tekrar hesaplar. Hesap zamanı ve ayar revizyonu gösterilir; orijinal rapor değiştirilmez. Eksik iplik kodu varsa hesap reddedilir.

## Entegrasyonların gerçek durumu

- ERP rezervasyon/satın alma uçları bağlı adaptör olmadığında 503 döndürür; sahte başarı oluşturmaz.
- Tezgâha gönderim doğrulanmış kontrolör adaptörü olmadığında 409 döndürür. IP kaydetmek bağlantı kurmaz veya dosya göndermez.
- EP/JC5 dosyaları yerel deneysel çıktılardır; üretici uyumluluğu doğrulanmadı. Audit skoru gerçek tezgâhta çalışabilirlik onayı değildir.
- DXF/SVG sadeleştirilmiş inceleme çıktılarıdır; makine için doğrulanmış dokuma talimatının yerine geçmez.
- Attio kayıt ID alanı CRM referansıdır; uygulama otomatik CRM eşitlemesi yapmaz.
- Eski demo/şirket kaynağı doğrulanmamış raporlar diskten silinmedi; uygulama geçmişinde, görsel ve indirme uçlarında erişime kapatıldı. Eski `palette/factory_palette.json` canlı uygulamada kullanılmaz.

## CLI

`python cli.py --image <fotoğraf-yolu> --config <üretim-parametreleri-json-yolu>`

Komut sentetik fotoğraf üretmez. `loom_config` nesnesindeki tüm üretim parametreleri zorunludur ve kayıtlı şirket paleti kullanılır.

## Doğrulama

- `python -m unittest discover -s tests -v` (GitHub Actions'ta da çalıştırılır)
- `python -m compileall -q api core tests cli.py`
- Frontend: `npm run build`

Test verileri yalnız geçici test dizinlerinde kullanılır; şirket ayarlarına veya canlı analize yazılmaz.

## Kalan işler

Kalıcı iş kuyruğu/aşama ilerlemesi; fotoğraf renk kalibrasyonu; cihaz ölçüm koşullarının doğrulanması; üretici belgelerine dayalı tezgâh adaptörü; gerçek ERP/Attio bağlantısı ve kullanıcı kimlik doğrulaması.

## Lisans

ÖZEL LİSANS — TÜM HAKLAR SAKLIDIR. Telif hakkı (c) 2026 Seydi Eryılmaz (@seydivakkas). Ayrıntılar `LICENSE` dosyasındadır.
