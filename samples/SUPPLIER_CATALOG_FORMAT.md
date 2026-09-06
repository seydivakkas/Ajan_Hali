# Tedarikçi kataloğu ve ölçümlü kartela

Katalog boş başlar. Gerçek kayıtları Fabrika Ayarları ekranında elle ekleyebilir veya JSON dosyasından yükleyebilirsiniz. `supplier_catalog_empty.json` yalnızca boş yapıyı gösterir; örnek iplik veya ölçüm içermez.

JSON üst düzeyde `products` ve `colors` dizilerini içerir. Yeni kayıtlar eklenir; mevcut kimliklerin üzerine yazılmaz. Düzeltme için yeni kayıt kimliği kullanın ve envanterde yeni kaydı seçin. İçe aktarımda bir kayıt geçersizse dosyanın tamamı reddedilir.

## products alanları

| Alan | İçerik |
|---|---|
| id | Benzersiz kayıt kimliği; harf, sayı, alt çizgi ve tire |
| supplier | Tedarikçi adı |
| product_code | Tedarikçinin ürün kodu |
| material | Teknik föydeki malzeme, en fazla 100 karakter |
| count_value | Pozitif iplik numarası |
| count_unit | dtex, tex, denier veya Nm |
| count_basis | FINISHED_YARN; bitmiş ipliğin toplam numarası |
| source_ref | Teknik föy/etiket/ERP belge referansı veya kaynak URL |

dtex, tex × 10; denier × 10 / 9; Nm için 10000 / Nm olarak hesaplanır. Ondalık sonuçlar altı ondalık basamağa kadar korunur. Kaynak numara ve birim de saklanır. Katlı iplikte tek kat numarası otomatik olarak toplam numara kabul edilmez.

Numara sistemleri kaynağı: https://www.coats.com/en/info-hub/thread-numbering/

## colors alanları

| Alan | İçerik |
|---|---|
| id | Benzersiz kartela ölçüm kimliği |
| product_id | Ait olduğu products.id |
| color_code | Tedarikçi/kartela renk kodu |
| name | Ölçülen rengin adı |
| dye_lot | Boya parti/lot kodu |
| lab | Üç sayı: L*, a*, b* |
| illuminant | D50, D65, A veya F11 |
| observer | Metin olarak 2 veya 10 |
| device | Ölçüm cihazı |
| measured_at | YYYY-MM-DD biçiminde ölçüm tarihi |
| source_ref | Ölçüm raporu referansı veya kaynak URL |

Şirket stok kodu, stok, fiyat ve bobin ağırlığı katalogdan varsayılmaz; envanterde ayrıca girilir.

## Kaynak ve ölçüm sınırları

Kaynak referansları kullanıcı/tedarikçi beyanıdır; uygulama URL'ye bağlanıp belgeyi doğrulamaz. Pantone veya başka lisanslı kartela verisi paketlenmez. Ekran rengi önizlemedir.

Mevcut fotoğraf renk motoru D65/2° kullanır. Farklı koşullardaki kayıtlar katalogda ve envanterde tutulabilir ancak analiz öncesinde reddedilir. D50↔D65 veya 2°↔10° arasında otomatik eşdeğerlik varsayılmaz.

Katalogdan bağlı dtex/malzeme ve karteladan bağlı ad/Lab alanları kilitlidir. Manuel düzenleme için ilgili seçimi Manuel girişe alın; kaynak bağlantısı kaldırılır. Fiyat ve stok her zaman düzenlenebilir.

Kaydederken kaynak kopyası sunucu tarafından katalogdan oluşturulur. Bu kopya analiz raporunun palette_snapshot alanında da korunur. Eski analiz raporları katalog eklemelerinden etkilenmez.
