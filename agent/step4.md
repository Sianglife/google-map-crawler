# Step 4：資料模型與記憶體序列化

## 狀態與依據

- 狀態：已完成，2026-11-23（Asia/Taipei）。
- 所屬階段：階段一「套件骨架與資料契約」。
- 前置步驟：[Step 2](step2.md)、[Step 3](step3.md)。依據：[spec.md](../spec.md)。

## 目標與範圍

以標準函式庫 `dataclasses` 完成五種資料模型、預設值及建構時驗證，提供 `to_dict()` 回傳 JSON 相容字典，不提供寫檔或資料庫功能。

## 預計檔案異動

- `src/google_map_crawler/models.py`。
- `tests/unit/test_models.py`。
- `agent.md`、本文件。

## 執行順序

1. 所有模型以具名參數建構，明確要求 `location_id`；地點模型另外要求 `maps_url`。
2. 建立 `PlaceSearchResult`、`PlaceDetail`、`ReviewSummary`、`Review`、`ReviewTag`，欄位依規格逐一實作。
3. 可選資料預設 `None`，清單使用各自的 `default_factory`；明確傳入的清單也複製容器，避免不同物件共用容器。
4. `fetched_at` 在建立實例時產生 UTC 時間；傳入含時區時間時轉為 UTC，無時區或錯誤型別拒絕。
5. 驗證欄位型別、評分與數量；未知數值保留 `None`，不以零替代。地點評分遵守 0–5 與一位小數的規格。
6. 摘要中的評論及標籤須為對應模型，且與摘要使用相同 ID；不自動產生或覆寫子物件的 ID。
7. `to_dict()` 遞迴保留巢狀資料、空值、清單順序與原始文字，時間轉為 UTC ISO 8601 字串。
8. 測試預設值、容器獨立性、時間、錯誤輸入、純評分評論、關聯及序列化。

## 驗收條件

- [x] 五種模型的欄位及預設值符合規格。
- [x] 可選文字保留原始內容，不新增地點比對正規化行為。
- [x] 清單彼此獨立，含時區時間正規化為 UTC，無時區輸入被拒絕。
- [x] 純評分評論有效；未知評論總數與確認為零可區分。
- [x] 摘要與子資料的 ID 一致，錯誤關聯被拒絕。
- [x] 字典結果可由呼叫端交給 `json.dumps()`，且不修改原始模型。

## 待定事項與限制

建構時驗證不等於後續欄位賦值會自動驗證。模型維持可變，供後續地點 ID 關聯工具使用；不在此步實作比對或合併。評分等欄位只依已定規格施加限制，不新增尚未定義的比對條件。

## 實際變更與驗證結果

已完成五種模型，透過共用基底處理 ID、UTC 時間及 `to_dict()`，地點詳細資料共用搜尋結果的基本欄位。模型建立時驗證型別；地點評分限制 0–5 及最多一位小數，不靜默四捨五入。評論評分依規格驗證整數型別；總數與標籤數量驗證非負整數。

執行 `.venv\Scripts\python.exe -m pytest -q tests/unit/test_models.py`：81 項通過（Python 3.14.7），涵蓋五種模型的時間與 ID 驗證、非共用清單、原始文字、純評分評論、錯誤關聯及巢狀 JSON 相容字典。

URL 此時只驗證非空字串，支援網址形式及定位可用性留待階段三。建構完成後的欄位賦值不會自動重新驗證；關聯模型的物件本身仍由呼叫端管理，僅複製傳入清單的容器。這些限制會在 Step 5 使用文件說明。

實作時依 Python 3.11 官方文件核對 [dataclasses](https://docs.python.org/3.11/library/dataclasses.html)、[UUID](https://docs.python.org/3.11/library/uuid.html) 與 [datetime](https://docs.python.org/3.11/library/datetime.html) 的行為。Context7 工具未提供，故使用官方文件核對。
