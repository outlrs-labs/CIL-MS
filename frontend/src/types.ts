export type Role = 'cil_admin' | 'cmpdi' | 'subsidiary';
export type Entity = {id:string;code:string;name:string;kind:'holding'|'operating'|'technical';parent_id:string|null;location:string;active:boolean;created_at?:string};
export type Profile = {id:string;email:string;full_name:string;role:Role;entity_id:string;active:boolean;must_change_password:boolean;review_position?:'contributor'|'assistant_manager'|'manager';created_at:string};
export type Identity = {profile:Profile;entity:Entity;permissions:string[]};
export type AccessEvent = {id:number;action:string;target:string;created_at:string};
export const roleNames: Record<Role,string> = {cil_admin:'CIL administrator',cmpdi:'Technical coordinator',subsidiary:'Subsidiary member'};
