export interface Operation {id:string;kind:string;status:string;error:string|null;trace_id:string|null}
export interface Category {id:number;name:string;description:string;revision:number;document_count:number}
export interface ChunkSettings {separator:string;target_chars:number;overlap_chars:number}
export interface KnowledgeVersion {id:number;version:number;status:string;purpose:string;effective_from:string|null;effective_until:string|null;created_at:string;published_at:string|null;error:string|null;settings:ChunkSettings;chunk_count:number;content?:string;chunks?:{id:number;ordinal:number;content:string}[]}
export interface KnowledgeDocument {id:number;title:string;category_id:number;enabled:boolean;revision:number;updated_at:string;state:string;active_version_id:number|null;published:KnowledgeVersion|null;candidate:KnowledgeVersion|null;operation:Operation|null;versions?:KnowledgeVersion[];candidate_metadata?:{title:string;category_id:number}}
