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
- 若多筆既有紀錄同時符合，不任選其中一筆合併；回報比對歧義，交由呼叫端處理。
- 搜尋列表資料不完整，不直接套用完整 `PlaceDetail` 的比對規則；跨紀錄的地點判定在取得詳細資料後進行。

例：既有資料的名稱、地址等欄位有值，新資料只修正電話與網站，差異為 2，視為同一地點；若又改變名稱，差異為 3，則不符合。若既有資料沒有營業時間，而新資料補上營業時間，該新增資料不增加差異數。

### 未來可改善或測試的條件

此為初版啟發式規則，尚未驗證辨識準確率。尤其既有資料僅有 2 個以內的有效比對欄位時，即使全部不同仍會符合規則，可能造成誤合併；目前不額外加入最低欄位數限制，保留後續測試及改善。

後續應測試欄位稀少、同名不同地點、同址多個場所、改名、搬遷、欄位缺漏與多候選符合等情境，並評估最低有效欄位數、必要相同欄位、欄位權重、文字正規化、座標距離及 Plus Code 等條件。分享網址、評分、照片 URL 與清單順序變動對差異計數的影響也須驗證。

### URL 處理

- `maps_url` 保存實際取得、可開啟地點的 Google Maps URL，與 `location_id` 分開處理。
- 保留 `expand_short_url(url)`，展開短網址並回傳重新導向後的完整 URL。
- 移除 `location_id_to_url()` 與 `extract_location_id()`；隨機 ID 無法直接轉換成 Maps URL。
- 地點詳細資料及評論透過 URL 定位；僅提供內部 ID 而沒有 URL 時，呼叫端須先從既有資料查得 URL。
- 同次搜尋須追蹤已處理的結果與來源連結，避免捲動或重試重複配置 ID；不同分享網址不能單獨作為不同地點的證據。

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
