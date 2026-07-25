# EveDirector L6 完成與驗收報告

> **狀態註記**：本報告保留原文。其中「PR 狀態：Draft、未合併」一項已不再成立——L0–L6 已落到
> `main`，PR #11 關閉並註明落地位置。第 12 節的成片驗收數據仍然是現行的參考基準。
> 落地過程見 [`EVEDIRECTOR_L0-L6_HANDOFF_zh-TW.md`](EVEDIRECTOR_L0-L6_HANDOFF_zh-TW.md) 的狀態註記。

- 專案：OpenMontage / EveDirector
- 階段：L6 — Unified Infinite Canvas, Workflow and Timeline
- 分支：`evedirector-l6-unified-workbench`
- Pull Request：`#11`
- 基底分支：`evedirector-l5-constrained-editor`
- 最終提交：`316790deb466569ffa81c051a429aa965004e9e9`
- 狀態：Repository、Runtime、Authority、Regression 與 Render 合約完成
- PR 狀態：Draft、未合併、可合併

---

## 1. L6 的目標

L6 將同一份來源化 Project Graph 同時投影為：

```text
Infinite Canvas
＋
Workflow
＋
Timeline
＋
Inspector
```

這四個視圖不維護彼此獨立的專案資料，而是共享相同的 Scene Model。

核心流程：

```text
來源化候選 Run
→ 統一 Scene Model
→ Canvas／Workflow／Timeline／Inspector
→ L5 白名單 Operations
→ 新 Derived Run
→ L3 來源與政策驗證
→ L4 語義 Diff 與證據審查
→ 明確 Validate／Apply／Reject
```

---

## 2. 路由

```text
/p/<project-id>/director/<run-id>
GET /api/project/<project-id>/director/<run-id>
```

L6 Router 本身是唯讀的。

語義編輯仍送往既有 L5 端點：

```text
POST /api/project/<project-id>/agent-edit/<run-id>/derive
```

L6 不具有直接 Apply、直接修改正式規格或自動批准的端點。

---

## 3. 統一 Scene Model

API 會驗證下列四處的 Scene ID 與順序完全一致：

```text
model.scenes
views.canvas
views.workflow
views.timeline
```

不一致時直接失敗，不呈現互相矛盾的視圖。

每個 Scene 節點仍保留：

- Scene ID
- Cut type
- 時間範圍
- 變更狀態
- Markdown 來源行
- 來源摘錄
- Evidence Edge

---

## 4. Infinite Canvas

畫布支援：

- 背景平移
- 滾輪縮放
- Fit to content
- Reset layout
- 節點拖曳
- Source／Canonical／Candidate／Validation／Human Gate 節點
- Scene 節點
- Evidence 與 Workflow 邊

畫布位置僅儲存在瀏覽器：

```text
evedirector.canvas.<project-id>.<run-id>
```

拖動畫布節點：

- 不產生 L5 Operation
- 不修改 Candidate
- 不修改正式規格
- 不建立 Run
- 不寫入 Audit

因此「整理認知空間」與「修改影片作品」保持不同權限。

L6 仍不允許：

- 任意新增節點
- 任意新增邊
- 刪除 Scene
- 改寫 Scene ID
- 讓畫布布局進入正式影片規格

---

## 5. Workflow

Workflow 使用共享的 `working.scenes`。

在 L5 合約允許時，可透過明確的前移／後移控制調整順序。

結果會轉換為：

```json
{"op":"reorder_scenes","scene_ids":["scene-b","scene-a"]}
```

不允許：

- 遺漏 Scene
- 重複 Scene
- 新增或刪除 Scene
- 修改來源錨點
- 任意建立流程邊

---

## 6. Timeline

Timeline 與 Workflow 使用同一 Scene 陣列。

時長修改會轉換為：

```json
{"op":"set_scene_duration","scene_id":"scene-a","duration_seconds":8}
```

瀏覽器會重算連續時間軸預覽；伺服器仍重新執行 L5／L3 驗證。

使用者不直接編輯：

```text
in_seconds
out_seconds
```

這避免手動製造時間間隙或重疊。

---

## 7. Overlay Timeline Guard

現有 Overlay 使用絕對秒數，尚未具有 Scene Anchor。

當候選包含 Overlay 時：

- Workflow 排序停用
- Timeline 時長停用
- 前端顯示鎖定原因
- 伺服器拒絕偽造的結構性操作

仍可編輯：

- 專案標題
- Theme
- 場景旁白
- 白名單文字元件欄位

未來必須先建立正式的 Overlay→Scene Anchor 合約，才能安全解鎖結構性時間軸編輯。

---

## 8. Inspector

Inspector 僅公開 L5 Policy 白名單：

- Project title
- Theme
- Scene narration
- 允許的字串 Cut fields
- Scene ID 與來源錨點的唯讀資訊

不公開：

- 完整 Prompt
- 原始模型回覆
- Token
- 環境變數
- 任意 YAML 編輯
- Cut type 編輯
- Terminal steps 編輯
- Overlay 編輯
- Source anchor 編輯

---

## 9. Authority Flow

```text
Canvas layout
→ browser local storage only
→ 無語義權力

Semantic working model
→ L5 allow-listed Operations
→ BACKLOT_ENABLE_AGENT_ACTIONS=1
→ X-EveDirector-Action: review
→ Editor identity
→ EDIT <run-id>
→ 新 Derived Run
→ L3 validation
→ L4 evidence review
→ explicit Validate / Apply / Reject
```

L6 頁面不能直接套用正式規格。

---

## 10. 主要檔案

```text
backlot/director.py
backlot/ui/director.html
backlot/ui/director.css
backlot/ui/director.js
backlot/ui/agent-review-l5.js
tests/test_evedirector_unified_workbench.py
docs/EVEDIRECTOR_L6_UNIFIED_WORKBENCH.md
.github/workflows/evedirector-l6-unified-workbench.yml
```

並修改：

```text
backlot/__init__.py
.github/workflows/evedirector-l2-markdown-video.yml
```

---

## 11. 測試結果

最終 L6 診斷：

```text
46 passed, 13 warnings in 3.34s
```

十三個 Warning 為既有 FastAPI／Starlette 棄用提醒，不是 EveDirector 行為失敗。

通過項目：

- Python 模組編譯
- JavaScript 語法
- L3 Local Agent 回歸
- L4 Review Workbench 回歸
- L5 Constrained Editor 回歸
- L6 統一 Scene Identity
- Canvas／Workflow／Timeline 同步
- Source Evidence 保留
- Raw Response 私密資料不洩漏
- Canvas Layout 本機化
- L6 Write Endpoint 不存在
- L5 Derived Run 委派
- Canonical 在 Derive 階段保持不變
- Overlay Guard
- 權限標記
- 診斷 Artifact 上傳

第一次 L6 CI 的唯一失敗是測試期待 `overlay_count`，而 L5 Guard 原本只公開布林鎖定狀態。L6 後來加入純觀察用 `overlay_count`，沒有放寬權限；第二次及最終工作流均通過。

---

## 12. 最終成片驗收

```text
Codec：h264
解析度：1920x1080
幀率：30.0 FPS
時長：76.053333 秒
檔案大小：11,042,313 bytes
渲染時間：420.47 秒
警告：0
雲端 API Key：未使用
```

驗證結果：

- Remotion 渲染成功
- MP4 存在且非空
- FFprobe 找到可讀取的影片串流
- Render Report 生成成功
- 來源與 Grounding Manifest 保存
- 影片與稽核資料成功上傳

Final Artifact：

```text
Name：evedirector-l2-drc-search
Artifact ID：8614844209
Archive Size：8,031,919 bytes
SHA-256：ffe8042d642a2e40df5c5e89ec39fbba841eae6823aa7b6d782bcae608aefa64
```

---

## 13. 尚未宣稱完成的項目

尚未在使用者的 Windows 目標機實際完成：

- 真實瀏覽器拖曳與縮放煙霧測試
- LocalStorage Layout 重開瀏覽器後的目標機驗證
- 真實 Ollama／LM Studio 模型 Run
- 使用真實本地模型候選走完 Derived Run
- 目標機 Validate／Reject／Apply
- 目標機再次渲染

這些屬於安裝與本機交接，不是 Repository 合約缺失。

---

## 14. L6 階段邊界

L6 不包含：

- 任意圖譜作者工具
- 新增／刪除 Scene
- 任意新增邊
- Overlay 編輯器
- Overlay→Scene Anchor
- 音訊波形
- Keyframe 編輯器
- 多使用者協作
- 雲端授權
- 私人 MCP
- 遠端部署
- 直接正式規格寫入
- 自動批准

---

## 15. 完成判定

L6 已達成：

```text
同一 Project Graph
＋
無限畫布
＋
可編輯 Workflow
＋
可編輯 Timeline
＋
來源證據
＋
Derived Run
＋
人類最終權限
```

至此 EveDirector L0–L6 的本地優先實作已封閉，後續交由使用者與本地 Agent 接手。
