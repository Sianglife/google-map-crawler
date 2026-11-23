# Step 2：共用例外與錯誤分類

## 狀態與依據

- 狀態：已完成，2026-11-23（Asia/Taipei）。
- 所屬階段：階段一「套件骨架與資料契約」。
- 依據：[spec.md](../spec.md)、[implementation.md](../implementation.md) 及 [agent.md](../agent.md)。

## 目標與範圍

建立可讓呼叫端分別捕捉輸入錯誤、定位失敗、載入逾時、解析失敗及比對歧義的例外。此步僅建立分類，不實作瀏覽器、重試或比對。

## 預計檔案異動

- `src/google_map_crawler/exceptions.py`：共用基底及明確例外。
- `agent.md`、本文件：索引、執行結果與狀態。

## 執行順序

1. 定義 `CrawlerError` 作為所有套件例外的基底。
2. 建立 `InvalidInputError`、其子類 `InvalidLocationIdError` 與 `InvalidMapsUrlError`。
3. 建立 `PlaceNotFoundError`、`PageLoadTimeoutError`、`ParseError`、`AmbiguousPlaceMatchError`。
4. 保留標準例外訊息及 `raise ... from ...` 的錯誤原因鏈，避免自訂不必要的建構介面。
5. 執行匯入與例外捕捉檢查；後續透過輸入驗證與模型測試實際驗證分類用途。

## 驗收條件

- [x] 可透過共用基底捕捉套件錯誤，也可針對 ID 等特定輸入錯誤分別處理。
- [x] 錯誤訊息與原因鏈可保留。
- [x] 匯入不啟動瀏覽器、不連線、不寫檔（功能行為；Python 可能產生一般的匯入快取）。

## 待定事項

不在此步決定重試政策或部分結果回傳行為；沿用規格與待定事項。

## 實際變更與驗證結果

已建立八種例外，使用單一繼承保留 Python 標準例外行為。以專案虛擬環境執行捕捉與原因鏈檢查：ID 錯誤可被 `InvalidInputError`／`CrawlerError` 捕捉，解析錯誤可保留原始 `ValueError`，檢查通過。完整匯入安全測試在 Step 5 再驗證整合後的套件入口。
