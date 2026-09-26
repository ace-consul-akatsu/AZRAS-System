from __future__ import annotations
import re
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from pathlib import Path
import cv2
from PIL import Image,ImageTk
from core.i18n import I18N
from services.legend_equipment_recognition_v9_2_4 import EQUIPMENT_LABELS,count_equipment,find_equipment_pages,load_symbol_library,render_pdf_pages,save_symbol_library
INPUT_BG="#fff4b8";AUTO_BG="#d9efff";RESULT_BG="#dff3df"

class LegendEquipmentApp(tk.Toplevel):
    def __init__(self,master,root_dir:Path,language='ja',pdf_path=''):
        super().__init__(master);self.root_dir=Path(root_dir);self.i18n=I18N(self.root_dir,language)
        self.pdf_path=tk.StringVar(value=pdf_path);self.pages=[];self.detected_pages=[];self.templates=[];self.analysis_regions={}
        self.page_index=0;self.threshold=tk.StringVar(value='0.78');self.variant_name=tk.StringVar(value='')
        self.zoom=0.55;self.photo=None;self.drag_start=None;self.selection_rectangle=None;self.last_selection=None;self.selection_mode='symbol';self.result=None
        self.mode_status=tk.StringVar(value=self.i18n.t('mode_symbol_status'))
        self.title(self.i18n.t('legend_equipment_title'));self.geometry('1700x980')
        self.transient(master)
        self.build()
        self.after(100,lambda:(self.lift(),self.focus_force()))
    def build(self):
        t=self.i18n.t
        top=ttk.LabelFrame(self,text=t('pdf'));top.pack(fill='x',padx=8,pady=4)
        tk.Entry(top,textvariable=self.pdf_path,bg=INPUT_BG,width=110).grid(row=0,column=0,padx=4,pady=4,sticky='ew')
        ttk.Button(top,text=t('select_pdf'),command=self.choose_pdf).grid(row=0,column=1,padx=3)
        ttk.Button(top,text=t('load_all_pdf_pages'),command=self.load_pdf).grid(row=0,column=2,padx=3);top.columnconfigure(0,weight=1)
        ttk.Label(self,text=t('legend_equipment_notice_v927'),foreground='#8b0000',wraplength=1640).pack(fill='x',padx=10,pady=2)
        controls=ttk.LabelFrame(self,text=t('legend_learning'));controls.pack(fill='x',padx=8,pady=4)
        ttk.Label(controls,text=t('drawing_page')).grid(row=0,column=0,padx=3);self.page_box=ttk.Combobox(controls,state='readonly',width=26);self.page_box.grid(row=0,column=1,padx=3);self.page_box.bind('<<ComboboxSelected>>',self.page_changed)
        ttk.Button(controls,text=t('zoom_out'),command=lambda:self.change_zoom(.8)).grid(row=0,column=2,padx=2)
        ttk.Button(controls,text=t('zoom_in'),command=lambda:self.change_zoom(1.25)).grid(row=0,column=3,padx=2)
        ttk.Button(controls,text=t('fit_page'),command=self.fit_page).grid(row=0,column=4,padx=2)
        ttk.Label(controls,text=t('equipment_type')).grid(row=0,column=5,padx=3)
        lk='ja' if self.i18n.language=='ja' else 'en';self.display_to_key={v[lk]:k for k,v in EQUIPMENT_LABELS.items()};self.key_to_display={v:k for k,v in self.display_to_key.items()}
        self.equipment_display=tk.StringVar(value=self.key_to_display['lighting']);ttk.Combobox(controls,textvariable=self.equipment_display,values=list(self.display_to_key),state='readonly',width=19).grid(row=0,column=6,padx=3)
        ttk.Label(controls,text=t('fixture_name_model')).grid(row=0,column=7,padx=3);tk.Entry(controls,textvariable=self.variant_name,bg=INPUT_BG,width=22).grid(row=0,column=8,padx=3)
        ttk.Label(controls,text=t('matching_threshold')).grid(row=0,column=9,padx=3);tk.Entry(controls,textvariable=self.threshold,bg=INPUT_BG,width=7).grid(row=0,column=10,padx=3)
        ttk.Button(controls,text=t('select_legend_symbol_mode'),command=lambda:self.set_mode('symbol')).grid(row=1,column=0,columnspan=2,padx=3,pady=3)
        ttk.Button(controls,text=t('register_selected_symbol'),command=self.register_symbol).grid(row=1,column=2,columnspan=2,padx=3)
        ttk.Button(controls,text=t('select_drawing_area_mode'),command=lambda:self.set_mode('region')).grid(row=1,column=4,columnspan=2,padx=3)
        ttk.Button(controls,text=t('register_drawing_area'),command=self.register_region).grid(row=1,column=6,columnspan=2,padx=3)
        ttk.Button(controls,text=t('run_symbol_count'),command=self.run_count).grid(row=1,column=8,columnspan=2,padx=3)
        ttk.Label(
            controls,
            textvariable=self.mode_status,
            foreground='#005a9c',
        ).grid(row=2,column=0,columnspan=11,padx=5,pady=(2,4),sticky='w')
        body=ttk.Panedwindow(self,orient='horizontal');body.pack(fill='both',expand=True,padx=8,pady=4)
        left=ttk.LabelFrame(body,text=t('legend_and_drawing'));right=ttk.LabelFrame(body,text=t('equipment_reading_result'));body.add(left,weight=5);body.add(right,weight=3)
        self.canvas=tk.Canvas(left,bg='white');xs=ttk.Scrollbar(left,orient='horizontal',command=self.canvas.xview);ys=ttk.Scrollbar(left,orient='vertical',command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=xs.set,yscrollcommand=ys.set);self.canvas.grid(row=0,column=0,sticky='nsew');xs.grid(row=1,column=0,sticky='ew');ys.grid(row=0,column=1,sticky='ns');left.rowconfigure(0,weight=1);left.columnconfigure(0,weight=1)
        self.canvas.bind('<ButtonPress-1>',self.begin_selection);self.canvas.bind('<B1-Motion>',self.update_selection);self.canvas.bind('<ButtonRelease-1>',self.end_selection);self.canvas.bind('<Control-MouseWheel>',self.mouse_zoom)
        notebook=ttk.Notebook(right);notebook.pack(fill='both',expand=True,padx=4,pady=4)
        ptab=ttk.Frame(notebook);ttab=ttk.Frame(notebook);rtab=ttk.Frame(notebook);notebook.add(ptab,text=t('analysis_pages_areas'));notebook.add(ttab,text=t('registered_symbols'));notebook.add(rtab,text=t('count_result'))
        ttk.Label(ptab,text=t('select_pages_for_count')).pack(anchor='w',padx=5,pady=3)
        self.page_list=tk.Listbox(ptab,selectmode='extended',exportselection=False,height=15);self.page_list.pack(fill='x',padx=5,pady=3)
        pb=ttk.Frame(ptab);pb.pack(fill='x');ttk.Button(pb,text=t('select_detected_pages'),command=self.select_detected).pack(side='left',padx=3);ttk.Button(pb,text=t('select_all_pages'),command=self.select_all).pack(side='left',padx=3)
        self.region_tree=ttk.Treeview(ptab,columns=('page','rect'),show='headings');self.region_tree.heading('page',text=t('drawing_page'));self.region_tree.heading('rect',text=t('drawing_area'));self.region_tree.column('page',width=80);self.region_tree.column('rect',width=300);self.region_tree.pack(fill='both',expand=True,padx=5,pady=5)
        ttk.Button(ptab,text=t('delete_selected_area'),command=self.delete_region).pack(pady=3)
        self.template_tree=ttk.Treeview(ttab,columns=('category','variant','page','threshold','rect'),show='headings')
        for c,h,w in [('category',t('equipment_type'),120),('variant',t('fixture_name_model'),180),('page',t('drawing_page'),60),('threshold',t('matching_threshold'),80),('rect',t('selected_range'),220)]:self.template_tree.heading(c,text=h);self.template_tree.column(c,width=w)
        self.template_tree.pack(fill='both',expand=True,padx=5,pady=5)
        tb=ttk.Frame(ttab);tb.pack(fill='x');ttk.Button(tb,text=t('delete_selected_template'),command=self.delete_template).pack(side='left',padx=3);ttk.Button(tb,text=t('save_symbol_library'),command=self.save_library).pack(side='left',padx=3);ttk.Button(tb,text=t('load_symbol_library'),command=self.load_library).pack(side='left',padx=3)
        self.result_tree=ttk.Treeview(rtab,columns=('category','variant','quantity','basis'),show='headings')
        for c,h,w in [('category',t('equipment_type'),130),('variant',t('fixture_name_model'),200),('quantity',t('quantity'),80),('basis',t('basis'),220)]:self.result_tree.heading(c,text=h);self.result_tree.column(c,width=w)
        self.result_tree.pack(fill='both',expand=True,padx=5,pady=5);ttk.Button(rtab,text=t('apply_equipment_counts'),command=self.apply_to_parent).pack(pady=5)
    def choose_pdf(self):
        p=filedialog.askopenfilename(filetypes=[('PDF','*.pdf')]);
        if p:self.pdf_path.set(p)
    def load_pdf(self):
        if not self.pdf_path.get():return
        try:
            self.pages=render_pdf_pages(self.pdf_path.get(),dpi=180);self.detected_pages=find_equipment_pages(self.pdf_path.get());self.analysis_regions={}
            vals=[];self.page_list.delete(0,'end')
            for i in range(len(self.pages)):
                mark=' ★' if i in self.detected_pages else '' ;label=f'{self.i18n.t("page")} {i+1}{mark}';vals.append(label);self.page_list.insert('end',label)
            self.page_box['values']=vals;self.page_box.current(0);self.page_index=0;self.select_detected();self.fit_page()
        except Exception as e:messagebox.showerror('Error',str(e),parent=self)
    def page_changed(self,_e=None):self.page_index=max(0,self.page_box.current());self.show_page()
    def selected_pages(self):return list(self.page_list.curselection())
    def select_detected(self):
        self.page_list.selection_clear(0,'end')
        for i in (self.detected_pages or range(len(self.pages))):self.page_list.selection_set(i)
    def select_all(self):self.page_list.selection_set(0,'end')
    def fit_page(self):
        if not self.pages:return
        self.update_idletasks();h,w=self.pages[self.page_index].shape[:2];cw=max(300,self.canvas.winfo_width()-20);ch=max(300,self.canvas.winfo_height()-20);self.zoom=min(cw/w,ch/h);self.show_page()
    def change_zoom(self,f):self.zoom=max(.12,min(4.0,self.zoom*f));self.show_page()
    def mouse_zoom(self,e):self.change_zoom(1.15 if e.delta>0 else .87);return 'break'
    def show_page(self):
        if not self.pages:return
        im=self.pages[self.page_index];display=cv2.resize(im,None,fx=self.zoom,fy=self.zoom,interpolation=cv2.INTER_AREA if self.zoom<1 else cv2.INTER_CUBIC);rgb=cv2.cvtColor(display,cv2.COLOR_BGR2RGB);pil=Image.fromarray(rgb);self.photo=ImageTk.PhotoImage(pil);self.canvas.delete('all');self.canvas.create_image(0,0,image=self.photo,anchor='nw');self.canvas.configure(scrollregion=(0,0,pil.width,pil.height));self.draw_registered_regions();self.last_selection=None
    def draw_registered_regions(self):
        for r in self.analysis_regions.get(self.page_index,[]):self.canvas.create_rectangle(*(v*self.zoom for v in r),outline='blue',width=3)
    def set_mode(self,m):
        self.selection_mode=m
        self.last_selection=None
        self.mode_status.set(
            self.i18n.t('mode_symbol_status' if m=='symbol' else 'mode_region_status')
        )
        self.lift()
        self.focus_force()
    def begin_selection(self,e):
        x=self.canvas.canvasx(e.x);y=self.canvas.canvasy(e.y);self.drag_start=(x,y)
        if self.selection_rectangle:self.canvas.delete(self.selection_rectangle)
        self.selection_rectangle=self.canvas.create_rectangle(x,y,x,y,outline='red' if self.selection_mode=='symbol' else 'blue',width=3)
    def update_selection(self,e):
        if self.drag_start:self.canvas.coords(self.selection_rectangle,self.drag_start[0],self.drag_start[1],self.canvas.canvasx(e.x),self.canvas.canvasy(e.y))
    def end_selection(self,e):
        if not self.drag_start:return
        x,y=self.canvas.canvasx(e.x),self.canvas.canvasy(e.y);x1,y1=self.drag_start;self.last_selection=(int(min(x1,x)/self.zoom),int(min(y1,y)/self.zoom),int(max(x1,x)/self.zoom),int(max(y1,y)/self.zoom));self.drag_start=None
    def register_symbol(self):
        if not self.last_selection or self.selection_mode!='symbol':messagebox.showwarning('Notice',self.i18n.t('select_symbol_rectangle'),parent=self);return
        cat=self.display_to_key[self.equipment_display.get()];name=self.variant_name.get().strip() or f'{self.equipment_display.get()} {1+sum(1 for t in self.templates if t["equipment_key"]==cat)}';variant=f'{cat}_{len(self.templates)+1}'
        self.templates.append({'equipment_key':cat,'equipment_name':self.equipment_display.get(),'variant_id':variant,'variant_name':name,'source_page':self.page_index,'rect_px':list(self.last_selection),'threshold':float(self.threshold.get())});self.refresh_templates()
    def register_region(self):
        if not self.last_selection or self.selection_mode!='region':messagebox.showwarning('Notice',self.i18n.t('select_drawing_rectangle'),parent=self);return
        self.analysis_regions.setdefault(self.page_index,[]).append(list(self.last_selection));self.refresh_regions();self.show_page()
    def refresh_regions(self):
        for i in self.region_tree.get_children():self.region_tree.delete(i)
        n=0
        for p,regions in sorted(self.analysis_regions.items()):
            for r in regions:self.region_tree.insert('', 'end',iid=str(n),values=(p+1,','.join(map(str,r))),tags=(str(p),str(regions.index(r))));n+=1
    def delete_region(self):
        sel=self.region_tree.selection()
        if not sel:return
        vals=self.region_tree.item(sel[0],'values');p=int(vals[0])-1;rect=[int(v) for v in str(vals[1]).split(',')];self.analysis_regions[p].remove(rect)
        if not self.analysis_regions[p]:del self.analysis_regions[p]
        self.refresh_regions();self.show_page()
    def refresh_templates(self):
        for i in self.template_tree.get_children():self.template_tree.delete(i)
        for i,t in enumerate(self.templates):self.template_tree.insert('', 'end',iid=str(i),values=(t['equipment_name'],t['variant_name'],t['source_page']+1,t['threshold'],','.join(map(str,t['rect_px']))))
    def delete_template(self):
        for i in sorted((int(x) for x in self.template_tree.selection()),reverse=True):del self.templates[i]
        self.refresh_templates()
    def save_library(self):
        if not self.templates:return
        p=filedialog.asksaveasfilename(defaultextension='.json',filetypes=[('JSON','*.json')]);
        if p:save_symbol_library(p,self.templates)
    def load_library(self):
        p=filedialog.askopenfilename(filetypes=[('JSON','*.json')]);
        if p:self.templates=load_symbol_library(p);self.refresh_templates()
    def run_count(self):
        pages=self.selected_pages()
        if not self.templates:messagebox.showwarning('Notice',self.i18n.t('register_legend_first'),parent=self);return
        missing=[p+1 for p in pages if not self.analysis_regions.get(p)]
        if missing:messagebox.showwarning('Notice',self.i18n.t('drawing_area_required')+' '+','.join(map(str,missing)),parent=self);return
        try:self.result=count_equipment(self.pages,self.templates,self.analysis_regions,pages);self.show_result()
        except Exception as e:messagebox.showerror('Error',str(e),parent=self)
    def show_result(self):
        for i in self.result_tree.get_children():self.result_tree.delete(i)
        if not self.result:return
        lk='ja' if self.i18n.language=='ja' else 'en'
        for d in self.result['details']:
            category=EQUIPMENT_LABELS.get(d['equipment_key'],{}).get(lk,d['equipment_key']);self.result_tree.insert('', 'end',values=(category,d['variant_name'],d['count'],self.i18n.t('legend_region_matching')))
    def apply_to_parent(self):
        if self.result and callable(getattr(self.master,'apply_recognized_equipment',None)):self.master.apply_recognized_equipment(self.result);messagebox.showinfo('OK',self.i18n.t('equipment_counts_applied'),parent=self)
