# Step 8：URL 驗證與短網址展開

## 狀態與範圍

- 狀態：已完成。
- 計畫日期：2026-11-24（Asia/Taipei）。
- 完成日期：2026-11-24（Asia/Taipei）。
- 所屬階段：階段三；前置條件：Step 7。
- 依據：[spec.md](../spec.md)、[implementation.md](../implementation.md) 及 [agent.md](../agent.md)。

只實作 URL 格式及展開，不加入搜尋或地點資料解析。

## 實作流程

**輸入：**呼叫端提供的 Maps URL。

**要做的事：**

1. 先離線解析 URL，驗證 scheme、主機及路徑。初版至少涵蓋 `maps.app.goo.gl` 短網址與 `google.com/maps`、`www.google.com/maps`、`maps.google.com` 常見形式；實作前列出明確支援清單。
2. 格式無效時拋出 `InvalidMapsUrlError`，不啟動瀏覽器或送出請求。
3. 短網址先用標準函式庫 HTTP 請求處理重新導向，設定連線／讀取等待與最大重新導向次數，並確實關閉 response。
4. 完整 Maps URL 可直接回傳；短網址若需 JavaScript 才能展開，使用受管理的瀏覽器流程，等待 URL 與頁面狀態到達目標。
5. HTTP 與瀏覽器策略共用本次操作的時間與重試預算，不各自取得額外三次重試。重新導向迴圈或持續停在短網址時回報展開失敗。
6. 僅在有明確證據表示連結失效或地點不存在時使用 `PlaceNotFoundError`。網路失敗、逾時、要求登入或驗證不能當作地點不存在。
7. 驗證最終 URL 可用於定位 Maps 地點，原樣保留定位所需資訊，不從 URL 產生或改變 `location_id`。

**完成條件：**單次與多次重新導向、逾時、迴圈、失效連結及瀏覽器補充策略皆有可測試的結果；任何路徑都有時間及次數上限。

## 預計檔案

`urls.py`、`test_urls.py`、URL 整合測試、規格、README、範例與步驟索引。

## 本次採用的介面與操作預算

- `validate_maps_url(url)` 從 `google_map_crawler.urls` 使用，回傳原字串，不執行 I/O。
- `expand_short_url(url, *, timeout=30, max_redirects=10, max_retries=3, browser_fallback=True)` 同時從模組及套件根目錄使用。
- 支援 HTTP／HTTPS 的 `maps.app.goo.gl/<token>`、舊版 `goo.gl/maps/<token>`，以及 `google.com`、`www.google.com` 的 `/maps/…` 與 `maps.google.com` 的位置查詢形式。主機、路徑、連接埠與空白等均先驗證，國別網域不自動推測支援。
- 完整 URL 在驗證參數後直接回傳；只有短網址展開才連線。
- HTTP 策略嘗試與瀏覽器策略嘗試共用最多 `max_retries + 1` 次，最大四次；切換至瀏覽器亦占一次。因此重試設為零時，HTTP 無法直接展開便不再啟動第二種策略。
- `max_redirects` 為 HTTP 重新導向的累積上限；重新導向本身不是重試。瀏覽器導航由共用剩餘時間限制，不宣稱能逐一觀察所有 JavaScript／瀏覽器內部跳轉。
- `timeout` 為 HTTP／頁面操作共用的 monotonic 時間預算，後續請求及等待都使用剩餘時間。DNS、瀏覽器建立／清理等底層阻塞無法保證被 Python 的截止時間硬中斷；結束後仍須清理資源，不宣稱絕對 wall-clock 限制。
- 新增 `UrlExpansionTimeoutError(UrlExpansionError)`，明確表示展開逾時。失效使用 `PlaceNotFoundError`，已知登入／驗證跳轉或 HTTP 存取拒絕使用 `PageAccessBlockedError`；其他失敗保留 `UrlExpansionError` 與原因鏈。
- 真實 Chrome 使用本機 HTTP 及 JavaScript 頁面測試，僅測試中將本機 fixture 來源視為支援 URL，不放寬正式支援網域；另用少量公開短網址驗證真實定位。

## 測試方式

離線測試涵蓋支援形式、重新導向、逾時、迴圈及錯誤分類；瀏覽器 fallback 若有新增或變更，必須加入並執行實際 Chrome 測試，再以少量真實短網址確認定位。

瀏覽器操作有變更時，假物件測試不能替代實際測試。整合測試使用明確 opt-in 開關，實作時記錄命令、環境與結果；無法執行須明列原因，不標記該項完成。

## 驗收條件

- [x] URL 支援清單及操作預算已補入規格。
- [x] 無效 URL 不啟動瀏覽器或連線。
- [x] HTTP 與瀏覽器策略共用時間／重試預算，最多四次，不改 location_id。
- [x] 錯誤分類與資源釋放正確，新增瀏覽器行為已實際測試。

## 執行結果與限制

### 實際變更

| 檔案 | 結果 |
|---|---|
| `src/google_map_crawler/urls.py` | 離線驗證、HTTP 轉址、Chrome JavaScript fallback、共用預算及明確失敗分類 |
| `src/google_map_crawler/exceptions.py`、`__init__.py` | 新增及公開 `UrlExpansionTimeoutError`，根目錄匯出 `expand_short_url` |
| `tests/unit/test_urls.py` | 支援／無效網址、無 I/O、參數、轉址與 fragment、國際文字、狀態碼、重試預算、剩餘時間、原因鏈及 response／session 清理 |
| `tests/unit/test_import_safety.py`、`test_public_usage.py` | 隔離程序確認匯入、完整／無效 URL 不連線、不啟動 Selenium；驗證範例可從其他目錄執行 |
| `tests/integration/test_urls.py` | 真實本機 HTTP 多次轉址，以及 Chrome JavaScript 成功、逾時、明確失效與不支援目的地 |
| `tests/integration/test_maps_urls.py` | 公開短網址展開後，以真實 Chrome 地點標題確認定位 |
| `tests/integration/conftest.py`、`test_browser_session.py` | 共用自有程序退出檢查，保留既有正常／例外 session 實測 |
| `examples/expand_url.py`、相關 README／規格／索引 | 完整 URL 離線範例、短網址連線用法、參數與限制、實作進度 |

HTTP response 僅讀取狀態與標頭，所有分支關閉 response。國際文字只在傳輸時編碼，不改回傳表示；轉址未指定 fragment 時沿用來源 fragment。瀏覽器使用 `BrowserSession` 與條件等待，完成或失敗時均釋放自有資源。通用等待／重試工具仍留給 Step 9。

### 最終驗證命令與結果

於 `google-map-crawler/` 執行；實際瀏覽器／外網及隔離建置在允許啟動程序與連線的環境執行。

```powershell
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

結果：**360 passed、9 skipped**。9 項為預設不啟用的整合測試，不列入離線通過數。

```powershell
$env:GOOGLE_MAP_CRAWLER_RUN_BROWSER_TESTS = "1"
$env:GOOGLE_MAP_CRAWLER_RUN_MAPS_TESTS = "1"
.venv\Scripts\python.exe -X utf8 -m pytest -q -s -p no:cacheprovider tests/integration
Remove-Item Env:GOOGLE_MAP_CRAWLER_RUN_BROWSER_TESTS
Remove-Item Env:GOOGLE_MAP_CRAWLER_RUN_MAPS_TESTS
```

結果：**9 passed**，最終執行約 41 秒。包含既有 session 測試 2 項、本機 HTTP／URL／Chrome 測試 5 項及公開短網址定位 2 項。各 Chrome 路徑均確認自有 ChromeDriver 已退出、Chrome PID 已退出且無清理錯誤；HTTP 直接展開不建立 session。

公開樣本取自 [臺灣政府提供的 ESC29 行政說明文件](https://www.ccsbt.org/system/files/2024-06/AdministrativeCircular_ESC29_provided_by_TW_government.pdf) 第 6–7 頁：

| 短網址 | Chrome 實際地點標題 | 結果 |
|---|---|---|
| `https://maps.app.goo.gl/EGSCc4KavHEFuwVZ7` | 國立故宮博物院北部院區天下為公牌樓 | 通過；為故宮園區牌樓，未宣稱定位主館 |
| `https://maps.app.goo.gl/PrYs3qc14ipRMSHu7` | Taipei 101 | 通過 |

```powershell
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe -m build
git diff --check
```

結果：相依性檢查通過；隔離建置成功產生 `dist/google_map_crawler-0.1.0.tar.gz` 及 `dist/google_map_crawler-0.1.0-py3-none-any.whl`，兩者皆包含 URL 模組；diff 無空白錯誤。

本次曾嘗試 `python -m build --no-isolation`，因現有開發 venv 未安裝 setuptools，出現 `Cannot import 'setuptools.build_meta'`。改用專案標準 `python -m build`，由隔離環境安裝已宣告的建置相依性後成功；未因此新增執行時相依性。

受限沙盒讀取建置產物時曾出現 `PermissionError`；改用與建置相同的執行權限只讀檢查，已確認 sdist／wheel 內的 `urls.py` 皆與目前原始碼逐位元組相同。

實測環境：Windows、Python **3.14.7**、Selenium **4.54.0**、Chrome **158.0.8127.36**、ChromeDriver **158.0.8127.88**；隔離建置使用 setuptools **84.2.1**。

### 限制與後續

- 本機伺服器僅測試時被 classifier 接受，正式驗證仍維持 Google 主機白名單。
- 公開實測只驗證上列兩筆目前可用連結；舊 `goo.gl/maps` 的語法與導向流程有離線測試，不代表所有歷史連結仍有效。
- 網頁／短網址服務、地區及存取限制可能改變；不將某次成功視為所有 Maps 頁面的相容保證，也未實作完整地點資料解析。
- 時間預算與 HTTP 轉址上限的限制依前述介面定義，不保證硬中斷 DNS、Chrome 啟動／清理或逐一計數瀏覽器內部轉址。
- Step 9–12 及後續爬取介面尚未實作；階段三仍為部分完成。

技術依據：[Python urllib.request](https://docs.python.org/3.11/library/urllib.request.html)、[Selenium WebDriverWait](https://www.selenium.dev/selenium/docs/api/py/selenium_webdriver_support/selenium.webdriver.support.wait.html)、[RFC 9110 Location／fragment 規則](https://www.rfc-editor.org/rfc/rfc9110.html#field.location)。

部分結果回傳、零筆評論摘要等既有待定事項不在此步擅自定案。
