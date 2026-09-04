"""One bounded local PDF/image extraction process. No cloud or model credentials."""
import csv
import io
import json
import statistics
import subprocess
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from app.integration.repository import Repository,atomic_json
from app.integration import ocr,submissions

def write_csv(folder,name,headers,rows,artifacts,kind):
    if not rows:return
    with (folder/name).open('w',encoding='utf8',newline='') as f:
        writer=csv.writer(f);writer.writerow(headers);writer.writerows(rows)
    artifacts.append({'name':name,'kind':kind,'rows':len(rows),'approved':False})

def recognize(image_path):
    binary=ocr.engine()
    if not binary:raise RuntimeError('Tesseract is not installed. Install it on the backend host and retry.')
    result=subprocess.run([binary,str(image_path),'stdout','-l','eng','--psm','6','tsv'],capture_output=True,text=True,timeout=90,check=True)
    words=[]
    for r in csv.DictReader(io.StringIO(result.stdout),delimiter='\t',quoting=csv.QUOTE_NONE):
        if r.get('level')=='5' and r.get('text','').strip():
            words.append({'text':r['text'],'x':float(r['left']),'y':float(r['top']),'w':float(r['width']),'h':float(r['height']),'confidence':float(r['conf'])})
    return words

def layout(words):
    lines=[]
    for word in sorted(words,key=lambda w:(w['y'],w['x'])):
        match=next((line for line in reversed(lines[-8:]) if abs(line[0]['y']-word['y'])<=max(line[0]['h'],word['h'])*.55),None)
        if match is None:lines.append([word])
        else:match.append(word)
    return [sorted(line,key=lambda w:w['x']) for line in lines]

def table_headers(values):
    headers=[str(v or '').strip() for v in values]
    reserved={'source_file','page','source_row','source_line','ocr_confidence'}
    if len(set(headers))==len(headers) and not reserved.intersection(headers) and all(h and any(c.isalpha() for c in h) for h in headers):return headers
    return None

def extract(repo,id):
    import pdfplumber
    import pypdfium2 as pdfium
    from PIL import Image,ImageOps
    Image.MAX_IMAGE_PIXELS=40_000_000
    job=ocr.get(repo,id);job['error']=None;folder=repo.root/job['folder'];source=repo.root/job['source_path']
    if submissions.hash_file(source)!=job['source_sha256']:raise RuntimeError('Source changed since upload. Submit a new version before extraction.')
    pdf=None;renderer=None;image=None
    try:
        if source.suffix.lower()=='.pdf':
            pdf=pdfplumber.open(source);renderer=pdfium.PdfDocument(source);count=len(pdf.pages)
        else:image=Image.open(source);count=getattr(image,'n_frames',1)
        if count>100:raise RuntimeError('Document exceeds the current 100-page extraction limit. Split it into smaller documents.')
        job['page_count']=count;job['engine']='Tesseract English + PDF text/table extraction';ocr.save(repo,job)
        for index in range(count):
            page_no=index+1;preview=f'page-{page_no}.png';words=[];tables=[];method='ocr'
            try:
                if pdf:
                    page=pdf.pages[index];page_image=renderer[index]
                    if page.width*page.height*(200/72)**2>40_000_000:raise ValueError('Page is too large to render safely.')
                    bitmap=page_image.render(scale=200/72);picture=bitmap.to_pil().copy();bitmap.close();page_image.close()
                    # Mixed pages/images need OCR even when a digital header exists.
                    if len(page.chars)>40 and not page.images:
                        method='digital_text'
                        words=[{'text':w['text'],'x':w['x0'],'y':w['top'],'w':w['x1']-w['x0'],'h':w['bottom']-w['top'],'confidence':None} for w in page.extract_words()]
                        tables=page.extract_tables()
                else:
                    image.seek(index)
                    if image.width*image.height>40_000_000:raise ValueError('Image exceeds 40 megapixels.')
                    picture=ImageOps.exif_transpose(image).convert('RGB')
                picture.save(folder/preview);picture.close()
                if method=='ocr':words=recognize(folder/preview)
                lines=layout(words);line_rows=[];candidate_rows=[]
                for number,line in enumerate(lines,1):
                    scores=[w['confidence'] for w in line if w['confidence'] is not None]
                    confidence=round(statistics.mean(scores),1) if scores else ''
                    line_rows.append([job['filename'],page_no,number,' '.join(w['text'] for w in line),confidence,method,job['source_sha256']])
                    cells=[];current='';edge=None
                    threshold=max(12,statistics.median(w['h'] for w in line)*1.1)
                    for w in line:
                        if edge is not None and w['x']-edge>threshold:cells.append(current);current=''
                        current+=(' ' if current else '')+w['text'];edge=w['x']+w['w']
                    cells.append(current)
                    if len(cells)>1:candidate_rows.append((number,cells,confidence))
                write_csv(folder,f'page-{page_no}-text.csv',['source_file','page','line','text','ocr_confidence','method','source_sha256'],line_rows,job['artifacts'],'text')
                write_csv(folder,f'page-{page_no}-words.csv',['text','left','top','width','height','ocr_confidence'],[[w['text'],w['x'],w['y'],w['w'],w['h'],w['confidence']] for w in words],job['artifacts'],'word_positions')
                if tables:
                    for n,table in enumerate(tables,1):
                        width=max(map(len,table),default=0)
                        if width<2:continue
                        headings=table_headers(table[0]) if len(table[0])==width else None
                        rows=[[job['filename'],page_no,i+1,*[(v or '') for v in row],*['']*(width-len(row))] for i,row in enumerate(table) if not headings or i>0]
                        write_csv(folder,f'page-{page_no}-table-{n}.csv',['source_file','page','source_row']+(headings or [f'column_{i+1}' for i in range(width)]),rows,job['artifacts'],'table_candidate')
                elif len(candidate_rows)>=2:
                    width=max(len(c[1]) for c in candidate_rows)
                    headings=table_headers(candidate_rows[0][1]) if len(candidate_rows[0][1])==width else None
                    rows=[[job['filename'],page_no,num,*cells,*['']*(width-len(cells)),conf] for num,cells,conf in (candidate_rows[1:] if headings else candidate_rows)]
                    write_csv(folder,f'page-{page_no}-table-1.csv',['source_file','page','source_line']+(headings or [f'column_{i+1}' for i in range(width)])+['ocr_confidence'],rows,job['artifacts'],'table_candidate')
                scores=[w['confidence'] for w in words if w['confidence'] is not None]
                job['pages'].append({'page':page_no,'preview':preview,'method':method,'words':len(words),'confidence':round(statistics.mean(scores),1) if scores else None,'status':'needs_review' if words else 'no_text'})
            except Exception as exc:
                job['pages'].append({'page':page_no,'preview':preview if (folder/preview).exists() else None,'status':'failed','error':str(exc)[:250]})
            ocr.save(repo,job)
        failures=any(p['status'] in ('failed','no_text') for p in job['pages'])
        job['status']=('partial' if failures else 'needs_review') if job['artifacts'] else 'failed'
        if job['artifacts']:job['error']=None
        if not job['artifacts']:job['error']='No text could be extracted. Review page errors and source quality.'
        atomic_json(folder/'extraction.json',job);ocr.save(repo,job)
    finally:
        if image:image.close()
        if renderer:renderer.close()
        if pdf:pdf.close()

if __name__=='__main__':
    repo=Repository(Path(sys.argv[1]),Path(sys.argv[2]));id=sys.argv[3]
    try:extract(repo,id)
    except Exception as exc:
        job=ocr.get(repo,id);job.update(status='failed',error=str(exc)[:350]);ocr.save(repo,job)
