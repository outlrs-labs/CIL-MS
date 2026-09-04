import {useState} from 'react';
import {ArrowRight,Building2,FileCheck2,Layers3} from 'lucide-react';
import type {Entity} from './types';

const productionReports=[
 {name:'Production & off-take',cadences:['Daily','Monthly'],description:'Production volumes, dispatch and off-take figures.'},
 {name:'Washery operations',cadences:['Daily','Monthly'],description:'Washery inputs, output and operating performance.'},
 {name:'Operational statistics',cadences:['Monthly'],description:'Mine and project operating statistics.'},
 {name:'Financial report',cadences:['Quarterly','Annual'],description:'Financial statements and supporting figures.'},
 {name:'Environmental clearance & compliance',cadences:['Half-yearly'],description:'Clearance conditions, compliance evidence and monitoring.'},
];
export function ReportingWorkspace({entity,technical,entities,onOpenReports}:{entity:Entity;technical:boolean;entities:Entity[];onOpenReports?:()=>void}){
 const [cadence,setCadence]=useState('All');
 return <div className={`reporting-workspace ${technical?'coordination':'production'}`}>
  <section className="reporting-hero">
   <span className="eyebrow">{technical?'CMPDI · TECHNICAL & PLANNING':'PRODUCTION SUBSIDIARY · '+entity.code}</span>
   <h2>{technical?'Technical coordination':entity.code+' reporting'}</h2>

   {onOpenReports&&<button className="button primary" onClick={onOpenReports}>{technical?'View submissions':'Open Upload'} <ArrowRight size={17}/></button>}<div className="responsibility-tags"><span><FileCheck2 size={17}/>{technical?'Receives reports from production subsidiaries':'Reporting destination: CMPDI'}</span><span><Building2 size={17}/>Group administrator: CIL Central Admin</span></div>
  </section>
  <section className="panel reporting-flow"><div className="section-heading"><div><h2>Reporting relationship</h2></div></div><ol>
   <li className={!technical?'current':''}><Building2/><strong>{technical?'7 production subsidiaries':entity.code}</strong><span>Submit source data</span></li><li className={technical?'current':''}><Layers3/><strong>CMPDI</strong><span>Review & consolidate</span></li><li><FileCheck2/><strong>CIL Central Admin</strong><span>Final approval</span></li>
  </ol></section>
  {technical?<>
   <div className="reporting-cards"><section className="panel"><h2>Subsidiary submissions</h2><p>Incoming reports and data.</p><span className="planned-label">Versioned ZIP submissions · Available</span></section><section className="panel"><h2>Technical review</h2><p>Check evidence and completeness.</p><span className="planned-label">Review workflow · Planned</span></section><section className="panel"><h2>Consolidated reports</h2><p>Prepare group report drafts.</p><span className="planned-label">Analytics & report drafts · Available</span></section></div>
   <section className="panel"><div className="section-heading"><div><h2>Production subsidiaries</h2></div></div><div className="reporting-entity-list">{entities.filter(e=>e.kind==='operating').map(e=><div key={e.id}><strong>{e.code}</strong><span>{e.name}</span><small>{e.active?'Active entity':'Inactive entity'}</small></div>)}</div></section>
  </>:<>
   <div className="reporting-cards">{[['Daily','Production and washery operating figures'],['Monthly','Production, washery and operational statistics'],['Annual','Annual financial reporting']].map(([label,description])=><section className="panel" key={label}><span className="eyebrow">REPORTING CYCLE</span><h2>{label}</h2><p>{description}</p></section>)}</div>
   <section className="panel"><div className="section-heading"><div><h2>Your reporting responsibilities</h2></div></div><div className="report-cycle-filter" role="group" aria-label="Reporting cycle">{['All','Daily','Monthly','Quarterly','Half-yearly','Annual'].map(c=><button key={c} className={cadence===c?'selected':''} aria-pressed={cadence===c} onClick={()=>setCadence(c)}>{c}</button>)}</div><div className="report-family-list">{productionReports.filter(r=>cadence==='All'||r.cadences.includes(cadence)).map(r=><article key={r.name}><FileCheck2/><div><h3>{r.name}</h3><small>{r.cadences.join(' · ')} <span aria-hidden="true">→</span> Submit to CMPDI</small></div><span className="planned-label">ZIP submission · Available</span></article>)}</div></section>
  </>}
 </div>
}
