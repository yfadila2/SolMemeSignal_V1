# Solana Memecoin Telegram Screener

Bot ini memantau token Solana dari Dexscreener dan mengirim sinyal ke Telegram jika menemukan:

1. New coin signal
2. Accumulation signal

## File penting

- `bot.py`: program utama
- `requirements.txt`: dependency Python
- `.env.example`: contoh variable rahasia
- `Procfile`: start command untuk Railway/Render-like worker

## Cara menjalankan lokal

1. Install Python 3.11+
2. Buka folder project
3. Install dependency:

```bash
pip install -r requirements.txt
```

4. Buat file `.env` atau isi environment variables:

```bash
TELEGRAM_BOT_TOKEN=xxxxx
TELEGRAM_CHAT_ID=xxxxx
```

5. Jalankan:

```bash
python bot.py
```

## Deploy 24 jam

Paling mudah: deploy sebagai Worker/Background Service di Railway/Render/VPS.

Start command:

```bash
python bot.py
```

Environment variables wajib:

```bash
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

## Catatan keamanan

Bot ini hanya mengirim sinyal. Bot tidak meminta seed phrase, private key, atau akses wallet. Jangan pernah memasukkan seed phrase ke bot, website, atau server apa pun.
