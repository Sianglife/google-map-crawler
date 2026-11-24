# 使用範例

`create_models.py` 使用示意資料建立地點、純評分評論、標籤與摘要，所有資料共用同一個 UUID v4。範例不連線 Google Maps、不啟動瀏覽器、不寫入檔案或資料庫，輸出至標準輸出，並非真實抓取結果。

在專案目錄完成開發安裝後執行：

```powershell
.venv\Scripts\python.exe -X utf8 examples/create_models.py
```

`to_dict()` 回傳 JSON 相容字典，時間為含 UTC 時區的 ISO 8601 字串。範例中的 `total_count=100` 表示顯示總數，`reviews` 則只示範一則實際取得的評論；兩者不要求相等。

搜尋、詳細資料及評論擷取的使用範例將於對應介面完成後加入。

## 地點比對與 ID 沿用

```powershell
.venv\Scripts\python.exe -X utf8 examples/match_places.py
```

`match_places.py` 使用虛構資料展示三種結果：

1. 兩筆候選都符合時，選出差異欄位較少的一筆，再分別為地點與評論摘要建立使用既有 ID 的副本。
2. 所有候選都超過兩欄差異時，回傳 `None`，保留新資料原 ID。
3. 最低差異數並列時，捕捉 `AmbiguousPlaceMatchError`，列出 `matches` 內的候選 ID 與差異欄位。

比對與 ID 套用分開執行，不會合併欄位。原始資料、時間與清單內容保留；範例只輸出至標準輸出，不連線或儲存。
