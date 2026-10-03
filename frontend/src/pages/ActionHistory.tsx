import { useEffect, useState } from "react";
import type { ActionAudit } from "../types";
import { useStore } from "../hooks/useStore";
import { useTask } from "../hooks/useTask";
import { api } from "../services/api";
import { formatDate } from "../services/format";
import { EmptyState, ErrorAlert, Loading, PageTitle } from "../components/common";
export function ActionHistory() {
  const store=useStore();const [rows,setRows]=useState<ActionAudit[]>([]),[revision,setRevision]=useState(0),[more,setMore]=useState(false);
  const task=useTask<ActionAudit[]>(`${store.merchantId}:${revision}`);
  useEffect(()=>{setRows([]);if(store.merchantId)task.run(signal=>api.getActionHistory(store.merchantId!,signal),data=>{setRows(data);setMore(data.length===100);});},[store.merchantId,revision]);
  return <>{store.error && <ErrorAlert message={store.error} />}<PageTitle title="Action History" description="Persistent audit events for human-reviewed local and simulated actions." /><button className="btn secondary" disabled={task.loading} onClick={()=>setRevision(value=>value+1)}>Refresh history</button>{task.loading&&<Loading text="Loading audit history…" />}{task.error&&<ErrorAlert message={task.error} retry={()=>setRevision(value=>value+1)} />}{!task.loading&&!task.error&&!rows.length&&<EmptyState>No action events recorded for this merchant.</EmptyState>}{rows.length>0&&<div className="panel table-scroll"><table><thead><tr>{["Time","Action","Product","Agent","Event","Status","Performed by","Details"].map(label=><th key={label}>{label}</th>)}</tr></thead><tbody>{rows.map(row=><tr key={row.id}><td>{formatDate(row.created_at)}</td><td>#{row.action_id}</td><td>{String(row.metadata?.product_id??"—")}</td><td>{String(row.metadata?.agent??"—")}</td><td>{row.event_type.replace(/_/g," ")}</td><td>{String(row.metadata?.status??"—")}</td><td>{String(row.metadata?.performed_by??"—")}</td><td><details><summary>View details</summary><pre className="action-result">{JSON.stringify(row.metadata,null,2)}</pre></details></td></tr>)}</tbody></table></div>}{more&&<button className="btn secondary" disabled={task.loading} onClick={()=>{if(store.merchantId)task.run(signal=>api.getActionHistory(store.merchantId!,signal,rows.length),data=>{setRows(current=>[...current,...data]);setMore(data.length===100);});}}>Load more history</button>}</>;
}
