# 驗收報告：2026 遊戲熱度觀察（2026-10-19）

全部測試：`python -m unittest discover -s tests` → 88 個測試全部通過（Edge，1440×900 與 375×812 觸控）。

## 1. SPEC §12 驗收條件

| # | 條件 | 結果 | 依據 |
|---|---|---|---|
| 1 | 內嵌數據與 `site_data.json` 完全一致 | ✅ | `Acceptance.test_embedded_matches_site_data`、`Inject.test_inject_idempotent` |
| 2 | Top 10 與六房 Top 5 與 build 輸出一致；每款遊戲只在一間房 | ✅ | `Acceptance.test_each_game_in_one_room`、`Plan.test_plan_shows_all_rooms_in_order`、`Hud.test_tab_hold_shows_scoreboard`；對照見第 2 節 |
| 3 | 數字旁有口徑、時間、平台徽章；沒有用 0 代替缺值 | ✅ | `Plan.test_every_number_has_context`、`Plan.test_no_nan_or_null_text`、`Build.test_missing_now_is_null` |
| 4 | 梗都標「（轉述）」；頁面沒有佔位字樣 | ✅ | `Plan.test_memes_marked_paraphrase`、`Lint.test_placeholders`、`Real.test_real_copy_is_clean_and_complete` |
| 5 | 只用鍵盤就能走完、進出、翻卡、叫出計分板 | ✅ | `Input.test_keyboard_walk_and_open`、`Input.test_enter_opens_immediately`、`Input.test_first_tab_reaches_skip_link`、`Hud.test_tab_hold_shows_scoreboard` |
| 6 | 手機用滑動、長按完成同樣的事；計分板圖示可開關 | ✅ | `Input.test_swipe_and_long_press_mobile`、`Hud.test_mobile_toggle`、`Acceptance.test_touch_targets`、`Acceptance.test_hint_matches_device` |
| 7 | reduced-motion 預設開導覽圖、沒有過場 | ✅ | `Acceptance.test_reduced_motion_defaults_to_plan` |
| 8 | §7.10 的 4 種網址直達；返回等於轉身 | ✅ | `Acceptance.test_all_hash_states`、`Scene.test_turn_back_and_history`、`Skeleton.test_invalid_hash_falls_back` |
| 9 | 網路請求只有 `index.html`；主控台沒有錯誤 | ✅ | `Skeleton.test_loads_offline_without_errors`、`Acceptance.test_screenshots`（`errors == []`） |
| 10 | 截圖逐張看過：沒有重疊溢出、手機沒有橫捲 | ✅（修正後） | `Acceptance.test_no_horizontal_scroll_mobile`；逐張結論見第 6 節 |

## 2. 排名與 SPEC 試算表的差異

`build_data.py` 重算（月度 2026/01～2026/09，當下人數 2026/10/19 16:28）：

- **Top 10** 與 §4.3 完全一致：要塞英雄（Fortnite）285.9 萬、絕對武力 2 153.7 萬、PUBG 85.2 萬、Dota 2 84.1 萬、TBH 33.6 萬、Apex 英雄 26.2 萬、殺戮尖塔 2 23.5 萬、幻獸帕魯 22.7 萬、GTA V 21.6 萬、Rust 20.3 萬。
- **六房 Top 5** 與 §6.2.1 完全一致。
- 不影響排名的差異：
  - 「無月度數據」多了 NBA 2K27（4356430），因為抓取當天它新進前 100 名。
  - 前 100 名的增減：多了 4356430、526870，少了 39210、216150。
  - 頁面上的名稱改用 `name_fix` 的中文顯示名。例如 CS2 顯示為「絕對武力 2」，Fortnite 顯示為「要塞英雄」。

## 3. 抓取來源（`fetch_log.json`，2026-10-19 16:39）

- 六個來源全部成功：steam_ccu、enriched、steamcharts、fortnitegg_1y、fortnitegg_now、rolimons。
- 個別遊戲在 Steamcharts 回 404 或 500，因此歸到「無月度數據」：3393110、1422450、4623570、4080220、4891320、3219030、5166840、4356430。
- 沒有遇到 Cloudflare 驗證頁。

## 4. 規格書沒寫到、實作時自行決定的地方

1. Fortnite 的「當下」與「24 小時峰值」用對戰中（in-match）人數，而不是線上人數。這樣和排名用的年度日資料口徑一致，對應 SPEC §3.1 的「對戰峰值」。
2. WARDOGS 沒有玩家標籤，官方類型會判成模擬，所以人工分到射擊，並列在公開的人工修正清單。
3. 20 款遊戲改用中文顯示名（`name_fix`），讓名稱和規格表一致。
4. 導覽圖額外顯示 `copy.json` 的 spectator_note、pain_title、pain_question、vote.note，對應 SPEC §7.8 要求的說明文字。
5. 3D 鏡頭模型重寫：視點在 z=900，轉向時旋轉 ±90° 對準門。規格只要求門牌看得到、走廊能走。
6. 房間主題只套用在 Top 5 物件上。黑馬卡與無月度數據卡維持一般樣式。
7. 開門推進的 0.6 秒內按 Esc 也會退出。
8. 手機的擊殺訊息放在右上角，收成一排可以橫向捲動的單行訊息，以免蓋住下半部的滑動區。桌機縮窄寬度，避開大標題。
9. 計分板改成不透明底；桌機另外加暗色背板。
10. 翻開卡片時，同排的其他卡片留在原位（`align-items:start`），不會被推到畫面外。
11. 第一次進站的操作提示依裝置顯示：觸控裝置顯示滑動與長按的說法，桌機顯示鍵盤說法。
12. 房間主題用了材質色：紙（#d9cfb6、#d6c39a、靶紙 ink）、木頭（#4a3524、#4a3422）、地圖桌（#2a2620、#3a332a）。這些不是新的主色，但嚴格來說不在五色之內，請確認是否接受（SPEC §8.1 寫「只換物件形狀與材質，不加主色」）。

## 5. 文案查證

| 原句 | 結論 | 來源 |
|---|---|---|
| CS2：2025 年 10 月更新開放用飾品合成刀具與手套 | 保留 | https://en.wikipedia.org/wiki/Counter-Strike_2 |
| CS2：trade-up 改動「曾引發飾品市場大震盪」 | 刪除（查不到可靠來源） | — |
| ARC Raiders：部分角色語音使用文字轉語音，引發爭議 | 保留 | https://en.wikipedia.org/wiki/Arc_Raiders |
| 梗內的手寫數字（「玩了 3000 小時」「花 3 小時」） | 改寫成「幾千小時」「一下午」，仍標（轉述） | — |

頁面上已經沒有任何「⚠️請核對」字樣（`Real.test_real_copy_is_clean_and_complete`）。

## 6. 截圖逐張檢查（`screenshots/`）

| 截圖 | 結論 |
|---|---|
| spawn-desktop | 大標題、資料時間、擊殺訊息（右上，縮窄後不壓到標題）、小地圖、操作提示，沒有重疊 |
| spawn-mobile | 標題縮成 48px；擊殺訊息一排在右上；下半部留給滑動；提示是觸控說法 |
| scoreboard-desktop | 不透明面板，Top 10 加上 Roblox「口徑不同，不參與排名」與觀戰者列 |
| room-shooter-desktop / mobile | 靶紙主題；靶心移到卡片上方，不再壓到遊戲名稱；黑馬區與卡片之間有間距 |
| room-shooter_game-730-desktop / mobile | 翻開 CS2 卡，其他四張留在原位 |
| room-strategy-desktop / mobile | 地圖桌網格，金色頂邊，文字清楚 |
| room-sim-desktop / mobile | 儀表板弧形，指針比例正確 |
| room-casual-desktop / mobile | 便利貼略微傾斜，標籤清楚 |
| room-rpg-desktop / mobile | 委託單與圖釘，深色文字對比足夠 |
| room-action-desktop / mobile | 通緝令，「#N 號通緝」「賞金」字樣置中 |
| view-plan-desktop / mobile | 六房、計分板、觀戰席、塗鴉牆、規則牆依序排列。手機整頁截圖在 Playwright 行動模擬下會重複拼接，改用 4 張捲動截圖（plan-scroll-0～3-mobile）確認：沒有重複、沒有溢出，長網址會斷行 |

手機版的「轉身」和「計分板」是固定按鈕，會蓋住捲動中的卡片內容。房間底部留了 96px，捲到底時內容可以完全露出。
