# 📱 iPad ile Kullanım Rehberi (Bilgisayarsız)

Bu sistem iki parçadan oluşur: **web arayüzü** (iş gönderir) ve **GitHub Actions** (videoyu üretir).
iPad'inden tek yapman gereken ses + metin yüklemek; gerisini GitHub'un ücretsiz sunucuları halleder.

---

## 🔑 Bir kere yapılacaklar (ilk kurulum)

### 1) API anahtarlarını al
- **Brave Search** (fotoğraflar için): [brave.com/search/api](https://brave.com/search/api/) → *Free* plan → API key'i kopyala.
- **Pexels** (videolar için): [pexels.com/api](https://www.pexels.com/api/) → ücretsiz üye ol → API key'i kopyala.

### 2) Anahtarları GitHub'a tanıt (iPad Safari'den)
1. GitHub uygulamasını ya da Safari'yi aç → bu repoya git.
2. **Settings → Secrets and variables → Actions** → **New repository secret**
   - Name: `BRAVE_API_KEY` → Secret: Brave anahtarın
   - Aynı şekilde: `PEXELS_API_KEY` → Pexels anahtarın

### 3) Arayüzde de kaydet
Web arayüzünü aç → **⚙️ Ayarlar** sekmesi → iki anahtarı yapıştır → **Kaydet**.

> ⚠️ Ekran üstündeki durum çubuğunda "Bu ortamdan erişilemiyor" uyarısı görürsen panik yok:
> o yalnızca web arayüzünün çalıştığı sunucunun internet kısıtı olabilir. Asıl üretim
> GitHub Actions'ta yapılır ve orada anahtarlar secret'tan okunur.

---

## 🎬 Her video için (günde 10+ kez yapabileceğin akış)

### Yöntem A — Web arayüzünden (en kolayı)
1. Web arayüzünü aç → **➕ Yeni Video** sekmesi.
2. Üretim yöntemi: **☁️ GitHub Actions ile üret** seçili olsun.
3. **Ses dosyanı seç** (mp3/m4a/wav). Uzun videolar için m4a 64-96 kbps mono önerilir.
4. **Metnini yapıştır** (ya da .txt seç). Metin, seslendirdiğinle birebir aynı olmalı.
5. İstersen **Elle yazı efekti** alanına satır satır belirt:
   ```
   0:12 | 3.5 Milyar Dolar
   2:45 | Atatürk
   ```
   Boş bırakırsan sistem ilk 3-5 önemli bilgiyi kendisi seçer (girişe öncelik verir).
6. Video başlığı yaz → **🚀 Üretimi Başlat**.
7. **📋 İşler** sekmesinden ilerlemeyi izle. Bittiğinde **⬇️ indir** bağlantısı çıkar.

### Yöntem B — Doğrudan GitHub'dan (arayüz kapalıyken bile çalışır)
1. Safari'den repoyu aç → **Add file → Upload files**.
2. `jobs/videonun-adi/` yoluna dosyaları yükle (klasör adını yazınca otomatik oluşur):
   - `audio.m4a` (veya .mp3/.wav)
   - `script.txt` (video metni)
3. Üstteki **Commit** butonuna bas.
4. **Actions** sekmesi → sol menüden **Render Video** → **Run workflow**:
   - `job` alanına klasör adını yaz: `videonun-adi`
   - `test_mode` işaretsiz kalsın (gerçek görseller için)
5. **Run** → birkaç dakika sonra işin yeşil tik olur.
6. İşe gir → aşağıda **Releases** bölümünde üretilen MP4 → iPad'ine indir.
   (İş sayfasının **Artifacts** bölümünden de indirebilirsin.)

> 📥 Release kalıcıdır; Artifact linkleri bir süre sonra iter. Her video için ayrı klasör adı kullan
> (örn: `osmanli-bolum-3`), böylece işler karışmaz.

---

## ⚡ Önce hızlı deneme yap

İlk kez kullanıyorsan **⚡ Hızlı önizleme (test görselleri)** modunu seç:
API kotası harcamaz, renkli kartlarla zamanlamayı/efektleri dakikalar içinde görürsün.
Her şey istediğin gibiyse gerçek modda tekrar üret.

---

## 📏 Kurallar & ipuçları

| Konu | Davranış |
|---|---|
| Video süresi | 10 dk – 1,5 saat hepsi desteklenir |
| Görsel değişimi | Cümle değişince; ortalama 5-6 saniyede bir |
| Geçiş | Her değişimde 0,35 sn fade (ayarlanabilir) |
| Ken Burns | Her fotoğrafta otomatik (zoom/pan yönü sahneye göre değişir) |
| Yazı efekti | Video başına 3-5; para/sayı/isim önceliğiyle, girişe ağırlık verilir |
| Video/foto oranı | Varsayılan %25 stok video, gerisi foto |
| Dil | Metin dili otomatik algılanır (Türkçe dahil 16+ dil) |
| Kotalar | Aynı konu tekrar sorulursa önbellekten gelir; günde 10+ video sorunsuz |
| Uzun kuyruk | Her iş ayrı Actions işi; aynı anda birden fazla iş başlatabilirsin |

## 🆘 Sık karşılaşılanlar

- **"BRAVE_API_KEY eksik" hatası**: 2. adımdaki secret'ları ekle. Test etmek istersen `test_mode` işaretle.
- **"jobs/klasör yok" hatası**: Run workflow'da yazdığın ad ile yüklediğin klasör adı aynı olmalı.
- **Ses-metin hizalaması kayarsa**: metnin seslendirmede atlanan/eklenen yerler olmadığından emin ol.
- **İş 5 saatte bitmedi**: Actions işi açıp log'a bak; çoğunlukla ses dosyası bozuktur.
