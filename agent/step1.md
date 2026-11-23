# Step 1：套件設定

## 狀態與依據

- 狀態：已完成。
- 完成日期：2026-11-23（Asia/Taipei）。
- 所屬階段：[implementation.md](../implementation.md) 的階段 1「套件骨架與資料契約」。
- 本步驟對應階段一生成計畫的第一步「套件設定」，不代表整個階段一已完成。
- 功能契約依 [spec.md](../spec.md)，步驟紀錄方式依 [agent.md](../agent.md)。

## 目標與範圍

建立可安裝、可建置、可從專案目錄外匯入的 Python 套件基礎，讓後續模型與工具可以逐步加入。

- 安裝名稱：`google-map-crawler`。
- 匯入名稱：`google_map_crawler`。
- 使用 `src/` 結構與 setuptools 建置後端，初始版本為 `0.1.0`。
- Python 版本要求設為 `>=3.11`；驗證紀錄只宣告實際測過的版本。
- 此步驟執行程式不需要第三方相依套件，開發工具使用 pytest 與 build。
- Selenium 相依性在瀏覽器階段加入。
- 本步驟僅建立套件設定與骨架；資料模型、例外、ID 工具、參數驗證及爬取介面由後續步驟實作。

## 預計檔案異動

| 檔案 | 用途 |
|---|---|
| `pyproject.toml` | 套件資訊、Python 版本要求、MIT 授權、建置設定與開發相依性 |
| `src/google_map_crawler/__init__.py` | 無外部副作用的套件入口，不匯出尚未完成的爬取介面 |
| `tests/unit/test_import_safety.py` | 在獨立程序與其他工作目錄驗證匯入，阻擋網路及外部程序啟動 |
| `examples/README.md` | 說明目前骨架狀態及後續範例安排 |
| `README.md` | 開發安裝、測試、建置方式與目前進度 |
| `implementation.md` | 更新已完成的骨架及套件設定項目 |
| `agent.md` | 步驟索引與每步存檔規則 |
| `agent/step1.md` | 本步驟計畫、執行結果與驗證紀錄 |

## 執行順序

1. 建立本計畫與步驟索引。
2. 建立 `pyproject.toml`，使用明確的 `src/` 套件搜尋範圍，測試採 importlib 匯入模式。
3. 建立套件入口、測試與範例目錄；不加入 `sys.path` 或 `PYTHONPATH` 修改。
4. 在專案內建立隔離虛擬環境，安裝開發相依性與 editable 套件。
5. 執行匯入安全測試，再建置 sdist 與 wheel。
6. 將 wheel 安裝至另一個乾淨虛擬環境，從專案目錄外驗證匯入與套件 metadata。
7. 更新 README、實作進度與本步驟驗證結果。

## 驗收條件

- [x] 開發環境可以 editable 安裝套件。
- [x] pytest 使用已安裝套件，不依賴手動調整匯入路徑。
- [x] 獨立程序匯入時不建立網路連線或啟動外部程序。
- [x] 可建置 sdist 與 wheel，且可由 sdist 建置 wheel。
- [x] wheel 可安裝至乾淨環境，並從專案目錄外匯入。
- [x] 安裝 metadata 保留正確名稱、版本、Python 要求與授權。
- [x] 實作進度及步驟索引只標記本步驟實際完成的部分。

## 待定事項與限制

- 整個階段一的模型、例外、ID 及驗證工具尚未包含在本步驟。
- `search_places(max_places=0)` 的實際呼叫行為須待搜尋介面實作後驗收。
- 部分結果回傳及零筆評論摘要等未定行為維持待定，不因套件設定而定案。
- 套件建置與安裝需要開發依賴可取得；測試本身不需要 Google Maps 或資料庫連線。

## 實際變更與驗證結果

### 實際變更

- 建立套件設定、無副作用的套件入口、獨立程序匯入測試及範例說明。
- 開發依賴使用 `dependency-groups.dev`，pytest 採 `importlib` 模式，未設定額外匯入路徑。
- README 補齊 PowerShell 環境建立、editable 安裝、測試及建置指令。
- `implementation.md` 僅標記階段一的目錄骨架與套件設定完成，模型等項目維持待實作。

### 驗證環境

- Windows，Python 3.14.7。
- pip 26.2.1、pytest 9.2.0、build 1.6.1；隔離建置使用 setuptools 84.2.1。
- Python 最低版本宣告為 3.11，但本步驟未執行其他 Python 版本的相容性測試。

### 執行結果

| 驗證 | 結果 |
|---|---|
| `.venv\Scripts\python.exe -m pip install -e . --group dev` | 成功建立 editable 安裝並安裝開發工具 |
| `.venv\Scripts\python.exe -m pytest -q` | `1 passed`；從其他目錄以獨立程序匯入，audit hook 阻擋網路與外部程序操作 |
| `.venv\Scripts\python.exe -m build` | 成功建立 sdist，並從 sdist 建立 wheel |
| 乾淨環境安裝 wheel | 使用 `build/wheel-check/` 虛擬環境及 `pip install --no-index --no-deps`，成功離線安裝 |
| 專案目錄外匯入 | 在專案父目錄以乾淨環境的 `python -I` 匯入成功，確認模組來源位於該環境的 `site-packages` |
| 安裝 metadata | 名稱 `google-map-crawler`、版本 `0.1.0`、Python 要求 `>=3.11`、授權 `MIT`、無執行時第三方依賴 |

本環境首次下載依賴受到 sandbox 網路限制，取得授權後完成；建置產物讀取亦曾受 sandbox 權限限制，取得授權後完成離線安裝。最終匯入驗證可在 sandbox 內成功執行，沒有待處理的驗證阻礙。

建置產物位於 `dist/`，開發環境位於 `.venv/`，乾淨驗證環境位於 `build/wheel-check/`；均符合既有 `.gitignore` 排除規則。

### 後續步驟

下一步為例外分類，應先建立 `agent/step2.md` 並更新步驟索引，再進行實作。整個階段一尚未完成。

上述為 Step 1 完成當時的狀態。後續已完成 Step 2–5，階段一目前狀態與驗證結果請見 [agent.md](../agent.md) 及 [step5.md](step5.md)。

### 設定參考

- [Python Packaging：pyproject.toml](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
- [setuptools：套件搜尋與 src 結構](https://setuptools.pypa.io/en/latest/userguide/package_discovery.html)
- [pytest：安裝與匯入模式](https://docs.pytest.org/en/stable/explanation/goodpractices.html)
