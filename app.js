const $ = (id) => document.getElementById(id);
const state = {data:null, marks:null, tab:"jobs"};
const labels = {
  jobs: ["待投","准备中","已投","笔试","面试","暂缓","结束"],
  fairs: ["待查看","计划参加","已报名","已参加","不参加"]
};

function el(tag, className, value) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value !== undefined) node.textContent = value;
  return node;
}
function add(parent, child) { parent.appendChild(child); return child; }
function cell(row) { return add(row, el("td")); }
function line(parent, text, className="secondary") { add(parent, el("div", className, text)); }
function displayError(message) { $("error").textContent=message; $("error").hidden=!message; }
function saveStatus(message, kind="") { $("save-status").textContent=message; $("save-status").className="save-status "+kind; }
function markFor(kind, id) { return state.marks?.[kind]?.[id] || {status:"",note:""}; }

function getFairEnd(dateText) {
  const found = dateText.match(/\d{4}-\d{2}-\d{2}/g) || [];
  if (!found.length) return "";
  if (found.length > 1) return found[found.length-1];
  const shortened = dateText.match(/\d{4}-\d{2}-\d{2}[^\d]+(\d{2})-(\d{2})/);
  if (shortened) return found[0].slice(0,5)+shortened[1]+"-"+shortened[2];
  return found[0];
}
function todayLocal() {
  const now=new Date();
  return [now.getFullYear(),String(now.getMonth()+1).padStart(2,"0"),String(now.getDate()).padStart(2,"0")].join("-");
}
function filteredItems() {
  const q=$("search").value.trim().toLowerCase();
  const availability=$("availability-filter").value;
  return state.data[state.tab].filter(item=>{
    if (state.tab==="jobs" && availability && item.availability!==availability) return false;
    if (state.tab==="fairs" && $("upcoming").checked && getFairEnd(item.date)<todayLocal()) return false;
    if (!q) return true;
    const fields=state.tab==="jobs"
      ? [item.company,item.role,item.category,item.location,item.fit,item.availability]
      : [item.name,item.date,item.location,item.audience,item.roles];
    return fields.some(v=>String(v||"").toLowerCase().includes(q));
  });
}
async function saveMark(kind,id,status,note) {
  saveStatus("正在保存…");
  try {
    const response=await fetch("/api/mark",{
      method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({kind,id,status,note})
    });
    const result=await response.json();
    if (!response.ok) throw new Error(result.error||"保存失败");
    state.marks[kind][id]=result.saved;
    saveStatus("已保存到本机","saved");
    displayError("");
  } catch(error) {
    saveStatus("保存失败","failed");
    displayError("标记未保存："+error.message+"。请确认启动窗口仍在运行。");
  }
}
function markControls(row,kind,item) {
  const current=markFor(kind,item.id);
  const select=add(cell(row),el("select","mark-select"));
  select.setAttribute("aria-label",item.role||item.name+" 的进度");
  add(select,el("option","", "未标记")).value="";
  for(const value of labels[kind]) add(select,el("option","",value)).value=value;
  select.value=current.status;
  const note=add(cell(row),el("textarea","note-input"));
  note.placeholder="写一句跟进备注";
  note.setAttribute("aria-label",(item.role||item.name)+" 的备注");
  note.value=current.note;
  select.addEventListener("change",()=>saveMark(kind,item.id,select.value,note.value));
  let noteTimer;
  note.addEventListener("input",()=>{
    clearTimeout(noteTimer);
    noteTimer=setTimeout(()=>saveMark(kind,item.id,select.value,note.value),350);
  });
  note.addEventListener("blur",()=>{
    clearTimeout(noteTimer);
    saveMark(kind,item.id,select.value,note.value);
  });
}
function roleLink(parent,url,label="打开官网 ↗") {
  const link=add(parent,el("a","entry",label));
  link.href=url;
  link.target="_blank";
  link.rel="noopener noreferrer";
}
function jobRow(item) {
  const row=el("tr");
  const role=cell(row);
  line(role,item.company,"primary");
  line(role,item.role,"");
  line(role,item.category);
  const availability=item.availability||"官网岗位页";
  add(role,el("span","tag "+(availability==="历史线索"?"c":availability==="官网岗位列表"?"b":""),availability));
  const location=cell(row);
  line(location,item.location,"primary");
  line(location,item.eligibility);
  line(cell(row),item.deadline);
  const fit=cell(row);
  line(fit,item.fit,"");
  line(fit,item.verified);
  roleLink(cell(row),item.url,availability==="历史线索"?"查看历史来源 ↗":availability==="官网岗位列表"?"官网查找岗位 ↗":"查看职位 / 投递 ↗");
  markControls(row,"jobs",item);
  return row;
}
function fairRow(item) {
  const row=el("tr");
  const date=cell(row);
  line(date,item.date,"primary");
  line(date,item.time);
  const name=cell(row);
  line(name,item.name,"primary");
  line(name,item.location);
  const entry=cell(row);
  line(entry,item.entry,"");
  line(entry,item.audience);
  const roles=cell(row);
  line(roles,item.roles,"");
  line(roles,item.verified);
  roleLink(cell(row),item.url);
  markControls(row,"fairs",item);
  return row;
}
function render() {
  if (!state.data) return;
  const items=filteredItems();
  const body=$(state.tab+"-body");
  body.replaceChildren();
  if (!items.length) {
    const row=add(body,el("tr"));
    const empty=add(row,el("td","empty","没有符合条件的记录"));
    empty.colSpan=7;
  } else {
    for(const item of items) add(body,state.tab==="jobs"?jobRow(item):fairRow(item));
  }
  $("jobs-count").textContent=state.data.jobs.length;
  $("fairs-count").textContent=state.data.fairs.length;
}
function switchTab(kind) {
  state.tab=kind;
  for(const name of ["jobs","fairs"]) {
    $(name+"-panel").hidden=name!==kind;
    $(name+"-tab").classList.toggle("active",name===kind);
    $(name+"-tab").setAttribute("aria-selected",String(name===kind));
  }
  $("upcoming-wrap").hidden=kind!=="fairs";
  $("availability-filter").parentElement.hidden=kind!=="jobs";
  $("search").value="";
  $("availability-filter").value="";
  render();
}
async function load() {
  displayError("");
  try {
    const response=await fetch("/api/state",{cache:"no-store"});
    const payload=await response.json();
    if (!response.ok) throw new Error(payload.error||"数据读取失败");
    state.data=payload.data;
    state.marks=payload.marks;
    $("updated-at").textContent=payload.data.updated_at||"未标注";
    render();
    saveStatus("标记会自动保存");
  } catch(error) {
    displayError("读取失败："+error.message+"。请重新双击“启动求职表.cmd”。");
  }
}
$("jobs-tab").addEventListener("click",()=>switchTab("jobs"));
$("fairs-tab").addEventListener("click",()=>switchTab("fairs"));
$("search").addEventListener("input",render);
$("availability-filter").addEventListener("change",render);
$("upcoming").addEventListener("change",render);
$("reload").addEventListener("click",load);
load();
