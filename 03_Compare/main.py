from __future__ import annotations
import csv,math,re
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
# PATCH_003: measure legend label widths instead of assuming a fixed pitch.
from tkinter import font as tkfont
from comparison.extractor import extract_core_project,regional_projects,MONTHS_JA
# PATCH_005: comparison premise book (see comparison/premise_book.py).
from comparison import premise_book as PB
from comparison.premise_book_ui import PremiseBookTab
# PATCH_006: Japanese display names for English-canonical identifiers.
from comparison import display_ja as DJ
import json as _json
from pathlib import Path
PRODUCT='AZRAS Compare';COMPANY='ACE Comprehensive Consulting Co., Ltd.'
# PATCH_006: the on-screen version comes from VERSION.json (it was a stale
# hard-coded '1.1.17' while VERSION.json said 2.2.0).
def _read_version():
    try:
        return str(_json.loads((Path(__file__).resolve().parent/'VERSION.json').read_text(encoding='utf-8')).get('version') or '2.2.0')
    except Exception:
        return '2.2.0'
VERSION=_read_version()

LANGUAGE_ORDER=('en','ja')
LANG_LABELS={'en':'English','ja':'日本語'}
LANG_CODES={v:k for k,v in LANG_LABELS.items()}
CURRENT_UI_LANGUAGE='en'
MONTHS_EN=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
TEXT_EN={
    '1. 建物・JSON選択':'1. Building / JSON Selection',
    '2. 建物比較指標':'2. Building Comparison Metrics','3. 月間比較グラフ':'3. Monthly Comparison Graphs',
    '6. 世界地域別比較':'6. Global Regional Comparison',
        '比較表CSV保存':'Save Comparison CSV','新規':'New','表紙へ戻る':'Back to Start Screen',
    '建物比較を開く':'Open Building Comparison','異なる用途・間取り・規模・構造の建物を比較します':'Compare buildings with different uses, layouts, scales, and structures',
    '表紙と比較画面の言語設定は共通です':'The start screen and comparison view share one language setting',
    '比較するProject JSON（2～7建物）':'Project JSONs to Compare (2–7 buildings)',
    '選択':'Select','解除':'Clear','JSONを読み込み比較を作成':'Load JSONs and Create Comparison',
    '年間比較（建設関係イベントは含まない）':'Annual Comparison (excluding construction-related events)',
    '年間エネルギー消費量 kWh/年':'Annual Energy Consumption kWh/year',
    '年間CO₂排出量 t/年':'Annual CO₂ Emissions t/year',
    '電力CO₂係数 kg-CO₂/kWh':'Grid CO₂ Factor kg-CO₂/kWh',
    '3. 月間比較グラフ（1～12月）':'3. Monthly Comparison Graphs (Jan–Dec)',
    '指定地域：':'Region:','未読込':'Not loaded',
    '① 月間エネルギー（年間予測）':'① Monthly Energy (annual forecast)',
    '② 月間CO₂排出量（年間予測）':'② Monthly CO₂ Emissions (annual forecast)',
    '4. 200年間CO₂比較グラフ':'4. 200-Year CO₂ Comparison Graph',
    'CO₂表示年：':'CO₂ display year:','③ 200年間CO₂累積（建設関係イベント含む）':'③ 200-Year Cumulative CO₂ (including construction events)',
    '5. 200年間投資回収比較グラフ':'5. 200-Year Investment Recovery Graph',
    'CF表示年：':'CF display year:','④ 単純投資回収比較（初回回収の確認）':'④ Simple Payback Comparison (first recovery)',
    '⑤ 現在価値ベース回収比較（割引累積CF）':'⑤ Present-Value Recovery Comparison (discounted cumulative CF)',
    '比較未実行':'Comparison not run','工法':'Method','単位：':'Unit: ',
    '表示':'Show','任意年 1～200：':'Custom year 1–200:','言語':'Language',
    '計算済みデータがありません':'No calculated data is available',
    '±0（投資回収基準）':'±0 (investment recovery threshold)',
    '建物':'Building','単位':'Unit','未計算':'Not calculated','完了':'Complete','一部未計算':'Partially calculated','済':'Done',
    '2. 建物比較指標（絶対値＋床面積当たり）':'2. Building Comparison Metrics (absolute and per floor area)',
    '用途・間取り・規模・構造・所在地が異なる建物を、各Project JSONに保存された条件のまま比較できます。規模差による誤解を避けるため、総量とm²当たりを併記します。':'Buildings with different uses, layouts, scales, structures, and locations can be compared using each Project JSON exactly as saved. Totals and per-m² values are shown together to avoid misleading scale effects.',
    '注意：通貨が異なる建物が含まれています。金額の絶対比較・投資CF比較は為替換算なしでは行いません。環境・エネルギー・m²当たり指標は比較できます。':'Caution: Buildings with different currencies are included. Absolute cost and investment-CF comparisons are not performed without FX conversion. Environmental, energy, and per-m² metrics remain comparable.',
    '用途・規模・構造が異なる場合は、総量だけでなくm²当たり指標も併せて確認してください。':'When use, scale, or structure differs, review per-m² metrics as well as totals.',
    'この画面は各Projectの地域比較データを使い、同じ地域名の列で建物を横並びにする標準化比較です。主比較画面は各Project JSON固有の所在地・条件をそのまま使用します。':'This screen uses each Project regional-comparison dataset to place buildings side by side under matching region names. The main comparison screen uses each Project JSON own saved location and conditions.',
    '表示：年間エネルギー消費量 kWh/年':'Display: Annual Energy Consumption kWh/year',
    '算定根拠：各地域の8760時間解析結果の年間合計　｜　参照元：Project JSON → regional_analysis.module10_snapshot':'Basis: annual total of each region 8760-hour analysis | Source: Project JSON → regional_analysis.module10_snapshot',
    '電力CO₂係数整合監査：比較未実行':'Grid CO₂ factor consistency audit: comparison not run',
    '電力CO₂係数整合監査：OK　全地域で比較対象建物の地域係数が一致':'Grid CO₂ factor consistency audit: OK — regional factors match across compared buildings',
    '　指定地域：':'  Region:',
    '年間エネルギー消費量合計（kWh/年）':'Total annual energy consumption (kWh/year)',
    '年間運用CO₂排出量合計（t-CO₂/年）':'Total annual operational CO₂ emissions (t-CO₂/year)',
    '【ご注意】 ①月間エネルギー\n・同一EPW（8760時間）による年間エネルギー予測値です。\n・年間値は冷暖房・換気・給湯・照明等の合計（設備構成に依存）です。':'[Note] ① Monthly Energy\n• Annual energy forecast based on the same EPW (8,760 hours).\n• Annual values combine heating, cooling, ventilation, hot water, lighting, etc., depending on the equipment configuration.',
    '【ご注意】 ②月間CO₂排出量\n・各月の8760時間電力量 × 地域別電力CO₂係数から算定した運用CO₂です。\n・建設・更新・解体イベントCO₂は含みません。\n・同一地域では比較対象の各建物で同一の電力CO₂係数を使用します。':'[Note] ② Monthly CO₂ Emissions\n• Operational CO₂ is calculated from monthly 8,760-hour electricity use × regional grid CO₂ factor.\n• Construction, renewal, and demolition event CO₂ is excluded.\n• The same grid CO₂ factor is used for all compared buildings in the same region.',
    '【ご注意】 ③CO₂累積\n・同一EPW（8760時間）の運用値＋建設・更新・解体イベントCO₂を統合した年次累積です。\n・電力CO₂係数は地域別設定値を使用し、同一地域では比較対象の各建物で同一です。\n・税金（炭素税等）は含めていません。':'[Note] ③ Cumulative CO₂\n• Annual cumulative series combines operational values from the same EPW (8,760 hours) with construction, renewal, and demolition event CO₂.\n• Regional grid CO₂ factors are used consistently across compared buildings in the same region.\n• Taxes such as carbon tax are excluded.',
    '※ 事業性は各Project JSONに保存された収益・空室率・上昇率・割引率等の前提条件に従います。異用途建物では、前提条件が異なること自体も比較結果に含まれます。':'Business performance follows the revenue, vacancy, escalation, discount-rate, and other assumptions saved in each Project JSON. For buildings with different uses, differences in those assumptions are themselves part of the comparison.',
    '【ご注意】 ④単純投資回収\n・Module 6の「simple_payback_year」と同じ名目累積CF系列で、初回の投資回収を確認します。\n・0円ラインを下から上へ初めて超える年が単純投資回収年です。\n・初回回収を見やすくするため、グラフは回収年の約10年後までを拡大表示します。\n・30年以降の更新・建替えを含む200年間の長期評価は右側の現在価値ベース回収で確認します。':'[Note] ④ Simple Payback\n• Uses the same nominal cumulative CF series as Module 6 simple_payback_year to identify the first recovery.\n• Simple payback is the first year the series crosses the zero line from below.\n• The graph is expanded to about 10 years after recovery for visibility.\n• Long-term 200-year evaluation including renewal/rebuild after year 30 is shown in the present-value recovery panel.',
    '【ご注意】 ⑤現在価値ベース回収\n・Module 6の割引率で将来CFを現在価値へ割り引いて累積します。\n・0円ラインを下から上へ初めて超える年を現在価値ベース回収年とします。\n・0未満は現在価値ベースで投資未回収であり、年間利益が赤字という意味ではありません。\n・終価（売却価値）は含みません。':'[Note] ⑤ Present-Value Recovery\n• Future CF is discounted using the Module 6 discount rate and accumulated at present value.\n• Present-value recovery is the first year the cumulative series crosses zero from below.\n• A value below zero means the investment has not recovered on a present-value basis; it does not mean annual profit is negative.\n• Terminal/sale value is excluded.',
    '単純投資回収年':'Simple payback year','単純投資回収年：—':'Simple payback year: —','現在価値ベース回収：—':'Present-value recovery: —',
    '比較':'Comparison','確認':'Confirmation','読込エラー':'Load Error','年数入力':'Year Input','保存先確認':'Save Location','保存完了':'Saved','比較表CSVを保存しました。':'The comparison CSV was saved.',
    '先に比較を実行してください。':'Run the comparison first.',
    '標準保存先「Data\\比較」が見つかりません。\n保存先を指定してください。':'The standard save folder "Data\\Comparison" was not found.\nPlease choose a save location.',
    '地域未設定':'Region not set','各Project所在地':'Each Project location',
    '算定根拠：春日井を含む全地域=各Project JSONのEPW 8760時間解析値　｜　参照元：regional_analysis.module10_snapshot':'Basis: all regions, including Kasugai, use each Project JSON EPW 8,760-hour analysis | Source: regional_analysis.module10_snapshot',
    '算定根拠：年間運用CO₂（建設・修繕・更新・解体イベントは含まない）　｜　全地域=各地域8760時間値×地域電力CO₂係数':'Basis: annual operational CO₂ (excluding construction, repair, renewal, and demolition events) | All regions = regional 8,760-hour values × regional grid CO₂ factor',
    '参照元：各地域Project JSON → regional_analysis.module10_snapshot.annual.electricity_co2_factor_kg_per_kWh　｜　係数の値・基準年・出典は今後の係数マスタで管理':'Source: each regional Project JSON → regional_analysis.module10_snapshot.annual.electricity_co2_factor_kg_per_kWh | Factor value, base year, and source are managed by the coefficient master.',
    'CO₂・CF共通表示年数':'CO₂ / CF display year',
    '建設関係イベントを含む正式なCO₂時系列がありません。':'No saved official CO₂ timeline including construction-related events is available.',
    '通貨が異なる建物の金額CFは、為替換算なしでは同一グラフ比較しません。回収年は上部表示で確認できます。':'Cash-flow amounts in different currencies are not plotted together without FX conversion. Recovery years remain visible above.',
    '単純投資回収用の名目累積CFを作成できません。':'No saved nominal cumulative CF series is available for simple payback.',
    '通貨が異なる建物の現在価値CFは、為替換算なしでは同一グラフ比較しません。回収年は上部表示で確認できます。':'Present-value CF amounts in different currencies are not plotted together without FX conversion. Recovery years remain visible above.',
    '指定期間までの現在価値累積CFを作成できません。':'No saved cumulative present-value CF series is available through the selected year.',
    '通貨混在：回収年のみ比較':'Mixed currencies: compare recovery years only',
    '年以内未回収':'Not recovered within years',
    '指標':'Metric','用途':'Use','構造':'Structure','通貨':'Currency','概算建設費':'Approx. construction cost','概算建設費/m²':'Approx. construction cost/m²',
    '延床面積 m²':'GFA m²','年間エネルギー kWh':'Annual energy kWh','200年CO₂ t':'200-year CO₂ t','200年CO₂ kg/m²':'200-year CO₂ kg/m²',
    '電力CO2係数 建物間整合監査':'Grid CO₂ factor cross-building consistency audit','建物比較指標':'Building Comparison Metrics','未登録':'Not registered',
    '2件以上のJSONを選択してください。':'Select at least two Project JSON files.',
    'JSON選択確認':'JSON Selection Check','02 Evaluation 未計算確認':'02 Evaluation Calculation Status','税金取扱いの確認':'Tax Treatment Check',
    # PATCH_003
    '比較前提の確認':'Comparison Premise Check',
    # PATCH_005
    '7. 比較前提表':'7. Comparison Premise Book',
    '7. 比較前提表（同じ建物・工法違いの比較前提をそろえる）':'7. Comparison premise book (align the premises of the same building built by different methods)',
    '一覧を作成':'Build lists','比較用コピーを作成':'Create comparison copies','区分表を読込':'Load classification',
    'B 単価差リスト':'B Unit-price differences','C 範囲差リスト':'C Scope differences','A 除外工種リスト':'A Item classification',
    'D 事業前提':'D Business premises','E 工法差の前提（表示のみ）':'E Method premises (display only)',
    '未作成':'Not built',
    # PATCH_004
    '保存データの整合性確認':'Saved Data Consistency Check',
    '200年累積CO₂排出量合計（t-CO₂）':'Total 200-year cumulative CO₂ emissions (t-CO₂)',
    '200年現在価値累積CF（JPY）':'200-year cumulative present-value CF (JPY)',
    '建物 / Project':'Building / Project','kWh/m²・年':'kWh/m²·year',
    '年間CO2排出量 t/年':'Annual CO₂ Emissions t/year','電力CO2係数 kg-CO2/kWh':'Grid CO₂ Factor kg-CO₂/kWh',
    '200年CO2 kg':'200-year CO₂ kg','200年CO2 kg/m2':'200-year CO₂ kg/m²','kWh/m2年':'kWh/m²·year','延床面積 m2':'GFA m²','概算建設費/m2':'Approx. construction cost/m²',
    'OK':'OK','NG':'NG',
}


# PATCH_006: reverse lookup so a widget first created in English can still be
# switched back to Japanese (the startup language is English).
TEXT_JA={v:k for k,v in TEXT_EN.items()}
TEXT_EN.update({'kWh/月':'kWh/month','t-CO₂/月':'t-CO₂/month','キャンセル':'Cancel'})
TEXT_JA.update({'kWh/month':'kWh/月','t-CO₂/month':'t-CO₂/月'})

def to_ja_canonical(text):
    if not isinstance(text,str):return text
    if text in TEXT_JA:return TEXT_JA[text]
    m=re.match(r'^(\d+) years$',text)
    if m:return f'{m.group(1)}年'
    m=re.match(r'^Building (\d+)$',text)
    if m:return f'建物 {m.group(1)}'
    return text

def tr(text,language):
    if language=='ja': return text
    if text in TEXT_EN:return TEXT_EN[text]
    if text.startswith('建物 ') and text[3:].isdigit():return 'Building '+text[3:]
    # Dynamic labels generated from saved results. Preserve project/region names and units.
    m=re.match(r'^(.*) 建物別月間エネルギー消費量$', text)
    if m:return f'{m.group(1)} Monthly Energy Consumption by Building'
    m=re.match(r'^(.*) 建物別月間CO₂排出量$', text)
    if m:return f'{m.group(1)} Monthly CO₂ Emissions by Building'
    m=re.match(r'^(.*) CO₂期間別累積排出量（0～(\d+)年）$', text)
    if m:return f'{m.group(1)} Cumulative CO₂ Emissions (Years 0–{m.group(2)})'
    m=re.match(r'^(.*) 単純投資回収（0～(\d+)年・初回回収点拡大）$', text)
    if m:return f'{m.group(1)} Simple Payback (Years 0–{m.group(2)}, first-recovery zoom)'
    m=re.match(r'^(.*) 単純投資回収$', text)
    if m:return f'{m.group(1)} Simple Payback'
    m=re.match(r'^(.*) 現在価値累積CF（0～(\d+)年・終価除外・土地建物税別途）$', text)
    if m:return f'{m.group(1)} Cumulative Present-Value CF (Years 0–{m.group(2)}, terminal value excluded, property taxes separate)'
    m=re.match(r'^(.*) 現在価値累積CF$', text)
    if m:return f'{m.group(1)} Cumulative Present-Value CF'
    m=re.match(r'^(\d+)年累積CO₂（t-CO₂）$', text)
    if m:return f'{m.group(1)}-year cumulative CO₂ (t-CO₂)'
    m=re.match(r'^(\d+)年現在価値累積CF（(.+)）$', text)
    if m:return f'{m.group(1)}-year cumulative present-value CF ({m.group(2)})'
    m=re.match(r'^(.*)：(\d+)年$', text)
    if m:return f'{m.group(1)}: Year {m.group(2)}'
    m=re.match(r'^(.*)：(\d+)年以内未回収$', text)
    if m:return f'{m.group(1)}: not recovered within {m.group(2)} years'
    m=re.match(r'^(.*)は1～200の整数で入力してください。$', text)
    if m:return f'Enter {m.group(1)} as an integer from 1 to 200.'
    m=re.match(r'^(.*)は1～200年の範囲で指定してください。$', text)
    if m:return f'Specify {m.group(1)} within 1–200 years.'
    m=re.match(r'^(\d+)年$', text)
    if m:return f'{m.group(1)} years'
    if text=='年':return 'years'
    if text=='kWh/年':return 'kWh/year'
    if text=='t-CO₂/年':return 't-CO₂/year'
    if text=='kWh/月':return 'kWh/month'
    if text=='t-CO₂/月':return 't-CO₂/month'
    return text


def friendly_exception_text(exc,language='ja'):
    """PATCH_17b: mirrors core.error_text.friendly_exception_text used in
    Planning/Evaluation. ValueError is assumed to already be a hand-written
    human sentence; any other exception type is wrapped with a short generic
    framing sentence instead of being shown to the user on its own."""
    if isinstance(exc,ValueError):
        return str(exc)
    ja=(language=='ja')
    type_name=type(exc).__name__
    msg=str(exc) or "(no detail)"
    if ja:
        return f"予期しないエラーが発生しました。\n詳細: {type_name}: {msg}\n繰り返し発生する場合は開発者にご連絡ください。"
    return f"An unexpected error occurred.\nDetail: {type_name}: {msg}\nIf this keeps happening, please contact the developer."

class LineChart(tk.Canvas):
    def __init__(self,parent,**kw):
        super().__init__(parent,bg='white',highlightthickness=1,highlightbackground='#bbb',**kw)
        self.title='';self.ylabel='';self.labels=[];self.series=[];self.tick_every=None;self.empty_message='計算済みデータがありません';self.zero_line=False
        self._hover_points=[]
        self.bind('<Configure>',lambda e:self.redraw())
        self.bind('<Motion>',self._on_motion)
        self.bind('<Leave>',lambda e:self.delete('tooltip'))
    def set_data(self,title,ylabel,labels,series,tick_every=None,empty_message='計算済みデータがありません',zero_line=False):
        self.title=title;self.ylabel=ylabel;self.labels=labels;self.series=series;self.tick_every=tick_every;self.empty_message=empty_message;self.zero_line=zero_line;self.redraw()
    def _on_motion(self,event):
        self.delete('tooltip')
        if not self._hover_points:
            return
        nearest=None;best=10.0**9
        for px,py,name,xlabel,value in self._hover_points:
            d=(event.x-px)**2+(event.y-py)**2
            if d<best:
                best=d;nearest=(px,py,name,xlabel,value)
        if nearest is None or best>12**2:
            return
        px,py,name,xlabel,value=nearest
        if isinstance(value,(int,float)):
            value_text=f'{value:,.3f}' if abs(value)<100 else f'{value:,.1f}'
        else:
            value_text=str(value)
        text=f'{name}\n{xlabel}：{value_text} {self.ylabel}'
        tid=self.create_text(px+12,py-12,text=text,anchor='sw',justify='left',
                             font=('Yu Gothic UI',9),fill='black',tags='tooltip')
        box=self.bbox(tid)
        if box:
            pad=5
            rect=self.create_rectangle(box[0]-pad,box[1]-pad,box[2]+pad,box[3]+pad,
                                       fill='#fffde7',outline='#777',tags='tooltip')
            self.tag_lower(rect,tid)
        self.tag_raise('tooltip')
    LEGEND_FONT=('Yu Gothic UI',8)
    LEGEND_SWATCH_W=20
    LEGEND_TEXT_GAP=5
    LEGEND_ITEM_GAP=18
    LEGEND_ROW_H=14

    def _measure(self,text):
        """PATCH_003: real pixel width of a legend label.

        Falls back to a per-character estimate only if the font cannot be
        queried (no Tk font manager yet). The estimate deliberately assumes
        full-width for anything outside Latin-1 so a Japanese project name is
        never under-measured.
        """
        try:
            return int(tkfont.Font(font=self.LEGEND_FONT).measure(text))
        except Exception:
            return int(sum(11 if ord(ch)>0x2000 else 6 for ch in str(text)))

    def _legend_layout(self,names,avail_w):
        """PATCH_003: lay legend entries out left to right, wrapping to new rows.

        Returns ({series_index:(x_offset,row_index)}, row_count, {index:label}).

        The previous implementation placed every entry at a fixed 155 px pitch.
        Any label wider than 155 px ran straight over the next entry, which is
        why "AZRAS_Sample [AZRAS Platform]" overlapped
        "RC_Rahmen_Sample [Conventional RC]" on every chart in this product.
        Project labels are user data (project name + method name) and have no
        bounded width, so the pitch has to come from the text, not a constant.
        """
        avail_w=max(int(avail_w),80)
        placements={};shown={};x=0;row=0
        for si,raw in enumerate(names):
            name=str(raw)
            text_w=self._measure(name)
            item_w=self.LEGEND_SWATCH_W+self.LEGEND_TEXT_GAP+text_w
            if item_w>avail_w:
                # A single label longer than the whole plot width: trim it with
                # an ellipsis rather than letting it run off the canvas.
                budget=avail_w-self.LEGEND_SWATCH_W-self.LEGEND_TEXT_GAP-self._measure('…')
                trimmed=name
                while trimmed and self._measure(trimmed)>budget:
                    trimmed=trimmed[:-1]
                name=(trimmed+'…') if trimmed else '…'
                text_w=self._measure(name)
                item_w=self.LEGEND_SWATCH_W+self.LEGEND_TEXT_GAP+text_w
            if x>0 and x+item_w>avail_w:
                row+=1;x=0
            placements[si]=(x,row);shown[si]=name
            x+=item_w+self.LEGEND_ITEM_GAP
        return placements,row+1,shown

    def redraw(self):
        self.delete('all');self._hover_points=[];w=max(self.winfo_width(),360);h=max(self.winfo_height(),220);L,R,T,B=78,22,46,42
        self.create_text(w/2,20,text=self.title,font=('Yu Gothic UI',12,'bold'))
        vals=[v for _,pts in self.series for _,v in pts if isinstance(v,(int,float))]
        if not vals:self.create_text(w/2,h/2,text=self.empty_message,font=('Yu Gothic UI',11),justify='center');return
        # PATCH_003: the legend sits above the plot, so its wrapped height has
        # to be reserved before the axes are drawn or a second legend row would
        # be painted over the top gridline.
        legend_top=T-14
        legend_place,legend_rows,legend_text=self._legend_layout([str(nm) for nm,_ in self.series],w-L-R)
        T=T+max(0,legend_rows-1)*self.LEGEND_ROW_H
        ymin=min(0,min(vals));ymax=max(vals);ymax=ymax if ymax>ymin else ymin+1
        for i in range(5):
            y=T+(h-T-B)*i/4;val=ymax-(ymax-ymin)*i/4
            self.create_line(L,y,w-R,y,fill='#ddd');self.create_text(L-7,y,text=f'{val:,.0f}',anchor='e',font=('Yu Gothic UI',8))
        self.create_line(L,T,L,h-B);self.create_line(L,h-B,w-R,h-B)
        # Y軸単位は目盛数字と重ならないよう、数字の下側へ寄せてやや大きく表示。
        # 特にCFの「JPY」が縦目盛の数値に埋もれないようにする。
        self.create_text(18,h-B+27,text=self.ylabel,font=('Yu Gothic UI',10,'bold'),anchor='w')
        colors=['#1565c0','#d32f2f','#2e7d32','#6a1b9a','#ef6c00','#00838f','#5d4037']
        n=max((len(x) for _,x in self.series),default=1)
        def xy(i,v):return L+(w-L-R)*(i/max(n-1,1)),T+(h-T-B)*(ymax-v)/(ymax-ymin)
        if self.zero_line and ymin<=0<=ymax:
            zy=xy(0,0)[1]
            self.create_line(L,zy,w-R,zy,fill='#333',width=2,dash=(6,4))
            self.create_text(L+6,zy-6,text=tr('±0（投資回収基準）',CURRENT_UI_LANGUAGE),anchor='sw',font=('Yu Gothic UI',9,'bold'),fill='#333')
        for si,(name,pts) in enumerate(self.series):
            coords=[]
            for i,v in pts:coords.extend(xy(i,v))
            if len(coords)>=4:self.create_line(*coords,fill=colors[si%len(colors)],width=2.2)
            for i,v in pts:
                x,y=xy(i,v);self.create_oval(x-2.2,y-2.2,x+2.2,y+2.2,fill=colors[si%len(colors)],outline='')
                xlabel=self.labels[i] if isinstance(i,int) and 0<=i<len(self.labels) else i
                self._hover_points.append((x,y,name,xlabel,v))
            x_off,row=legend_place.get(si,(0,0));x0=L+x_off;ly=legend_top+row*self.LEGEND_ROW_H
            self.create_line(x0,ly,x0+self.LEGEND_SWATCH_W,ly,fill=colors[si%len(colors)],width=3)
            self.create_text(x0+self.LEGEND_SWATCH_W+self.LEGEND_TEXT_GAP,ly,
                             text=legend_text.get(si,str(name)),anchor='w',font=self.LEGEND_FONT)
        if self.tick_every:
            indices=[i for i,lab in enumerate(self.labels) if isinstance(lab,(int,float)) and int(lab)%self.tick_every==0]
            if 0 not in indices:indices=[0]+indices
            if n-1 not in indices:indices.append(n-1)
        else:
            step=max(1,math.ceil(n/12));indices=list(range(0,n,step))
            if n-1 not in indices:indices.append(n-1)
        for i in sorted(set(indices)):
            x,_=xy(i,ymin);lab=self.labels[i] if i<len(self.labels) else str(i);self.create_text(x,h-B+15,text=str(lab),font=('Yu Gothic UI',8))

class ScrollMatrix(ttk.Frame):
    def __init__(self,parent):
        super().__init__(parent)
        self.canvas=tk.Canvas(self,bg='white',highlightthickness=0);self.inner=ttk.Frame(self.canvas)
        self.xbar=ttk.Scrollbar(self,orient='horizontal',command=self.canvas.xview);self.ybar=ttk.Scrollbar(self,orient='vertical',command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=self.xbar.set,yscrollcommand=self.ybar.set)
        self.canvas.grid(row=0,column=0,sticky='nsew');self.ybar.grid(row=0,column=1,sticky='ns');self.xbar.grid(row=1,column=0,sticky='ew')
        self.rowconfigure(0,weight=1);self.columnconfigure(0,weight=1)
        self.win=self.canvas.create_window((0,0),window=self.inner,anchor='nw')
        self.inner.bind('<Configure>',lambda e:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',lambda e:self.canvas.itemconfigure(self.win,height=max(e.height,self.inner.winfo_reqheight())))
        self.canvas.bind_all('<Shift-MouseWheel>',self._hscroll)
    def _hscroll(self,e):
        try:self.canvas.xview_scroll(int(-1*(e.delta/120)),'units')
        except tk.TclError:pass
    def clear(self):
        for w in self.inner.winfo_children():w.destroy()
    def render(self,cities,methods,values,best_mode,unit,city_text=None,method_text=None):
        city_text=city_text or (lambda c:c);method_text=method_text or (lambda m:m)
        self.clear();header_bg='#e9eef5';best_bg='#0b4da2';font=('Yu Gothic UI',10);bold=('Yu Gothic UI',10,'bold')
        def cell(text,r,c,bg='white',fg='black',fnt=font,width=18,anchor='center'):
            lab=tk.Label(self.inner,text=text,bg=bg,fg=fg,font=fnt,relief='solid',bd=1,padx=6,pady=5,width=width,anchor=anchor)
            lab.grid(row=r,column=c,sticky='nsew');return lab
        cell(tr('建物',CURRENT_UI_LANGUAGE),0,0,header_bg,fnt=bold,width=22)
        for j,city in enumerate(cities,1):cell(city_text(tr(city,CURRENT_UI_LANGUAGE)),0,j,header_bg,fnt=bold,width=18)
        best=[]
        for j in range(len(cities)):
            nums=[values[m][j] for m in methods if values[m][j] is not None]
            best.append((min(nums) if best_mode=='min' else max(nums)) if nums else None)
        for i,m in enumerate(methods,1):
            cell(method_text(m),i,0,header_bg,fnt=bold,width=22)
            for j,v in enumerate(values[m],1):
                isbest=v is not None and best[j-1] is not None and abs(v-best[j-1])<=max(1e-7,abs(best[j-1])*1e-9)
                if v is None:
                    txt='―'
                elif 'CO₂' in unit or 'CO2' in unit:
                    txt=f'{v:,.3f}'
                else:
                    txt=f'{v:,.1f}'
                cell(txt,i,j,best_bg if isbest else 'white','white' if isbest else 'black',bold if isbest else font,width=18,anchor='e')
        tk.Label(self.inner,text=(f'単位：{unit}　濃い青色のセルだけが、その都市における最良値です。' if CURRENT_UI_LANGUAGE=='ja' else f'Unit: {unit}  Only dark-blue cells indicate the best value for that city.'),bg='white',fg='#333',font=('Yu Gothic UI',9)).grid(row=len(methods)+1,column=0,columnspan=max(1,len(cities)+1),sticky='w',pady=8)


class CompareStartScreen(tk.Toplevel):
    """Cover/start screen linked to the same language state as the comparison UI."""
    def __init__(self, app):
        super().__init__(app)
        self.app=app
        self.protocol("WM_DELETE_WINDOW", app.destroy)
        self.geometry("860x560")
        self.minsize(760,500)
        self.resizable(True,True)
        self._build()
        # Do not make the cover window transient to the hidden root window.
        # On Windows, a transient Toplevel whose master is withdrawn can remain invisible.
        self.deiconify()
        self.lift()

    def _build(self):
        for w in self.winfo_children():
            w.destroy()
        lang=self.app.language
        self.title(f"{PRODUCT} — {COMPANY}")

        outer=ttk.Frame(self,padding=(34,28))
        outer.pack(fill='both',expand=True)

        ttk.Label(
            outer,text=f"{PRODUCT} Version {VERSION}",
            font=('Yu Gothic UI',26,'bold'),anchor='center'
        ).pack(fill='x',pady=(32,8))

        subtitle='異なる用途・間取り・規模・構造の建物を比較します'
        ttk.Label(
            outer,text=tr(subtitle,lang),
            font=('Yu Gothic UI',14,'bold'),anchor='center'
        ).pack(fill='x',pady=(0,24))

        langrow=ttk.Frame(outer)
        langrow.pack(pady=12)
        ttk.Label(langrow,text='言語 / Language').pack(side='left',padx=(0,6))
        cb=ttk.Combobox(
            langrow,textvariable=self.app.language_var,
            values=[LANG_LABELS[code] for code in LANGUAGE_ORDER],
            state='readonly',width=14
        )
        cb.pack(side='left')
        cb.bind('<<ComboboxSelected>>',self._language_changed)

        ttk.Label(
            outer,
            text=tr('表紙と比較画面の言語設定は共通です',lang),
            foreground='#555555',anchor='center'
        ).pack(fill='x',pady=(4,24))

        ttk.Button(
            outer,text=tr('建物比較を開く',lang),
            command=self.open_compare
        ).pack(ipadx=34,ipady=12,pady=18)

        ttk.Label(
            outer,text=f"© 2026 {COMPANY}",
            foreground='#555555',anchor='center'
        ).pack(side='bottom',fill='x',pady=(20,4))

    def _language_changed(self,event=None):
        self.app._change_language()
        self._build()

    def open_compare(self):
        self.destroy()
        self.app.deiconify()
        self.app.lift()
        self.app.focus_force()


class App(tk.Tk):
    def __init__(self):
        super().__init__();self.title(f'{PRODUCT} Version {VERSION} — {COMPANY}');self.geometry('1500x920');self.minsize(1080,700)
        self.language='en';self.language_var=tk.StringVar(value=LANG_LABELS[self.language]);self.paths=[tk.StringVar() for _ in range(7)];self.projects=[];self.regional={};self.annual_metric=tk.StringVar(value='energy');self.co2_year=tk.IntVar(value=200);self.cash_year=tk.IntVar(value=200);self.period_year_input=tk.StringVar(value='200')
        self.start_screen=None
        self.build()
        self.withdraw()
        self.after(60,self.show_start_screen)
    def show_start_screen(self):
        try:
            if self.start_screen is not None and self.start_screen.winfo_exists():
                self.start_screen.lift()
                return
        except Exception:
            pass
        self.withdraw()
        self.start_screen=CompareStartScreen(self)
        self.start_screen.deiconify()
        self.start_screen.lift()
        self.start_screen.focus_force()

    def back_to_start(self):
        self.show_start_screen()

    def build(self):
        ttk.Label(self,text=f'{PRODUCT} Version {VERSION}',font=('Yu Gothic UI',22,'bold'),anchor='center').pack(fill='x',pady=(10,2))
        nav=ttk.Frame(self);nav.pack(fill='x',padx=12,pady=4)
        ttk.Label(nav,text='言語 / Language').pack(side='left',padx=(2,4))
        self.language_box=ttk.Combobox(nav,textvariable=self.language_var,values=[LANG_LABELS[code] for code in LANGUAGE_ORDER],state='readonly',width=12)
        self.language_box.pack(side='left',padx=(0,8));self.language_box.bind('<<ComboboxSelected>>',self._change_language)
        self.tabs=ttk.Notebook(self);self.tabs.pack(fill='both',expand=True,padx=10,pady=4)
        self.select_tab=ttk.Frame(self.tabs); self.overview_tab=ttk.Frame(self.tabs); self.monthly_tab=ttk.Frame(self.tabs); self.co2_tab=ttk.Frame(self.tabs); self.invest_tab=ttk.Frame(self.tabs); self.matrix_tab=ttk.Frame(self.tabs)
        self.tabs.add(self.select_tab,text='1. 建物・JSON選択')
        self.tabs.add(self.overview_tab,text='2. 建物比較指標')
        self.tabs.add(self.monthly_tab,text='3. 月間比較グラフ')
        self.tabs.add(self.co2_tab,text='4. 200年間CO₂比較グラフ')
        self.tabs.add(self.invest_tab,text='5. 200年間投資回収比較グラフ')
        self.tabs.add(self.matrix_tab,text='6. 世界地域別比較')
        self.premise_tab=PremiseBookTab(self.tabs,self)
        self.tabs.add(self.premise_tab,text='7. 比較前提表')
        ttk.Button(nav,text='比較表CSV保存',command=self.save_csv).pack(side='right',padx=3)
        ttk.Button(nav,text='新規',command=self.clear).pack(side='right',padx=3)
        ttk.Button(nav,text='表紙へ戻る',command=self.back_to_start).pack(side='right',padx=3)
        self.build_select();self.build_overview();self.build_monthly();self.build_co2_long();self.build_investment();self.build_matrix()
        ttk.Label(self,text=f'{PRODUCT} Version {VERSION}  |  © 2026 {COMPANY}',anchor='center').pack(fill='x',pady=4)
        self._apply_tab_language();self._apply_language_to_widgets(self)

    def _change_language(self,event=None):
        global CURRENT_UI_LANGUAGE
        self.language=LANG_CODES.get(self.language_var.get(),'en')
        CURRENT_UI_LANGUAGE=self.language
        self._apply_language_to_widgets(self)
        self._apply_tab_language()
        if hasattr(self,'overview_tree'):
            heads={'building':'建物 / Project','use':'用途','structure':'構造','method':'工法','eval_status':'02 Evaluation','gfa':'延床面積 m²','cost':'概算建設費','cost_m2':'概算建設費/m²','energy':'年間エネルギー kWh','energy_m2':'kWh/m²・年','co2_200':'200年CO₂ t','co2_200_m2':'200年CO₂ kg/m²','currency':'通貨'}
            for c,h in heads.items(): self.overview_tree.heading(c,text=tr(h,self.language))
        # PATCH_006: summary-table headings were only re-translated after a
        # comparison had been run; re-apply them on every language change.
        for t in (getattr(self,n,None) for n in ('energy_summary','monthly_co2_summary','co2_summary','nominal_cash_summary','cash_summary')):
            heads=getattr(t,'_azras_heads',None) if t is not None else None
            if heads:
                for col,h in heads.items():t.heading(col,text=tr(h,self.language))
        if self.projects:
            self.refresh_overview(); self.refresh_comparisons(); self.show_annual(self.annual_metric.get())
        try:
            if getattr(self.premise_tab,'lists',None):self.premise_tab._refresh()
        except Exception:
            pass
        try:
            if self.start_screen is not None and self.start_screen.winfo_exists():
                self.start_screen._build()
        except Exception:
            pass

    def _apply_tab_language(self):
        tabs=[
            (self.select_tab,'1. 建物・JSON選択'),(self.overview_tab,'2. 建物比較指標'),
            (self.monthly_tab,'3. 月間比較グラフ'),(self.co2_tab,'4. 200年間CO₂比較グラフ'),
            (self.invest_tab,'5. 200年間投資回収比較グラフ'),(self.matrix_tab,'6. 世界地域別比較'),
            (self.premise_tab,'7. 比較前提表')]
        for tab,label in tabs:self.tabs.tab(tab,text=tr(label,self.language))

    def _apply_language_to_widgets(self,parent):
        # Keep data values, units and project names untouched; translate UI labels/buttons only.
        for w in parent.winfo_children():
            try:
                txt=w.cget('text')
                if isinstance(txt,str) and txt:
                    if not hasattr(w,'_azras_ja_text'):w._azras_ja_text=to_ja_canonical(txt)
                    w.configure(text=tr(w._azras_ja_text,self.language))
            except Exception:pass
            self._apply_language_to_widgets(w)

    def build_select(self):
        box=ttk.LabelFrame(self.select_tab,text='比較するProject JSON（2～7建物）');box.pack(fill='x',padx=18,pady=14)
        for i,v in enumerate(self.paths):
            ttk.Label(box,text=f'建物 {i+1}',width=9).grid(row=i,column=0,padx=5,pady=4);ttk.Entry(box,textvariable=v,state='readonly').grid(row=i,column=1,sticky='ew',padx=4)
            ttk.Button(box,text='選択',command=lambda n=i:self.pick(n)).grid(row=i,column=2,padx=3);ttk.Button(box,text='解除',command=lambda n=i:self.paths[n].set('')).grid(row=i,column=3,padx=3)
        box.columnconfigure(1,weight=1);ttk.Button(box,text='JSONを読み込み比較を作成',command=self.compare).grid(row=8,column=0,columnspan=4,pady=12)
    def build_overview(self):
        ttk.Label(self.overview_tab,text='2. 建物比較指標（絶対値＋床面積当たり）',font=('Yu Gothic UI',15,'bold')).pack(anchor='w',padx=14,pady=(8,4))
        ttk.Label(self.overview_tab,text='用途・間取り・規模・構造・所在地が異なる建物を、各Project JSONに保存された条件のまま比較できます。規模差による誤解を避けるため、総量とm²当たりを併記します。',foreground='#555',wraplength=1380).pack(fill='x',padx=14,pady=(0,6))
        frame=ttk.Frame(self.overview_tab);frame.pack(fill='both',expand=True,padx=10,pady=5)
        cols=('building','use','structure','method','eval_status','gfa','cost','cost_m2','energy','energy_m2','co2_200','co2_200_m2','currency')
        heads=[('building','建物 / Project',220),('use','用途',110),('structure','構造',110),('method','工法',140),('eval_status','02 Evaluation',115),('gfa','延床面積 m²',105),('cost','概算建設費',130),('cost_m2','概算建設費/m²',130),('energy','年間エネルギー kWh',150),('energy_m2','kWh/m²・年',110),('co2_200','200年CO₂ t',115),('co2_200_m2','200年CO₂ kg/m²',130),('currency','通貨',70)]
        self.overview_tree=ttk.Treeview(frame,columns=cols,show='headings')
        for c,h,w in heads:
            self.overview_tree.heading(c,text=tr(h,self.language));self.overview_tree.column(c,width=w,anchor='w' if c in ('building','use','structure','method','eval_status') else 'e')
        y=ttk.Scrollbar(frame,orient='vertical',command=self.overview_tree.yview);x=ttk.Scrollbar(frame,orient='horizontal',command=self.overview_tree.xview)
        self.overview_tree.configure(yscrollcommand=y.set,xscrollcommand=x.set);self.overview_tree.grid(row=0,column=0,sticky='nsew');y.grid(row=0,column=1,sticky='ns');x.grid(row=1,column=0,sticky='ew');frame.rowconfigure(0,weight=1);frame.columnconfigure(0,weight=1)
        self.overview_note=ttk.Label(self.overview_tab,text='比較未実行',foreground='#555',wraplength=1380);self.overview_note.pack(fill='x',padx=14,pady=(2,8))

    def _assign_unique_labels(self):
        counts={}
        for r in self.projects:
            base=str(r.get('label') or r.get('project') or r.get('method') or 'Project')
            n=counts.get(base,0)+1;counts[base]=n
            r['label']=base if n==1 else f'{base} #{n}'
            ja_base=str(r.get('label_ja') or base)
            r['label_ja']=ja_base if n==1 else f'{ja_base} #{n}'
        # PATCH_006: 'label' remains the comparison key everywhere; the map below
        # is used only when text is put on screen.
        self._label_ja={r['label']:r.get('label_ja') or r['label'] for r in self.projects}

    def disp(self,label):
        if self.language=='ja':
            return getattr(self,'_label_ja',{}).get(label,label)
        return label

    def cdisp(self,city):
        return DJ.city_ja(city) if self.language=='ja' else city

    def refresh_overview(self):
        if not hasattr(self,'overview_tree'):return
        for iid in self.overview_tree.get_children():self.overview_tree.delete(iid)
        currencies=sorted({str(r.get('currency') or '') for r in self.projects if r.get('currency')})
        ja=(self.language=='ja')
        for r in self.projects:
            def f(v,d=1):
                return '—' if v is None else f'{float(v):,.{d}f}'
            self.overview_tree.insert('','end',values=(
                r.get('project',''),
                (r.get('building_use_ja') or DJ.use_ja('Unknown')) if ja else r.get('building_use','Unknown'),
                (r.get('structure_ja') or r.get('structure','Unknown')) if ja else r.get('structure','Unknown'),
                (r.get('method_ja') or r.get('method','Unknown')) if ja else r.get('method','Unknown'),
                tr({'complete':'完了','partial':'一部未計算','not_calculated':'未計算'}.get(r.get('evaluation_status'),'未計算'),self.language),
                f(r.get('gfa_m2'),1),f(r.get('construction_cost'),0),f(r.get('construction_cost_per_m2'),0),
                f(r.get('annual_energy'),1),f(r.get('annual_energy_per_m2'),1),
                f((r.get('lifecycle_co2_200_kg')/1000.0) if r.get('lifecycle_co2_200_kg') is not None else None,1),
                f(r.get('lifecycle_co2_200_per_m2_kg'),1),r.get('currency','')
            ))
        if len(currencies)>1:
            self.overview_note.config(text=tr('注意：通貨が異なる建物が含まれています。金額の絶対比較・投資CF比較は為替換算なしでは行いません。環境・エネルギー・m²当たり指標は比較できます。',self.language),foreground='#8b0000')
        else:
            self.overview_note.config(text=tr('用途・規模・構造が異なる場合は、総量だけでなくm²当たり指標も併せて確認してください。',self.language),foreground='#1b6e1b')

    def build_matrix(self):
        ttk.Label(self.matrix_tab,text='年間比較（建設関係イベントは含まない）',font=('Yu Gothic UI',15,'bold')).pack(anchor='w',padx=14,pady=(8,2))
        ttk.Label(self.matrix_tab,text='この画面は各Projectの地域比較データを使い、同じ地域名の列で建物を横並びにする標準化比較です。主比較画面は各Project JSON固有の所在地・条件をそのまま使用します。',foreground='#555',wraplength=1380).pack(fill='x',padx=14,pady=(0,4))
        btn=ttk.Frame(self.matrix_tab);btn.pack(fill='x',padx=12,pady=4)
        ttk.Button(btn,text='年間エネルギー消費量 kWh/年',command=lambda:self.show_annual('energy')).pack(side='left',padx=3)
        ttk.Button(btn,text='年間CO₂排出量 t/年',command=lambda:self.show_annual('co2')).pack(side='left',padx=3)
        ttk.Button(btn,text='電力CO₂係数 kg-CO₂/kWh',command=lambda:self.show_annual('co2_factor')).pack(side='left',padx=3)
        self.annual_caption=ttk.Label(btn,text='表示：年間エネルギー消費量 kWh/年',foreground='#0b4da2',font=('Yu Gothic UI',10,'bold'));self.annual_caption.pack(side='left',padx=14)
        self.annual_basis=ttk.Label(
            self.matrix_tab,
            text='算定根拠：各地域の8760時間解析結果の年間合計　｜　参照元：Project JSON → regional_analysis.module10_snapshot',
            foreground='#444'
        );self.annual_basis.pack(anchor='w',padx=14,pady=(0,3))
        self.co2_factor_audit=ttk.Label(
            self.matrix_tab,
            text='電力CO₂係数整合監査：比較未実行',
            foreground='#555'
        );self.co2_factor_audit.pack(anchor='w',padx=14,pady=(0,3))
        self.matrix=ScrollMatrix(self.matrix_tab);self.matrix.pack(fill='both',expand=True,padx=10,pady=5)
    def build_monthly(self):
        top=ttk.Frame(self.monthly_tab);top.pack(fill='x',padx=10,pady=(6,3))
        ttk.Label(top,text='3. 月間比較グラフ（1～12月）',font=('Yu Gothic UI',14,'bold')).pack(side='left')
        ttk.Label(top,text='　指定地域：').pack(side='left')
        self.monthly_city_label=ttk.Label(top,text='未読込',font=('Yu Gothic UI',10,'bold'));self.monthly_city_label.pack(side='left')

        body=ttk.Frame(self.monthly_tab);body.pack(fill='both',expand=True,padx=8,pady=4)
        body.columnconfigure(0,weight=1,uniform='monthly')
        body.columnconfigure(1,weight=1,uniform='monthly')
        body.rowconfigure(0,weight=1)

        e=ttk.LabelFrame(body,text='① 月間エネルギー（年間予測）');e.grid(row=0,column=0,sticky='nsew',padx=(0,4))
        self.p_energy=LineChart(e,height=430);self.p_energy.pack(fill='both',expand=True,padx=5,pady=(4,2))
        self.energy_summary=self.summary_table_bottom(e,'年間エネルギー消費量合計（kWh/年）')
        ttk.Label(e,text='【ご注意】 ①月間エネルギー\n・同一EPW（8760時間）による年間エネルギー予測値です。\n・年間値は冷暖房・換気・給湯・照明等の合計（設備構成に依存）です。',
                  foreground='#d00000',wraplength=690,justify='left').pack(fill='x',padx=8,pady=(4,8))

        c=ttk.LabelFrame(body,text='② 月間CO₂排出量（年間予測）');c.grid(row=0,column=1,sticky='nsew',padx=(4,0))
        self.p_monthly_co2=LineChart(c,height=430);self.p_monthly_co2.pack(fill='both',expand=True,padx=5,pady=(4,2))
        self.monthly_co2_summary=self.summary_table_bottom(c,'年間運用CO₂排出量合計（t-CO₂/年）')
        ttk.Label(c,text='【ご注意】 ②月間CO₂排出量\n・各月の8760時間電力量 × 地域別電力CO₂係数から算定した運用CO₂です。\n・建設・更新・解体イベントCO₂は含みません。\n・同一地域では比較対象の各建物で同一の電力CO₂係数を使用します。',
                  foreground='#d00000',wraplength=690,justify='left').pack(fill='x',padx=8,pady=(4,8))

    def _year_controls(self,parent,label):
        controls=ttk.Frame(parent);controls.pack(fill='x',padx=10,pady=(1,4));ttk.Label(controls,text=label,font=('Yu Gothic UI',10,'bold')).pack(side='left')
        for y in (50,100,150,200):ttk.Button(controls,text=f'{y}年',command=lambda n=y:self.set_period_year(n)).pack(side='left',padx=2)
        ttk.Label(controls,text='任意年 1～200：').pack(side='left',padx=(12,2));ttk.Entry(controls,textvariable=self.period_year_input,width=6).pack(side='left',padx=2);ttk.Button(controls,text='表示',command=self.apply_period_year).pack(side='left',padx=3)

    def build_co2_long(self):
        top=ttk.Frame(self.co2_tab);top.pack(fill='x',padx=10,pady=(6,3));ttk.Label(top,text='4. 200年間CO₂比較グラフ',font=('Yu Gothic UI',14,'bold')).pack(side='left');ttk.Label(top,text='　指定地域：').pack(side='left');self.co2_city_label=ttk.Label(top,text='未読込',font=('Yu Gothic UI',10,'bold'));self.co2_city_label.pack(side='left')
        self._year_controls(self.co2_tab,'CO₂表示年：')
        c=ttk.LabelFrame(self.co2_tab,text='③ 200年間CO₂累積（建設関係イベント含む）');c.pack(fill='both',expand=True,padx=8,pady=4)
        self.p_co2=LineChart(c,height=500);self.p_co2.pack(fill='both',expand=True,padx=5,pady=(4,2));self.co2_summary=self.summary_table_bottom(c,'200年累積CO₂排出量合計（t-CO₂）')
        ttk.Label(c,text='【ご注意】 ③CO₂累積\n・同一EPW（8760時間）の運用値＋建設・更新・解体イベントCO₂を統合した年次累積です。\n・電力CO₂係数は地域別設定値を使用し、同一地域では比較対象の各建物で同一です。\n・税金（炭素税等）は含めていません。',foreground='#d00000',wraplength=1300,justify='left').pack(fill='x',padx=8,pady=(4,8))

    def build_investment(self):
        top=ttk.Frame(self.invest_tab);top.pack(fill='x',padx=10,pady=(6,3));ttk.Label(top,text='5. 200年間投資回収比較グラフ',font=('Yu Gothic UI',14,'bold')).pack(side='left');ttk.Label(top,text='　指定地域：').pack(side='left');self.invest_city_label=ttk.Label(top,text='未読込',font=('Yu Gothic UI',10,'bold'));self.invest_city_label.pack(side='left')
        self._year_controls(self.invest_tab,'CF表示年：')
        ttk.Label(
            self.invest_tab,
            text='※ 事業性は各Project JSONに保存された収益・空室率・上昇率・割引率等の前提条件に従います。異用途建物では、前提条件が異なること自体も比較結果に含まれます。',
            foreground='#8b0000', wraplength=1380, justify='left'
        ).pack(fill='x', padx=12, pady=(0,3))
        body=ttk.Frame(self.invest_tab);body.pack(fill='both',expand=True,padx=8,pady=4);body.columnconfigure(0,weight=1,uniform='inv');body.columnconfigure(1,weight=1,uniform='inv');body.rowconfigure(0,weight=1)
        n=ttk.LabelFrame(body,text='④ 単純投資回収比較（初回回収の確認）');n.grid(row=0,column=0,sticky='nsew',padx=(0,4));self.simple_payback=ttk.Label(n,text='単純投資回収年：—',foreground='#333');self.simple_payback.pack(anchor='e',padx=8,pady=(3,0));self.p_nominal_cash=LineChart(n,height=390);self.p_nominal_cash.pack(fill='both',expand=True,padx=5,pady=(1,2));self.nominal_cash_summary=self.summary_table_bottom(n,'単純投資回収年',cf=False);ttk.Label(n,text='【ご注意】 ④単純投資回収\n・Module 6の「simple_payback_year」と同じ名目累積CF系列で、初回の投資回収を確認します。\n・0円ラインを下から上へ初めて超える年が単純投資回収年です。\n・初回回収を見やすくするため、グラフは回収年の約10年後までを拡大表示します。\n・30年以降の更新・建替えを含む200年間の長期評価は右側の現在価値ベース回収で確認します。',foreground='#d00000',wraplength=690,justify='left').pack(fill='x',padx=8,pady=(4,8))
        f=ttk.LabelFrame(body,text='⑤ 現在価値ベース回収比較（割引累積CF）');f.grid(row=0,column=1,sticky='nsew',padx=(4,0));self.cash_payback=ttk.Label(f,text='現在価値ベース回収：—',foreground='#333');self.cash_payback.pack(anchor='e',padx=8,pady=(3,0));self.p_cash=LineChart(f,height=390);self.p_cash.pack(fill='both',expand=True,padx=5,pady=(1,2));self.cash_summary=self.summary_table_bottom(f,'200年現在価値累積CF（JPY）',cf=True);ttk.Label(f,text='【ご注意】 ⑤現在価値ベース回収\n・Module 6の割引率で将来CFを現在価値へ割り引いて累積します。\n・0円ラインを下から上へ初めて超える年を現在価値ベース回収年とします。\n・0未満は現在価値ベースで投資未回収であり、年間利益が赤字という意味ではありません。\n・終価（売却価値）は含みません。',foreground='#d00000',wraplength=690,justify='left').pack(fill='x',padx=8,pady=(4,8))

    def summary_table_bottom(self,parent,value_head,cf=False):
        t=ttk.Treeview(parent,columns=('method','value'),show='headings',height=3)
        t.heading('method',text=tr('建物',self.language));t.heading('value',text=tr(value_head,self.language))
        t._azras_heads={'method':'建物','value':value_head}  # PATCH_006: JA canonical, re-translated on language change
        t.column('method',width=175,anchor='w');t.column('value',width=230,anchor='e')
        t.tag_configure('negative',foreground='#d00000')
        t.tag_configure('nonnegative',foreground='#000000')
        t.pack(fill='x',padx=8,pady=(3,2))
        return t

    def summary_table(self,parent,value_head):
        t=ttk.Treeview(parent,columns=('no','method','value'),show='headings',height=5)
        t.heading('no',text='No.');t.heading('method',text=tr('建物',self.language));t.heading('value',text=tr(value_head,self.language))
        t.column('no',width=42,anchor='center');t.column('method',width=145,anchor='center');t.column('value',width=175,anchor='e')
        t.tag_configure('negative',foreground='#b00020')
        t.tag_configure('nonnegative',foreground='#000000')
        t.pack(side='right',fill='y',padx=6);return t
    def pick(self,i):
        p=filedialog.askopenfilename(filetypes=[('Core Project JSON','*.json'),('All files','*.*')]);
        if p:self.paths[i].set(p)
    def clear(self):
        for p in self.paths:p.set('')
        self.projects=[];self.regional={};self.monthly_city_label.config(text=tr('未読込',self.language));self.co2_city_label.config(text=tr('未読込',self.language));self.invest_city_label.config(text=tr('未読込',self.language));self.matrix.clear()
        if hasattr(self,'overview_tree'):
            for iid in self.overview_tree.get_children():self.overview_tree.delete(iid)
    def compare(self):
        ps=[x.get() for x in self.paths if x.get()]
        if len(ps)<2:return messagebox.showwarning(tr('確認',self.language),tr('2件以上のJSONを選択してください。',self.language), parent=self)
        try:
            self.projects=[extract_core_project(p) for p in ps]
            # 同じProject JSONを複数枠に選んだ場合は、同一建物の重複比較になるため比較を開始しない。
            ids={}
            for x in self.projects:
                pid=str((x.get('raw') or {}).get('project_id') or '')
                key=pid or str(Path(x['source']).resolve()).lower()
                if key in ids:
                    title=tr('JSON選択確認',self.language)
                    msg=(
                        '同じProject JSONが複数選択されています。\n\n'
                        f'重複：{x["project"]}\n'
                        f'建物：{x.get("label_ja") or x["label"]}\n\n'
                        '同じProject JSONは重複選択できません。別の建物Project JSONを選択してください。'
                        if self.language=='ja' else
                        'The same Project JSON is selected more than once.\n\n'
                        f'Duplicate: {x["project"]}\n'
                        f'Building: {x["label"]}\n\n'
                        'A Project JSON cannot be selected more than once. Select a different building Project JSON.'
                    )
                    return messagebox.showwarning(title,msg,parent=self)
                ids[key]=x
            self._assign_unique_labels()
            self.regional={x['label']:regional_projects(x['source']) for x in self.projects}
            self.audit_regional_co2_factors()
            incomplete=[x for x in self.projects if x.get('evaluation_status')!='complete']
            if incomplete:
                lines=[]
                for x in incomplete:
                    if self.language=='ja':
                        env='済' if x.get('evaluation_200_environment_done') else '未計算'
                        biz='済' if x.get('evaluation_200_business_done') else '未計算'
                        lines.append(f'・{self.disp(x["label"])}：200年環境={env} / 200年事業={biz}')
                    else:
                        env='Done' if x.get('evaluation_200_environment_done') else 'Not calculated'
                        biz='Done' if x.get('evaluation_200_business_done') else 'Not calculated'
                        lines.append(f'• {x["label"]}: 200-year environment={env} / 200-year business={biz}')
                msg=(
                    '次のProjectは02 Evaluationの200年結果が未完了です。\n\n' + '\n'.join(lines)
                    + '\n\n未計算値を0として比較しません。該当グラフ・集計では「未計算」として扱います。\n'
                      '02 Evaluationで計算・保存後、同じProject JSONを再読込してください。'
                    if self.language=='ja' else
                    'The following Projects do not have complete 200-year results from 02 Evaluation.\n\n' + '\n'.join(lines)
                    + '\n\nMissing values are never converted to zero. Affected graphs and summaries remain Not calculated.\n'
                      'Run and save the calculations in 02 Evaluation, then reload the same Project JSON.'
                )
                messagebox.showwarning(tr('02 Evaluation 未計算確認',self.language),msg,parent=self)
            # PATCH_003: warn once when the compared Projects do not share the
            # premises that make a comparison mean anything. Nothing is
            # changed or suppressed; the graphs still draw exactly as before.
            premise=[]
            yield_based=[x for x in self.projects if x.get('rent_derived_from_cost')]
            if yield_based:
                names='、'.join(self.disp(x['label']) for x in yield_based) if self.language=='ja' else ', '.join(self.disp(x['label']) for x in yield_based)
                rents=' / '.join(
                    f"{self.disp(x['label'])}: {x['resolved_annual_rent_per_m2']:,.0f}"
                    for x in yield_based if isinstance(x.get('resolved_annual_rent_per_m2'),(int,float))
                )
                if self.language=='ja':
                    premise.append(
                        '【家賃の前提】次のProjectは家賃を建設費から目標表面利回りで逆算しています。\n  '+names
                        +('\n  逆算後の年額家賃(円/㎡)：'+rents if rents else '')
                        +'\n  利回り固定のため単純投資回収年は建設費に依存せず、建設費の高いProjectほど家賃も高く設定されます。'
                        '\n  建物間の事業性を比較する場合は、Module 6で「市場家賃を直接入力」に切り替え、全Projectで同じ家賃を設定してください。'
                    )
                else:
                    premise.append(
                        '[Rent premise] The following Projects derive rent from construction cost at a target gross yield.\n  '+names
                        +('\n  Resolved annual rent per m2: '+rents if rents else '')
                        +'\n  With the yield fixed, simple payback does not depend on construction cost, and a more expensive Project is given proportionally higher rent.'
                        '\n  To compare buildings, switch Module 6 to "Enter market rent directly" and use the same rent for every Project.'
                    )
            basis={}
            for x in self.projects:
                basis.setdefault(str(x.get('price_basis_token') or 'unknown'),[]).append(self.disp(x['label']))
            if len(basis)>1:
                detail='\n'.join(f'  {k}: '+('、'.join(v) if self.language=='ja' else ', '.join(v)) for k,v in basis.items())
                if self.language=='ja':
                    premise.append(
                        '【単価根拠の前提】比較対象のProjectで建設費の単価根拠が揃っていません。\n'+detail
                        +'\n  AI概算単価は施工込み一本値、内蔵地域単価は材料/労務/機械の分離単価で、単価水準そのものが異なります。'
                        '\n  建設費差の一部は工法差ではなく価格根拠差です。全Projectを同じ根拠で値付けしてから比較してください。'
                    )
                else:
                    premise.append(
                        '[Price basis premise] The compared Projects were not priced on the same basis.\n'+detail
                        +'\n  An AI approximate-cost session returns installed all-in rates; the built-in regional estimate returns a material/labor/equipment split, at a different price level.'
                        '\n  Part of the cost difference is a price-origin difference, not a construction-method difference. Price every Project on one basis before comparing.'
                    )
            if premise:
                messagebox.showwarning(
                    tr('比較前提の確認',self.language),
                    '\n\n'.join(premise)
                    +('\n\nグラフと集計はそのまま表示します。値の書き換えや除外は行いません。'
                      if self.language=='ja' else
                      '\n\nGraphs and summaries are shown unchanged. No value is rewritten or excluded.'),
                    parent=self)

            # PATCH_004: saved-data consistency.  Each item below means a value
            # on screen does not come from the Project's current inputs.
            consistency=[]
            ja=(self.language=='ja')
            for x in self.projects:
                lines=[]
                for m in x.get('snapshot_envelope_mismatches') or []:
                    lines.append(
                        (f"  8760スナップショットの外皮が Module 2 と不一致（{m['component']}："
                         f"スナップショット U={m['snapshot_u_W_m2K']:.3f} × {m['snapshot_area_m2']:.2f}㎡ = {m['snapshot_conductance_W_K']:.1f} W/K ／ "
                         f"Module 2 U={m['module2_u_W_m2K']:.3f} × {m['module2_area_m2']:.2f}㎡ = {m['module2_conductance_W_K']:.1f} W/K）。"
                         "スナップショットは採用せず Module 2 の年間値に切り替えました。")
                        if ja else
                        (f"  8760 snapshot envelope disagrees with Module 2 ({m['component']}: "
                         f"snapshot U={m['snapshot_u_W_m2K']:.3f} x {m['snapshot_area_m2']:.2f} m2 = {m['snapshot_conductance_W_K']:.1f} W/K / "
                         f"Module 2 U={m['module2_u_W_m2K']:.3f} x {m['module2_area_m2']:.2f} m2 = {m['module2_conductance_W_K']:.1f} W/K). "
                         "The snapshot is not used; the Module 2 annual value is shown instead.")
                    )
                stale=x.get('stale_downstream_results') or []
                if stale:
                    pairs=sorted({(s['input_module'],s['result_module']) for s in stale})
                    names={'module2':'Module 2','module3':'Module 3','module4':'Module 4','module5':'Module 5','module6':'Module 6','module7':'Module 7'}
                    detail=', '.join(f"{names[a]}→{names[b]}" for a,b in pairs)
                    lines.append(
                        f"  入力より古い評価結果があります（{detail}）。02 Evaluation で再計算・保存が必要です。"
                        if ja else
                        f"  Evaluation results are older than their inputs ({detail}). Recalculate and save in 02 Evaluation."
                    )
                if x.get('currency_conflict'):
                    lines.append(
                        f"  通貨の不一致：Project識別情報は {x.get('declared_identity_currency')}、建設費・事業性は {x.get('currency')} で計算されています。"
                        f"表示は計算通貨（{x.get('currency')}）に合わせています。Module 0 の通貨設定を修正してください。"
                        if ja else
                        f"  Currency conflict: project identity says {x.get('declared_identity_currency')}, but cost and business results were calculated in {x.get('currency')}. "
                        f"Values are labelled in the calculation currency ({x.get('currency')}). Correct the currency in Module 0."
                    )
                if lines:
                    consistency.append(('・' if ja else '• ')+self.disp(x['label'])+'\n'+'\n'.join(lines))
            # PATCH_005: a comparison copy is only comparable once it has been
            # recalculated from the premise book, its source is unchanged, and
            # every copy shares one premise-book version and one rent premise.
            ja=(self.language=='ja')
            names={'source_missing':('元Projectが見つかりません','Source Project not found'),
                   'source_changed':('元Projectが更新されています。03 Compare でコピーを作り直してください。',
                                     'The source Project has changed. Rebuild the copies in 03 Compare.'),
                   'source_unreadable':('元Projectを読めません','Source Project cannot be read'),
                   'not_recalculated':('再計算されていません（01 Planning の Module 5 → 02 Evaluation の Module 6/7）',
                                       'Not recalculated (Module 5 in 01 Planning, then Modules 6/7 in 02 Evaluation)'),
                   'priced_with_other_version':('別の版の比較前提表で値付けされています',
                                                'Priced with a different premise-book version')}
            for x in self.projects:
                raw=x.get('raw') or {}
                lines=[]
                for issue in PB.verify_copy(raw):
                    text=names.get(issue.get('code'),(issue.get('code'),issue.get('code')))[0 if ja else 1]
                    extra=issue.get('module') or issue.get('path') or issue.get('found') or ''
                    lines.append(f"  {text}{(' : '+str(extra)) if extra else ''}")
                if lines:
                    consistency.append(('・' if ja else '• ')+self.disp(x['label'])+'\n'+'\n'.join(lines))
            for issue in PB.verify_group([x.get('raw') or {} for x in self.projects]):
                code=issue.get('code')
                if code=='different_premise_book_versions':
                    consistency.append(('・比較前提表の版が揃っていません：' if ja else '• Premise-book versions differ: ')
                                       +', '.join(issue.get('versions') or []))
                elif code=='different_rent_premises':
                    consistency.append(('・家賃の前提がコピー間で揃っていません。' if ja else '• The rent premise differs between copies.'))
                elif code=='mixed_copies_and_originals':
                    consistency.append(('・比較用コピーと元Projectが混在しています。どちらかに揃えてください。' if ja
                                        else '• Comparison copies and source Projects are mixed. Use one or the other.'))
            if consistency:
                messagebox.showwarning(
                    tr('保存データの整合性確認',self.language),
                    '\n\n'.join(consistency),
                    parent=self)

            legacy_tax=[self.disp(x['label']) for x in self.projects if x.get('cashflow_available') and not x.get('tax_excluded_from_cashflow')]
            if legacy_tax:
                msg=(
                    '次のJSONは「土地・建物関連税をCFから除外」の新方針が確認できません。\n' + '、'.join(legacy_tax)
                    + '\n\n最新の02 AZRAS EvaluationでModule 6を再計算・更新保存してください。'
                    if self.language=='ja' else
                    'The following JSON files do not confirm the current policy that land/building-related taxes are excluded from CF.\n' + ', '.join(legacy_tax)
                    + '\n\nRecalculate Module 6 in the latest 02 AZRAS Evaluation and save the updated Project JSON.'
                )
                messagebox.showwarning(tr('税金取扱いの確認',self.language),msg,parent=self)
        except Exception as e:return messagebox.showerror(tr('読込エラー',self.language),friendly_exception_text(e,self.language), parent=self)
        self.show_annual('energy');self.refresh_overview();self.refresh_comparisons();self.tabs.select(self.overview_tab)
    def val_at(self,s,year):
        # 正式時系列は指定年の値が存在するときだけ使用する。
        # 最終値の横持ち・補間・外挿は一切行わない。
        if not s:return None
        return next((v for y,v in s if y==year),None)
    def city_order(self):
        order=[]
        for rows in self.regional.values():
            for r in rows:
                c=r['city'] or r['country'] or '地域未設定'
                if c not in order:order.append(c)
        return order
    def audit_regional_co2_factors(self):
        """Check that every compared building uses the same grid factor in the same city."""
        if not self.regional:
            self.co2_factor_audit.config(text=tr('電力CO₂係数整合監査：比較未実行',self.language),foreground='#555')
            return True

        cities=self.city_order()
        problems=[]
        missing=[]
        for city in cities:
            vals=[]
            for building_label,rows in self.regional.items():
                row=next((r for r in rows if (r.get('city') or r.get('country') or '地域未設定')==city),None)
                if row is None:
                    continue
                v=row.get('electricity_co2_factor_kg_per_kWh')
                if v is None:
                    missing.append(f'{self.cdisp(city)}/{self.disp(building_label)}')
                else:
                    vals.append((building_label,float(v)))
            if len(vals)>=2:
                base=vals[0][1]
                if any(abs(v-base)>1e-12 for _,v in vals[1:]):
                    problems.append(self.cdisp(city)+': '+', '.join(f'{self.disp(m)}={v:.6g}' for m,v in vals))

        if problems:
            self.co2_factor_audit.config(
                text=(('電力CO₂係数整合監査：NG　同一地域で建物間の係数が不一致 → ' if self.language=='ja' else 'Grid CO₂ factor consistency audit: NG — factors differ between buildings in the same region → ')+' | '.join(problems)),
                foreground='#b00020'
            )
            return False
        if missing:
            self.co2_factor_audit.config(
                text=(('電力CO₂係数整合監査：要確認　係数未登録 → ' if self.language=='ja' else 'Grid CO₂ factor consistency audit: review required — factor not registered → ')+', '.join(missing)),
                foreground='#b26a00'
            )
            return False

        self.co2_factor_audit.config(
            text=tr('電力CO₂係数整合監査：OK　全地域で比較対象建物の地域係数が一致',self.language),
            foreground='#006400'
        )
        return True

    def show_annual(self,metric):
        self.audit_regional_co2_factors()
        self.annual_metric.set(metric);cities=self.city_order();methods=[p['label'] for p in self.projects]
        if metric=='energy':
            key='annual_energy';unit=tr('kWh/年',self.language);caption='年間エネルギー消費量 kWh/年'
        elif metric=='co2':
            key='annual_co2_t';unit=tr('t-CO₂/年',self.language);caption='年間CO₂排出量 t/年'
        else:
            key='electricity_co2_factor_kg_per_kWh';unit='kg-CO₂/kWh';caption='電力CO₂係数 kg-CO₂/kWh'
        self.annual_caption.config(text=(('表示：' if self.language=='ja' else 'Display: ')+tr(caption,self.language)))
        if metric=='energy':
            self.annual_basis.config(text=tr('算定根拠：春日井を含む全地域=各Project JSONのEPW 8760時間解析値　｜　参照元：regional_analysis.module10_snapshot',self.language))
        elif metric=='co2':
            self.annual_basis.config(text=tr('算定根拠：年間運用CO₂（建設・修繕・更新・解体イベントは含まない）　｜　全地域=各地域8760時間値×地域電力CO₂係数',self.language))
        else:
            self.annual_basis.config(text=tr('参照元：各地域Project JSON → regional_analysis.module10_snapshot.annual.electricity_co2_factor_kg_per_kWh　｜　係数の値・基準年・出典は今後の係数マスタで管理',self.language))
        values={}
        for m in methods:
            by={r['city'] or r['country'] or '地域未設定':r for r in self.regional.get(m,[])}
            values[m]=[by[c].get(key) if c in by else None for c in cities]
        self.matrix.render(cities,methods,values,'min',unit,city_text=self.cdisp,method_text=self.disp)
    def _primary_rows(self):
        # PATCH 06: the main building-to-building comparison follows each loaded
        # Project JSON exactly as saved.  Different buildings may have different
        # uses, layouts, scales, structures, methods, and locations.  Do not
        # silently replace a project's own results with the first project's city.
        # Standardized same-region comparison remains available separately in
        # the Global Regional Comparison screen.
        return tr('各Project所在地',self.language), list(self.projects)
    def _timeline_to_year(self,series,end):
        if not series:return []
        by=dict(series);start=0 if 0 in by else 1
        # グラフには毎年の正式値が必要。欠年が1つでもあれば表示しない。
        required=list(range(start,end+1))
        if any(y not in by for y in required):return []
        return [(y,by[y]) for y in required]
    def _validate_display_year(self,value,label):
        try:
            y=int(str(value).strip())
        except Exception:
            messagebox.showwarning(tr('年数入力',self.language),tr(f'{label}は1～200の整数で入力してください。',self.language), parent=self)
            return None
        if not 1 <= y <= 200:
            messagebox.showwarning(tr('年数入力',self.language),tr(f'{label}は1～200年の範囲で指定してください。',self.language), parent=self)
            return None
        return y
    def set_period_year(self,y):
        self.co2_year.set(y)
        self.cash_year.set(y)
        self.period_year_input.set(str(y))
        self.refresh_comparisons()

    def apply_period_year(self):
        y=self._validate_display_year(self.period_year_input.get(),'CO₂・CF共通表示年数')
        if y is not None:
            self.set_period_year(y)

    def _discounted_payback_year(self,timeline):
        if not timeline:return None
        prev=None
        for year,value in timeline:
            if prev is None and value>=0:return int(year)
            if prev is not None and prev[1]<0<=value:return int(year)
            prev=(year,value)
        return None

    def refresh_comparisons(self):
        if not self.projects:return
        city,primary=self._primary_rows()
        self.monthly_city_label.config(text=city)
        self.co2_city_label.config(text=city)
        self.invest_city_label.config(text=city)
        currencies=sorted({str(r.get('currency') or '') for r in primary if r.get('currency')})
        mixed_currency=len(currencies)>1

        # ① 月間エネルギー
        energy_series=[]
        for r in primary:
            monthly=r.get('monthly',{}).get('energy')
            if monthly:
                energy_series.append((self.disp(r['label']),list(enumerate(monthly))))
        self.p_energy.set_data(tr(f'{city} 建物別月間エネルギー消費量',self.language),tr('kWh/月',self.language),MONTHS_JA if self.language=='ja' else MONTHS_EN,energy_series)

        # ② 月間運用CO2 = 月間電力量 × 地域電力CO2係数
        monthly_co2_series=[]
        annual_monthly_co2={}
        for r in primary:
            monthly=r.get('monthly',{}).get('energy')
            factor=r.get('electricity_co2_factor_kg_per_kWh')
            if monthly and factor is not None:
                vals=[float(kwh)*float(factor)/1000.0 for kwh in monthly]
                monthly_co2_series.append((self.disp(r['label']),list(enumerate(vals))))
                annual_monthly_co2[r['label']]=sum(vals)
            else:
                annual_monthly_co2[r['label']]=None
        self.p_monthly_co2.set_data(tr(f'{city} 建物別月間CO₂排出量',self.language),tr('t-CO₂/月',self.language),MONTHS_JA if self.language=='ja' else MONTHS_EN,monthly_co2_series)

        # ③ 累積CO2
        cy=self.co2_year.get();co2_series=[]
        for r in primary:
            tl=self._timeline_to_year(r.get('co2'),cy)
            if tl:
                co2_series.append((self.disp(r['label']),[(y,val/1000.0) for y,val in tl]))
        self.p_co2.set_data(
            tr(f'{city} CO₂期間別累積排出量（0～{cy}年）',self.language),'t-CO₂',
            list(range(0,cy+1)),co2_series,tick_every=10,
            empty_message=tr('建設関係イベントを含む正式なCO₂時系列がありません。',self.language)
        )

        # ④ 単純投資回収
        # Module 6 の simple_payback_year と同じ「名目累積CF・初回0円超過」を使う。
        # 200年全体を描くと後年の大規模更新費で縦軸が数百億円規模となり、
        # 19年前後の初回回収点が視覚的に潰れるため、初回回収の確認に必要な
        # 範囲（最も遅い回収年 + 10年、最低30年）だけを拡大表示する。
        fy=self.cash_year.get()
        simple_years={}
        simple=[]
        for r in primary:
            full_tl=self._timeline_to_year(r.get('nominal_cashflow'),fy)
            yr=self._discounted_payback_year(full_tl)
            simple_years[r['label']]=yr
            simple.append((f"{self.disp(r['label'])}：{yr}年" if yr is not None else f"{self.disp(r['label'])}：{fy}年以内未回収") if self.language=='ja' else (f"{r['label']}: Year {yr}" if yr is not None else f"{r['label']}: not recovered within {fy} years"))
        self.simple_payback.config(text=(('単純投資回収年：' if self.language=='ja' else 'Simple payback year: ')+(' ／ '.join(simple))))

        recovered=[y for y in simple_years.values() if isinstance(y,int)]
        if recovered:
            simple_display_year=min(fy,max(30,max(recovered)+10))
        else:
            simple_display_year=min(fy,50)

        nominal_series=[]
        for r in primary:
            tl=self._timeline_to_year(r.get('nominal_cashflow'),simple_display_year)
            if tl:
                nominal_series.append((self.disp(r['label']),[(y,val) for y,val in tl]))
        currency=primary[0].get('currency') or 'JPY'
        if mixed_currency:
            self.p_nominal_cash.set_data(
                tr(f'{city} 単純投資回収',self.language), '—', list(range(0,simple_display_year+1)), [],
                tick_every=5,
                empty_message=tr('通貨が異なる建物の金額CFは、為替換算なしでは同一グラフ比較しません。回収年は上部表示で確認できます。',self.language),
                zero_line=True
            )
        else:
            self.p_nominal_cash.set_data(
                tr(f'{city} 単純投資回収（0～{simple_display_year}年・初回回収点拡大）',self.language),
                currency,list(range(0,simple_display_year+1)),nominal_series,
                tick_every=5,
                empty_message=tr('単純投資回収用の名目累積CFを作成できません。',self.language),
                zero_line=True
            )

        # ⑤ 現在価値CF
        fy=self.cash_year.get();cf_series=[]
        for r in primary:
            tl=self._timeline_to_year(r.get('cashflow'),fy)
            if tl:
                cf_series.append((self.disp(r['label']),[(y,val) for y,val in tl]))
        if mixed_currency:
            self.p_cash.set_data(
                tr(f'{city} 現在価値累積CF',self.language), '—', list(range(0,fy+1)), [], tick_every=10,
                empty_message=tr('通貨が異なる建物の現在価値CFは、為替換算なしでは同一グラフ比較しません。回収年は上部表示で確認できます。',self.language),
                zero_line=True
            )
        else:
            self.p_cash.set_data(
                tr(f'{city} 現在価値累積CF（0～{fy}年・終価除外・土地建物税別途）',self.language),
                currency,list(range(0,fy+1)),cf_series,tick_every=10,
                empty_message=tr('指定期間までの現在価値累積CFを作成できません。',self.language),
                zero_line=True
            )

        payback=[]
        for r in primary:
            tl=self._timeline_to_year(r.get('cashflow'),fy)
            yr=self._discounted_payback_year(tl)
            payback.append((f"{self.disp(r['label'])}：{yr}年" if yr is not None else f"{self.disp(r['label'])}：{fy}年以内未回収") if self.language=='ja' else (f"{r['label']}: Year {yr}" if yr is not None else f"{r['label']}: not recovered within {fy} years"))
        self.cash_payback.config(text=(('現在価値ベース回収：' if self.language=='ja' else 'Present-value recovery: ')+(' ／ '.join(payback))))

        # 合計表更新
        for t in (self.energy_summary,self.monthly_co2_summary,self.co2_summary,self.nominal_cash_summary,self.cash_summary):
            for x in t.get_children():t.delete(x)

        self.energy_summary.heading('value',text=tr('年間エネルギー消費量合計（kWh/年）',self.language))
        self.monthly_co2_summary.heading('value',text=tr('年間運用CO₂排出量合計（t-CO₂/年）',self.language))
        self.co2_summary.heading('value',text=tr(f'{cy}年累積CO₂（t-CO₂）',self.language))
        self.nominal_cash_summary.heading('value',text=tr('単純投資回収年',self.language))
        self.cash_summary.heading('value',text=tr(('通貨混在：回収年のみ比較' if mixed_currency else f'{fy}年現在価値累積CF（{currency}）'),self.language))

        for r in primary:
            self.energy_summary.insert('','end',values=(self.disp(r['label']),'―' if r.get('annual_energy') is None else f"{r['annual_energy']:,.1f}"))
            mc=annual_monthly_co2.get(r['label'])
            self.monthly_co2_summary.insert('','end',values=(self.disp(r['label']),tr('未計算',self.language) if mc is None else f'{mc:,.3f}'))

            cv=self.val_at(r.get('co2'),cy)
            self.co2_summary.insert('','end',values=(self.disp(r['label']),tr('未計算',self.language) if cv is None else f'{cv/1000:,.1f}'))

            sy=simple_years.get(r['label'])
            stext=(f'{sy}年' if sy is not None else f'{fy}年以内未回収') if self.language=='ja' else (f'Year {sy}' if sy is not None else f'Not recovered within {fy} years')
            self.nominal_cash_summary.insert('','end',values=(self.disp(r['label']),stext),tags=('nonnegative',))

            fv=self.val_at(r.get('cashflow'),fy)
            if mixed_currency:
                py=self._discounted_payback_year(self._timeline_to_year(r.get('cashflow'),fy))
                cf_text=(f'{py}年' if py is not None else f'{fy}年以内未回収') if self.language=='ja' else (f'Year {py}' if py is not None else f'Not recovered within {fy} years')
                cf_tag='nonnegative'
            else:
                cf_text=tr('未計算',self.language) if fv is None else f'{fv:,.0f}'
                cf_tag='nonnegative' if (fv is not None and fv>=0) else ('negative' if fv is not None else 'nonnegative')
            self.cash_summary.insert('','end',values=(self.disp(r['label']),cf_text),tags=(cf_tag,))

    def _default_compare_folder(self):
        candidates=[]
        for project in self.projects:
            src=project.get('source')
            if not src:continue
            p=Path(src).resolve()
            for parent in [p.parent,*p.parents]:
                if parent.name.lower()=='data':
                    candidates.append(parent/'比較')
                    break
        for c in candidates:
            if c.exists() and c.is_dir():
                return c
        return None

    def save_csv(self):
        if not self.projects:return messagebox.showinfo(tr('確認',self.language),tr('先に比較を実行してください。',self.language), parent=self)
        initialdir=self._default_compare_folder()
        if initialdir is None:
            messagebox.showinfo(tr('保存先確認',self.language),('標準保存先「Data\\比較」が見つかりません。\n保存先を指定してください。' if self.language=='ja' else 'The standard save folder Data\\Comparison was not found.\nPlease choose a save location.'), parent=self)
        p=filedialog.asksaveasfilename(
            initialdir=str(initialdir) if initialdir is not None else None,
            initialfile='AZRAS_Compare_Regional_Comparison.csv',
            defaultextension='.csv',
            filetypes=[('CSV','*.csv')]
        , parent=self)
        if not p:return
        cities=self.city_order()
        with open(p,'w',encoding='utf-8-sig',newline='') as f:
            w=csv.writer(f);w.writerow(([tr('指標',self.language),tr('建物',self.language)]+[self.cdisp(c) for c in cities]))
            for label,key in [
                (tr('年間エネルギー消費量 kWh/年',self.language),'annual_energy'),
                (tr('年間CO2排出量 t/年',self.language),'annual_co2_t'),
                (tr('電力CO2係数 kg-CO2/kWh',self.language),'electricity_co2_factor_kg_per_kWh')
            ]:
                for m,rows in self.regional.items():
                    by={r['city'] or r['country'] or '地域未設定':r for r in rows};w.writerow([label,self.disp(m)]+[by[c].get(key,'') if c in by else '' for c in cities])

            # Regional grid-factor consistency audit.
            audit=[]
            for c in cities:
                vals=[]
                for m,rows in self.regional.items():
                    by={r['city'] or r['country'] or '地域未設定':r for r in rows}
                    if c in by and by[c].get('electricity_co2_factor_kg_per_kWh') is not None:
                        vals.append(float(by[c]['electricity_co2_factor_kg_per_kWh']))
                if len(vals)<len(self.regional):
                    audit.append('未登録')
                elif max(vals)-min(vals)<=1e-12:
                    audit.append('OK')
                else:
                    audit.append('NG')
            w.writerow([tr('電力CO2係数 建物間整合監査',self.language),'']+[(x if self.language=='ja' else tr(x,self.language)) for x in audit])
            w.writerow([])
            w.writerow([tr('建物比較指標',self.language)])
            w.writerow([tr(x,self.language) for x in ['建物','用途','構造','工法','延床面積 m2','概算建設費','通貨','概算建設費/m2','年間エネルギー kWh','kWh/m2年','200年CO2 kg','200年CO2 kg/m2']])
            for row in self.projects:
                w.writerow([
                    row.get('project',''),
                    (row.get('building_use_ja') if self.language=='ja' else row.get('building_use','')) or row.get('building_use',''),
                    (row.get('structure_ja') if self.language=='ja' else row.get('structure','')) or row.get('structure',''),
                    (row.get('method_ja') if self.language=='ja' else row.get('method','')) or row.get('method',''),
                    row.get('gfa_m2',''),row.get('construction_cost',''),row.get('currency',''),row.get('construction_cost_per_m2',''),
                    row.get('annual_energy',''),row.get('annual_energy_per_m2',''),row.get('lifecycle_co2_200_kg',''),row.get('lifecycle_co2_200_per_m2_kg','')
                ])
        messagebox.showinfo(tr('保存完了',self.language),tr('比較表CSVを保存しました。',self.language), parent=self)
if __name__=='__main__':App().mainloop()