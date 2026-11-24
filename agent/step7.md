# Step 7：瀏覽器設定與生命週期管理

## 狀態與範圍

- 狀態：已完成。
- 更新日期：2026-11-24（Asia/Taipei）。
- 所屬階段：階段三；依據 [spec.md](../spec.md)、[implementation.md](../implementation.md) 及 [agent.md](../agent.md)。
- 本步整合原階段三計畫的步驟一、二，視為同一類「瀏覽器建立與資源管理」功能。

建立有效設定後，只在明確進入 session 時啟動 Chrome；正常完成或發生例外都清理自有資源。URL、等待重試、捲動、Maps 實測及整合驗收分別移至 Step 8–12。

## 採用的介面

- 從 `google_map_crawler.browser` 匯入 `BrowserConfig` 與 `BrowserSession`，不在根目錄匯出瀏覽器操作 API。
- 設定為不可變物件，所有參數使用具名參數；headless=True、language=zh-TW、page_load_timeout=30、wait_timeout=10、max_retries=3、no_progress_limit=3、max_scroll_rounds=100。
- 重試與捲動欄位此步只驗證數值，不代表那些功能已實作。
- `BrowserSession(config=None, driver_factory=None)` 在 `with` 內回傳 driver，為單次使用；建構與重複 `close()` 不啟動瀏覽器。
- `driver_factory(config)` 須建立新 driver。回傳後 driver 與其 service 交由 session 管理；工廠回傳前若失敗，其未交接資源由工廠自行清理。預設建立流程會先保存 Service，再建立 WebDriver。
- 正常清理先 `quit()`，再停止自有 Service。失敗資訊保存於 `cleanup_errors`；已有原始操作錯誤時保留同一錯誤並加註記，否則拋出 `BrowserCleanupError`，其 `errors` tuple 保存原因。
- 啟動失敗使用 `BrowserStartError` 保留原因鏈；中斷及退出訊號不轉為一般啟動錯誤。
- `UrlExpansionError`、`PageAccessBlockedError` 先建立分類，對應功能仍屬後續步驟。

## 工作一：設定、相依性與例外

**輸入：**目前套件設定及規格中的等待、重試與資源管理要求。

**要做的事：**

1. 在 `pyproject.toml` 加入 Selenium 執行時相依性，依實作時的 Python 相容性選擇版本範圍，並記錄實際驗證版本。
2. 建議初始設定為語言 `zh-TW`、headless 啟用、頁面載入 timeout 30 秒、元素等待 timeout 10 秒；允許呼叫端調整，不使用固定設定檔。
3. timeout 必須是有限正數，捲動輪數等參數須為正整數；重試次數接受 0–3，不接受布林值。
4. 沿用既有 `InvalidInputError`、`InvalidMapsUrlError`、`PlaceNotFoundError` 與 `PageLoadTimeoutError`。
5. 明確區分瀏覽器啟動失敗、URL 展開失敗與頁面要求登入／驗證等情況。需要新增的例外先定義於規格，繼承 `CrawlerError` 並保留原因鏈。

**完成條件：**錯誤設定會在啟動瀏覽器或連線前被拒絕；匯入套件不呼叫 Selenium Manager、不下載 driver、不開啟 Chrome。

## 工作二：session 建立與清理

**輸入：**有效設定，以及可選的 driver 建立函式。測試可傳入假 driver；此介面不借用呼叫端已開啟的 driver。

**要做的事：**

1. 建立 `BrowserSession` 物件時只保存設定，在進入 `with` 區塊時才啟動 Chrome。
2. 將語言、headless、載入 timeout 等設定套用到本次 session；不共用全域 driver。
3. 將本 session 建立的 driver 與 Service 視為自行管理的資源。正常離開、頁面操作例外及初始化中途失敗，都要清理已建立的資源。
4. 使用 `quit()` 結束整個 session，不能只關閉單一分頁；需要時停止本 session 的 Service，不終止其他使用者程序。
5. 清理可重複呼叫；若操作與清理同時失敗，保留原操作錯誤，另保留清理失敗資訊，避免掩蓋主要原因。

**完成條件：**測試可確認正常、操作失敗及啟動中途失敗時的清理行為；實際 Chrome 測試離開後，本 session 不留存 driver／Service。

## 檔案分工

| 檔案 | 工作 |
|---|---|
| `pyproject.toml` | Selenium 依賴與 integration 標記 |
| `src/google_map_crawler/browser.py` | 設定、延後啟動、資源管理與錯誤保留 |
| `src/google_map_crawler/exceptions.py`、`__init__.py` | 例外分類與公開匯入 |
| `tests/unit/test_browser.py` | 設定、正常及失敗分支的假 driver 測試 |
| `tests/unit/test_import_safety.py` | 匯入、設定與 session 建構無外部副作用 |
| `tests/integration/test_browser_session.py` | opt-in 真實 Chrome 正常及例外清理測試 |
| `README.md`、`spec.md` | 明確介面與使用限制 |
| 本文件、`agent.md`、`implementation.md` | 計畫、結果與完成狀態 |

## 驗收條件

- [x] Selenium 已安裝，設定與錯誤分類同步規格。
- [x] 設定邊界、單次使用、重複清理與錯誤保留通過單元測試。
- [x] 匯入、建立設定與 session 不啟動 Chrome、不連線或下載 driver。
- [x] 假 driver 驗證初始化失敗及 Service 清理，操作與清理同時失敗時保留主要錯誤。
- [x] 真實 Chrome 可載入本機頁面，設定正確，正常與例外路徑皆確認自有程序已退出。
- [x] 完整測試無退化，文件及步驟紀錄已同步。

## 執行結果

目前 Selenium 4.54.0 已安裝。瀏覽器與匯入安全的針對性測試 51 項通過；真實 headless Chrome 的正常與區塊錯誤測試 2 項通過，驗證頁面標題、元素、語言、載入 timeout、implicit wait=0 與 Chrome／ChromeDriver 退出。

### 驗證命令與環境

| 檢查 | 結果 |
|---|---|
| `.venv\Scripts\python.exe -m pip install -e . --group dev` | Selenium 4.54.0 與依賴已安裝，editable 安裝成功 |
| `.venv\Scripts\python.exe -m pytest -q tests/unit/test_browser.py tests/unit/test_import_safety.py` | 51 項通過 |
| 設定 `GOOGLE_MAP_CRAWLER_RUN_BROWSER_TESTS=1` 後執行 `pytest -q -s tests/integration/test_browser_session.py` | 2 項真實 Chrome 測試通過：正常與 body-error；確認語言 en-US、頁面載入 timeout=10、implicit wait=0、本機頁面可讀及兩種程序退出 |
| `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider` | 246 項通過，2 項 opt-in Chrome 測試預設跳過；這兩項已在上列命令獨立實際執行通過 |
| `.venv\Scripts\python.exe -m pip check` | 無相依性衝突 |

環境：Windows、Python 3.14.7、pytest 9.2.0、Selenium 4.54.0、本機 Chrome 158.0.8127.36、Selenium Manager 取得的 ChromeDriver 158.0.8127.88。瀏覽器與 driver 程序均依本次 session 的 PID 檢查退出，不影響其他程序。

實際測試首次執行有 pytest cache 權限警告，測試仍通過；完整離線測試停用 cache provider 後無此警告。實際 Chrome 測試使用授權執行以取得 driver 及啟動瀏覽器，頁面為本機 data URL，不連線 Maps。

本步不代表整個階段三完成，也未宣稱 Python 3.11 執行時或其他作業系統已驗證。後續完整建置／乾淨安裝與 Maps 實測依各步驟計畫驗收。

## 限制與後續

清理皆失敗時不能保證程序已退出，必須回報錯誤。工廠未交接的未知資源不由 session 猜測或終止。URL 與實際 Maps 操作尚未實作。

後續計畫：[Step 8](step8.md) URL、[Step 9](step9.md) 等待重試、[Step 10](step10.md) 捲動、[Step 11](step11.md) Maps 頁面實測、[Step 12](step12.md) 階段整合驗收。

參考 [Selenium Chrome API](https://www.selenium.dev/selenium/docs/api/py/selenium_webdriver_chrome/selenium.webdriver.chrome.webdriver.html) 與 [Service 原始碼](https://www.selenium.dev/selenium/docs/api/py/_modules/selenium/webdriver/common/service.html)。Context7 工具未提供，實作依官方文件與已安裝版本核對。
