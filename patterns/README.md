# 📁 Pattern Images Folder

Place your reference chart pattern PNG images here.

## Recommended patterns to add:

| Filename | Pattern | Bias |
|----------|---------|------|
| `hammer.png` | Hammer | Bullish reversal |
| `inverted_hammer.png` | Inverted Hammer | Bullish reversal |
| `shooting_star.png` | Shooting Star | Bearish reversal |
| `hanging_man.png` | Hanging Man | Bearish reversal |
| `bullish_engulfing.png` | Bullish Engulfing | Bullish reversal |
| `bearish_engulfing.png` | Bearish Engulfing | Bearish reversal |
| `morning_star.png` | Morning Star | Bullish reversal |
| `evening_star.png` | Evening Star | Bearish reversal |
| `doji.png` | Doji | Indecision |
| `head_and_shoulders.png` | Head & Shoulders | Bearish reversal |
| `inverse_head_and_shoulders.png` | Inverse H&S | Bullish reversal |
| `double_top.png` | Double Top | Bearish reversal |
| `double_bottom.png` | Double Bottom | Bullish reversal |
| `ascending_triangle.png` | Ascending Triangle | Bullish continuation |
| `descending_triangle.png` | Descending Triangle | Bearish continuation |
| `symmetrical_triangle.png` | Symmetrical Triangle | Neutral / breakout |
| `bull_flag.png` | Bull Flag | Bullish continuation |
| `bear_flag.png` | Bear Flag | Bearish continuation |
| `rising_wedge.png` | Rising Wedge | Bearish reversal |
| `falling_wedge.png` | Falling Wedge | Bullish reversal |

## Tips for best results:

1. Use **clean, clear** pattern examples — no noise or extra indicators
2. Recommended size: **400×300** to **800×600** pixels
3. Use **dark background** images to match the bot's chart style
4. The more patterns you add, the more robust the recognition
5. You can create patterns by screenshotting from TradingView

## How matching works:

The bot uses **3 methods** to compare your chart against these images:

1. **SSIM** (40% weight) — pixel-level structural similarity
2. **pHash** (20% weight) — perceptual hash for shape matching
3. **CLIP** (40% weight) — deep learning semantic similarity (most powerful)

A weighted ensemble score is computed and the top 3 matches are returned.
