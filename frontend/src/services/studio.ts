import { apiFetch } from './auth';
import type { YarnConsumptionItem } from '../types/carpet';
export interface StudioLayer {id:string;name:string;role:'BASE'|'MOTIF'|'BORDER'|'FIELD'|'MEDALLION';visible:boolean;x:number;y:number;width:number;height:number;cells:number[]}
export interface StudioDocument {width:number;height:number;layers:StudioLayer[];colorway:number[]}
export interface StudioPalette {code:string;name:string;rgb:[number,number,number];is_demo?:boolean}
export interface StudioHistory {revision:number;parent_revision:number;author:string;note:string;created_at:string;kind:string;sha256:string}
export interface StudioEvaluation {recipe:YarnConsumptionItem[];summary:{total_order_cost_tl:number;total_order_yarn_kg:number};grid_sha256:string;gate:{status:string;reasons:string[];pending:string[]};seam:{left_right_mismatch_cells:number;top_bottom_mismatch_cells:number;note:string};source:string;delta_e_status:string}
export interface StudioState {job_id:string;revision:number;document:StudioDocument;palette:StudioPalette[];data_source:string;history:StudioHistory[];evaluation:StudioEvaluation|null;loom_config:{order_quantity:number}|null}
const base=import.meta.env.VITE_API_URL||'';
async function request(path:string,options?:RequestInit){const res=await apiFetch(`${base}/api/v1/jobs/${path}`,options);const body=await res.json();if(!res.ok)throw new Error(typeof body.detail==='string'?body.detail:JSON.stringify(body.detail));return body;}
export function fetchStudio(job:string):Promise<StudioState>{return request(`${encodeURIComponent(job)}/studio`);}
export function fetchRevision(job:string,revision:number){return request(`${encodeURIComponent(job)}/studio/revisions/${revision}`);}
export function saveRevision(job:string,parent_revision:number,document:StudioDocument,author:string,note:string,kind:string){return request(`${encodeURIComponent(job)}/studio/revisions`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({parent_revision,document,author,note,kind})});}
export function composeStudio(document:StudioDocument,applyColorway=true):number[]{
  const cells=new Array<number>(document.width*document.height).fill(0);
  for(const l of document.layers)if(l.visible)for(let y=0;y<l.height;y++)for(let x=0;x<l.width;x++){const c=l.cells[y*l.width+x];if(c>=0)cells[(l.y+y)*document.width+l.x+x]=c;}
  return applyColorway?cells.map(c=>document.colorway[c]):cells;
}
export function downloadStudio(name:string,value:unknown){const url=URL.createObjectURL(new Blob([JSON.stringify(value)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
