# 🎬 YT-Editing — Yüzsüz YouTube Kanalları İçin Otomatik Video Editörü

Seslendirdiğin **ses dosyasını** ve **yazdığın metni** ver; sistem sana **paylaşıma hazır MP4** üretir.

- ✅ 10 dakika – 1,5 saat arası her süre
- ✅ Her cümle değişiminde, ortalama 5-6 saniyede bir fotoğraf/video değişimi
- ✅ Fotoğraflarda Ken Burns (yavaş zoom/kayma), her geçişte sade fade efekti
- ✅ Metindeki önemli **para / sayı / isim** bilgilerinde temiz yazı efekti (video başına 3-5, girişe öncelik)
- ✅ **Tüm majör diller + Türkçe** (16 dil: tr, en, es, pt, fr, de, it, ru, uk, ar, he, hi, th, id, nl, pl, ja, ko, zh…)
- ✅ Fotoğraflar **Brave Search API**, videolar **Pexels API** ile
- ✅ Günde 10+ video: sorgu önbelleği + GitHub Actions ile paralel üretim
- ❌ Müzik, ses efekti, agresif grafik YOK — tam senin istediğin sadelik

---

## Nasıl çalışır?

```
ses + metin ──► cümlelere böl ──► sese hizala (sessizlik kenetleme)
        │
        ├─► 5-6 sn'lik sahneler oluştur
        ├─► her sahneye anahtar kelime sorgusu üret
        ├─► Brave (foto) / Pexels (video) → indir, önbelleğe al
        ├─► para/sayı/isim algıla → 3-5 yazı efekti seç
        └─► ffmpeg: Ken Burns + fade geçişleri + ses → MP4 (1080p)
```

Her cümle ~5-6 saniyelik bir sahneye düşer; görseller **cümle değiştikçe** değişir.
Hizalama, cümle aralarındaki **sessizlikler** algılanarak yapılır (whisper gibi ağır modeller gerekmez).

---

## Hızlı başlangıç (bilgisayar / sunucu)

```bash
bash setup.sh                 # Python paketleri + ffmpeg
python3 app.py                # Web arayüzü → http://0.0.0.0:8000
```

Web arayüzünden: **Ayarlar** → Brave + Pexels anahtarını gir → **Yeni Video** → ses + metin yükle.

### CLI ile

```bash
export BRAVE_API_KEY="..."    # Brave Search API (fotoğraflar)
export PEXELS_API_KEY="..."   # Pexels API (videolar)

# jobs/ klasörüne ses + script.txt koy, sonra:
python3 render_cli.py --job-dir jobs/ornek-video
# → output/ornek-video.mp4
```

Test modu (API'siz, hızlı deneme): `python3 render_cli.py --job-dir jobs/ornek-video --mode test`

---

## iPad ile kullanım (bilgisayarsız)

Bu repoya bağladığın **GitHub Actions** gerçek render motorudur: işi başlatırsın, GitHub'un
sunucuları videoyu üretir, sen iPad'inden indirirsin. Detaylar: **[KULLANIM.md](KULLANIM.md)**

---

## Repo yapısı

```
app.py                  Web arayüzü + API (Flask)
render_cli.py           Komut satırı render (GitHub Actions bunu kullanır)
pipeline/
  job.py                İş akışı (analiz → görseller → render → final)
  timings.py            Ses-metin hizalama + sahne gruplama
  textproc.py           Cümle bölme, anahtar kelime, para/sayı/isim algılama
  languages.py          Dil algılama + stopwords (16+ dil)
  visuals.py            Brave/Pexels arama + indirme + önbellek
  render.py             ffmpeg: Ken Burns, fade, concat, ses miks
  overlays.py           Yazı efekti PNG üretimi (çok dilli fontlar)
  fonts.py              Yazıya göre otomatik font seçimi
assets/fonts/           Gömülü fontlar (Latin/Arapça/Devanagari/Thai/İbranice/CJK)
.github/workflows/      Render Video workflow (GitHub Actions)
jobs/<isim>/            audio.* + script.txt + options.json  → iş tanımı
output/                 Üretilen MP4'ler
cache/                  Görsel/video önbelleği (API kotasını korur)
web/                    Arayüz (iPad uyumlu, Türkçe)
```

## Ayarlar (options.json)

| Anahtar | Varsayılan | Açıklama |
|---|---|---|
| `resolution` | `1080p` | `1080p` veya `720p` |
| `fps` | `30` | Çıkış kare hızı |
| `transition` | `0.35` | Geçiş (fade) süresi, saniye |
| `video_ratio` | `0.25` | Sahnelerin kaçta kaçı stok video olsun |
| `overlay_max` | `5` | En fazla yazı efekti sayısı |
| `overlay_min_gap` | `40` | İki yazı efekti arası min saniye |
| `language` | `auto` | Metin dili (otomatik algılanır) |
| `mode` | `real` | `real` / `test` |
| `workers` | `cpu-1` | Paralel sahne render sayısı |

## API anahtarları

- **Brave Search**: https://brave.com/search/api/ — ücretsiz plan: 1 istek/sn (sistem otomatik yavaşlatır, önbellekler)
- **Pexels**: https://www.pexels.com/api/ — ücretsiz, 200 istek/saat

Anahtarlar `settings.json`'da tutulur (git'e girmez). GitHub Actions için repo
**Settings → Secrets → Actions** altına `BRAVE_API_KEY` ve `PEXELS_API_KEY` ekleyin.

> Not: Fotoğraf telif sorumluluğu kullanıcıya aittir (Brave web'den görsel döndürür).
