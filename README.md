# Google Map Crawler

本專案建立可供其他 Python 專案使用的 Google Maps 爬蟲套件，範圍以「期末專案提案書」中的 GoogleMap Crawler Library 為準。

## 功能範圍

- 擷取關鍵字搜尋結果。
- 擷取地點詳細資料、評論與照片 URL。
- 支援自訂 Google Maps 清單中的地點內容擷取；此為提案方向，清單輸入形式、存取方式及公開介面尚待補入規格與驗證。
- 使用 Selenium 操作 Google Maps 網頁。
- 提供可獨立呼叫的 Python 介面與一致的資料模型，所有結果直接回傳。

套件不依賴特定資料庫，不提供 dump，也不下載圖片檔案。資料儲存與跨次執行的地點 ID 保存由呼叫端負責。

## 目前進度

目前已完成階段一：套件設定、五種資料模型、例外分類、UUID 工具、輸入驗證與離線使用範例。地點比對、瀏覽器操作及爬取介面仍待後續階段實作。

開發步驟與驗證結果記錄於 [agent.md](agent.md)，每一步的獨立計畫存放在 `agent/`。

## 目前可用介面

可從 `google_map_crawler` 匯入下列模型與工具。

| 模型 | 用途 |
|---|---|
| `PlaceSearchResult` | 搜尋列表中的地點資料 |
| `PlaceDetail` | 地點詳細資料 |
| `ReviewSummary` | 平均評分、總評論數、標籤與實際取得的評論 |
| `Review` | 單則評論，允許沒有文字或照片的純評分評論 |
| `ReviewTag` | 評論標籤與數量 |

| 工具 | 行為 |
|---|---|
| `create_location_id()` | 產生新的 UUID v4 字串 |
| `validate_location_id(location_id)` | 驗證 UUID v4，回傳原始字串，不重新格式化 |
| `resolve_location_id(location_id=None)` | 未提供 ID 時產生新值，否則驗證並沿用；無效 ID 不會被靜默替換 |
| `validate_count(value, *, name)` | 接受非負整數（包含 `0`），拒絕布林值及其他型別 |
| `validate_non_empty_string(value, *, name)` | 驗證必填文字不是空值或只有空白，回傳原始內容 |

所有模型使用具名參數建構，`location_id` 必填；兩種地點模型的 `maps_url` 亦必填。只有新地點紀錄需配置 ID，評論與標籤應沿用對應地點的 ID。

```python
from google_map_crawler import PlaceDetail, Review, ReviewSummary, resolve_location_id

location_id = resolve_location_id()
place = PlaceDetail(
    location_id=location_id,
    maps_url="https://www.google.com/maps/search/?api=1&query=範例地點",
    name="離線範例地點",
)
review = Review(location_id=location_id, rating=5)
summary = ReviewSummary(location_id=location_id, reviews=[review])
data = summary.to_dict()
```

上述為離線示意資料，不會開啟 URL。完整範例見 [examples/create_models.py](examples/create_models.py)。

### 資料契約與限制

- 可選資料預設為 `None` 或獨立空清單；`total_count=None` 表示未知，`0` 表示確認為零，與 `len(reviews)` 分開管理。
- `fetched_at` 在建立實例時產生含時區的 UTC 時間。明確傳入其他含時區時間時轉為 UTC，無時區時間會被拒絕。
- 地點評分接受 0–5、最多一位小數，不靜默四捨五入；評論評分依規格驗證整數型別。
- 摘要內的評論與標籤須使用相同的 `location_id`，錯誤關聯會被拒絕，不會自動覆寫子物件的 ID。
- 模型複製傳入的清單容器；子模型物件本身不會自動深複製。後續欄位賦值或清單修改不會自動觸發建構時驗證。
- `to_dict()` 回傳與原物件分離的巢狀字典，保留空值與清單順序，時間轉為 UTC ISO 8601 字串；呼叫端可再交給 `json.dumps()`。
- 目前 `maps_url` 僅驗證為非空字串，支援網址形式、短網址展開與地點定位可用性留待 URL 階段實作。

### 例外處理

所有套件例外繼承 `CrawlerError`。目前模型與工具使用 `InvalidInputError`，無效 ID 使用其子類 `InvalidLocationIdError`，錯誤訊息會指出參數或欄位。

另已建立 `InvalidMapsUrlError`、`PlaceNotFoundError`、`PageLoadTimeoutError`、`ParseError` 與 `AmbiguousPlaceMatchError`，供後續 URL、瀏覽器及比對流程使用；對應功能目前尚未實作。

## 開發環境

需要 Python 3.11 以上版本。以下為 PowerShell 指令，請在本專案目錄執行；`--group dev` 需要 pip 25.1 以上版本。

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -e . --group dev
```

目前套件沒有執行時第三方相依性。`dev` 群組提供 pytest 與 build；瀏覽器功能實作時再加入 Selenium。

## 測試與建置

```powershell
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m build
```

測試使用已安裝的套件，不需要修改 `PYTHONPATH`。建置產物位於 `dist/`；目前所有單元測試及離線範例不需要網路、Chrome 或資料庫。

```powershell
.venv\Scripts\python.exe -X utf8 examples/create_models.py
```

## 規格與開發順序

- 提案書中的 crawler 部分定義功能方向，[spec.md](spec.md) 定義目前套件的詳細行為。功能方向不代表已完成實作或可行性驗證。
- 優先完成搜尋、詳細資料、評論、照片 URL、隨機地點 ID 與初版地點比對規則。
- 接續驗證自訂清單擷取，補齊清單輸入、存取方式與公開介面的規格。
- 以 Codex 輔助開發，搭配離線測試與受控實測確認行為。
