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

目前已完成階段一、二，以及階段三的 Step 7–8：瀏覽器設定與生命週期管理、URL 驗證與短網址展開。通用條件等待與重試、捲動、Maps 選擇器及爬取介面仍待後續步驟實作。

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
| `compare_places(existing, incoming)` | 以既有非空欄位為基準比較，回傳不可變的 `PlaceComparison` |
| `find_place_match(incoming, candidates)` | 從差異不超過兩欄者選出差異唯一最少的候選；無符合回傳 `None`，最低差異並列時拋出錯誤 |
| `rebind_location_id(record, location_id)` | 回傳套用目標 ID 的新模型，包含摘要的子評論與標籤；不修改原物件 |
| `expand_short_url(url, *, timeout=30, max_redirects=10, max_retries=3, browser_fallback=True)` | 驗證完整 URL 或展開短網址，直接回傳 URL 字串 |

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

### 地點比對與 ID 沿用

新資料須為 `PlaceDetail`；既有候選可為 `PlaceDetail` 或欄位名稱相同的 mapping（例如資料庫傳回的字典），且必須具有合法 UUID v4 `location_id`。歷史資料可缺少欄位，不先補值或轉成完整模型。

比對只看既有資料中非空的地點欄位，排除 `location_id`、`fetched_at` 及 `_id` 等額外欄位。空字串、僅含空白的字串、`None`、空清單或缺漏欄位不作基準；數值 `0` 仍參與。新資料補上的欄位不計差異，清單的內容與順序都必須相同。

符合門檻是最多兩欄差異。若多筆符合，優先取絕對差異數最少的一筆，只有最低差異數仍並列時才拋出 `AmbiguousPlaceMatchError`。候選會完整讀取，不自行去重；不合法候選明確回報輸入錯誤，不會被靜默略過。

`PlaceComparison` 提供 `existing_location_id`、`compared_fields`、`different_fields`、`difference_count` 與 `is_match`。它不保存原始模型的可變參照，因此之後修改輸入也不會改變已回傳的診斷。

延續前例的 `place` 與 `summary`，由呼叫端明確採用比對結果：

```python
from google_map_crawler import create_location_id, find_place_match, rebind_location_id

existing = {
    "location_id": create_location_id(),
    "maps_url": place.maps_url,
    "name": place.name,
}
match = find_place_match(place, [existing])
if match is not None:
    updated_place = rebind_location_id(place, match.existing_location_id)
    updated_summary = rebind_location_id(summary, match.existing_location_id)
# match 為 None 時保留原資料與原 ID。
```

`rebind_location_id()` 保留具體模型型別、時間及非 ID 資料，回傳獨立副本；摘要會一併複製子評論與標籤，清單亦不與原資料共用。它不會自動合併欄位或保存結果。完整三種情境見 [examples/match_places.py](examples/match_places.py)。

此規則尚未驗證地點辨識準確率：有效欄位少的紀錄可能以較低差異數勝出，網址、評分及照片同時變動也可能讓同一地點不符合。初版不加入最低欄位數、文字正規化或空間距離條件。

### 資料契約與限制

- 可選資料預設為 `None` 或獨立空清單；`total_count=None` 表示未知，`0` 表示確認為零，與 `len(reviews)` 分開管理。
- `fetched_at` 在建立實例時產生含時區的 UTC 時間。明確傳入其他含時區時間時轉為 UTC，無時區時間會被拒絕。
- 地點評分接受 0–5、最多一位小數，不靜默四捨五入；評論評分依規格驗證整數型別。
- 摘要內的評論與標籤須使用相同的 `location_id`，錯誤關聯會被拒絕，不會自動覆寫子物件的 ID。
- 模型複製傳入的清單容器；子模型物件本身不會自動深複製。後續欄位賦值或清單修改不會自動觸發建構時驗證。
- `to_dict()` 回傳與原物件分離的巢狀字典，保留空值與清單順序，時間轉為 UTC ISO 8601 字串；呼叫端可再交給 `json.dumps()`。
- 模型中的 `maps_url` 仍僅驗證為非空字串，不自動展開或連線；需要 URL 檢查時明確呼叫下列工具。

### URL 驗證與短網址展開

```python
from google_map_crawler import expand_short_url
from google_map_crawler.urls import validate_maps_url

url = "https://www.google.com/maps/search/?api=1&query=Taipei%20101"
assert validate_maps_url(url) == url  # 離線格式驗證。
assert expand_short_url(url) == url  # 完整 URL 直接回傳，不連線。

# 短網址會連線；必要時啟動 headless Chrome，結束或失敗時清理。
# expanded = expand_short_url("https://maps.app.goo.gl/PrYs3qc14ipRMSHu7")
```

支援 HTTP／HTTPS 的 `maps.app.goo.gl/<token>`、`goo.gl/maps/<token>`，以及 `google.com`、`www.google.com`、`maps.google.com` 的 `/maps/…`。`/maps` 根路徑須有非空 `q`、`query`、`cid`、`ll`、`saddr` 或 `daddr` 參數，`maps.google.com` 亦接受根路徑的位置查詢。國別網域、帳密、非預設連接埠、反斜線、原始空白及無效編碼會被拒絕。

完整 URL 原樣回傳，定位參數與 fragment 不會被刪除。工具不產生或改變 location_id，也不驗證地點的詳細欄位；公開短網址的實測範圍見 [Step 8](agent/step8.md)。

HTTP 與瀏覽器共用 `timeout` 的剩餘時間，以及 `max_retries + 1` 次策略嘗試（最多四次）；切換至瀏覽器也占一次。`max_retries=0` 只做 HTTP，`browser_fallback=False` 明確停用 Chrome。HTTP 轉址不算重試，另受跨嘗試累積的 `max_redirects` 限制；只重試暫時性連線錯誤、逾時與 429／500／502／503／504。

timeout 為有限正數，max_redirects 為非負整數，max_retries 為 0–3 整數。所有參數在 I/O 前驗證；DNS、瀏覽器啟動及清理等底層阻塞不能保證被硬中斷，時間預算不是嚴格 wall-clock 上限。瀏覽器內部跳轉受剩餘時間限制，不計入 HTTP 轉址計數。

完整使用方式見 [examples/expand_url.py](examples/expand_url.py)。

### 例外處理

所有套件例外繼承 `CrawlerError`。目前模型與工具使用 `InvalidInputError`，無效 ID 使用其子類 `InvalidLocationIdError`，錯誤訊息會指出參數或欄位。

`AmbiguousPlaceMatchError` 表示最低差異數仍有多筆候選並列，其 `matches` tuple 提供這些候選的 `PlaceComparison`，可查看 ID 及差異欄位。

URL 格式無效使用 `InvalidMapsUrlError`；短網址 HTTP 404／410 或明確失效頁使用 `PlaceNotFoundError`；HTTP 401／403、已知登入／驗證跳轉使用 `PageAccessBlockedError`。逾時使用 `UrlExpansionTimeoutError`（繼承 `UrlExpansionError`），其他展開失敗使用 `UrlExpansionError` 並保留原因鏈。無法建立或清理 Chrome 時亦可能回報 `BrowserStartError`／`BrowserCleanupError`。

`PageLoadTimeoutError` 與 `ParseError` 留待後續頁面操作及解析功能使用。

## 瀏覽器設定與生命週期

```python
from google_map_crawler.browser import BrowserConfig, BrowserSession

session = BrowserSession(BrowserConfig(headless=True, language="zh-TW"))
with session as driver:
    driver.get("data:text/html,<title>Local example</title>")
    print(driver.title)
```

匯入、建立設定或 session 都不啟動瀏覽器；進入 `with` 才建立本次專用 Chrome，離開時執行 `quit()` 並清理自有 Service。預設 headless，載入 timeout 為 30 秒、implicit wait 為 0。元素等待 timeout、重試與捲動相關欄位目前只做設定驗證，對應工具尚未實作。

session 為單次使用，拒絕重入或關閉後重開；`close()` 可重複呼叫。若有原始操作錯誤，保留同一錯誤並附加清理失敗註記；沒有操作錯誤但清理失敗時拋出 `BrowserCleanupError`，可讀取 `errors`。session 的 `cleanup_errors` 亦保留原始清理錯誤。啟動或初始設定失敗使用 `BrowserStartError` 並保留原因鏈。

測試可傳入 `driver_factory(config)`。工廠須建立新 driver，回傳後的 driver 與其 service 交由 session 管理；回傳前失敗的未交接資源由工廠自行清理。不要回傳使用者正在使用的 driver。清理皆失敗時無法保證程序已退出，會明確回報。

## 開發環境

需要 Python 3.11 以上版本。以下為 PowerShell 指令，請在本專案目錄執行；`--group dev` 需要 pip 25.1 以上版本。

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -e . --group dev
```

執行時依賴 Selenium 4，`dev` 群組提供 pytest 與 build。實際瀏覽器操作需要 Chrome；預設使用 Selenium Manager 尋找或取得相容 driver，首次明確啟動 session 可能需要網路。模型、比對與設定不觸發 driver 下載。

## 測試與建置

```powershell
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m build
```

測試使用已安裝的套件，不需要修改 `PYTHONPATH`。建置產物位於 `dist/`；目前所有單元測試及離線範例不需要網路、Chrome 或資料庫。

真實 Chrome 測試預設跳過，明確啟用後只存取本機示意頁，驗證 session 與 URL 的 HTTP／JavaScript 轉址、逾時及程序退出：

```powershell
$env:GOOGLE_MAP_CRAWLER_RUN_BROWSER_TESTS = "1"
.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests/integration/test_browser_session.py tests/integration/test_urls.py
Remove-Item Env:GOOGLE_MAP_CRAWLER_RUN_BROWSER_TESTS
```

公開 Maps 連結另行 opt-in，需網路與 Chrome，驗證故宮園區及台北 101 短網址的最終地點標題；外部頁面、網址或存取限制可能改變：

```powershell
$env:GOOGLE_MAP_CRAWLER_RUN_MAPS_TESTS = "1"
.venv\Scripts\python.exe -X utf8 -m pytest -s -p no:cacheprovider tests/integration/test_maps_urls.py
Remove-Item Env:GOOGLE_MAP_CRAWLER_RUN_MAPS_TESTS
```

瀏覽器行為變更須更新並執行實際測試，不能只以假 driver 測試代替。完整分步與驗證紀錄見 [agent.md](agent.md)。

```powershell
.venv\Scripts\python.exe -X utf8 examples/create_models.py
.venv\Scripts\python.exe -X utf8 examples/match_places.py
.venv\Scripts\python.exe -X utf8 examples/expand_url.py
```

## 規格與開發順序

- 提案書中的 crawler 部分定義功能方向，[spec.md](spec.md) 定義目前套件的詳細行為。功能方向不代表已完成實作或可行性驗證。
- 優先完成搜尋、詳細資料、評論、照片 URL、隨機地點 ID 與初版地點比對規則。
- 接續驗證自訂清單擷取，補齊清單輸入、存取方式與公開介面的規格。
- 以 Codex 輔助開發，搭配離線測試與受控實測確認行為。
