# Step 9：條件等待與操作重試

## 狀態與範圍

- 狀態：已完成；條件等待與有限重試均已驗證。
- 計畫日期：2026-11-24（Asia/Taipei）。
- 條件等待完成日期：2026-11-24（Asia/Taipei）。
- 有限重試完成日期：2026-11-24（Asia/Taipei）。
- 所屬階段：階段三；前置條件：Step 7；URL 測試需 Step 8。
- 依據：[spec.md](../spec.md)、[implementation.md](../implementation.md) 及 [agent.md](../agent.md)。

將等待與可恢復操作重試作為同一類操作控制功能，不實作捲動或批次爬取。

## 工作一的實作決定（前次完成）

- 從 `google_map_crawler.interaction` 提供 `wait_for_element(driver, locator, *, state="visible", timeout=10, operation="wait_for_element")` 與 `wait_until(driver, condition, *, timeout=10, operation="wait_until", locator=None)`，不於套件根目錄匯出瀏覽器操作工具。
- `locator` 使用 `(by, value)` tuple，支援 Selenium 標準八種定位方式；元素狀態為 `present`、`visible`、`clickable`。每次輪詢重新定位，缺少元素或 stale 時繼續同一次等待，不重新啟動等待預算。
- `clickable` 代表可見且啟用，不保證沒有遮擋，也不自動點擊。遮擋解除等狀態用自訂條件等待；回呼應只檢查狀態、不執行有副作用的操作。
- 自訂條件接收 driver，回傳 truthy 值即成功並原樣回傳；falsy 值繼續等待。既有套件例外及非 Selenium 的回呼錯誤原樣拋出。
- timeout 為有限正數，operation 為非空字串，所有一般參數在 driver 操作前驗證。共用正數 timeout 驗證移至 `validation.py`，供 BrowserConfig 與等待工具使用。
- driver 的 implicit wait 必須為 0；若不是零則明確拒絕，不擅自修改呼叫端設定。BrowserSession 已符合此條件。
- 使用 Selenium explicit wait，輪詢間隔 0.1 秒；同一次等待用 monotonic 截止時間，逾時不回傳 None／空結果，也不自動重跑操作。WebDriver 命令不能保證被硬中斷，故 timeout 不宣稱為嚴格 wall-clock 上限。
- 新增 `PageWaitError`，既有 `PageLoadTimeoutError` 繼承它，保留原有 CrawlerError 關係；兩者保存 operation、locator、state、timeout、last_error，原因鏈保留原始 Selenium 例外。無效 selector／失效 session 等非暫時錯誤立即回報，不輪詢到逾時。
- 可選欄位由呼叫端於確認必要容器與資料就緒後查詢；等待工具本身不將逾時視為欄位不存在。以本機 fixture 驗證必要容器未就緒時報錯，以及就緒後缺少可選欄位可使用預設值。
- 工作一當時僅完成等待，未加入操作重試、點擊包裝或結果收集；本次工作二另外補齊有限重試及控制層級檢查，最終結果見下方。

## 工作一：條件等待

**輸入：**driver、定位條件、需要等待的狀態及 timeout。

**要做的事：**

1. 使用 explicit wait 等待元素存在、可見、可點擊或自訂頁面狀態，不混用 implicit wait 增加不明確的等待時間。
2. 區分「頁面已可用，但可選欄位不存在」與「必要頁面／容器尚未載入」。前者可讓呼叫端使用預設值，後者逾時須拋出錯誤。
3. 元素失效時依定位條件重新查找，不一直操作同一個 stale element。
4. 等待失敗保留操作名稱、定位資訊與原因，轉為可辨識的套件例外。
5. 條件等待本身只負責一次等待；是否重新執行整個操作，由下一步的重試層決定。

**完成條件：**存在不代表可見、可見不代表可點擊，測試可分別驗證；逾時不會回傳假空結果，且不用固定 `time.sleep()` 判定就緒。

## 工作二：有限重試

### 本次有限重試的實作決定

- 在 `interaction.py` 加入 `retry_operation(action, *, max_retries=3, timeout=30, operation="retry_operation", locator=None, recover=None)`；action 接收剩餘秒數並回傳資料，recover 接收最後錯誤與剩餘秒數。成功值含 None、False、空集合均原樣回傳，不用 truthiness 判斷操作成功。
- 預設最多四次 action，max_retries 僅接受 0–3 整數；所有嘗試與 recover 共用一個 monotonic 預算。回呼須將剩餘時間交給等待工具，且不得在失敗嘗試中對外追加資料；只有回傳成功後才由呼叫端保存、依識別值去重。工具無法回復任意回呼已造成的副作用。
- 泛用 action 限可安全重做的讀取／操作。只重試具體 stale、點擊遭拒或已知暫時連線錯誤；既有等待逾時、URL 展開失敗、無效輸入、解析失敗、登入／驗證、失效連結及其他未知錯誤不自動重試。
- 加入 `click_with_retry(driver, locator, *, is_complete, max_retries=3, timeout=30, operation="click", recover=None)`。is_complete 為必要的只讀狀態查核，每次嘗試先確認是否已生效；click 丟出錯誤時也重新查核。已生效則回傳確認結果，只有明確遭拒且尚未生效時可重點；未知結果或查核失敗立即報錯。
- click 成功返回後用同一剩餘預算等待目標狀態，不因驗證逾時重點。recover(driver, error, remaining) 可用於等待遮擋解除；只在有下一次嘗試時執行，不新增隱藏重試或固定 sleep。
- 新增 `OperationRetryError` 與 `OperationRetryTimeoutError`，保存 operation、locator、attempts、max_retries、timeout、reason、last_error 及原因鏈。耗盡、時間到、復原失敗、狀態無法確認皆明確回報，永久錯誤保留原例外。
- 用 ContextVar 保存同步控制範圍：禁止重試包重試、等待回呼內啟動重試，以及重試／等待包短網址策略；允許單次等待位於重試內。URL 完整格式的離線直接回傳不受影響；Step 8 短網址策略只新增層級檢查，獨立呼叫時的預算與流程維持原樣。
- 單元測試驗證次數、期限、錯誤分類、原因鏈、層級重設與成功後收集資料；真實 Chrome 測試驗證遮擋後重試、實際 stale、已生效但回應錯誤、查核失敗與耗盡，均確認程序清理。
- 完成後更新 spec、README、implementation、agent 索引與本檔結果。捲動、批次爬取及部分結果回傳仍不在本次範圍。

**輸入：**一個明確的操作，例如定位、讀取或可恢復的頁面操作。

**要做的事：**

1. 預設初次執行加上最多三次重試，總計最多四次。`max_retries=0` 時只執行一次。
2. 依具體例外與頁面狀態判斷可重試性，例如短暫 stale、可恢復的點擊遮擋或暫時性連線失敗；不能將所有 Selenium 例外都視為暫時性錯誤。
3. 無效輸入、已確認的失效連結、解析失敗、持續登入／驗證要求等不盲目重試。
4. 同一操作只由一層管理重試。等待、URL 策略與外層流程不能疊加成 4 × 4 次執行。
5. 操作成功後才把新資料加入結果。失敗嘗試不先追加資料；重試後仍依項目識別值去重。
6. 點擊等會改變頁面的操作，重試前先確認目前狀態；若前次已生效，不再重複點擊。不對未知副作用的整個流程直接重跑。
7. 耗盡後回報明確錯誤及原因鏈，不以空結果表示成功；部分爬取結果如何回傳仍留待既有待定事項處理。

**完成條件：**測試證明總執行次數最多四次、永久性錯誤只執行一次，且重試不產生重複結果或重複頁面動作。

## 預計檔案

`interaction.py`、`test_interaction.py`、本機 HTML fixtures、Chrome 整合測試與相關文件。

## 測試方式

使用假時鐘／driver 測邊界，並以真實 Chrome 加載本機動態 HTML，驗證存在、可見、可點擊、stale、暫時遮擋與逾時；重試成功不重複執行已生效動作。

瀏覽器操作有變更時，假物件測試不能替代實際測試。整合測試使用明確 opt-in 開關，實作時記錄命令、環境與結果；無法執行須明列原因，不標記該項完成。

## 驗收條件

- [x] 條件等待有 timeout，不混用 implicit wait 或固定 sleep 判定頁面就緒。
- [x] 暫時失敗最多四次，永久錯誤不重試，無巢狀倍增。
- [x] 等待與重試的原因、操作、定位及預算可查閱，失敗不變成空結果。
- [x] 條件等待與有限重試的實際 Chrome 測試通過，成功／失敗均檢查程序清理。

## 工作一完成時的結果（歷史紀錄）

### 本次完成的檔案與行為

| 檔案 | 變更 |
|---|---|
| `src/google_map_crawler/interaction.py` | 實作單次元素／自訂條件等待、fresh locator、implicit wait 0 檢查、單一截止時間及錯誤轉換 |
| `src/google_map_crawler/exceptions.py`、`__init__.py` | 新增並匯出 `PageWaitError`，`PageLoadTimeoutError` 沿用名稱並繼承此類，保留診斷欄位與原因鏈 |
| `src/google_map_crawler/validation.py`、`browser.py` | 共用正數 timeout 驗證，BrowserConfig 既有接受／拒絕行為維持一致 |
| `tests/unit/test_interaction.py` | 新增 48 項離線測試：條件差異、重新定位、時間預算、參數、永久錯誤及原始回呼錯誤 |
| `tests/unit/test_import_safety.py` | 隔離程序驗證 interaction 匯入與無效參數不載入 Selenium、不連線及不啟動程序 |
| `tests/fixtures/wait_states.html`、`tests/integration/test_interaction.py` | 本機動態 HTML 與 6 項實際 Chrome 測試，每條路徑確認自有 Chrome／driver 程序退出 |
| `README.md`、`spec.md`、`implementation.md`、`agent.md` | 介面、可選欄位範例、限制及部分完成狀態 |

### 驗證命令與結果

於 `google-map-crawler/` 執行：

```powershell
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/unit/test_interaction.py tests/unit/test_browser.py tests/unit/test_import_safety.py
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

結果：第一輪定向測試 **99 passed**；完整離線回歸 **408 passed、15 skipped**，約 2 秒。跳過的是需明確 opt-in 的整合測試，不列為離線通過。

```powershell
$env:GOOGLE_MAP_CRAWLER_RUN_BROWSER_TESTS = "1"
.venv\Scripts\python.exe -X utf8 -m pytest -q -s -p no:cacheprovider tests/integration/test_interaction.py
.venv\Scripts\python.exe -X utf8 -m pytest -q -s -p no:cacheprovider tests/integration/test_browser_session.py tests/integration/test_urls.py
Remove-Item Env:GOOGLE_MAP_CRAWLER_RUN_BROWSER_TESTS
```

結果：新增測試 **6 passed**（23.44 秒）；既有本機瀏覽器／URL 回歸 **7 passed**（27.20 秒）。本次共 13 項整合測試通過，沒有失敗結果；公開 Maps 2 項沒有重跑，不宣稱本次驗證通過。

Chrome 實測確認：

- hidden 元素可被 presence 找到，但 visibility 等待逾時，顯示後才成功。
- disabled 按鈕可見但不符合 clickable，啟用後才成功。
- 被遮擋的可見且啟用按鈕仍符合 clickable；自訂條件確認遮擋消失後，由測試端點擊一次，工具本身未執行點擊。
- 真實 DOM 在定位後替換，visible／clickable 等待會重新尋找新元素。測試以包裝 finder 安排競態，實際使用 Chrome WebElement 與 stale 例外，不以假 driver 代替。
- 必要資料就緒前逾時會報錯；確認容器資料已就緒後，缺少可選電話可使用 None。
- 不合法 CSS selector 立即失敗；持續 stale 仍以同一截止時間結束。
- 正常與例外路徑均確認自有 ChromeDriver 已退出、Chrome PID 已退出且無清理錯誤。

實測環境：Windows、Python **3.14.7**、Selenium **4.54.0**、Chrome **158.0.8127.36**、ChromeDriver **158.0.8127.88**。`git diff --check` 無空白錯誤；本次未新增相依性。

### 工作一當時的限制與待實作

- 此次只完成工作一，不包含操作重試、點擊重試、去重或捲動，Step 9 整體不標記完成。
- 狀態輪詢不算操作重試，也不讀取 max_retries；預設 10 秒 timeout 可由呼叫端明確使用 BrowserConfig.wait_timeout 傳入。
- timeout 不保證硬中斷 WebDriver 命令或使用者回呼；回呼須及時返回且無副作用。
- 回傳元素只代表該次檢查符合條件，後續重繪仍可能使元素失效。可選欄位判定須依呼叫端已確認的頁面資料就緒狀態。
- 診斷保存目標等待條件及最後一次缺少／stale 例外，不在錯誤處理中額外讀取 DOM 或 URL。
- 沒有把 Step 8 的 URL 私有等待改用新工具，原有共用預算及策略維持不變。

技術依據：[Selenium 等待策略](https://www.selenium.dev/documentation/webdriver/waits/)、[WebDriverWait](https://www.selenium.dev/selenium/docs/api/py/selenium_webdriver_support/selenium.webdriver.support.wait.html)、[元素條件定義](https://www.selenium.dev/selenium/docs/api/py/selenium_webdriver_support/selenium.webdriver.support.expected_conditions.html)。

## 工作二完成結果與最終驗收

### 實際變更

| 檔案 | 結果 |
|---|---|
| `src/google_map_crawler/interaction.py` | 泛用 retry_operation、具狀態查核的 click_with_retry、單一時間／次數預算、復原回呼及明確錯誤分類 |
| `src/google_map_crawler/_control.py` | ContextVar 控制範圍，防止等待／重試／短網址策略巢狀倍增；例外退出亦重設範圍 |
| `src/google_map_crawler/urls.py` | 短網址展開新增控制層級檢查；獨立呼叫的 HTTP／Chrome 策略及原預算不變 |
| `src/google_map_crawler/exceptions.py`、`__init__.py` | 新增並公開 OperationRetryError、OperationRetryTimeoutError 與重試診斷欄位 |
| `tests/unit/test_retry.py` | 新增 62 項測試，涵蓋 0–3 次重試、falsy 成功值、錯誤分類、共用期限、查核／復原失敗、點擊與控制層級、成功後收集資料 |
| `tests/unit/test_import_safety.py` | 隔離程序確認匯入、無效輸入與成功的純 retry action 不載入 Selenium、不連線或啟動程序 |
| `tests/integration/test_interaction.py` | 新增 6 項有限重試 Chrome 測試，沿用本機 fixture；與既有 6 項等待測試合計 12 項 |
| `README.md`、`spec.md`、`implementation.md`、`agent.md` | 完整重試契約、範例、限制與 Step 9 完成狀態 |

### 最終命令與結果

```powershell
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

結果：**470 passed、21 skipped**（2.77 秒）。新增有限重試測試 62 項，既有條件等待與 URL 等離線測試均通過。第一輪定向驗證曾為 220 passed；補上未知網路點擊結果及雙向控制層級測試後，最終採完整回歸數字。

```powershell
$env:GOOGLE_MAP_CRAWLER_RUN_BROWSER_TESTS = "1"
.venv\Scripts\python.exe -X utf8 -m pytest -q -s -p no:cacheprovider tests/integration
Remove-Item Env:GOOGLE_MAP_CRAWLER_RUN_BROWSER_TESTS
```

結果：**19 passed、2 skipped**（74.05 秒）。19 項為本機條件等待／有限重試 12 項、既有 BrowserSession 2 項與 HTTP／URL 5 項；2 項公開 Maps 測試本次未啟用，不算通過。

新增實際 Chrome 驗證：

1. 遮擋造成實際 ElementClickInterceptedException，recover 等待遮擋解除後重試，最終只產生一次 click 事件。
2. click 前替換真實 DOM，使原 WebElement 發生 stale，下一次重新定位成功，只有一次有效事件。
3. 實際 click 已生效後注入回應逾時，查核目標狀態後直接成功；再次呼叫亦不重點，事件數維持一次。
4. 實際 click 後注入回應錯誤及查核失敗，立即以 verification_failed 結束，不重點。
5. 持續遮擋在 max_retries=1 下共兩次嘗試耗盡，保留實際攔截原因，沒有 click 事件。
6. click 已成功但完成條件一直不成立，使用同一時間預算逾時，事件數仍為一次。

上述注入只模擬回應／查核錯誤；click、DOM、元素狀態及事件均由真實 Chrome 執行。所有 Chrome 成功及例外路徑均確認自有 ChromeDriver 與 Chrome PID 已退出，無清理錯誤。

```powershell
.venv\Scripts\python.exe -m build
git diff --check
```

結果：隔離建置成功產生 sdist／wheel，均包含 interaction.py 及 _control.py；diff 無空白錯誤。本次驗證未發生測試／建置失敗。環境：Windows、Python 3.14.7、Selenium 4.54.0、Chrome 158.0.8127.36、ChromeDriver 158.0.8127.88，建置 setuptools 84.2.1。

### 最終限制

- action 必須可安全重做，只有成功回傳後才由呼叫端加入集合並依識別值去重；不回復任意回呼已造成的外部修改。不在本步建立批次爬取或部分結果回傳規則。
- click 完成狀態由呼叫端定義；查核必須只讀且能辨識預期結果。未知結果與查核失敗選擇停止，由呼叫端處理。
- 呼叫端須將剩餘時間傳給等待／復原操作。底層命令與回呼仍無法保證被硬中斷。
- 控制範圍僅防止本套件同步介面的巢狀呼叫，無法監控呼叫端自行撰寫的迴圈、其他執行緒或第三方重試器。
- Step 10–12 尚未實作，階段三不標記完成；公開 Maps 相容性本次未另行實測。

技術依據：[Selenium 例外定義](https://www.selenium.dev/selenium/docs/api/py/selenium_common/selenium.common.exceptions.html)、[W3C WebDriver Element Click 工作草案](https://www.w3.org/TR/webdriver2/#element-click)。

部分結果回傳、零筆評論摘要等既有待定事項不在此步擅自定案。
