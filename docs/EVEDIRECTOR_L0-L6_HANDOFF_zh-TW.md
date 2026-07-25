# EveDirector L0–L6 本地接手交接手冊

> **狀態註記（已被 `main` 取代）**
>
> 本文件是 L0–L6 完成當時的交接紀錄，保留原文不改。其中第 1 節與第 14、15 節的分支指示
> **已經過時**：L0–L6 的 88 個 commit 已經以 fast-forward 落到 `main`，PR #1–#11 全部關閉並註明落地
> 位置，`evedirector-web-runtime` 分支的 4 個 hosted-runtime commit 也已 cherry-pick 上主線。
>
> 現在直接用 `main` 即可，不需要 checkout `evedirector-l6-unified-workbench`：
>
> ```powershell
> git clone https://github.com/kakon77777-commits/evedirector-web-runtime.git
> ```
>
> 另有兩項修正不在本文件內：`lib/`、`schemas/`、`tools/`、`scripts/` 的文字 I/O 全面補上
> `encoding="utf-8"`（原本在 CJK code page 的 Windows 上會讓 L2 build 直接失敗），以及所有階段
> workflow 的 push trigger 已改指向 `main`。第 3 節之後的驗收步驟本身仍然有效。
>
> 當前架構總覽見 [`README.md`](../README.md)。

## 1. 最終接手分支

最終分支已包含 L0–L6 的完整堆疊：

```text
evedirector-l6-unified-workbench
```

不要在本機逐一合併所有 Draft PR 才開始測試。直接取回最終分支即可：

```powershell
git fetch origin
git checkout evedirector-l6-unified-workbench
git pull origin evedirector-l6-unified-workbench
```

最終 Git 提交：

```text
316790deb466569ffa81c051a429aa965004e9e9
```

PR #11 保持 Draft、未合併，作為實作與驗收紀錄。

---

## 2. 階段總覽

| 階段 | 已完成內容 |
|---|---|
| L0／L1 | 本地環境診斷、Backlot、零密鑰驗證 |
| L2 | 真實 Markdown → Scene Plan → Remotion → MP4 |
| L3 | 本地模型候選、政策、來源錨定、Diff、審計 |
| L4 | 視覺審批工作台、Validate／Apply／Reject |
| L5 | 受約束 Project Graph／Workflow 編輯、Derived Run |
| L6 | 統一 Infinite Canvas＋Workflow＋Timeline＋Inspector |

---

## 3. 首次環境診斷

在 Repository 根目錄執行：

```powershell
.\scripts\evedirector-local-first.ps1 doctor
```

應檢查：

- Python 3.10+
- Node.js
- npm／npx
- FFmpeg／FFprobe
- OpenMontage Python 套件
- Remotion Composer
- Backlot
- 零密鑰示範素材

完整 L1 驗證：

```powershell
.\scripts\evedirector-local-first.ps1 all
```

---

## 4. L2 真實 Markdown 影片

驗證來源：

```powershell
python scripts\markdown_to_video.py --json validate
```

建立專案：

```powershell
python scripts\markdown_to_video.py --force build
```

渲染：

```powershell
python scripts\markdown_to_video.py --force render
```

預期輸出：

```text
projects/evedirector-drc-search/renders/drc-search.mp4
projects/evedirector-drc-search/artifacts/render_report.json
```

---

## 5. 啟動 Backlot

唯讀模式：

```powershell
python -m backlot serve --port 4750
```

允許受保護的 Agent／Editor 動作：

```powershell
$env:BACKLOT_ENABLE_AGENT_ACTIONS = "1"
python -m backlot serve --port 4750
```

只在本機綁定與測試，不要先開放公網。

---

## 6. L3 真實本地模型煙霧測試

參閱：

```text
docs/EVEDIRECTOR_L3_LOCAL_AGENT.md
```

Ollama 或 OpenAI-compatible 本機端點必須使用：

- `localhost`
- Loopback IP
- 私有網路 IP

不要把 API Key 貼到對話、GitHub 或命令紀錄中。

本地模型只能建立 Candidate Run，不能直接修改正式規格。

完成後應出現：

```text
projects/evedirector-drc-search/agent_runs/<run-id>/
```

至少包含：

```text
candidate.video_spec.yaml
candidate.diff
candidate.unified.diff
audit.json
```

---

## 7. L4 Review Workbench

開啟：

```text
http://127.0.0.1:4750/p/evedirector-drc-search/agent-review
```

檢查：

- Run 清單
- 語義 Diff
- 每個 Scene 的來源行與摘錄
- Project Graph
- Raw Response 未出現在 API
- Validate
- Reject
- Apply

寫入動作需要：

```text
X-EveDirector-Action: review
Reviewer
VALIDATE <run-id>
APPLY <run-id>
REJECT <run-id>
```

先用測試 Candidate 執行 Reject，再對可接受 Candidate 執行 Apply。

---

## 8. L5 Constrained Editor

從 Review Workbench 選擇 Run，開啟：

```text
OPEN CONSTRAINED EDITOR ↗
```

或：

```text
http://127.0.0.1:4750/p/evedirector-drc-search/agent-edit/<run-id>
```

驗證：

1. 修改標題。
2. 修改 Theme。
3. 修改旁白。
4. 修改允許的 Subtitle／Title／Text。
5. 確認 Scene ID 與來源查詢不可編輯。
6. 確認 Cut type、in/out、steps 不可編輯。
7. 建立 Derived Candidate。
8. 回到 L4 查看 Diff 與來源證據。
9. 確認 Parent Run 與 Canonical 在 Derive 時未修改。

DRC Search 含絕對時間 Overlay，因此排序與時長應被鎖住。

---

## 9. L6 Unified Workbench

從 Review Workbench 選擇 Run，開啟：

```text
OPEN UNIFIED WORKBENCH ↗
```

或：

```text
http://127.0.0.1:4750/p/evedirector-drc-search/director/<run-id>
```

### Canvas 煙霧測試

- 拖曳背景平移。
- 滾輪縮放。
- FIT。
- RESET LAYOUT。
- 拖曳節點。
- 重新整理頁面，確認布局仍存在。
- 修改節點布局後，不應增加 Semantic Operation 數量。

### 視圖同步

- 點選 Workflow Scene。
- Canvas 對應節點應選取。
- Timeline 對應 Clip 應選取。
- Inspector 應顯示相同 Scene。
- Scene ID 與來源證據必須一致。

### 語義編輯

- 修改 Project title。
- 修改 Scene narration。
- 修改一個允許的 Cut 文字欄位。
- 確認操作數量增加。
- 點擊 `CREATE DERIVED CANDIDATE`。
- 確認產生新 Run，不是修改舊 Run。
- 回到 L4 檢查 Diff。
- Validate／Reject／Apply。

### Overlay Guard

在 DRC Search：

- Workflow 順序控制應停用。
- Timeline 時長輸入應停用。
- 文字與旁白仍可編輯。
- 偽造排序／時長請求應由伺服器拒絕。

---

## 10. Apply 後重新渲染

Apply 可接受的 Derived Run 後：

```powershell
python scripts\markdown_to_video.py --force render
```

檢查：

```text
projects/evedirector-drc-search/artifacts/render_report.json
```

並用播放器觀看：

```text
projects/evedirector-drc-search/renders/drc-search.mp4
```

確認：

- 畫面完整
- 時間軸正確
- Overlay 沒有錯位
- FFprobe 通過
- Audit 與 Backup 存在

---

## 11. 本機接手驗收清單

```text
[ ] doctor 通過
[ ] L1 all 通過
[ ] L2 validate/build/render 通過
[ ] Backlot 唯讀開啟
[ ] Backlot 寫入閘門開啟
[ ] 真實本地模型建立 Candidate Run
[ ] L4 能查看 Diff 與來源
[ ] Reject 不修改 Canonical
[ ] Apply 產生 Backup 與 Audit
[ ] L5 編輯只建立 Derived Run
[ ] L6 Canvas 可平移、縮放、拖曳
[ ] Canvas Layout 重開後仍存在
[ ] Canvas Layout 不產生 Semantic Operation
[ ] Canvas／Workflow／Timeline／Inspector 同步
[ ] Overlay Guard 生效
[ ] Derived Run 通過 Validate／Apply
[ ] 最終 MP4 再渲染並 FFprobe
```

---

## 12. 現有安全邊界

保持不變：

- 模型不能直接改正式規格。
- 瀏覽器不能直接改正式規格。
- Candidate 必須通過來源錨定。
- 過期 Candidate 不可 Apply。
- Reviewer 身分不可空白。
- Apply 必須明確批准。
- Raw Prompt／Response 不進 Review API。
- Canvas Layout 不進語義規格。
- Overlay 未錨定前不能做結構性時間軸修改。
- 本地端點預設封鎖公網。

---

## 13. 後續不在 L0–L6 範圍

後續由本地端自行發展：

- Overlay→Scene Anchor
- Overlay Editor
- 新增／刪除 Scene
- 任意 Graph Node／Edge
- Audio Waveform
- Keyframe Editor
- Provider／素材／TTS API
- 多使用者
- 遠端部署
- 私人 MCP
- 成本與組織權限
- 正式產品 UX

不要透過簡單放寬白名單實作這些能力；每一項都應建立獨立資料模型、權限與回歸測試。

---

## 14. Draft PR 保留方式

目前各階段 PR 保持 Draft，作為分層實作歷史。

本機直接使用最終分支即可，不必先合併它們。

確認本機全部煙霧測試後，再由你自行決定：

- 保持分支
- Squash
- Rebase
- 建立正式產品分支
- 將 EveDirector 抽離成獨立 Repository

---

## 15. 最終交接點

```text
Branch:
evedirector-l6-unified-workbench

Commit:
316790deb466569ffa81c051a429aa965004e9e9

PR:
#11
```

Repository 驗收與零密鑰成片已完成。

剩餘工作只有你的 Windows 目標機安裝、真實本地模型、瀏覽器操作與後續產品化。
