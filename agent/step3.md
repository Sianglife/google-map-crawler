# Step 3：UUID 工具與輸入驗證

## 狀態與依據

- 狀態：已完成，2026-11-23（Asia/Taipei）。
- 所屬階段：階段一「套件骨架與資料契約」。
- 前置步驟：[Step 2](step2.md)。依據：[spec.md](../spec.md) 與 [implementation.md](../implementation.md)。

## 目標與範圍

提供可離線呼叫的 ID 產生、驗證及沿用工具，並讓數量與必填文字在進入後續瀏覽器流程前就能被驗證。

## 預計檔案異動

- `src/google_map_crawler/identity.py`。
- `src/google_map_crawler/validation.py`。
- `tests/unit/test_identity.py`、`tests/unit/test_validation.py`。
- `agent.md`、本文件。

## 執行順序

1. 提供 `create_location_id()`，產生 UUID v4 字串。
2. 提供 `validate_location_id(location_id)`，驗證字串可解析為 UUID v4，成功時保留原字串。
3. 提供 `resolve_location_id(location_id=None)`，僅在沒有提供 ID 時產生新值，提供無效 ID 時回報錯誤而非靜默重建。
4. 提供 `validate_count(value, *, name)`，接受非負整數，拒絕布林值、負數、浮點數及字串。
5. 提供 `validate_non_empty_string(value, *, name)`，驗證必填文字，成功時保留原始內容。
6. 測試錯誤分類、訊息及 ID 沿用；不實作地點比對或任何 URL 連線。

## 驗收條件

- [x] 新 ID 為 UUID v4；既有合法 ID 原樣沿用。
- [x] 非 UUID、其他 UUID 版本、錯誤型別與空 ID 回報明確例外。
- [x] `0` 與正整數通過；錯誤數量包含參數名稱。
- [x] 必填字串拒絕空值及只有空白的內容。
- [x] 所有測試離線執行。

## 待定事項

URL 形式驗證與短網址展開留待瀏覽器／URL 階段，不在本步假設支援網域清單。`max_reviews=0` 的摘要行為不在此步定案。

## 實際變更與驗證結果

已建立 `identity.py` 與 `validation.py`，包括五個公開工具；未加入比對或 URL 連線。執行 `.venv\Scripts\python.exe -m pytest -q tests/unit/test_identity.py tests/unit/test_validation.py`：28 項通過（Python 3.14.7）。測試確認既有 ID（含大寫表示）原樣保留，無效輸入不會觸發新的 ID 配置。
