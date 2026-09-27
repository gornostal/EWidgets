# Weather API research

Research for a weather widget, done 2026-09-24. Criteria:

- weather for the current location based on IP
- weather for a city name or coordinates
- free to use
- hourly forecast for the next 5 hours
- daily forecast for the next 5 days
- trusted and accurate

## Recommendation: Open-Meteo, with GeoClue for location

It meets every criterion, needs no API key or account, and fits the project's
"no extra dependencies" rule: `urllib` plus `json` from the standard library
is enough.

- **Forecasts:** one request returns the current weather, the next 5 hours and
  the next 5 days (`forecast_hours=5&forecast_days=5`).
- **City name:** it has its own free geocoding endpoint
  (`https://geocoding-api.open-meteo.com/v1/search?name=Kyiv&count=1`).
- **Accuracy:** it doesn't run its own forecast model. It combines output from
  national weather services (ECMWF, the German DWD's ICON, NOAA's GFS,
  Météo-France and others) and picks the best one for each location. Its code
  is open source.
- **Limits:** 600 calls/min, 5,000/hour, 10,000/day, 300,000/month. Free for
  non-commercial use under CC-BY 4.0. Show a small "Weather data by
  Open-Meteo" credit to meet the licence.
- **Weather codes:** it returns standard WMO codes, which map easily to icons.

Example request (tested, returns clean JSON):

```
https://api.open-meteo.com/v1/forecast?latitude=50.45&longitude=30.52
  &current=temperature_2m,weather_code
  &hourly=temperature_2m,weather_code,precipitation_probability
  &daily=weather_code,temperature_2m_max,temperature_2m_min
  &forecast_hours=5&forecast_days=5&timezone=auto
```

### Location

None of the good free weather APIs look up your location from your IP, so
location is resolved separately, in this order:

1. **GeoClue2** (`org.freedesktop.GeoClue2` on the system bus). It runs on
   elementary OS by default and uses Wi-Fi positioning, so it's more precise
   than IP. It can be called through D-Bus from GTK with no new dependencies.
2. **IP lookup** as a fallback: `http://ip-api.com/json/` is free with no key
   (non-commercial, HTTP only) and returns latitude and longitude. IP location
   is often only accurate to the city or region. `ipapi.co` refused a test
   call for exceeding its rate limit, so it's not a good choice.

## Comparison

| API | IP lookup | City name | Free | Next 5 h, hourly | 5 days | Trust / accuracy |
|---|---|---|---|---|---|---|
| **Open-Meteo** | ✗ (use GeoClue or IP) | ✓ own geocoder | ✓ no key, 10k/day | ✓ | ✓ up to 16 | High, national-service models |
| **MET Norway** (api.met.no) | ✗ | ✗ (coordinates only) | ✓ no key, needs User-Agent | ✓ | ✓ ~9 days | Very high, Norwegian state weather service |
| **wttr.in** | ✓ built in | ✓ | ✓ no key | ~ 3-hour steps | ✗ 3 days | Low: a hobby service that's often down |
| **WeatherAPI.com** | ✓ (`q=auto:ip`) | ✓ | key, 100k/month | ✓ | ✗ 3 days on free | Good |
| **OpenWeatherMap** (free plan) | ✗ | ✓ | key, 1M/month | ✗ 3-hour steps | ✓ | Good, well known |
| **OpenWeatherMap One Call 4.0** | ✗ | via geocoder | 1,000/day, then pay per call (a card is usually needed) | ✓ | ✓ 8 | Good |
| **Tomorrow.io** | ✗ | ✓ | key, tight free limits | ✓ | ✓ | Good, commercial |
| **Pirate Weather** | ✗ | ✗ | key, about 10k/month | ✓ | ✓ | Decent, based on NOAA models |
| Google Weather / Apple WeatherKit | ✗ | – | paid, or a $99/yr Apple developer account | ✓ | ✓ | High, but overkill here |

The Pirate Weather row is from memory and was not checked against its docs.

### Why not the others

- **MET Norway** is the strongest alternative, and arguably the most "official"
  source. But it has no geocoder and no daily summaries, so the 5-day highs and
  lows have to be worked out from the time series. Its terms also require an
  identifying User-Agent (app name, version, contact), gzip, caching with
  `If-Modified-Since` and `Expires`, and coordinates rounded to at most 4
  decimal places (5+ decimals get a 403). Good as a backup provider.
- **wttr.in** is the only one that handles IP location itself. But it gives
  only 3 days in 3-hour steps and isn't reliable.
- **WeatherAPI.com** also handles IP location, but the free plan stops at
  3 days, so it fails the 5-day criterion.
- **OpenWeatherMap's** free plan has only 3-hour steps, not hourly. The hourly
  One Call API needs a paid subscription.

## Suggested design

- `ewidgets/widgets/weather/`: current temperature and icon, a row of
  5 hourly forecasts, and a row of 5 daily highs and lows.
- Location chain: GeoClue → ip-api.com.
- Refresh every 15–30 minutes (Open-Meteo updates hourly) and run requests off
  the GTK main thread so the blade never stutters.
- Cache the last response so the blade shows something right away when it
  opens.

## Sources

- [Open-Meteo terms](https://open-meteo.com/en/terms)
- [MET Norway terms](https://api.met.no/doc/TermsOfService)
- [WeatherAPI pricing](https://www.weatherapi.com/pricing.aspx)
- [OpenWeather pricing](https://openweathermap.org/price)
- [Tomorrow.io API](https://www.tomorrow.io/weather-api/)
