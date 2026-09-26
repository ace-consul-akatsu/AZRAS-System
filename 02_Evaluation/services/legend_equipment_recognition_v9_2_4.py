from __future__ import annotations
from pathlib import Path
from typing import Any
import json
import cv2
import fitz
import numpy as np

EQUIPMENT_LABELS = {
    "lighting": {"ja": "照明", "en": "Lighting"},
    "outlets": {"ja": "コンセント", "en": "Outlets"},
    "air_conditioning": {"ja": "エアコン", "en": "Air Conditioning"},
    "ventilation": {"ja": "換気扇", "en": "Ventilation"},
    "refrigerator": {"ja": "冷蔵庫", "en": "Refrigerator"},
    "distribution_board": {"ja": "分電盤", "en": "Distribution Board"},
    "emergency_light": {"ja": "非常灯", "en": "Emergency Light"},
    "exit_sign": {"ja": "誘導灯", "en": "Exit Sign"},
    "detector": {"ja": "感知器", "en": "Detector"},
    "lan": {"ja": "LAN", "en": "LAN"},
    "tv": {"ja": "TV", "en": "TV"},
    "telephone": {"ja": "TEL", "en": "Telephone"},
    "other": {"ja": "その他", "en": "Other"},
}

def render_pdf_pages(pdf_path: str | Path, dpi: int = 180) -> list[np.ndarray]:
    doc=fitz.open(str(pdf_path)); matrix=fitz.Matrix(dpi/72.0,dpi/72.0); pages=[]
    for page in doc:
        pix=page.get_pixmap(matrix=matrix,alpha=False)
        image=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,pix.n)
        image=cv2.cvtColor(image,cv2.COLOR_RGBA2BGR if pix.n==4 else cv2.COLOR_RGB2BGR)
        pages.append(image)
    return pages

def find_equipment_pages(pdf_path: str | Path) -> list[int]:
    doc=fitz.open(str(pdf_path)); keys=("電気設備","設備平面図","照明","コンセント","換気","エアコン","凡例","equipment","electrical","power")
    return [i for i,p in enumerate(doc) if any(k.lower() in p.get_text('text').lower() for k in keys)]

def preprocess_symbol(image: np.ndarray) -> np.ndarray:
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY) if image.ndim==3 else image
    gray=cv2.GaussianBlur(gray,(3,3),0)
    _,binary=cv2.threshold(gray,210,255,cv2.THRESH_BINARY_INV)
    return binary

def _nms(points,width,height,overlap_threshold=0.30):
    boxes=sorted([[x,y,x+width,y+height,s] for x,y,s in points],key=lambda b:b[4],reverse=True); kept=[]
    while boxes:
        cur=boxes.pop(0); kept.append(cur); rem=[]
        for b in boxes:
            xx1=max(cur[0],b[0]); yy1=max(cur[1],b[1]); xx2=min(cur[2],b[2]); yy2=min(cur[3],b[3])
            inter=max(0,xx2-xx1)*max(0,yy2-yy1); union=(cur[2]-cur[0])*(cur[3]-cur[1])+(b[2]-b[0])*(b[3]-b[1])-inter
            if (inter/union if union else 0)<overlap_threshold: rem.append(b)
        boxes=rem
    return [(int(b[0]),int(b[1]),float(b[4])) for b in kept]

def match_template_in_region(page_image,template_image,region,threshold=0.78):
    x1,y1,x2,y2=[int(v) for v in region]; h,w=page_image.shape[:2]
    x1,x2=sorted((max(0,x1),min(w,x2))); y1,y2=sorted((max(0,y1),min(h,y2)))
    area=page_image[y1:y2,x1:x2]
    page=preprocess_symbol(area); templ=preprocess_symbol(template_image); th,tw=templ.shape[:2]
    if th<3 or tw<3 or th>page.shape[0] or tw>page.shape[1]: return []
    score_map=cv2.matchTemplate(page,templ,cv2.TM_CCOEFF_NORMED)
    ys,xs=np.where(score_map>=threshold)
    pts=_nms([(int(x),int(y),float(score_map[y,x])) for x,y in zip(xs,ys)],tw,th)
    return [{"x":x+x1,"y":y+y1,"width":tw,"height":th,"score":s} for x,y,s in pts]

def count_equipment(pages,templates,analysis_regions,page_indices=None):
    if page_indices is None: page_indices=sorted(analysis_regions)
    totals={}; totals_by_category={}; details=[]
    for ti,t in enumerate(templates):
        sp=int(t['source_page']); x1,y1,x2,y2=[int(v) for v in t['rect_px']]; source=pages[sp]
        crop=source[min(y1,y2):max(y1,y2),min(x1,x2):max(x1,x2)]
        if crop.size==0: continue
        category=t['equipment_key']; variant=t.get('variant_id') or f'{category}_{ti+1}'
        name=t.get('variant_name') or t.get('equipment_name') or variant; threshold=float(t.get('threshold',.78))
        total=0; page_results=[]
        for pi in page_indices:
            matches=[]
            for ri,region in enumerate(analysis_regions.get(pi,[])):
                found=match_template_in_region(pages[pi],crop,region,threshold)
                for m in found:m['region_index']=ri+1
                matches.extend(found)
            # remove duplicates across overlapping registered regions
            if matches:
                pts=_nms([(m['x'],m['y'],m['score']) for m in matches],crop.shape[1],crop.shape[0])
                matches=[{"x":x,"y":y,"width":crop.shape[1],"height":crop.shape[0],"score":s} for x,y,s in pts]
            total+=len(matches); page_results.append({'page':pi+1,'count':len(matches),'matches':matches})
        totals[variant]=total; totals_by_category[category]=totals_by_category.get(category,0)+total
        details.append({'variant_id':variant,'variant_name':name,'equipment_key':category,'equipment_name':t.get('equipment_name',category),'threshold':threshold,'count':total,'pages':page_results})
    return {'method':'legend_template_matching_with_registered_drawing_regions','totals':totals,'totals_by_category':totals_by_category,'details':details,'analysis_regions':{str(k):v for k,v in analysis_regions.items()}}

def save_symbol_library(path,templates):
    Path(path).write_text(json.dumps({'version':'2.0','templates':templates},ensure_ascii=False,indent=2),encoding='utf-8')

def load_symbol_library(path):
    return list(json.loads(Path(path).read_text(encoding='utf-8')).get('templates',[]))
