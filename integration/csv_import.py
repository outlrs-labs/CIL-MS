"""Bounded CSV import with delimiter/encoding handling and stable string schema."""
import csv
import codecs
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
import math

def csv_to_parquet(source, destination):
    source=Path(source)
    with source.open('rb') as binary:prefix=binary.read(65536)
    encoding='utf-16' if prefix.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig'
    if encoding=='utf-8-sig':
        try:codecs.getincrementaldecoder(encoding)().decode(prefix,final=False)
        except UnicodeDecodeError:encoding='cp1252'
    with source.open(encoding=encoding,newline='') as stream:
        sample=stream.read(65536);stream.seek(0)
        skip=sample.lower().startswith('sep=') and len(sample.splitlines()[0])==5
        if skip:
            delimiter=stream.readline().strip()[-1]
        else:
            try:delimiter=csv.Sniffer().sniff(sample,delimiters=',;\t|').delimiter
            except csv.Error:delimiter=','
        reader=csv.reader(stream,delimiter=delimiter,strict=True)
        names=next(reader,None)
        if not names or not all(n.strip() for n in names) or len(set(names))!=len(names):
            raise ValueError('CSV needs a non-empty, unique header for each column.')
        # Inspect the whole column before fixing its type, so a late text value
        # does not break a later record batch. Numeric measures remain chartable.
        types=['integer']*len(names)
        for line,row in enumerate(reader,2):
            if not row:continue
            if len(row)!=len(names):raise ValueError(f'CSV row {line} has {len(row)} columns; expected {len(names)}. Check delimiter and quoting.')
            for i,value in enumerate(row):
                if not value.strip() or types[i]=='string':continue
                try:
                    if value.strip().lstrip('+-').isdigit():
                        number=int(value)
                        if abs(number)>2**53 or (len(value.strip())>1 and value.strip().startswith('0')):types[i]='string'
                    else:
                        if not math.isfinite(float(value)):raise ValueError()
                        types[i]='number'
                except ValueError:types[i]='string'
        stream.seek(0)
        if skip:stream.readline()
        reader=csv.reader(stream,delimiter=delimiter,strict=True);next(reader)
        schema=pa.schema([(n,pa.int64() if t=='integer' else pa.float64() if t=='number' else pa.string()) for n,t in zip(names,types)]);batch=[]
        with pq.ParquetWriter(destination,schema,compression='zstd') as writer:
            for line,row in enumerate(reader,2):
                if not row:continue
                if len(row)!=len(names):raise ValueError(f'CSV row {line} has {len(row)} columns; expected {len(names)}. Check delimiter and quoting.')
                converted=[v if t=='string' else None if not v.strip() else int(v) if t=='integer' else float(v) for v,t in zip(row,types)]
                batch.append(dict(zip(names,converted)))
                if len(batch)>=10000:writer.write_table(pa.Table.from_pylist(batch,schema=schema));batch=[]
            if batch:writer.write_table(pa.Table.from_pylist(batch,schema=schema))
