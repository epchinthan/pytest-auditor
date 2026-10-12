const $ = id => document.getElementById(id);
let result, view = 'issues';
const esc = value => String(value ?? '—').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const displayPath = path => result?.path_labels?.[path] ?? path;
const cell = value => esc(Array.isArray(value) ? value.join(', ') : typeof value === 'object' && value !== null ? JSON.stringify(value) : value);
let uploadedFiles = [], uploadIsFolder = false;
const ignoredFolders = new Set(['.git','.venv','venv','node_modules','__pycache__','.azure-cli','.cache']);
$('upload-kind').addEventListener('change', () => {
  const folder = $('upload-kind').value === 'folder';
  const picker = $('upload-source');
  picker.value = ''; uploadedFiles = []; uploadIsFolder = folder;
  picker.toggleAttribute('webkitdirectory', folder);
  picker.multiple = folder;
  if (folder) picker.removeAttribute('accept'); else picker.accept = '.py';
  $('upload-selection').textContent = 'Choose a file or folder. Up to 10 MB / 2,000 files. Files are deleted after auditing.';
});
$('upload-source').addEventListener('change', () => {
  uploadIsFolder = $('upload-kind').value === 'folder';
  uploadedFiles = [...$('upload-source').files].filter(file => {
    const parts = (file.webkitRelativePath || file.name).split('/');
    return !parts.some(part => ignoredFolders.has(part)) &&
      (/\.py$/i.test(file.name) || ['pytest.ini','pyproject.toml','setup.cfg','tox.ini','coverage.json'].includes(file.name));
  });
  $('upload-selection').textContent = `${uploadedFiles.length} source/configuration files selected (${(uploadedFiles.reduce((n,f)=>n+f.size,0)/1024/1024).toFixed(2)} MB). Files are deleted after auditing.`;
});
async function uploadPayload() {
  if (!uploadedFiles.length) throw new Error('Choose a Python file or a folder containing Python files.');
  if (uploadedFiles.length > 2000 || uploadedFiles.reduce((n,f)=>n+f.size,0) > 10*1024*1024) throw new Error('Upload limit is 10 MB / 2,000 files.');
  const files = [];
  for (const file of uploadedFiles) {
    const content = await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(new Error(`Could not read ${file.name}`));reader.readAsDataURL(file);});
    files.push({path:file.webkitRelativePath || file.name, content});
  }
  return {source:'upload', files, folder:uploadIsFolder, test:$('test').value};
}
$('audit-form').addEventListener('submit', async event => {
  event.preventDefault(); $('run').disabled = true; $('status').className = ''; $('status').textContent = $('source').value === 'github' ? 'Downloading repository and analyzing tests…' : 'Analyzing your tests…';
  try {
    const session = await fetch('/api/session').then(r => r.json());
    const upload = $('source').value === 'upload';
    const payload = upload ? await uploadPayload() : {source:$('source').value,repository:$('repository').value,ref:$('ref').value,github_token:$('github-token').value,path:$('path').value,test:$('test').value};
    const response = await fetch(upload ? '/api/upload' : '/api/audit', {method:'POST', headers:{'Content-Type':'application/json','X-Audit-Token':session.token}, body:JSON.stringify(payload)});
    const data = await response.json(); if (!response.ok) throw new Error(data.error);
    result = data; const r = data.report;
    $('results').hidden = false; $('empty').hidden = true;
    $('result-title').textContent = r.root; $('result-meta').textContent = `Generated ${r.generated_at} UTC · ${r.total_files} test files · ${r.total_issues} findings`;
    $('status').textContent = r.score_breakdown.status === 'no_tests' ? 'No tests found. Select a folder containing test_*.py files or choose a Python test file.' : `Audit complete.${r.errors ? ` ${r.errors} error${r.errors === 1 ? '' : 's'} found.` : ''}`;
    const grade = r.score_breakdown.status === 'no_tests' ? 'No tests found' : r.score >= 90 ? 'Excellent' : r.score >= 80 ? 'Good' : r.score >= 65 ? 'Needs work' : r.score >= 50 ? 'Poor' : 'Critical';
    const metrics = [['Quality score',r.score === null ? 'Not assessed' : `${r.score}/100`,grade],['Tests',r.total_tests,`${r.async_count} async · ${r.total_fixtures} fixtures`],['Findings',r.total_issues,`${r.errors} errors · ${r.warnings} warnings · ${r.infos} info`],['Coverage',r.coverage_pct === null?'—':`${r.coverage_pct}%`,r.coverage_pct === null?'No coverage.json found':'Existing coverage report'],['Suite health',`${r.test_debt_pct}% debt`,`${r.isolation_score}% isolation · ${r.skip_count} skip · ${r.xfail_count} xfail`]];
    $('metrics').innerHTML = metrics.map(([label,value,note],i) => `<div class="metric ${i===0?'primary':''}"><div class="label">${esc(label)}</div><div class="value">${esc(value)}</div><small>${esc(note)}</small></div>`).join('');
    $('score-note').textContent = r.score === null ? r.score_breakdown.note : `${r.score_breakdown.note} Based on ${r.score_breakdown.units} analysis units. Deductions start from 100; coverage is assessed only when available.`;
    $('score-breakdown').innerHTML = Object.entries(r.score === null ? {} : r.score_breakdown.deductions).map(([name,points])=>`<div><span>${esc(name)}</span><strong>−${esc(points)} pts</strong></div>`).join(''); render();
  } catch(error) { $('status').className = 'error'; $('status').textContent = error.message; }
  finally { $('run').disabled = false; $('github-token').value = ''; }
});
document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => { view = button.dataset.view; document.querySelectorAll('[data-view]').forEach(b => b.setAttribute('aria-selected',String(b===button))); render(); }));
$('search').addEventListener('input',render); $('severity').addEventListener('change',render);
$('issue-sort').addEventListener('change',render); $('sort-order').addEventListener('change',render);
function render() {
  if (!result) return;
  const r=result.report; let rows=[], columns=[];
  ['severity-label','sort-label','sort-order-label'].forEach(id => $(id).hidden = view !== 'issues');
  if(view==='issues'){columns=['File','Line','Severity','Category','Rule code','Message'];rows=r.files.flatMap(f=>f.issues).filter(i=>!$('severity').value||i.level===$('severity').value).sort((a,b)=>compareIssues({...a,file:displayPath(a.file)},{...b,file:displayPath(b.file)},$('issue-sort').value,$('sort-order').value)).map(i=>[displayPath(i.file),i.line,i.level,i.category,i.code,[i.message,i.explanation,i.suggestion]]);}
  if(view==='files'){columns=['File','Tests','Classes','Fixtures','Lines','Async','Issues'];rows=r.files.map(f=>[displayPath(f.path),f.test_count,f.class_count,f.fixture_count,f.line_count,f.async_count,f.issues.length]);}
  if(view==='tests'||view==='fixtures'){
    const key=view==='tests'?'tests':'fixtures'; const keys=[...new Set(r.files.flatMap(f=>f[key].flatMap(t=>Object.keys(t))))];
    columns=['File',...keys];rows=r.files.flatMap(f=>f[key].map(t=>[displayPath(f.path),...keys.map(k=>t[k])]));
  }
  if(view==='directories'){columns=['Directory','Tests','Errors','Issues']; rows=Object.entries(r.dir_breakdown).map(([name,d])=>[name,d.tests,d.errors,d.issues]);}
  if(view==='configuration'){columns=['Setting','Value'];rows=[['Registered marks',r.registered_marks],['conftest.py files',r.conftest_paths],['Coverage missing',r.coverage_missing],['Skip count',r.skip_count],['Expected failures',r.xfail_count],['Async tests',r.async_count],['Test debt (%)',r.test_debt_pct],['Isolation (%)',r.isolation_score]];}
  const query=$('search').value.toLowerCase();rows=rows.filter(row=>row.map(v=>Array.isArray(v)?v.join(' '):typeof v==='object'&&v!==null?JSON.stringify(v):String(v??'')).join(' ').toLowerCase().includes(query));
  $('row-count').textContent=`${rows.length} results`;
  $('table').innerHTML=rows.length?`<table><thead><tr>${columns.map(c=>`<th scope="col">${esc(c)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map((v,i)=>`<td>${view==='issues'&&i===2?`<span class="badge ${esc(v)}">${esc(v)}</span>`:view==='issues'&&i===5?`<div class="finding-message">${esc(v[0])}</div><details><summary>Why this matters · How to fix</summary><p>${esc(v[1])}</p><p><strong>Suggested fix:</strong> ${esc(v[2])}</p></details>`:cell(v)}</td>`).join('')}</tr>`).join('')}</tbody></table>`:'<div class="no-results">No results for this view or filter.</div>';
}
function download(content,type,name){if(!result)return;const url=URL.createObjectURL(new Blob([content],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('json-download').addEventListener('click',()=>download(JSON.stringify(result.report,null,2),'application/json','pytest_audit.json'));
$('html-download').addEventListener('click',()=>download(result.html,'text/html','pytest_audit.html'));

$('source').addEventListener('change', () => {
  const github = $('source').value === 'github';
  const upload = $('source').value === 'upload';
  $('upload-fields').hidden = !upload; $('path-fields').hidden = upload;
  $('github-fields').hidden = !github; $('browse').hidden = github;
  $('repository').required = github; $('path').required = !github && !upload;
  $('path-title').textContent = github ? 'Path inside repository' : 'Local path';
  $('path').value = ''; $('path').placeholder = github ? 'tests (leave empty for repository root)' : '/path/to/project/tests';
  $('path-help').textContent = github ? 'Folder or file audits are selected automatically from the repository path.' : 'Paths refer to the server running this app. Use Upload from laptop for your own files.';
});
let currentFolder;
async function loadFolder(path) {
  $('picker-status').textContent = 'Loading…'; $('choose-folder').disabled = true; $('browse-entries').replaceChildren();
  try {
    const session = await fetch('/api/session').then(r => r.json());
    const response = await fetch('/api/browse', {method:'POST',headers:{'Content-Type':'application/json','X-Audit-Token':session.token},body:JSON.stringify({path})});
    const data = await response.json(); if(!response.ok) throw new Error(data.error);
    currentFolder = data; $('browse-path').value = data.path; $('browse-entries').replaceChildren();
    data.entries.forEach(entry => {const button=document.createElement('button');button.type='button';button.className='browse-entry secondary';button.textContent=`${entry.directory?'▸':'·'} ${entry.name}`;button.addEventListener('click',()=>{if(entry.directory)loadFolder(entry.path);else{$('path').value=entry.path;$('picker').close();}});$('browse-entries').append(button);});
    $('picker-status').textContent = data.entries.length ? 'Open a folder, select a file, or use the current folder.' : 'No visible folders or Python files.';
    $('choose-folder').disabled = false;
  } catch(error) {$('picker-status').textContent=error.message; $('choose-folder').disabled=true;}
}
$('browse').addEventListener('click',()=>{$('picker').showModal();loadFolder($('path').value || '');});
$('picker-close').addEventListener('click',()=>$('picker').close());
$('browse-form').addEventListener('submit',event=>{event.preventDefault();loadFolder($('browse-path').value);});
$('browse-up').addEventListener('click',()=>{if(currentFolder)loadFolder(currentFolder.parent);});
$('choose-folder').addEventListener('click',()=>{if(currentFolder){$('path').value=currentFolder.path;$('picker').close();}});

if (!['localhost','127.0.0.1','[::1]'].includes(location.hostname)) $('source').value = 'upload';
$('source').dispatchEvent(new Event('change'));
