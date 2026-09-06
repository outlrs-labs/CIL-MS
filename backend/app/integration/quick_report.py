"""Deterministic multi-file report generation for the fast Analyse path."""
import csv
import hashlib
import json
import textwrap
import time
import zipfile
from collections import Counter
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from PIL import Image, ImageDraw, ImageFont

from .repository import PRODUCTION, TECHNICAL, atomic_json
from .report_templates import load_report_template

PARAMETERS={
 'production_offtake':['Production','Off-take','Dispatch','Stock balance'],
 'washery_operations':['Raw coal feed','Washed output','Yield','Plant utilisation'],
 'environmental_compliance':['Compliance status','Clearance conditions','Monitoring coverage','Exceptions'],
 'financial':['Revenue','Operating cost','Variance','Period trend'],
 'operational_statistics':['Output','Productivity','Availability','Operational variance'],
 'annual':['Annual coverage','Performance trend','Material changes','Key observations'],
 'land_reclamation':['Area reclaimed','Plantation progress','Survival rate','Site coverage'],
 'geological_exploration':['Exploration coverage','Resources assessed','Drilling progress','Data confidence'],
 'hydrology_groundwater':['Water levels','Recharge trend','Extraction','Monitoring coverage'],
 'project_feasibility':['Scope','Schedule','Cost indicators','Key risks'],
 'specialized_surveys':['Survey coverage','Observations','Variance','Data quality'],
}

def _font(size,bold=False):
 try:return ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Bold.ttf' if bold else '/System/Library/Fonts/Supplemental/Arial.ttf',size)
 except OSError:
  try:return ImageFont.load_default(size=size)
  except TypeError:return ImageFont.load_default()

def _csv_profile(path):
 rows=0;numeric=Counter();sums=Counter()
 try:
  with path.open('r',encoding='utf-8-sig',errors='replace',newline='') as source:
   reader=csv.reader(source);headers=next(reader,[])
   for row in reader:
    rows+=1
    if rows>10000:break
    for index,value in enumerate(row[:50]):
     try:number=float(value.replace(',','').strip())
     except (ValueError,AttributeError):continue
     name=headers[index].strip() if index<len(headers) and headers[index].strip() else f'Column {index+1}'
     numeric[name]+=1;sums[name]+=number
  averages=[(name,sums[name]/count) for name,count in numeric.most_common(6)]
  return {'rows_sampled':min(rows,10000),'columns':len(headers),'averages':averages}
 except (OSError,csv.Error):return {'rows_sampled':0,'columns':0,'averages':[]}

def _bar(draw,x,y,width,label,value,maximum,color='#0f62fe'):
 draw.text((x,y),label[:34],font=_font(20),fill='#262626')
 draw.rounded_rectangle((x,y+32,x+width,y+58),4,fill='#e8eef8')
 fill=0 if maximum<=0 else max(4,int(width*value/maximum))
 draw.rounded_rectangle((x,y+32,x+fill,y+58),4,fill=color)
 draw.text((x+width+16,y+31),f'{value:,.0f}',font=_font(18,True),fill='#262626')

def generate(repo,owner,title,period,target_entity,target_family,entries,source=None):
 if not entries:raise HTTPException(422,'Select at least one source file.')
 family_name=({**TECHNICAL,**PRODUCTION} if target_entity=='CMPDI' else PRODUCTION).get(target_family,{}).get('name',target_family.replace('_',' ').title())
 profiles=[];total_bytes=0
 for entry in entries:
  path=(repo.root/entry['relative_path']).resolve()
  if not path.is_relative_to(repo.root) or not path.is_file() or path.is_symlink():raise HTTPException(422,'A selected source is no longer available.')
  profile=_csv_profile(path) if path.suffix.lower()=='.csv' else {'rows_sampled':0,'columns':0,'averages':[]}
  profiles.append({'name':entry['name'],'entity':entry['entity'],'family':entry['family'],'bytes':path.stat().st_size,**profile})
  total_bytes+=path.stat().st_size

 rid=str(uuid4());folder=repo.root/target_entity/target_family/'report_generated'/rid
 if not folder.resolve().is_relative_to(repo.root):raise HTTPException(403,'Unsafe report destination.')
 folder.mkdir(parents=True)
 template=load_report_template(target_entity,target_family)
 parameters=template['parameters'] or PARAMETERS.get(target_family,['Coverage','Source volume','Observed values','Data quality'])
 metrics=[('Files combined',len(profiles)),('Subsidiaries',len(set(x['entity'] for x in profiles))),('Rows sampled',sum(x['rows_sampled'] for x in profiles)),('Source size (KB)',round(total_bytes/1024))]
 numeric=[]
 for item in profiles:
  numeric.extend((f"{item['name']}: {name}",value) for name,value in item['averages'])
 numeric=sorted(numeric,key=lambda pair:abs(pair[1]),reverse=True)[:5]
 created=time.time()
 lines=[f'# {title}','',f'**Report family:** {family_name}',f'**Period / project:** {period or "Not specified"}',f'**Generated:** {time.strftime("%d %b %Y, %H:%M",time.localtime(created))}','','## Executive summary','',f'This draft combines {len(profiles)} selected source file(s) from {len(set(x["entity"] for x in profiles))} subsidiary or reporting entity. It is intended for review before CMPDI submission.','','## Report parameters','']+[f'- {value}' for value in parameters]+['','## Source observations','']
 lines += [f"- **{item['name']}** — {item['entity']} · {item['rows_sampled']:,} sampled rows · {item['columns']} columns" for item in profiles]
 if numeric:lines+=['','## Numeric indicators','']+[f'- {name}: {value:,.2f}' for name,value in numeric]
 lines+=['','## Review note','','Figures are generated from the selected source files. Review units, reporting periods and source completeness before approval.']
 markdown='\n'.join(lines)
 (folder/'report.md').write_text(markdown,encoding='utf8')

 image=Image.new('RGB',(1240,1754),'white');draw=ImageDraw.Draw(image)
 draw.rectangle((0,0,1240,18),fill='#198038');draw.text((72,72),'CIL REPORTING WORKSPACE',font=_font(18,True),fill='#198038')
 y=120
 for line in textwrap.wrap(title,48):
  draw.text((72,y),line,font=_font(38,True),fill='#262626');y+=48
 draw.text((72,y+8),f'{family_name}  ·  {period or "Period not specified"}',font=_font(20),fill='#6f6f6f');y+=80
 draw.line((72,y,1168,y),fill='#d8d8d8',width=2);y+=36
 box_width=250
 for index,(label,value) in enumerate(metrics):
  x=72+index*278;draw.rounded_rectangle((x,y,x+box_width,y+112),8,fill='#f4f4f4',outline='#dedede')
  draw.text((x+18,y+18),label,font=_font(17),fill='#6f6f6f');draw.text((x+18,y+54),f'{value:,}',font=_font(30,True),fill='#262626')
 y+=155;draw.text((72,y),'Source coverage',font=_font(27,True),fill='#262626');y+=50
 counts=Counter(x['entity'] for x in profiles);maximum=max(counts.values(),default=1)
 for label,value in counts.most_common(6):_bar(draw,72,y,660,label,value,maximum,'#198038');y+=82
 y+=18;draw.text((72,y),'Rows sampled by file',font=_font(27,True),fill='#262626');y+=50
 maximum=max((x['rows_sampled'] for x in profiles),default=1)
 for item in sorted(profiles,key=lambda x:x['rows_sampled'],reverse=True)[:6]:_bar(draw,72,y,660,item['name'],item['rows_sampled'],maximum);y+=82
 if numeric and y<1510:
  y+=18;draw.text((72,y),'Selected numeric indicators',font=_font(27,True),fill='#262626');y+=50
  maximum=max(abs(value) for _,value in numeric) or 1
  for label,value in numeric[:3]:_bar(draw,72,y,660,label,abs(value),maximum,'#8a3ffc');y+=82
 draw.text((72,1660),'Analytical draft · Review before CMPDI submission',font=_font(17),fill='#6f6f6f')
 image.save(folder/'report.png','PNG',optimize=True);image.save(folder/'report.pdf','PDF',resolution=150)
 manifest={'id':rid,'title':title,'status':template.get('status') or 'analytical-draft','created':created,'target_entity':target_entity,'target_family':target_family,'period':period,'sources':[{'id':e['id'],'name':e['name'],'relative_path':e['relative_path']} for e in entries],'parameters':parameters,'required_sections':template['required_sections'],'visuals':template['visuals'],'review_flow':template['review_flow'],'generator':'CIL direct report','template_schema':1 if template['prompt'] else None}
 if source:
  manifest.update({'source_family':source.get('family'),'source_version':source.get('version'),'source_cadence':source.get('cadence'),'source_period':source.get('period')})
 atomic_json(folder/'manifest.json',manifest)
 with zipfile.ZipFile(folder/'report.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
  for path in folder.iterdir():
   if path.name!='report.zip':archive.write(path,path.name)
 repo.register_report(owner,rid,folder,title)
 return {'id':rid,'title':title,'created':created,'series':rid,'version':1,'previous_id':None,'entity':target_entity,'family':target_family,'audit_status':None,**({'source_family':source.get('family'),'source_version':source.get('version'),'source_cadence':source.get('cadence'),'source_period':source.get('period')} if source else {})}
