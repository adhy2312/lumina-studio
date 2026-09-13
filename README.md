# 🔮 Lumina Studio • Smart Light Experience

> An artistic, fluid, and music-reactive smart lighting control studio custom-crafted for ESP8266 / Tasmota RGBW bulbs.

![Lumina Studio](https://images.unsplash.com/photo-1550745165-9bc0b252726f?auto=format&fit=crop&w=1200&q=80)

---

## ✨ Features

- **🔮 Centerpiece Aura Orb**: Interactive glowing canvas orb mirroring the physical bulb's live color, intensity, and ambiance.
- **🎨 Chroma Spectrum**: Full 360° fluid Hue wheel, brightness slider, and 8 curated mood presets (*Cyberpunk Neon, Tokyo Sunset, Nordic Aurora, Emerald Glow, Velvet Lounge, Deep Oceanic, Warm Amber, Fireplace Candlelight*).
- **☀️ High-CRI Tunable White**: Calibrated Kelvin curve from **6500K Arctic Crisp Daylight** down to **2000K Deep Golden Candlelight** without flickering or bulb shutdown.
- **🎵 Real-Time Music & Spotify Sync**:
  - Web Audio API real-time FFT spectrum analyzer.
  - Beat & Kick drum energy detection (20–120 Hz).
  - 4 Dynamic reaction modes: *Club Bass Kick, Lo-Fi Chill Flow, Frequency Chroma, Party Dynamic*.
- **⚡ Zero-Flicker Architecture**: Configured with `Sleep 0` and `PWMFrequency 1000Hz` for smooth illumination.
- **🌐 Dual-Mode Network Pipeline**: Works seamlessly on local networks via direct HTTP beacons and proxy backend, with built-in IP configurability.
- **📱 Mobile Ready**: Responsive glassmorphism interface engineered for iPhone, Android, tablets, and desktop.
- **🏠 Google Home & Matter Guide**: Comprehensive built-in walkthrough explaining 16–22 digit pairing codes and Google Assistant Philips Hue bridge voice discovery.

---

## 🚀 One-Click Deploy to Vercel

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new)

1. Fork or push this repository to your GitHub account (`https://github.com/<your-username>/lumina-studio`).
2. Go to [Vercel](https://vercel.com) and click **"Add New" > "Project"**.
3. Import your `lumina-studio` repository.
4. Click **Deploy**!
5. Open your deployed URL on your phone or computer on the same Wi-Fi network as your bulb.
6. In the header, tap the **Connection Pill (⚙️)** to set your Bulb's local IP (e.g., `192.168.1.11`).

---

## 💻 Local Quickstart

### Python Server (Includes Local API Proxy)
```bash
python server.py
```
Open in browser:
- Local PC: `http://localhost:7070`
- Phone on Wi-Fi: `http://192.168.1.9:7070`

---

## 🔧 Hardware & Firmware Compatibility

- **Target Device**: ESP8266 / ESP8285 based smart bulbs (Smitch, Syska, Tuya, etc.).
- **Firmware**: Tasmota 15.x / 14.x with 4-channel RGBW PWM.
  - Channel 1: Red (GPIO 4)
  - Channel 2: Green (GPIO 12)
  - Channel 3: Blue (GPIO 14)
  - Channel 4: White (GPIO 5)

---

## 📄 License
MIT © Adhithya Mohan
