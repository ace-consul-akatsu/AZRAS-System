PATCH 597

原因:
過去の HUMAN_REVIEW_FINAL 回答を永久に解決済みとして扱っていたため、最新 ChatGPT FINAL が RC/2x6 外壁面積を conflict として再提示しても、人間確認画面から質問が消えていました。

修正:
最新 FINAL が conflict/conflicting/unresolved を報告した項目は再び人間確認対象に戻します。過去回答は監査履歴として保持しますが、新しい矛盾を隠しません。RC外壁面積と2×6外壁面積は2つの独立回答欄を必須とします。
