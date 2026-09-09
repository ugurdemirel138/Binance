# Binance Grid Trading Bot

Web arayüzünden yönetilen, Binance Testnet üzerinde çalışan bir grid
trading botu. Belirlediğiniz fiyat aralığını eşit dilimlere böler,
fiyat düştüğünde otomatik alım, yükseldiğinde otomatik satım yapar.

## 1. Testnet API anahtarı alın

Gerçek parayla değil, **sahte parayla** test etmek için:

1. https://testnet.binance.vision adresine gidin.
2. GitHub hesabınızla giriş yapın.
3. "Generate HMAC_SHA256 Key" ile bir API Key + Secret oluşturun.
4. Testnet hesabınıza otomatik olarak sahte USDT/BTC bakiyesi tanımlanır.

## 2. Kurulum

```bash
cd binance-grid-bot
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# .env dosyasını açıp API_KEY / API_SECRET alanlarını doldurun
```

## 3. Çalıştırma

```bash
python app.py
```

Tarayıcıda `http://localhost:5000` adresini açın.

## 4. Kullanım

1. Sembol girin (örn. `BTCUSDT`).
2. Alt ve üst fiyat sınırlarını girin — botun işlem yapacağı aralık.
3. Grid sayısını girin — aralık kaça bölünecek.
4. Toplam yatırım miktarını girin (quote para birimi, örn. USDT).
5. "Botu Başlat"a basın.

Bot, mevcut fiyatın altındaki her seviyeye bir alım emri açar. Bir alım
emri dolduğunda otomatik olarak bir üst seviyeye satım emri koyar; o da
dolduğunda kâr kaydedilir ve tekrar bir alım emri açılır. Bu döngü
"Botu Durdur"a basana kadar sürer.

## Önemli uyarılar

- **Bu kod bir yatırım tavsiyesi değildir.** Grid trading, fiyat
  belirlediğiniz aralıkta kaldığında kâr eder; fiyat aralığın dışına
  çıkarsa (özellikle aşağı kırılırsa) zarar riski vardır.
- Öncelikle **mutlaka Testnet'te** deneyin (`USE_TESTNET=true`,
  varsayılan ayar budur).
- Gerçek hesaba geçmeden önce: küçük miktarlarla başlayın, API
  anahtarınıza **sadece "Spot Trading" izni verin, para çekme (withdraw)
  iznini asla açmayın**, ve `.env` dosyanızı kimseyle paylaşmayın.
- Bot şu an tek bir sembol/oturum için tasarlanmıştır ve sunucu
  yeniden başlatıldığında durum sıfırlanır (kalıcı veritabanı yoktur).
- İnternet/Binance bağlantısı kesilirse bot açık emirleri
  izleyemeyeceği için duruma manuel bakmanız gerekebilir.

## Dosya yapısı

```
binance-grid-bot/
├── app.py              # Flask backend + grid bot mantığı
├── templates/
│   └── index.html      # Dashboard arayüzü
├── static/
│   ├── style.css
│   └── app.js
├── requirements.txt
├── .env.example
└── README.md
```
