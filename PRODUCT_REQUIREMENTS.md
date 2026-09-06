# Ajan Halı — Carpet Production Intelligence gereksinimleri

## Ürün akışı ve veri sahipliği

Ham fotoğraf → AI taslak → renk/iplik eşleme → loom-grid → insan düzeltmesi →
sürüm kontrollü master adayı → reçete/maliyet → pre-flight → operatör ve üretim
kapısı → doğrulanmış CAD/CAM → entegrasyon → gerçek tüketim → kalibrasyon.

Kaynak analiz değişmez. Studio belgesi indeksli hücrelerden, katmanlardan ve
colorway eşlemesinden oluşur. Her kayıtta birleşik matrisin SHA-256 değeri ve
kaynak palet/tezgâh/fiyat/stok anlık görüntüsü korunur. Studio reçetesi birleşik
matristen yeniden hesaplanır. Eski analiz CAD dosyaları düzenlenmiş master değildir.

## V1.1 — Designer Production Studio (uygulanan ilk kapsam)

- Gerçek matris açılır; büyüklük sınırında sessiz küçültme yapılmaz.
- Tek düğüm boyama ve üst katmanda şeffaf silme; yakınlaştırma.
- Dikdörtgen seçimden motif kopyalama; X/Y konumu, yatay/dikey ayna, görünürlük,
  en üste taşıma, katman silme ve adlandırma.
- Bordür, zemin, madalyon rolleri manuel atanır; otomatik ayrıştırma değildir.
- Seçimi tüm matrise tekrarlama; bu işlem görünür deseni tek tabana indirger.
- Colorway kaynak palet içinden indeks eşlemesidir; serbest RGB gerçek iplik sayılmaz.
- Geri al/yinele oturum içindedir, bellek sınırına göre 1–30 adım tutulur.
- Kalıcı, değiştirilemez taslak/master adayı revizyonları; eski sürümden yeni taslak;
  eşzamanlı kayıt çatışmasının reddi; sürüm paketinin JSON indirilmesi.
- Taslak değiştiğinde kaydedilmiş reçetenin eski olduğu belirtilir.
- Master adayı asla otomatik APPROVED olmaz. Temel demo/cağlık/stok engelleri ve
  kenar indeks farkları görünür; bunlar V1.2 pre-flight'ın tamamı değildir.

Kabul: 12 hücreli örnekte üst katmanın sayıları reçeteye tam yansır; eski dosyalar
değişmez; eski parent_revision ile kayıt reddedilir; demo kaynak etiketi korunur.

V1.1 sınırları: 2 milyon düğüm, 16 katman, toplam 8 milyon katman hücresi.
Basınca duyarlı fırça, serbest lasso, vektör Bézier, PSD içe aktarma ve otomatik
motif semantiği kapsam dışıdır. JSON taslak indirme vardır; JSON geri içe aktarma
henüz yoktur. Desinatör adı beyan alanıdır; kurumsal kimlik doğrulaması değildir.

## V1.2 — Production pre-flight

Renk, kalibrasyon kartı, ölçüm koşulu, lot, cağlık, stok, boyut/düğüm matrisi,
raport, dosya formatı ve tezgâh profili için ayrı kontrol sonucu tutulmalı.
Her kontrol PASS / WARN / FAIL / NOT_VERIFIED, kanıt, zaman, kural sürümü taşımalı.
FAIL → BLOCKED; eksik kanıt → REVIEW_REQUIRED; yalnız gerekli kontroller tamam
ve yetkili onay geçerli ise APPROVED. Revizyon değişirse eski onay geçersizdir.
Numune-hedef ΔE00 aynı aydınlatıcı/gözlemci ve izlenebilir ölçümle hesaplanmalı;
fotoğraf tahmini gerçek ölçüm gibi gösterilmemeli. Raport uygunluğu sadece ilk/son
satır eşitliğinden çıkarılmamalı. Kalibrasyon kartı kırpımı, referans değerleri,
aydınlatma ve renk dönüşümü sürümlenmeli.

## V1.3 — Actual consumption ve kalibrasyon

Sipariş + master revizyonu + makine + konstrüksiyon + lot + iplik + hav yüksekliği
bağlantılı gerçek brüt/net tüketim, iade, fire, bobin tartımı, adet ve ölçüm kaynağı
saklanmalı. Fiyatlar para birimi, birim ve geçerlilik tarihiyle sürümlenmeli.

Örnek hesap (gereksinim örneğidir, şirket kaydı değildir): 412 kg tahmine karşı
427 kg gerçek tüketim, +15 kg ve tahmine göre yaklaşık %3,64 sapmadır. Tek sipariş
otomatik genel düzeltme katsayısı olmamalı. Kalibrasyon makine/konstrüksiyon/iplik
grubuna göre örnek sayısı, aykırı kayıtlar, validasyon hatası ve belirsizlikle
raporlanmalı. Eğitim/doğrulama siparişleri ayrılmalı; veri sızıntısı önlenmeli.
Kalibrasyon sürümü, kullandığı siparişler ve önceki sürüme dönüş kayıtlı olmalı.

## V1.4 — ERP/MES ve tezgâh adapter sözleşmesi

Adapter: capabilities, test_connection, validate_request, dry_run, prepare,
commit, status, cancel/compensate. SIMULATED / DRY_RUN / LIVE ayrı modlardır.
Sunucu tarafı yetki, operatör onayı, revision/hash bağı, idempotency anahtarı,
timeout/retry ve gizli bilgi içermeyen audit log zorunludur. Stok rezervasyonu
eşzamanlı kontrol ve güncel lot bilgisinden yapılmalı. Makinede fiziksel dokumayı
geri almak mümkün değildir; rollback yalnız desteklenen rezervasyon/iş emri
telafisini ifade etmeli. Cihaz ve ERP yetkileri gerçek kurulumda sağlanmalı.

## V2.0 — Vendor-validated CAM

EP/JC5 için üretici dokümanı veya kullanma yetkisi bulunan doğrulanmış dosyalar,
kontrolör modeli/firmware profili, parser/serializer round-trip ve üretici test
vektörleri gerekir. Laboratuvar/konsol kabul testi ve kontrollü numune dokuma
tamamlanmadan uyum ilan edilmez. Uzantı doğrulama değildir.

## UI hedefi

Dashboard / Yeni Analiz / Desen Studio / Üretim / Fabrika / Kalite / Geçmiş.
V1.1 mevcut navigasyona Desen Studio ekler; diğer alanlar ancak çalışan işlevleri
hazır olduğunda genişler. Boş bağlantılar çalışan modül olarak sunulmaz.
Demo veri ve sonuçları sürekli etiketlidir. Silme gerçek kayıtları korur;
Studio revizyonları ilgili analiz klasöründedir, demo analiz temizliğine dahildir.
