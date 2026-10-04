from collections import Counter
import html
import json

from interface.common import timed


@timed
def graph_report(audits,path):
    rows=[]
    examples=[]
    for design,example in zip(audits['designs'],audits['examples']):
        params=design['parameters']
        rows.append('<tr>'+''.join(f'<td>{html.escape(str(value))}</td>' for value in
                    (params['name'],', '.join(params.get('removed_components',())) or 'None',
                     ', '.join(str(v['nodes']) for v in design['snapshots']),', '.join(str(v['edges']) for v in design['snapshots'])))+'</tr>')
        examples.append(example)
    content='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Entity graph designs</title><style>
body{font:15px/1.5 system-ui;margin:32px auto;padding:0 24px;max-width:1500px;background:#f7f8f6;color:#182822}h1{font-size:32px}h2{margin-top:34px}p{max-width:1000px}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:9px;text-align:left;border-bottom:1px solid #cbd6cf}th{background:#e0eae3;position:sticky;top:0}.scroll{overflow:auto}label{display:inline-block;margin:8px 16px 8px 0}select,input,button{font:inherit;padding:7px;max-width:100%}svg{width:100%;height:620px;background:white;border:1px solid #d0ddd4}pre{white-space:pre-wrap;word-break:break-word;background:white;padding:14px;max-height:350px;overflow:auto}.grid{display:grid;grid-template-columns:2fr 1fr;gap:20px}.pill{display:inline-block;margin:3px;padding:3px 9px;border-radius:12px;background:#ddece1}.muted{color:#586960}a{color:#14784e}@media(max-width:900px){.grid{grid-template-columns:1fr}body{padding:0 12px}}
</style><p><a href="../report.html">Back to world review and tuning proposal</a></p><h1>Game entities, relationships and time</h1>
<p>The full recorded world is the baseline. Every country, state, province, individual pop, building, ownership entity, market, political entity and military entity is retained in each observation. The model carries history through recurrent memory.</p>
<h2>World graph</h2><div class="scroll"><table><thead><tr><th>Graph</th><th>Removed components</th><th>Nodes</th><th>Directed edges</th></tr></thead><tbody>ROWS</tbody></table></div>
<h2>Inspect an actual graph</h2><p>The diagram shows a bounded neighborhood of an individual entity. Select another node to inspect its exact attributes and incident relations. The downloaded file contains the entire graph, for the current observation. Entity IDs identify topology only; they are not model input attributes.</p>
<label>Design <select id="design"></select></label><label>Entity type <select id="kind"></select></label><label>Entity <select id="node"></select></label><label>Neighborhood <select id="hops"><option>1</option><option>2</option></select></label>
<p id="summary"></p><p id="coverage"></p><div class="grid"><div><svg id="graph" aria-label="Entity neighborhood"></svg><p id="shown" class="muted"></p></div><div><h3 id="entity"></h3><pre id="attrs"></pre><div id="relations"></div></div></div>
<h2>Measured node and relation counts</h2><div class="grid"><div id="nodesTable"></div><div id="edgesTable"></div></div>
<h2>Scope and semantics</h2><p>All recorded countries and geographic regions remain. Geographic borders, international ownership, market flows, politics, diplomacy, formations, units, supply, fronts, battles and naval relationships use actual recorded references. Shared named game definitions connect related facts. No temporal edges or duplicated historical worlds are stored in these graphs.</p>
<p>Coordinate-derived spatial links use the recorded province raster with game coordinates measured from the bottom left. Coordinate containment, coasts, water borders, map wrapping and explicit crossings are represented. Directed pair facts carry relative distance and direction for every positioned formation to every other formation, state centroid and front. Nearest coast, state-border and country-border facts retain exact segment distances and endpoint provinces. Recorded province links remain separately when they disagree with coordinates. These distances describe geometry, not travel time or military access.</p>
<p>Every graph retains individual pops, workplaces, location, culture, religion, profession, wealth, food security, state and market goods, and production and consumption flows. No population contraction, geographic pruning or military simplification is used.</p>
<p>Entity and global GRUs carry state through every observation in sequence, including observations at the same game time. Current candidate blocks preserve action order and parameters. Every alternative reads the same state; only the recorded or selected block advances memory.</p>
<p>Source visibility still limits the observations; missing facts are not invented. Referenced identities without live records are explicit unobserved nodes. Availability, execution validation, verification results, picker predictions and chosen-candidate flags are excluded from features and training selection. Alternative action blocks are generated from the snapshot by loop.run.redraw.</p>
<script>const examples=DATA;
const $=id=>document.getElementById(id);let current,focus=0;
const palette=['#1b7652','#357fa0','#a76833','#745994','#aa485b','#70792c','#277d82'];
const escaped=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const label=n=>`${n.kind} ${JSON.stringify(n.key)} @${n.seq}`;
function counts(map){return '<table><tr><th>Type / relation</th><th>Count</th></tr>'+Object.entries(map).sort((a,b)=>b[1]-a[1]).map(([k,v])=>`<tr><td>${escaped(k)}</td><td>${v}</td></tr>`).join('')+'</table>'}
function loadDesign(){current=examples[0];const kinds=[...new Set(current.nodes.map(n=>n.kind))].sort();$('kind').innerHTML=kinds.map(k=>`<option>${k}</option>`).join('');$('kind').value='formation';$('summary').innerHTML=`Run ${current.run}, decision ${current.seq}: <b>${current.nodes.length.toLocaleString()} nodes</b>, <b>${current.edges.length.toLocaleString()} directed edges</b>. <a href="${current.design.name}.json.gz">Download complete graph</a>`;$('nodesTable').innerHTML=counts(current.audit.node_types);$('edgesTable').innerHTML=counts(current.audit.relations);const a=current.audit;if(a.coverage){$('coverage').innerHTML=`${a.coverage.reduce((s,r)=>s+r.represented_rows,0).toLocaleString()} source facts represented; ${a.missing_entity_records.length} references lack live entity records; ${a.opaque_scope_targets.length} opaque scope values. <a href='../full_world/audit.json'>Complete coverage audit</a>`}loadKind()}
function loadKind(){const found=current.nodes.map((n,i)=>[n,i]).filter(([n])=>n.kind===$('kind').value);$('node').innerHTML=found.map(([n,i])=>`<option value="${i}">${escaped(label(n))}</option>`).join('');focus=found.at(-1)[1];$('node').value=focus;draw()}
function draw(){focus=+$('node').value;const all=current.edges;let ids=new Set([focus]);for(let h=0;h<+$('hops').value;h++){const old=new Set(ids);for(const [a,b] of all){if(old.has(a))ids.add(b);if(old.has(b))ids.add(a)}}const total=ids.size;ids=[focus,...[...ids].filter(i=>i!==focus)].slice(0,70);const kept=new Set(ids);const edges=all.filter(([a,b])=>kept.has(a)&&kept.has(b));const svg=$('graph');const w=svg.clientWidth,h=620;svg.setAttribute('viewBox',`0 0 ${w} ${h}`);const pos=new Map([[focus,[w/2,h/2]]]);ids.slice(1).forEach((id,i)=>{const angle=2*Math.PI*i/Math.max(1,ids.length-1);pos.set(id,[w/2+Math.cos(angle)*(w/2-90),h/2+Math.sin(angle)*240])});const kinds=[...new Set(current.nodes.map(n=>n.kind))].sort();svg.innerHTML=edges.map(([a,b,r])=>{const [x,y]=pos.get(a),[u,v]=pos.get(b);return `<line x1="${x}" y1="${y}" x2="${u}" y2="${v}" stroke="#9caea3" opacity=".45"><title>${escaped(r)}</title></line>`}).join('')+ids.map(id=>{const n=current.nodes[id],[x,y]=pos.get(id);return `<g data-id="${id}" style="cursor:pointer"><circle cx="${x}" cy="${y}" r="${id===focus?12:7}" fill="${palette[kinds.indexOf(n.kind)%palette.length]}"/><text x="${x+10}" y="${y-8}" font-size="10">${escaped(n.kind+' '+JSON.stringify(n.key)).slice(0,50)}</text><title>${escaped(label(n))}</title></g>`}).join('');svg.querySelectorAll('g[data-id]').forEach(g=>g.onclick=()=>{const id=+g.dataset.id;$('kind').value=current.nodes[id].kind;loadKind();$('node').value=id;draw()});$('shown').textContent=`Showing ${ids.length} of ${total} nodes in this neighborhood; ${edges.length} edges. The complete graph is available above.`;const node=current.nodes[focus];$('entity').textContent=label(node);$('attrs').textContent=JSON.stringify(node,null,2);const related=all.filter(([a,b])=>a===focus||b===focus);$('relations').innerHTML=related.slice(0,90).map(([a,b,r,v])=>`<p><b>${escaped(r)}</b> (${v.toPrecision(4)})<br>${escaped(label(current.nodes[a]))} &rarr; ${escaped(label(current.nodes[b]))}</p>`).join('')}
$('design').innerHTML=OPTIONS;$('design').value=JSONNAME;$('design').onchange=()=>{window.location.href=$('design').value+'.html'};$('kind').onchange=loadKind;$('node').onchange=draw;$('hops').onchange=draw;window.addEventListener('resize',draw);loadDesign();
</script></html>'''.replace('ROWS',''.join(rows))
    options=''.join('<option>'+e['design']['name']+'</option>' for e in examples)
    for i,example in enumerate(examples):
        body=content.replace('DATA',json.dumps([example]).replace('</','<\\/')).replace('OPTIONS',json.dumps(options)).replace('JSONNAME',json.dumps(example['design']['name']))
        destination=path.parent/(example['design']['name']+'.html')
        if destination.exists():
            destination.unlink()
        destination.write_text(body,encoding='utf-8')
        if example['design']['name']==('full_world' if any(e['design']['name']=='full_world' for e in examples) else examples[0]['design']['name']):
            if path.exists():
                path.unlink()
            path.write_text(body,encoding='utf-8')
