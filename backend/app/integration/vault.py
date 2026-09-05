"""Read-only, entity-scoped browsing of the local report repository."""
import os
import stat
import time
from pathlib import PurePosixPath
from fastapi import HTTPException
from .repository import ENTITIES, PRODUCTION, TECHNICAL

SCHEDULE='reporting_schedule.json'
TYPES={'all':None,'folders':set(),'tables':{'.csv','.xlsx','.json','.parquet'},'documents':{'.pdf','.md','.txt'},'images':{'.png','.jpg','.jpeg','.tif','.tiff'},'archives':{'.zip'}}
MAX_SCAN=25000
FOLDER_NAMES={'data':'Source data','report_generated':'Generated reports','submissions':'Uploaded submissions','report':'Submitted reports','versions':'Versions'}

def resolve(repo,path,scope=None):
    if not path:
        return repo.root
    parts=PurePosixPath(path).parts
    if (not parts or PurePosixPath(path).as_posix()!=path or '\\' in path or '\x00' in path
        or any(p.startswith('.') or ':' in p or p=='__MACOSX' for p in parts)):
        raise HTTPException(404,'Folder or file not found.')
    if path!=SCHEDULE:
        if parts[0] not in ([scope] if scope else ENTITIES):
            raise HTTPException(404,'Folder or file not found.')
        families=TECHNICAL if parts[0]=='CMPDI' else PRODUCTION
        if len(parts)>1 and parts[1] not in (*families,'report'):
            raise HTTPException(404,'Folder or file not found.')
        if len(parts)>2 and parts[1]!='report' and parts[2] not in ('data','report_generated','submissions'):
            raise HTTPException(404,'Folder or file not found.')
    current=repo.root
    for part in parts:
        current=current/part
        if current.is_symlink():
            raise HTTPException(404,'Folder or file not found.')
    if not current.resolve().is_relative_to(repo.root):
        raise HTTPException(404,'Folder or file not found.')
    return current

def item(repo,path):
    info=path.stat(follow_symlinks=False)
    if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
        return None
    return {'name':path.name,'path':path.relative_to(repo.root).as_posix(),
            'kind':'folder' if stat.S_ISDIR(info.st_mode) else 'file',
            'bytes':None if stat.S_ISDIR(info.st_mode) else info.st_size,'modified':info.st_mtime}

def decorate(entry,report_labels):
    """Add stable, human-readable labels while preserving immutable paths."""
    parts=PurePosixPath(entry['path']).parts
    report=report_labels.get(entry['name']) if entry['kind']=='folder' else None
    if report:
        family=(TECHNICAL if report['entity']=='CMPDI' else PRODUCTION).get(report['category'],{}).get('name',report['category'].replace('_',' ').title())
        entry.update({'display_name':report['title'],'description':f"{report['entity']} · {family} · v{report['version']}"})
    elif len(parts)==2 and parts[0] in ENTITIES and parts[1] in (TECHNICAL if parts[0]=='CMPDI' else PRODUCTION):
        family=(TECHNICAL if parts[0]=='CMPDI' else PRODUCTION).get(parts[1])
        entry['display_name']=family['name']
    elif entry['kind']=='folder' and entry['name'] in FOLDER_NAMES:
        entry['display_name']=FOLDER_NAMES[entry['name']]
    return entry

def breadcrumbs(repo,path,report_labels):
    result=[];parts=PurePosixPath(path).parts if path else ()
    for index in range(len(parts)):
        relative=PurePosixPath(*parts[:index+1]).as_posix()
        target=resolve(repo,relative)
        entry=decorate(item(repo,target),report_labels)
        result.append({'path':relative,'name':entry.get('display_name',entry['name'])})
    return result

def browse(repo,path='',scope=None,query='',kind='all',days=0,sort='name',offset=0,limit=200,entity_filter='',report_filter=''):
    base=resolve(repo,path,scope)
    if not base.is_dir():raise HTTPException(404,'Folder not found.')
    if scope:
        # The repository resolver already enforces the subsidiary boundary. Ignore
        # any client-supplied entity instead of turning the normal root into a
        # recursive result set.
        entity_filter=''
    if entity_filter and entity_filter not in ENTITIES:raise HTTPException(422,'Choose a valid subsidiary.')
    allowed_reports=TECHNICAL if (scope or entity_filter)=='CMPDI' else PRODUCTION
    if report_filter and report_filter not in allowed_reports:raise HTTPException(422,'Choose a valid report family.')
    recursive=bool(query or kind!='all' or days or entity_filter or report_filter)
    report_labels=repo.report_labels();matches=[];count=0;truncated=False;cutoff=time.time()-days*86400 if days else 0
    pending=[base]
    while pending:
        current=pending.pop()
        try:
            with os.scandir(current) as entries:
                for child in entries:
                    count+=1
                    if count>MAX_SCAN:truncated=True;break
                    relative=(current/child.name).relative_to(repo.root).as_posix()
                    try:
                        target=resolve(repo,relative,scope)
                        entry=item(repo,target)
                    except (HTTPException,OSError):continue
                    if not entry:continue
                    if recursive and entry['kind']=='folder':pending.append(target)
                    parts=PurePosixPath(relative).parts
                    if entity_filter and (not parts or parts[0]!=entity_filter):continue
                    if report_filter and (len(parts)<2 or parts[1]!=report_filter):continue
                    if query.casefold() not in entry['name'].casefold():continue
                    if kind=='folders' and entry['kind']!='folder':continue
                    if kind not in ('all','folders') and (entry['kind']!='file' or target.suffix.lower() not in TYPES[kind]):continue
                    if entry['modified']<cutoff:continue
                    # The global schedule is served as a scoped projection, never as the on-disk full file.
                    if relative==SCHEDULE and scope:
                        entry['bytes']=None;entry['modified']=None
                        if days:continue
                    matches.append(decorate(entry,report_labels))
        except OSError:raise HTTPException(404,'Folder is unavailable.') from None
        if truncated or not recursive:break
    if sort=='modified':matches.sort(key=lambda e:(-(e['modified'] or 0),e['name'].casefold()))
    elif sort=='modified_asc':matches.sort(key=lambda e:((e['modified'] or 0),e['name'].casefold()))
    elif sort=='name_desc':matches.sort(key=lambda e:(e['name'].casefold(),e['path']),reverse=True)
    else:matches.sort(key=lambda e:(e['name'].casefold(),e['path']))
    result=matches[offset:offset+limit]
    return {'path':path,'breadcrumbs':breadcrumbs(repo,path,report_labels),'entries':result,'total':len(matches),'recursive':recursive,'truncated':truncated,
            'next_offset':offset+limit if offset+limit<len(matches) else None,
            'filter_options':{'entities':[scope] if scope else list(ENTITIES),'reports':{
                entity:[{'id':key,'name':info['name']} for key,info in (TECHNICAL if entity=='CMPDI' else PRODUCTION).items()]
                for entity in ([scope] if scope else ENTITIES)}}}
