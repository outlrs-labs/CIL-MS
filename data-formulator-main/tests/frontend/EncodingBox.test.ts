import {describe,expect,it} from 'vitest';
import {encodingFieldsForTable} from '../../src/views/EncodingBox';
import type {FieldItem} from '../../src/components/ComponentType';

describe('encoding field dropdown',()=>{
  it('uses fields belonging to the active table when tables share column names',()=>{
    const fields:FieldItem[]=[
      {id:'original--table-a--page',name:'page',source:'original',tableRef:'table-a'},
      {id:'original--table-b--page',name:'page',source:'original',tableRef:'table-b'},
      {id:'original--table-b--value',name:'value',source:'original',tableRef:'table-b'},
    ];
    expect(encodingFieldsForTable(fields,{id:'table-b',names:['page','value']})).toEqual([fields[1],fields[2]]);
  });
});
