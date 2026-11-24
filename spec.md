# Google Map Crawler

## 1. 套件定位與專案位置

以 `temple-crawler` 為基礎，製作可安裝的 Python library，供其他 Python 專案獨立呼叫。

- 新專案放在獨立的 `google-map-crawler/` 資料夾，本規格存放於該資料夾的 `spec.md`。
- 新 library 的程式碼、套件設定、測試與文件皆放在 `google-map-crawler/` 內。
- `temple-crawler` 作為既有功能參考來源，不直接覆寫原有爬蟲腳本。
- 不依賴 MongoDB、原專案工作目錄或固定設定檔。
- 匯入套件時不啟動瀏覽器。
- 正常結束或發生例外時，皆須釋放瀏覽器資源。
- 圖片僅回傳 URL，不下載圖片檔案。

## 2. 地點識別碼與 URL

### location_id

- `location_id` 為地點紀錄第一次建立時隨機產生的 UUID v4 字串，不由名稱、地址、座標或 Google Maps 短網址推算。
- 已確認為同一地點的後續資料沿用既有 `location_id`；欄位修正、補齊或分享網址改變不重新產生 ID。
- 搜尋首次建立結果時配置 ID；後續擷取詳細資料時傳入該 ID，維持同次流程的關聯。
- 若新資料與資料庫既有紀錄比對成功，改沿用既有紀錄的 ID，並使該地點的搜尋結果、詳細資料、評論及標籤使用同一 ID。
- 套件本身不讀寫資料庫；既有紀錄由呼叫端提供給比對流程，跨次執行的 ID 保存與對應由呼叫端負責。

### 地點相同比對（初版）

以資料庫既有的 `PlaceDetail` 為基準，比對新取得的 `PlaceDetail`：

1. 取既有紀錄中所有有資料的地點欄位；`location_id` 與 `fetched_at` 為識別及擷取中繼資料，不參與比對。
2. 「沒有資料」指欄位不存在、`None`、空字串（含僅有空白的字串）或空清單；數值 `0` 仍視為有資料。
3. 對每個基準欄位比較新舊值；新資料缺少該欄位、值為空或值不同，均計為一個不同欄位。
4. 不同欄位數 **不超過 2 個（含 0、1、2）**，即依初版規則判為同一地點，允許少量欄位修正；超過 2 個則不符合。
5. 既有紀錄沒有資料、而新資料補上的欄位不參與本次差異計數；新模型新增且既有紀錄不存在的欄位也不影響本次判斷。

- 每個欄位最多計一次差異；清單以整個欄位比較，初版採值與順序皆相同才視為相同。
- 除上述空值判定外，初版採欄位值直接比較，不額外做名稱、地址正規化或座標容差判斷。
- `maps_url`、`rating`、`photos` 等只要在既有紀錄中有資料，也依相同規則計入，不另行豁免。
- 比對有方向性，以既有紀錄為基準；新資料補上欄位後，若由呼叫端保存，該欄位會成為下一次比對的基準欄位。
- 若多筆既有紀錄同時符合（差異不超過 2 個），優先選擇差異欄位數量最少的一筆，沿用其 `location_id`。
- 若最少差異數仍有多筆並列，拋出 `AmbiguousPlaceMatchError`，交由呼叫端處理；不能以候選順序任選一筆。
- 差異超過 2 個的紀錄不參與優先選擇；若無符合紀錄，保留新資料的 ID。
- 搜尋列表資料不完整，不直接套用完整 `PlaceDetail` 的比對規則；跨紀錄的地點判定在取得詳細資料後進行。

例：既有資料的名稱、地址等欄位有值，新資料只修正電話與網站，差異為 2，視為同一地點；若又改變名稱，差異為 3，則不符合。若既有資料沒有營業時間，而新資料補上營業時間，該新增資料不增加差異數。

### 比對與 ID 套用介面

| 方法 | 行為 | 回傳 |
|---|---|---|
| `compare_places(existing, incoming)` | 以一筆既有紀錄為基準，比較新詳細資料 | `PlaceComparison` |
| `find_place_match(incoming, candidates)` | 完整檢查候選，從差異不超過兩欄者中選出差異唯一最少的一筆 | `PlaceComparison \| None` |
| `rebind_location_id(record, location_id)` | 將已確認的 ID 套用到模型副本，原始物件不變 | 與輸入相同具體型別的模型 |

- `incoming` 必須是 `PlaceDetail`，不能只提供 `PlaceSearchResult`。
- `existing` 接受 `PlaceDetail` 或使用相同欄位名稱的 mapping；`candidates` 是這些紀錄的 iterable，包含只能讀取一次的 iterable。
- 既有紀錄須有合法 UUID v4 `location_id`，但可缺少其他地點欄位。只比較目前 `PlaceDetail` 宣告的地點欄位，忽略 `_id` 等資料庫額外資訊，不先建立完整模型或補值。
- 非空欄位須符合模型型別，評分須符合現有範圍與精度限制；不合法輸入回報 `InvalidInputError` 或其子類，不跳過候選或轉成不符合結果。
- `PlaceComparison` 是不可變的結果，保存 `existing_location_id`、`compared_fields`、`different_fields`；欄位名稱以 tuple 保存，差異順序依 `PlaceDetail` 宣告順序。
- `difference_count` 由 `different_fields` 的長度計算，`is_match` 為 `difference_count <= 2`。結果不保留可變的原始紀錄參照。
- `find_place_match()` 不會修改或另產生地點 ID；沒有符合候選回傳 `None`，由呼叫端保留新資料 ID。最低差異並列時拋出 `AmbiguousPlaceMatchError`，其 `matches` 屬性包含並列最佳結果的 tuple。
- 必須讀完全部候選才回傳或判定歧義；重複候選不自行去重。不以候選順序、欄位覆蓋率或權重決定結果。
- `rebind_location_id()` 支援五種資料模型，驗證目標 ID，保留時間、非 ID 欄位與順序，即使 ID 相同也回傳副本。
- 摘要須先複製並更新各則評論與標籤，再建立使用目標 ID 的摘要。副本的模型與清單不與原資料共用可變內容；失敗不修改原資料。
- 比對及 ID 套用皆不讀寫資料庫，不自動儲存或合併欄位。呼叫端確認比對結果後，才明確套用 ID。

### 未來可改善或測試的條件

此為初版啟發式規則，尚未驗證辨識準確率。尤其既有資料僅有 2 個以內的有效比對欄位時，即使全部不同仍會符合規則，可能造成誤合併；目前不額外加入最低欄位數限制，保留後續測試及改善。

後續應測試欄位稀少、同名不同地點、同址多個場所、改名、搬遷、欄位缺漏與多候選符合等情境，並評估最低有效欄位數、必要相同欄位、欄位權重、文字正規化、座標距離及 Plus Code 等條件。分享網址、評分、照片 URL 與清單順序變動對差異計數的影響也須驗證。

### URL 處理

- `maps_url` 保存實際取得、可開啟地點的 Google Maps URL，與 `location_id` 分開處理。
- 保留 `expand_short_url(url)`，展開短網址並回傳重新導向後的完整 URL。
- 移除 `location_id_to_url()` 與 `extract_location_id()`；隨機 ID 無法直接轉換成 Maps URL。
- 地點詳細資料及評論透過 URL 定位；僅提供內部 ID 而沒有 URL 時，呼叫端須先從既有資料查得 URL。
- 同次搜尋須追蹤已處理的結果與來源連結，避免捲動或重試重複配置 ID；不同分享網址不能單獨作為不同地點的證據。

### URL 驗證與展開介面

- `validate_maps_url(url)` 位於 `google_map_crawler.urls`，離線檢查格式，成功時回傳原字串。
- `expand_short_url(url, *, timeout=30, max_redirects=10, max_retries=3, browser_fallback=True)` 從模組及套件根目錄提供；完整 URL 驗證後直接回傳，短網址先處理 HTTP 重新導向，需要時才啟動受管理瀏覽器。
- 支援 HTTP／HTTPS 的 `maps.app.goo.gl/<token>`、`goo.gl/maps/<token>`，及 `google.com`、`www.google.com` 的 `/maps/…`。`maps.google.com` 另支援根路徑的位置查詢；`/maps` 根路徑須帶有 q、query、cid、ll、saddr 或 daddr 等非空位置參數。
- 不接受帳密、非預設連接埠、反斜線、原始空白／控制字元、格式錯誤的主機與百分比編碼；國別網域與其他分享服務不在初版支援範圍。合法 URL 的 query、fragment、定位資訊及字串表示不被重寫；國際文字僅於 HTTP 傳輸時編碼，回傳仍保留來源表示。HTTP Location 未指定 fragment 時沿用原值，明確指定時依新值處理。
- timeout 為有限正數，max_redirects 為非負整數，max_retries 為 0–3 整數，browser_fallback 為布林值；數值不接受布林值，所有參數在 I/O 前驗證。
- HTTP／瀏覽器策略共用最多四次嘗試與 monotonic 剩餘時間；切換瀏覽器占一次。HTTP 重新導向另受跨嘗試累積的 max_redirects 限制，不算成重試。max_retries=0 時只有一次 HTTP 策略機會。
- 各 HTTP 請求與頁面等待使用剩餘時間，操作返回後亦檢查截止時間。底層 DNS、瀏覽器啟動與清理無法保證被此預算硬中斷，不能視為嚴格 wall-clock timeout；瀏覽器內部跳轉以時間預算約束，不假稱全部計入 HTTP 跳轉次數。
- 僅暫時性連線失敗、操作逾時及 429、500、502、503、504 等 HTTP 狀態可在剩餘時間內重試；格式錯誤、確認失效、存取受阻、迴圈或不支援的導向不重試。
- HTTP 404／410 或瀏覽器明確失效頁回報 `PlaceNotFoundError`；HTTP 401／403、已知 consent／登入／驗證 URL 回報 `PageAccessBlockedError`；逾時回報 `UrlExpansionTimeoutError`（繼承 `UrlExpansionError`），其他展開失敗保留原因鏈。
- response 與瀏覽器 session 於成功或例外時皆關閉；不下載圖片、不變更 location_id。URL 可回傳不代表此工具已解析完整地點資料，頁面樣本的定位結果另列實測紀錄。

## 3. 公開功能

| 方法 | 功能 | 回傳 |
|---|---|---|
| `search_places(keyword, max_places=50)` | 搜尋 Google Maps 地點列表 | `PlaceSearchResult` 序列 |
| `get_place_detail(maps_url, location_id=None, max_photos=20)` | 依 URL 擷取地點詳細資料；有傳入 ID 時沿用，否則首次建立時隨機產生 | `PlaceDetail` |
| `get_reviews(maps_url, location_id, max_reviews=100, max_photos=20)` | 依 URL 擷取評論摘要、評論及各則評論附圖，關聯至傳入的 ID | `ReviewSummary` |

搜尋列表只擷取列表可取得的資料，不自動為每筆結果補齊詳細資料。

建議流程為搜尋取得 URL 與 ID → 取得詳細資料 → 由呼叫端與既有紀錄比對並決定沿用的 ID → 使用確定的 ID 擷取評論。單獨擷取評論時，呼叫端亦須提供對應地點的 ID 與 URL。

`PlaceDetail.photos` 表示地點頁面的照片；`Review.photos` 表示該則評論附圖，兩者分別擷取。

`max_photos` 預設為 **20**，可由呼叫端調整：在 `get_place_detail()` 中限制該地點的照片數，在 `get_reviews()` 中限制每則評論的附圖數。設為 `0` 時不擷取照片，其他資料仍正常回傳。

評論依實際抓取順序回傳，去重後保留首次取得的順序，不另外依評分或發表時間排序。

### 瀏覽器設定與生命週期

- 從 `google_map_crawler.browser` 使用 `BrowserConfig`、`BrowserSession`，不在套件根目錄匯出瀏覽器操作介面。
- `BrowserConfig` 使用具名參數且不可變：`headless=True`、`language="zh-TW"`、`page_load_timeout=30`、`wait_timeout=10`、`max_retries=3`、`no_progress_limit=3`、`max_scroll_rounds=100`。
- timeout 必須為有限正數，捲動相關計數須為正整數，重試次數為 0–3 的整數；數值不接受布林值，headless 必須為布林值，語言須為非空字串。重試及捲動設定的操作行為留待相應工具實作。
- `BrowserSession(config=None, driver_factory=None)` 建構時只保存有效設定，進入 `with` 才啟動 Chrome，在區塊內回傳 driver。套用 page load timeout 並將 implicit wait 設為 0。
- 預設使用 Selenium 4 的 Chrome driver 與獨立使用者設定檔，Windows Service 隱藏啟動；匯入、設定及 session 建構不執行 Selenium Manager 或下載 driver。
- 測試工廠介面為 `driver_factory(config)`，必須建立新 driver。回傳後的 driver 與其 `service` 由 session 管理；工廠尚未回傳即失敗時，內部未交接資源由工廠負責。預設建立流程會先保留 Service，確保建構 driver 中途失敗仍能清理已知資源。
- session 為單次使用，拒絕重入及關閉後重開；`close()` 可重複呼叫，已清理後不重複執行。
- 正常或失敗時均先嘗試 `quit()`，再嘗試停止自有 Service。清理失敗保留於 `session.cleanup_errors` tuple；若有原始操作錯誤，保留該錯誤並附上清理失敗註記，不以清理錯誤覆蓋。
- 啟動／初始設定失敗清理後拋出 `BrowserStartError` 並保留原因鏈；只有清理失敗時拋出 `BrowserCleanupError`，其 `errors` tuple 保存原始錯誤。中斷與退出訊號不轉成一般啟動錯誤。
- URL 工具使用 `UrlExpansionError`（含子類 `UrlExpansionTimeoutError`）及 `PageAccessBlockedError` 區分展開失敗、逾時與登入／驗證要求；瀏覽器 session 的啟動與清理錯誤保留原有分類。
- 若 driver 與 Service 清理皆失敗，明確回報而不宣稱資源已退出；不猜測或終止其他使用者程序。

## 4. 資料結構與預設值

所有清單欄位均須建立獨立的空清單，避免不同物件共用可變預設值。

`fetched_at` 採用含時區的 UTC `datetime`；轉成 JSON 時使用 ISO 8601 字串。

### PlaceDetail

| 中文 | 英文欄位 | 型別 | 無資料時 |
|---|---|---|---|
| 地點識別碼 | `location_id` | `str` | 必填 |
| 名稱 | `name` | `str \| None` | `None` |
| 類型 | `category` | `str \| None` | `None` |
| 地址 | `address` | `str \| None` | `None` |
| Maps URL | `maps_url` | `str` | 必填 |
| 擷取時間 | `fetched_at` | `datetime` | 擷取時產生 |
| 評價等級 | `rating` | `float \| None` | `None` |
| 消費等級 | `price_level` | `str \| None` | `None` |
| 網站 | `website` | `str \| None` | `None` |
| 電話 | `phone` | `str \| None` | `None` |
| 營業時間 | `opening_hours` | `list[str]` | `[]` |
| 照片列表 | `photos` | `list[str]` | `[]` |

- `maps_url` 回傳實際取得的地點 URL，不由 `location_id` 組成，也不要求同一地點每次取得的 URL 完全相同。
- `rating` 範圍為 0–5，精度至小數一位；未知時不以 `0` 代替。
- `price_level` 保留原始文字，例如 `200–400 元`。
- `opening_hours` 保留畫面上的日期、時段與休息資訊，不在第一版轉換成排程模型。

### PlaceSearchResult

| 中文 | 英文欄位 | 型別 | 無資料時 |
|---|---|---|---|
| 地點識別碼 | `location_id` | `str` | 必填 |
| 名稱 | `name` | `str \| None` | `None` |
| 類型 | `category` | `str \| None` | `None` |
| 地址 | `address` | `str \| None` | `None` |
| Maps URL | `maps_url` | `str` | 必填 |
| 擷取時間 | `fetched_at` | `datetime` | 擷取時產生 |
| 評價等級 | `rating` | `float \| None` | `None` |

### ReviewSummary

| 中文 | 英文欄位 | 型別 | 無資料時 |
|---|---|---|---|
| 地點識別碼 | `location_id` | `str` | 必填 |
| 平均評分 | `average_rating` | `float \| None` | `None` |
| 評論總數 | `total_count` | `int \| None` | 未知為 `None`，確認無評論為 `0` |
| 標籤 | `tags` | `list[ReviewTag]` | `[]` |
| 已擷取評論 | `reviews` | `list[Review]` | `[]` |
| 擷取時間 | `fetched_at` | `datetime` | 擷取時產生 |

`total_count` 為 Google Maps 顯示的總數，本次取得數量以 `len(reviews)` 計算。

### Review

| 中文 | 英文欄位 | 型別 | 無資料時 |
|---|---|---|---|
| 作者 | `author` | `str \| None` | `None` |
| 作者資訊 | `author_info` | `str \| None` | `None` |
| 評分 | `rating` | `int \| None` | `None` |
| 內容 | `content` | `str \| None` | `None` |
| 相片 | `photos` | `list[str]` | `[]` |
| 擷取時間 | `fetched_at` | `datetime` | 擷取時產生 |
| 地點識別碼 | `location_id` | `str` | 必填 |

沒有文字或相片的純評分評論，仍可作為有效評論回傳。

### ReviewTag

| 中文 | 英文欄位 | 型別 | 無資料時 |
|---|---|---|---|
| 標籤文字 | `text` | `str \| None` | `None` |
| 數量 | `count` | `int \| None` | `None` |
| 擷取時間 | `fetched_at` | `datetime` | 擷取時產生 |
| 地點識別碼 | `location_id` | `str` | 必填 |

## 5. 無資料與失敗的區別

- 可選欄位不存在：使用欄位預設值。
- 搜尋無結果：回傳空序列。
- 地點沒有評論：回傳空的 `ReviewSummary`，`total_count=0`。
- 必要識別資訊無法取得：回報錯誤，不回傳無法定位的結果。
- 無效識別碼、失效連結、載入逾時、解析失敗：以明確例外區分。
- 不得將載入失敗當作「沒有評論」或「沒有相片」。

## 6. 執行邊界

- 地點最大回傳數量預設 **50**。
- 評論最大回傳數量預設 **100**。
- 地點照片及每則評論附圖的最大回傳數量預設各為 **20**，可透過 `max_photos` 調整。
- 數量參數接受非負整數；`0` 回傳空結果，負數拒絕。
- 數量限制只作用於對應的資料集合；例如 `max_photos=0` 僅使 `photos=[]`，不省略地點或評論本身。
- 最大數量是上限，不保證一定取得指定筆數。
- 每個可重試操作最多重試 **3 次**，即初次執行加上重試最多 **4 次**。
- 僅對暫時性錯誤重試；無效輸入不重試。
- 頁面同步使用條件等待，不以固定 `time.sleep()` 判斷載入完成。
- 條件等待仍須設定 timeout，避免無限等待。
- 捲動需設定「連續無新增內容」的終止條件。
- 操作重試不得重複加入已取得的結果。

部分結果的回傳方式尚未指定，保留待後續討論。

## 7. 相對於 temple-crawler 的功能分類

### 原本已有，需要保留與重構

| 功能 | 現有位置 | 重構工作 |
|---|---|---|
| 關鍵字搜尋 | `main.py` | 抽成公開搜尋介面 |
| 搜尋列表捲動 | `main.py`、`modules/search.py` | 改善去重與終止條件 |
| 地點名稱、類型、地址、電話、網站 | `crawler/detail.py` | 修復錯誤並轉成資料模型 |
| 取得分享網址 | `crawler/detail.py` | 驗證網址形式，串接識別碼處理 |
| 地點擷取時間 | `crawler/detail.py` | 改用含時區的時間 |
| 平均評分、評論總數、標籤 | `crawler/comment.py` | 統一解析與預設值 |
| 作者、作者資訊、評分、評論文字 | `crawler/comment.py` | 改善缺漏欄位與去重處理 |
| 長評論展開與評論捲動 | `crawler/comment.py` | 加入有限重試與無進展終止 |
| 元素等待 | `modules/element.py` | 統一存在、可見、可操作等條件 |

以上現有位置均相對於 `temple-crawler` 根目錄。

### 原本沒有，需要新增

| 功能 | 新增內容 |
|---|---|
| 可安裝的 Python library | 套件結構、相依性、公開 API |
| 實例化瀏覽器管理 | 移除全域 driver，統一啟動與釋放 |
| `location_id` 機制 | 首次建立時隨機配置 UUID v4，比對成功後沿用既有 ID |
| 地點相同比對 | 以既有 `PlaceDetail` 有資料的欄位為基準，允許最多 2 個欄位不同，新補欄位不計差異 |
| URL 工具 | `expand_short_url()`，地點 URL 與內部 ID 分離 |
| 透過 URL 擷取並關聯 ID | 以 URL 定位詳細資料及評論，沿用呼叫端提供的 `location_id` |
| 獨立搜尋結果模型 | 從列表取得 `PlaceSearchResult` |
| 地點頁評價等級 | 不依賴評論擷取即可取得評分 |
| 消費等級、營業時間 | 新增選擇器與解析 |
| 地點照片、評論附圖 | 新增圖片 URL 擷取 |
| 五種資料模型 | `PlaceDetail`、`PlaceSearchResult`、`ReviewSummary`、`Review`、`ReviewTag` 的型別、預設值及序列化 |
| 評論與標籤的擷取時間、地點關聯 | 補上 `fetched_at`、`location_id` |
| 統一例外與重試策略 | 區分無資料、暫時性失敗與解析錯誤 |
| 套件測試與文件 | 離線測試、受控實測、安裝及使用範例 |

## 8. 資料回傳

- 各爬取介面直接 `return` 第 3 節定義的資料模型或序列。
- 回傳資料保留巢狀模型、清單順序、照片 URL 與 `location_id` 關聯。
- 套件不提供 dump 介面，不寫入 JSON 檔案或 MongoDB。
- 後續序列化、寫檔及資料庫儲存由呼叫端自行處理。
