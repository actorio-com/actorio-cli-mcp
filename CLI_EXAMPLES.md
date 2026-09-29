# Example CLI Searches

Quick reference: 10 practical `actorio products search` examples.

All assume you've logged in: `actorio login --base-url http://127.0.0.1:9000`

---

## 1. Basic keyword search
```bash
actorio products search "lego"
```
Find all products matching "lego" (returns default 20 results).

---

## 2. Search with country filter
```bash
actorio products search "iphone" --country DE
```
Search for iPhones in Germany only.

---

## 3. Search with marketplace
```bash
actorio products search "smartwatch" --marketplace FR
```
Search for smartwatches, show profit/ROI data for Amazon FR only.

---

## 4. Price range filter
```bash
actorio products search "headphones" --price-min 20 --price-max 100
```
Find headphones between €20–€100 (supplier price, VAT incl.).

---

## 5. Minimum profit filter
```bash
actorio products search "gaming" --marketplace DE --profit-min 50
```
Find gaming products with at least €50 profit on Amazon DE.

---

## 6. ROI filter
```bash
actorio products search "" --roi-min 30 --profit-logic all
```
All products (empty keyword) with ≥30% ROI on ALL marketplaces.

---

## 7. Combination: price + profit + marketplace
```bash
actorio products search "camera" \
  --price-max 500 \
  --profit-min 100 \
  --marketplace DE \
  --limit 10
```
Find cameras under €500 with ≥€100 profit on Amazon DE, show 10 results.

---

## 8. Pagination: offset to skip results
```bash
actorio products search "tablet" --limit 20 --offset 40
```
Search for tablets, show results 40–60 (skipping first 40).

---

## 9. Sort by profit (descending)
```bash
actorio products search "monitor" --marketplace DE --sort "-profit_de"
```
Find monitors, sort by highest profit on Amazon DE first (descending).

---

## 10. JSON output for scripting
```bash
actorio products search "keyboard" --marketplace FR --json | jq '.results | length'
```
Search for keyboards, output raw JSON, pipe to `jq` to count results.

---

## Tips

- **Activate venv first**: `source env/bin/activate`
- **Check credits**: `actorio usage` (shows monthly allowance/used/remaining)
- **Export to CSV**: `actorio products export "keyword" --format csv --output results.csv`
- **List available countries**: Look at MARKETPLACES in `cli_api/search/params.py` (DE, ES, FR, GB, IT)
- **Similarity filter**: `-–similarity 0` (exact), `1`, `2` (default), `3` (loose)
- **Size categories**: `--size SML_PAR` (small parcel), `LRG_ENV` (large envelope), etc.

Each search costs **1 credit**; exports cost **5 credits**.
