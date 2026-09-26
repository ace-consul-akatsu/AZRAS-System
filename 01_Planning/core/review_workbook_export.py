from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from xml.etree.ElementTree import Element, SubElement, tostring
from datetime import datetime
import re

_NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def _col_letter(n: int) -> str:
    out = ""
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def _cell(row, col, value, style=0):
    c = SubElement(row, "c", {"r": f"{_col_letter(col)}{row.attrib['r']}", "s": str(style)})
    if value is None:
        return c
    if isinstance(value, bool):
        c.set("t", "b"); SubElement(c, "v").text = "1" if value else "0"; return c
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        SubElement(c, "v").text = str(value); return c
    c.set("t", "inlineStr")
    isel = SubElement(c, "is")
    t = SubElement(isel, "t")
    s = str(value)
    if s[:1].isspace() or s[-1:].isspace():
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    t.text = s
    return c


def _worksheet_xml(rows, widths, freeze_rows=2, auto_filter=True):
    ws = Element("worksheet", {"xmlns": _NS_MAIN})
    views = SubElement(ws, "sheetViews")
    view = SubElement(views, "sheetView", {"workbookViewId": "0"})
    if freeze_rows:
        SubElement(view, "pane", {"ySplit": str(freeze_rows), "topLeftCell": f"A{freeze_rows+1}", "activePane": "bottomLeft", "state": "frozen"})
    SubElement(ws, "sheetFormatPr", {"defaultRowHeight": "18"})
    cols = SubElement(ws, "cols")
    for i, w in enumerate(widths, 1):
        SubElement(cols, "col", {"min": str(i), "max": str(i), "width": str(w), "customWidth": "1"})
    data = SubElement(ws, "sheetData")
    for ridx, values in enumerate(rows, 1):
        attrs = {"r": str(ridx)}
        if ridx == 1: attrs["ht"] = "28"; attrs["customHeight"] = "1"
        elif ridx == 2: attrs["ht"] = "35"; attrs["customHeight"] = "1"
        row = SubElement(data, "row", attrs)
        for cidx, value in enumerate(values, 1):
            first = str(values[0]) if values else ""
            if ridx == 1:
                style = 1
            elif ridx == 2:
                style = 2
            elif first.startswith("ユーザー／設計者 追加項目入力欄") or first.startswith("User / Designer Additional Item Entry"):
                # PATCH_578: lower user-added section is separated by wording/spacing, not cell fill colors.
                style = 4
                attrs["ht"] = "24"; attrs["customHeight"] = "1"
            elif first in ("追加ID", "Additional ID"):
                # Plain, bold section header. Keep the entire lower entry area white like the approved sample workbook.
                style = 5
                attrs["ht"] = "35"; attrs["customHeight"] = "1"
            else:
                style = 3
            _cell(row, cidx, value, style)
    if auto_filter and len(rows) >= 2:
        SubElement(ws, "autoFilter", {"ref": f"A2:{_col_letter(max(len(r) for r in rows))}{len(rows)}"})
    return b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' + tostring(ws, encoding="utf-8")


def _styles_xml():
    # Four simple styles: normal, title, header, wrapped body.
    return b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="5">
    <font><sz val="10"/><name val="Aptos"/></font>
    <font><b/><sz val="14"/><color rgb="FFFFFFFF"/><name val="Aptos"/></font>
    <font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Aptos"/></font>
    <font><b/><sz val="11"/><color rgb="FF000000"/><name val="Aptos"/></font>
    <font><b/><sz val="10"/><color rgb="FF000000"/><name val="Aptos"/></font>
  </fonts>
  <fills count="4">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF1F4E78"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF5B9BD5"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="2">
    <border><left/><right/><top/><bottom/><diagonal/></border>
    <border><left style="thin"><color rgb="FFD9E1F2"/></left><right style="thin"><color rgb="FFD9E1F2"/></right><top style="thin"><color rgb="FFD9E1F2"/></top><bottom style="thin"><color rgb="FFD9E1F2"/></bottom><diagonal/></border>
  </borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="6">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"><alignment vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="2" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"><alignment vertical="top" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="3" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1"><alignment vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="4" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
  </cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>'''



def _ja_review_text(value):
    if value is None:
        return ""
    text = str(value)
    pairs = (
        ("User/designer confirmation is required.", "ユーザー／設計者確認が必要です。"),
        ("Designer confirmation is required.", "設計者確認が必要です。"),
        ("The final decision is based on evidence, not voting.", "最終判断は多数決ではなく、図面・仕様・根拠に基づいて行います。"),
        ("Both numeric AI answers rely on the same non-drawing provisional intensity.", "複数AIの数値回答はいずれも、図面確定値ではない同一の暫定原単位に依存しています。"),
        ("Structural drawing not provided; replace with verified quantity.", "構造図が未提示です。確認済み数量へ置き換えてください。"),
        ("The cited drawing does not support this quantity.", "引用図面ではこの数量を裏付けられません。"),
        ("This value must not be promoted to confirmed.", "この値を確定値へ格上げしてはいけません。"),
        ("No drawing evidence was found.", "図面根拠を確認できませんでした。"),
        ("Insufficient drawing evidence.", "図面根拠が不足しています。"),
        ("Conflicting information exists in the drawings.", "図面内に矛盾する情報があります。"),
        ("Multiple AI results disagree.", "複数AIの結果が一致していません。"),
        ("provisional value requires review", "暫定値のため確認が必要"),
        ("designer-approved general framing", "設計者承認の一般的な枠組仕様"),
        ("reinforcement schedule/bar list", "配筋表・鉄筋リスト"),
        ("foundation reinforcement details", "基礎配筋詳細"),
        ("slab reinforcement details", "スラブ配筋詳細"),
        ("anchorage and lap requirements", "定着・継手条件"),
        ("reinforcement plan", "配筋図"),
        ("bar diameters", "鉄筋径"),
        ("bar spacing", "鉄筋間隔"),
        ("member schedule", "部材表"),
        ("structural drawing", "構造図"),
        ("architectural drawing", "意匠図"),
        ("MEP drawing", "設備図"),
        ("drawing set", "図面一式"),
        ("drawing evidence", "図面根拠"),
        ("drawing proof", "図面根拠"),
        ("drawing facts", "図面確認事項"),
        ("checked sources", "確認済み資料"),
        ("missing inputs", "不足資料"),
        ("calculation basis", "算定根拠"),
        ("calculation ledger", "計算過程"),
        ("source file", "参照ファイル"),
        ("source page", "参照ページ"),
        ("drawing number", "図番"),
        ("drawing name", "図面名"),
        ("current AZRAS value", "現在のAZRAS値"),
        ("evidence status", "根拠状態"),
        ("requires confirmation", "確認が必要"),
        ("unresolved aspects", "未解決事項"),
        ("resolution attempted", "解決確認実施済み"),
        ("not supported by the cited drawing", "引用図面では裏付けられていません"),
        ("same non-drawing provisional intensity", "同一の図面外暫定原単位"),
        ("not provided", "未提示"),
        ("not found", "未確認"),
        ("not confirmed", "未確定"),
        ("not applicable", "該当なし"),
        ("provisional", "暫定"),
        ("estimated", "想定"),
        ("confirmed", "確定"),
        ("conflicting", "矛盾"),
        ("unresolved", "未解決"),
        ("unknown", "不明"),
        ("conflict", "矛盾"),
        ("current PDF", "現在PDF"),
        ("registered PDF", "登録PDF"),
        ("specification", "仕様"),
        ("quantity", "数量"),
        ("structure", "構造"),
        ("architecture", "意匠"),
        ("reinforcement", "鉄筋"),
        ("foundation", "基礎"),
        ("slab", "スラブ"),
        ("wall", "壁"),
        ("floor", "床"),
        ("roof", "屋根"),
        ("opening", "開口"),
        ("beam", "梁"),
        ("column", "柱"),
        ("drawing", "図面"),
        ("evidence", "根拠"),
        ("source", "参照元"),
        ("verify", "確認"),
        ("review", "確認"),
        ("final", "最終"),
    )
    for en, ja in pairs:
        text = re.sub(re.escape(en), ja, text, flags=re.I)
    text = re.sub(r"\s*;\s*", "／", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


def _localize_review_rows_ja(review_rows):
    out = []
    # Preserve IDs/keys, filename, numeric/unit fields, and the user's own instruction text.
    keep_raw = {0, 4, 5, 9, 10, 16, 18, 19, 20, 21}
    for row in review_rows:
        vals = list(row)
        for idx, val in enumerate(vals):
            if idx in keep_raw:
                continue
            if isinstance(val, str):
                vals[idx] = _ja_review_text(val)
        out.append(vals)
    return out

def write_review_workbook(path: str | Path, review_rows: list[list], language: str = "ja") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ja = str(language).lower().startswith("ja")
    if ja:
        title = "AZRAS 図面解析 ― 不明事項／図面矛盾 確認・指示リスト"
        headers = ["問題ID","問題区分","工種／カテゴリ","項目／数量名","Canonical Key / local_id","図面ファイル","シート／ページ／図番","図面位置／詳細","指摘したAI","現在のAZRAS値","単位","根拠状態","AIによる問題要約","図面から確認できた事実","不明点／矛盾点","ユーザー／設計者への質問","ユーザー／設計者の指示","判断状態","承認値","承認単位","指示者","指示日","ChatGPT最終処理","最終データ状態","備考／トレーサビリティ","回答1項目","回答1値","回答1単位","回答2項目","回答2値","回答2単位","回答3項目","回答3値","回答3単位"]
        instructions = [
            ["AZRAS 図面解析 確認・指示Excel 運用フロー", "", "", ""],
            ["手順","担当","作業","出力／ルール"],
            [1,"複数AI","図面と数量をそれぞれ独立して解析する。","不明点や図面矛盾を隠さず記録する。"],
            [2,"ChatGPT","各AI結果を統合し、このExcelへ「不明」「図面矛盾」に加え、ソフト／AI双方で数量行が欠落したAZRAS必須工種を下段へ抽出する。","AIだけで設計判断を確定しない。"],
            [3,"ユーザー／設計者","複数回答が必要な問題は、右側の『回答1～3』の各独立欄へ入力する。単一回答問題は回答1を使用する。","同じExcelを意匠・構造・設備等の設計者へ照会資料として送付できる。"],
            [4,"ユーザー／設計者","回答済みExcelを保存してChatGPTへ返送する。","ファイル先頭に回答日時 YYMMDD_HHMM_ を付け、名称に「（回答）」を含める。"],
            [5,"ChatGPT","回答内容だけをHUMAN_REVIEW_FINAL JSONへ変換する。","AI推定を人間回答として偽装しない。"],
            [6,"Planning","HUMAN_REVIEW_FINAL JSONを「正式JSON取込」で読み込む。","人間判断を設計パラメータとして保存し、関連数量を再計算する。"],
            [7,"Planning / ChatGPT","反映結果とトレーサビリティを保存する。","未回答項目は未解決のまま保持する。"],
            [8,"言語運用","AZRASに正式言語が追加された時点で、このExcelも同じ言語版を用意する。","English Canonicalを内部基準とする。"],
        ]
        lists = [["問題区分","根拠状態","判断状態","最終データ状態"],["不明","確定","指示待ち","未反映"],["必須工種・数量未登録","想定／暫定","設計者確認","反映準備完了"],["図面矛盾","想定／暫定","設計者確認","反映準備完了"],["","矛盾","ユーザー承認","最終データ反映済み"],["","未解決","却下","保留"]]
    else:
        title = "AZRAS Drawing Analysis — Unknown / Drawing Conflict Review & Instruction List"
        headers = ["Issue ID","Issue type","Discipline / category","Item / quantity","Canonical Key / local_id","Drawing file","Sheet / page / drawing no.","Drawing location / detail","Reporting AI(s)","Current AZRAS value","Unit","Evidence status","AI issue summary","Facts confirmed from drawings","Unknown / conflict","Question to user / designer","User / designer instruction","Decision status","Approved value","Approved unit","Decision maker","Decision date","ChatGPT final action","Final data status","Notes / traceability","Answer 1 item","Answer 1 value","Answer 1 unit","Answer 2 item","Answer 2 value","Answer 2 unit","Answer 3 item","Answer 3 value","Answer 3 unit"]
        instructions = [
            ["AZRAS Drawing Review & Instruction Excel Workflow", "", "", ""],
            ["Step","Owner","Action","Output / rule"],
            [1,"Multiple AIs","Independently analyze the same drawings and quantities.","Record unknowns and drawing conflicts explicitly."],
            [2,"ChatGPT","Consolidate AI results and export Unknown / Drawing Conflict items plus mandatory AZRAS scopes missing from both software/AI quantity rows.","Do not invent a final design decision."],
            [3,"User / designer","Enter instructions in the User / designer instruction column.","The workbook can be sent directly to architecture/structure/MEP designers."],
            [4,"User / designer","Save the answered workbook and return it to ChatGPT.","Prefix the filename with YYMMDD_HHMM_ and include '(ANSWERED)'."],
            [5,"ChatGPT","Convert only explicit answers into HUMAN_REVIEW_FINAL JSON.","Do not turn AI inference into a human answer."],
            [6,"Planning","Import HUMAN_REVIEW_FINAL JSON using Import Final JSON.","Persist human decisions as design parameters and recalculate dependent quantities."],
            [7,"Planning / ChatGPT","Preserve results and traceability.","Unanswered issues remain unresolved."],
            [8,"Language","When an AZRAS UI language is formally added, provide this workbook in that language.","English Canonical remains the internal base."],
        ]
        lists = [["Issue type","Evidence status","Decision status","Final data status"],["Unknown","Confirmed","Awaiting instruction","Not applied"],["Mandatory scope / quantity missing","Estimated / provisional","Designer review","Ready to apply"],["Drawing conflict","Estimated / provisional","Designer review","Ready to apply"],["","Conflicting","User approved","Applied to final data"],["","Unresolved","Rejected","On hold"]]

    # PATCH_577 workbook instructions for free additional items.
    if ja:
        instructions += [
            ["追加項目入力","ユーザー／設計者","下段の追加項目欄では C=工種、D=項目名、Q=指示、S=追加承認値、T=単位、U=指示者、V=指定日、Y=備考を入力する。","A列のADD-IDは変更しない。Y列は自由記入可。"],
            ["価格連携","Planning / Cost Provider","承認数量・単位・工種を正式数量候補として保存し、Cost Keyが特定できるものは建設費へ接続する。","Cost Key未特定項目は0円にせず『単価未取得』として残す。"],
        ]
    else:
        instructions += [
            ["Additional item entry","User / designer","In the lower section enter C=category, D=item, Q=instruction, S=approved quantity, T=unit, U=decision maker, V=date, Y=notes.","Do not change the ADD-ID in column A. Column Y is free-entry."],
            ["Cost linkage","Planning / Cost Provider","Persist approved quantity/unit/category as a formal quantity candidate and link mapped Cost Keys to construction cost.","Unmapped Cost Keys remain Unit Cost Not Acquired; never silently price them at zero."],
        ]

    if ja:
        review_rows = _localize_review_rows_ja(review_rows)

    # PATCH_582: structured multi-answer fields are exported to Excel as explicit
    # answer slots.  Existing A:Y columns remain stable for backward compatibility.
    # Z:AH carry up to three independent answers; compound questions must never be
    # forced into the single legacy Approved value cell.
    expanded_rows = []
    for src in review_rows:
        r = list(src) + [""] * max(0, len(headers) - len(src))
        item = str(r[3] if len(r) > 3 else "")
        low = item.lower()
        if "外壁工法別" in item or "exterior wall" in low:
            r[18] = ""  # legacy single approved value intentionally unused
            r[19] = ""
            labels = (("RC外壁面積","RC exterior wall area"),("2×6外壁面積","2x6 exterior wall area"))
            r[25], r[27] = (labels[0][0] if ja else labels[0][1]), "m2"
            r[28], r[30] = (labels[1][0] if ja else labels[1][1]), "m2"
            # Make the question itself explicit about the two required answers.
            r[15] = ("① RC外壁面積、② 2×6外壁面積を、それぞれ別の回答欄へ入力してください。" if ja else
                     "Enter (1) RC exterior wall area and (2) 2x6 exterior wall area in their separate answer fields.")
        else:
            r[25] = "承認値" if ja else "Approved quantity"
            r[27] = str(r[10] or "")
        expanded_rows.append(r)
    review_rows = expanded_rows

    # PATCH_577: free user/designer-added scope section.  This is intentionally
    # separate from AZRAS/AI-detected issues so project-specific items (finishes,
    # special work, etc.) can be added without expanding a hard-coded scope list.
    # Columns C,D,Q,S,T,U,V,Y are user-editable; Y is explicitly a free notes field.
    add_title = (
        "ユーザー／設計者 追加項目入力欄（任意）― AZRAS・AIで拾えなかった項目を追加"
        if ja else
        "User / Designer Additional Item Entry (optional) — add scopes not captured by AZRAS / AI"
    )
    add_headers = (
        ["追加ID","問題区分（自動）","工種／カテゴリ","項目／数量名","Canonical Key / local_id（AZRAS自動）",
         "図面ファイル（任意）","シート／ページ／図番（任意）","図面位置／詳細（任意）","指摘したAI（自動）",
         "現在のAZRAS値（自動）","単位（既存値）","根拠状態（自動）","AIによる問題要約（自動）",
         "図面から確認できた事実（任意）","不明点／矛盾点（任意）","ユーザー／設計者への質問（自動）",
         "ユーザー／設計者の指示","判断状態（自動）","追加承認値","単位","指示者","指定日",
         "ChatGPT最終処理（自動）","最終データ状態（自動）","備考／トレーサビリティ（任意・入力可）",
         "回答1項目","回答1値","回答1単位","回答2項目","回答2値","回答2単位","回答3項目","回答3値","回答3単位"]
        if ja else
        ["Additional ID","Issue type (auto)","Discipline / category","Item / quantity","Canonical Key / local_id (AZRAS auto)",
         "Drawing file (optional)","Sheet / page / drawing no. (optional)","Drawing location / detail (optional)","Reporting AI (auto)",
         "Current AZRAS value (auto)","Existing unit","Evidence status (auto)","AI issue summary (auto)",
         "Facts confirmed from drawings (optional)","Unknown / conflict (optional)","Question to user / designer (auto)",
         "User / designer instruction","Decision status (auto)","Additional approved value","Unit","Decision maker","Decision date",
         "ChatGPT final action (auto)","Final data status (auto)","Notes / traceability (optional; editable)",
         "Answer 1 item","Answer 1 value","Answer 1 unit","Answer 2 item","Answer 2 value","Answer 2 unit","Answer 3 item","Answer 3 value","Answer 3 unit"]
    )
    add_rows=[]
    for i in range(1,31):
        r=[""]*len(headers)
        r[0]=f"ADD-{i:04d}"
        r[1]="ユーザー追加項目" if ja else "User-added item"
        r[17]="入力待ち" if ja else "Awaiting entry"
        r[22]="未処理" if ja else "Not processed"
        r[23]="未反映" if ja else "Not applied"
        add_rows.append(r)
    sheet1 = ([[title] + [""] * (len(headers)-1), headers] + review_rows +
              [[""]*len(headers), [add_title]+[""]*(len(headers)-1), add_headers] + add_rows)
    widths1 = [14,14,18,30,22,26,24,26,24,16,10,16,38,40,42,42,42,18,16,12,18,16,42,20,42,22,16,12,22,16,12,22,16,12]
    sheet2 = instructions
    widths2 = [10,20,62,78]
    sheet3 = lists
    widths3 = [22,24,24,26]

    content_types = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/worksheets/sheet3.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>'''
    root_rels = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'''
    workbook = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Review_List" sheetId="1" r:id="rId1"/><sheet name="Instructions" sheetId="2" r:id="rId2"/><sheet name="Lists" sheetId="3" r:id="rId3"/></sheets></workbook>'''
    workbook_rels = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet3.xml"/><Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'''

    with ZipFile(path, "w", ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        z.writestr("xl/styles.xml", _styles_xml())
        z.writestr("xl/worksheets/sheet1.xml", _worksheet_xml(sheet1, widths1, freeze_rows=2, auto_filter=True))
        z.writestr("xl/worksheets/sheet2.xml", _worksheet_xml(sheet2, widths2, freeze_rows=2, auto_filter=False))
        z.writestr("xl/worksheets/sheet3.xml", _worksheet_xml(sheet3, widths3, freeze_rows=1, auto_filter=False))
    return path


def write_human_review_audit_workbook(path: str | Path, rows: list[list], language: str = "ja") -> Path:
    """Write a compact one-sheet HUMAN_REVIEW audit workbook.

    PATCH_583: this workbook is generated automatically when AZRAS UI answers are
    formally applied.  It is an audit/history artifact only; it is not a user-input
    workflow and it never replaces the Project JSON current state.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    widths = [16, 20, 34, 14, 12, 46, 18, 16, 34]
    content_types = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>'''
    root_rels = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'''
    workbook = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Human_Review_Audit" sheetId="1" r:id="rId1"/></sheets></workbook>'''
    workbook_rels = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'''
    with ZipFile(path, "w", ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        z.writestr("xl/styles.xml", _styles_xml())
        z.writestr("xl/worksheets/sheet1.xml", _worksheet_xml(rows, widths, freeze_rows=2, auto_filter=True))
    return path
