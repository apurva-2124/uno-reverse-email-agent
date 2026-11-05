'use strict';
const token = location.hash.slice(1);
history.replaceState(null, '', '/');
const $ = s => document.querySelector(s);
const stateLabel = s => s==='accepted_by_gmail'?'Accepted (simulated)':s.replaceAll('_',' ');
const element = (tag, text, cls) => {const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
async function api(path, body) {
  const response=await fetch('/api/'+path,{method:body?'POST':'GET',headers:{Authorization:'Bearer '+token,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined});
  const data=await response.json();if(!response.ok)throw new Error(data.error);return data;
}
function field(label,value,type='input') {const box=element('label',label);const input=element(type);input.value=value||'';box.append(input);return [box,input];}
async function action(name,body={}) {try {const data=await api(name,body);$('#notice').textContent=(data.result?stateLabel(data.result):null)||((data.new_replies||data.recovered)?JSON.stringify(data,null,2):'Saved.');await render();}catch(error){$('#notice').textContent=error.message;}}
function button(text,fn,cls) {const b=element('button',text,cls);b.addEventListener('click',fn);return b;}
async function render() {
  const state=await api('state');$('#mailbox').textContent=state.mailbox;
  $('#status').textContent=state.paused?'Paused: '+state.paused:'Ready for review · '+(state.policy?'Autopilot policy active':'Manual approval mode');
  const summary=$('#summary');summary.replaceChildren();
  for(const [label,count] of [['Candidates',state.candidates.length],['Ready to review',state.candidates.filter(c=>['ready','needs_review'].includes(c.state)).length],['Accepted (simulated)',state.candidates.filter(c=>c.state==='accepted_by_gmail').length],['Unresolved',state.candidates.filter(c=>c.state==='send_unknown').length]]) {const tile=element('div',undefined,'metric');tile.append(element('strong',String(count)),element('span',label));summary.append(tile);}
  const list=$('#candidates');list.replaceChildren();
  for(const c of state.candidates) {
    const p=c.plan,card=element('article',undefined,'candidate'),head=element('div',undefined,'card-head');
    head.append(element('h2',p.company||p.recipient||'Excluded message'),element('span',stateLabel(c.state),'state'));card.append(head);
    const cols=element('div',undefined,'columns'),source=element('div',undefined,'column'),out=element('div',undefined,'column');
    source.append(element('div','Original outreach','caption'));
    for(const m of c.source)source.append(element('p',m.sender,'meta'),element('strong',m.subject),element('pre',m.body));
    source.append(element('p',p.reason,'meta'));if(p.evidence)source.append(element('p','Evidence: '+p.evidence,'meta'));
    out.append(element('div','Your reverse pitch','caption'));
    const editable=['ready','needs_review','authorized'].includes(c.state);
    if(p.body) {
      out.append(element('p','To: '+p.recipient,'meta'),element('strong',p.subject));
      const [bodyBox,body]=field('Exact message',p.body,'textarea'),[companyBox,company]=field('Company',p.company),[brandBox,brand]=field('Stable brand ID',p.brand);
      const archiveBox=element('label'),archive=element('input');archive.type='checkbox';archive.checked=p.archive;archiveBox.append(archive,document.createTextNode(' Archive captured messages after acceptance'));
      for(const input of [body,company,brand,archive])input.disabled=!editable;
      out.append(bodyBox,companyBox,brandBox,archiveBox,element('p','Profile version: '+p.profile_version.slice(0,12)+' · Adds “uno reverse” label','meta'));
      const actions=element('div',undefined,'card-actions');
      if(editable) {
        const approve=button('Approve exact message',()=>action('approve',{id:c.id,hash:c.hash}),'primary');
        const send=button('Send to synthetic mailbox',()=>action('send',{id:c.id}),'primary');send.disabled=c.state!=='authorized';
        for(const input of [body,company,brand,archive])input.addEventListener('input',()=>{approve.disabled=true;send.disabled=true;$('#notice').textContent='Save edits, then approve the updated message.';});
        actions.append(button('Save edits',()=>action('edit',{id:c.id,body:body.value,company:company.value,brand:brand.value,archive:archive.checked})),approve,send,button('Exclude',()=>action('exclude',{id:c.id})));
      }
      cols.append(source,out);card.append(cols,actions);
    } else {out.append(element('p','No draft generated.','meta'));cols.append(source,out);card.append(cols);}
    list.append(card);
  }
}
document.querySelectorAll('[data-action]').forEach(b=>b.addEventListener('click',()=>action(b.dataset.action)));
render().catch(error=>{$('#notice').textContent=error.message;});
