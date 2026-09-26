from __future__ import annotations
import csv,tkinter as tk
from pathlib import Path
from tkinter import filedialog,messagebox,ttk
from batch_analysis.engine import run_batch
from core.i18n import I18N
from core.ui_style import apply_common_style

class BatchLocationAnalysisApp(tk.Toplevel):
    def __init__(self,master,root_dir:Path,language='ja',project_context=None):
        super().__init__(master); self.root_dir=Path(root_dir); self.i18n=I18N(self.root_dir,language); self.base_projects=[]; self.output_dir=tk.StringVar(); self.status=tk.StringVar(); self.title(self.t('title')); self.geometry('1180x820'); self.minsize(980,680); apply_common_style(self); self.build()
    def t(self,k):
        ja={'title':'一括地域・構造解析','notice':'保存済みの基準Project JSONを複数選び、地点を複数行登録すると、構造数×地点数のProject JSONを自動生成・保存します。','bases':'基準構造Project JSON（最大7件）','add':'JSONを追加','remove':'選択削除','locations':'地点一覧：1行につき 地点名,国,都市,緯度,経度','sample':'Tokyo,日本,東京,35.6762,139.6503\nLondon,United Kingdom,London,51.5074,-0.1278\nParis,France,Paris,48.8566,2.3522','csv_load':'地点CSV読込','output':'保存先フォルダー','select_output':'保存先選択','run':'一括解析・自動保存を開始','done':'一括解析が完了しました。','error':'入力内容を確認してください。','no_base':'基準Project JSONを1件以上選択してください。','no_location':'地点を1件以上入力してください。','no_output':'保存先フォルダーを選択してください。','status_ready':'待機中'}
        en={'title':'Batch Location and Structure Analysis','notice':'Select multiple base Project JSON files and enter multiple locations. The app automatically generates and saves structure-count × location-count Project JSON cases.','bases':'Base Structure Project JSONs (maximum 7)','add':'Add JSON','remove':'Remove Selected','locations':'Locations: one line per Name,Country,City,Latitude,Longitude','sample':'Tokyo,Japan,Tokyo,35.6762,139.6503\nLondon,United Kingdom,London,51.5074,-0.1278\nParis,France,Paris,48.8566,2.3522','csv_load':'Load Location CSV','output':'Output Folder','select_output':'Select Output','run':'Run Batch Analysis and Auto-Save','done':'Batch analysis completed.','error':'Check the input data.','no_base':'Select at least one base Project JSON.','no_location':'Enter at least one location.','no_output':'Select an output folder.','status_ready':'Ready'}
        return (ja if self.i18n.language=='ja' else en).get(k,k)
    def build(self):
        o=ttk.Frame(self,padding=12); o.pack(fill='both',expand=True); ttk.Label(o,text=self.t('title'),font=('Yu Gothic UI',18,'bold')).pack(fill='x'); ttk.Label(o,text=self.t('notice'),foreground='#8b0000',wraplength=1120).pack(fill='x',pady=(4,10))
        b=ttk.LabelFrame(o,text=self.t('bases')); b.pack(fill='x',pady=5); row=ttk.Frame(b); row.pack(fill='x',padx=5,pady=4); ttk.Button(row,text=self.t('add'),command=self.add_projects).pack(side='left',padx=4); ttk.Button(row,text=self.t('remove'),command=self.remove_projects).pack(side='left',padx=4); self.base_list=tk.Listbox(b,height=7,selectmode='extended'); self.base_list.pack(fill='x',padx=6,pady=5)
        l=ttk.LabelFrame(o,text=self.t('locations')); l.pack(fill='both',expand=True,pady=5); ttk.Button(l,text=self.t('csv_load'),command=self.load_csv).pack(anchor='e',padx=5,pady=4); self.location_text=tk.Text(l,height=12,wrap='none'); self.location_text.pack(fill='both',expand=True,padx=6,pady=5); self.location_text.insert('1.0',self.t('sample'))
        f=ttk.LabelFrame(o,text=self.t('output')); f.pack(fill='x',pady=5); ttk.Entry(f,textvariable=self.output_dir).pack(side='left',fill='x',expand=True,padx=6,pady=5); ttk.Button(f,text=self.t('select_output'),command=self.select_output).pack(side='left',padx=4)
        ttk.Button(o,text=self.t('run'),command=self.run,style='Primary.TButton').pack(pady=10); ttk.Label(o,textvariable=self.status).pack(fill='x'); self.status.set(self.t('status_ready'))
    def add_projects(self):
        for p in filedialog.askopenfilenames(parent=self,title=self.t('add'),filetypes=[('Project JSON','*.json'),('All files','*.*')]):
            if p not in self.base_projects and len(self.base_projects)<7: self.base_projects.append(p); self.base_list.insert('end',p)
    def remove_projects(self):
        for i in reversed(self.base_list.curselection()): self.base_list.delete(i); del self.base_projects[i]
    def load_csv(self):
        p=filedialog.askopenfilename(parent=self,title=self.t('csv_load'),filetypes=[('CSV','*.csv'),('All files','*.*')]);
        if not p:return
        rows=[]
        with open(p,newline='',encoding='utf-8-sig') as f:
            for r in csv.DictReader(f): rows.append(','.join([r.get('name',r.get('地点名','')),r.get('country',r.get('国','')),r.get('city',r.get('都市','')),r.get('latitude',r.get('緯度','')),r.get('longitude',r.get('経度',''))]))
        self.location_text.delete('1.0','end'); self.location_text.insert('1.0','\n'.join(rows))
    def select_output(self):
        p=filedialog.askdirectory(parent=self,title=self.t('select_output'));
        if p:self.output_dir.set(p)
    def parse_locations(self):
        out=[]
        for raw in self.location_text.get('1.0','end').splitlines():
            if not raw.strip():continue
            a=[x.strip() for x in raw.split(',')]
            if len(a)<5:raise ValueError(raw)
            out.append({'name':a[0],'country':a[1],'city':a[2],'latitude':float(a[3]),'longitude':float(a[4])})
        return out
    def run(self):
        if not self.base_projects:return messagebox.showwarning(self.t('title'),self.t('no_base'),parent=self)
        if not self.output_dir.get().strip():return messagebox.showwarning(self.t('title'),self.t('no_output'),parent=self)
        try:
            locs=self.parse_locations()
            if not locs:return messagebox.showwarning(self.t('title'),self.t('no_location'),parent=self)
            m=run_batch(self.base_projects,locs,self.output_dir.get()); self.status.set(f"{m.get('generated_case_count',0)} / {m.get('expected_case_count',0)}"); messagebox.showinfo(self.t('title'),f"{self.t('done')}\n{m.get('generated_case_count',0)} cases\n{m.get('comparison_csv','')}",parent=self)
        except Exception as e:messagebox.showerror(self.t('title'),f"{self.t('error')}\n{e}",parent=self)
