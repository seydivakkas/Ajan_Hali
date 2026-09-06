# Eğitim verisi

Fabrika ayarlarında **Demo iplikleri yükle**, 4 sentetik envanter kaydı ekler.
Şirket adı, bağlantılar ve tedarikçi kataloğu değiştirilmez. Gerçek kayıtlar korunur.
Tekrar yükleme kopya oluşturmaz. Fiyatlar, stok ve bobin ağırlıkları düzenlenebilir.
Lab değerleri cihaz ölçümü değildir; demo etiketi satırda ve sonuçta görünür.

1. Demo iplikleri yükleyin.
2. Üstteki **Örnek test parametrelerini doldur** düğmesine basın.
3. Analiz stüdyosunda bir JPG/PNG halı fotoğrafı yükleyip analiz başlatın.
4. Renk, reçete, stok ve kalite sekmelerini inceleyin. Bordo stoğu 0,1 kg'dır;
   desenin bordo oranı ve sipariş adedine bağlı olarak yetersiz stok uyarısı oluşur.
5. Fiyat veya sipariş miktarını değiştirerek hesaplamayı karşılaştırın.
6. **Demo iplikleri sil** yalnızca demo işaretli envanter satırlarını kalıcı siler.
7. Analiz geçmişindeki **Demo analizlerini ve dosyalarını sil**, demo sonuçlarını,
   bunlara ait yüklenmiş fotoğrafları, çıktıları ve değerlendirme kayıtlarını kalıcı siler.

Demo içeren palette analiz sonucu `DEMO_SYNTHETIC` ve `NOT_PRODUCTION_SAFE` olur.
İndirilen dosya adları `DEMO_` ile başlar. Eğitim dosyalarını üretimde kullanmayın.
Demo ipliklerini silmek eski analizleri değiştirmez; onları ayrıca silin.
Tarayıcıya indirilmiş kopyalar bu işlemle silinmez. Örnek tezgâh parametreleri
yalnızca açık sayfada kalır; gerçek çalışmaya geçerken gerçek değerlerinizi girin.
