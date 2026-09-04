// UI-only fixtures. Never accepted by the API and unavailable in production builds.
import type {Entity,Identity} from './types';
export const previewEntities:Entity[] = [
 ['CIL','Coal India Limited','holding','Kolkata'],
 ['ECL','Eastern Coalfields Limited','operating','Sanctoria'],
 ['BCCL','Bharat Coking Coal Limited','operating','Dhanbad'],
 ['CCL','Central Coalfields Limited','operating','Ranchi'],
 ['NCL','Northern Coalfields Limited','operating','Singrauli'],
 ['WCL','Western Coalfields Limited','operating','Nagpur'],
 ['SECL','South Eastern Coalfields Limited','operating','Bilaspur'],
 ['MCL','Mahanadi Coalfields Limited','operating','Sambalpur'],
 ['CMPDI','Central Mine Planning & Design Institute Limited','technical','Ranchi'],
].map(([code,name,kind,location])=>({id:code,code,name,kind:kind as Entity['kind'],location,active:true,parent_id:code==='CIL'?null:'CIL'}));
export const previewIdentity:Identity={profile:{id:'preview',email:'Read-only interface preview',full_name:'CIL Administrator',role:'cil_admin',entity_id:'CIL',active:true,must_change_password:false,created_at:''},entity:previewEntities[0],permissions:[]};
