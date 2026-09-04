import {fireEvent,render,screen} from '@testing-library/react';
import {ReportingWorkspace} from './ReportingWorkspace';
import type {Entity} from './types';
const entity:Entity={id:'test',code:'BCCL',name:'Bharat Coking Coal Limited',kind:'operating',parent_id:'cil',location:'Dhanbad',active:true};
test('production member sees CMPDI destination and filters annual report responsibilities',()=>{
 render(<ReportingWorkspace entity={entity} technical={false} entities={[entity]}/>);
 expect(screen.getByText('Reporting destination: CMPDI')).toBeInTheDocument();
 expect(screen.getByText('Group administrator: CIL Central Admin')).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Annual'}));
 expect(screen.getByRole('heading',{name:'Financial report'})).toBeInTheDocument();
 expect(screen.queryByRole('heading',{name:'Production & off-take'})).not.toBeInTheDocument();
 expect(screen.getByText('ZIP submission · Available')).toBeInTheDocument();
});
test('CMPDI sees coordinating responsibilities and the reporting subsidiary directory',()=>{
 render(<ReportingWorkspace entity={{...entity,code:'CMPDI',kind:'technical'}} technical entities={[entity]}/>);
 expect(screen.getByRole('heading',{name:'Technical review'})).toBeInTheDocument();
 expect(screen.getByRole('heading',{name:'Consolidated reports'})).toBeInTheDocument();
 expect(screen.getByText('BCCL')).toBeInTheDocument();
 expect(screen.queryByText('Your reporting responsibilities')).not.toBeInTheDocument();
});
