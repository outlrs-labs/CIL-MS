import asyncio
import csv
import io
import json
import sys
import zipfile
from pathlib import Path
import pytest
from fastapi import HTTPException
from app.integration import ocr,submissions
from app.integration.repository import Repository

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'integration'))
from csv_import import csv_to_parquet

@pytest.mark.parametrize('content,encoding',[
 ('month;production\nAugust;1200\nSeptember;1300\n','utf-8-sig'),
 ('month\tproduction\nAugust\t1200\nSeptember\t1300\n','utf-16'),
 ('month,production\nAoût,1200\nSeptember,1300\n','cp1252'),
 ('sep=;\nmonth;production\nAugust;1200\nSeptember;1300\n','utf-8')])
def test_csv_encodings_and_numeric_columns(tmp_path,content,encoding):
 import pyarrow.parquet as pq
 source=tmp_path/'source.csv';source.write_bytes(content.encode(encoding));dest=tmp_path/'table.parquet'
 csv_to_parquet(source,dest);table=pq.read_table(dest)
 assert table['production'].to_pylist()==[1200,1300]

def test_csv_mixed_type_and_bad_row(tmp_path):
 import pyarrow.parquet as pq
 source=tmp_path/'source.csv';dest=tmp_path/'table.parquet'
 source.write_text('code,value\n001,1200\n002,not recorded\n')
 csv_to_parquet(source,dest);assert pq.read_table(dest).to_pylist()==[{'code':'001','value':'1200'},{'code':'002','value':'not recorded'}]
 source.write_text('a,b\n1,2,3\n')
 with pytest.raises(ValueError,match='row 2'):csv_to_parquet(source,dest)

def test_dot_prefix_zip_is_valid(tmp_path):
 repo=Repository(tmp_path/'cil',tmp_path/'processing');repo.initialize();archive=tmp_path/'input.zip'
 with zipfile.ZipFile(archive,'w') as z:
  z.writestr('./','');z.writestr('./folder/production.csv','month,value\nAugust,1200\n')
 record=submissions.ingest(repo,archive,'BCCL','fixture','production_offtake','monthly','2026-08')
 assert record['files'][0]['name']=='folder/production.csv'

@pytest.mark.skipif(not ocr.engine(),reason='Local Tesseract is required')
def test_real_image_ocr_review_and_scoped_catalog(tmp_path):
 from PIL import Image,ImageDraw,ImageFont
 repo=Repository(tmp_path/'cil',tmp_path/'processing');repo.initialize();archive=tmp_path/'input.zip'
 picture=Image.new('RGB',(1400,650),'white');draw=ImageDraw.Draw(picture);font=ImageFont.load_default(size=42)
 for y,text in [(60,'MONTH       PRODUCTION       OFFTAKE'),(180,'August            1200                900'),(300,'September         1300               1100')]:draw.text((55,y),text,font=font,fill='black')
 png=io.BytesIO();picture.save(png,format='PNG');picture.close()
 with zipfile.ZipFile(archive,'w') as z:z.writestr('scan.png',png.getvalue())
 record=submissions.ingest(repo,archive,'BCCL','fixture','production_offtake','monthly','2026-08')
 async def run():
  job=ocr.enqueue(repo,record['id'],'scan.png','fixture','BCCL')
  await asyncio.gather(*list(ocr.tasks));return ocr.get(repo,job['id'],'BCCL')
 job=asyncio.run(run());assert job['status']=='needs_review',job
 texts=[a for a in job['artifacts'] if a['kind']=='text'];assert texts
 content=(repo.root/job['folder']/texts[0]['name']).read_text();assert '1200' in content and 'PRODUCTION' in content
 assert not ocr.catalog_files(repo,'BCCL',False)
 ocr.approve(repo,job,texts[0]['name'],'reviewer',None)
 files=ocr.catalog_files(repo,'BCCL',False);assert len(files)==1 and files[0]['source_sha256']==job['source_sha256']
 assert ocr.catalog_files(repo,'SECL',False)==[]
 with pytest.raises(HTTPException):ocr.get(repo,job['id'],'SECL')
 with pytest.raises(HTTPException):ocr.artifact_path(repo,job,'../source.png')
 with pytest.raises(HTTPException):ocr.approve(repo,job,texts[0]['name'],'reviewer',None)
