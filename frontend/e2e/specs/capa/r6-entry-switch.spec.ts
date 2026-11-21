import {test, expect} from '@playwright/test';
import {mkdir, writeFile} from 'node:fs/promises';
import {existsSync,chmodSync} from 'node:fs';
import path from 'node:path';

const details = JSON.parse(process.env.AGENT_BROWSER_LOGIN!);
const report = process.env.AGENT_BROWSER_REPORT!;
const artifacts = process.env.AGENT_BROWSER_ARTIFACTS!;
const network:Record<string,unknown>[]=[];
const savedSession=details.storage_file&&existsSync(details.storage_file)?details.storage_file:undefined;
test.use({storageState:savedSession});
test.afterEach(async({context})=>{await mkdir(artifacts,{recursive:true});await writeFile(path.join(artifacts,'network.json'),JSON.stringify(network),{mode:0o600});if(details.storage_file){await context.storageState({path:details.storage_file});chmodSync(details.storage_file,0o600);}});

test('R6 normal employee source review, correction and local approval', async ({page, context}) => {
  page.setDefaultTimeout(20000);
  const origins = new Set([new URL(process.env.AGENT_BACKEND_URL!).origin,new URL(process.env.AGENT_BROWSER_URL!).origin]);
  page.on('response',async response=>{const url=new URL(response.url());if(origins.has(url.origin)&&url.pathname.startsWith('/api/')){
    const entry:Record<string,unknown>={event:'response',method:response.request().method(),path:url.pathname,status:response.status()};network.push(entry);
    // Private diagnostic only: preserve the actual denial before unmount can
    // cancel a mutation. Never infer a source-freshness reason from status alone.
    if(response.status()>=400)try{entry.denial=await response.json();}catch{entry.denial_unavailable=true;}
  }});
  page.on('requestfailed',request=>{const url=new URL(request.url());if(origins.has(url.origin))network.push({event:'requestfailed',method:request.method(),path:url.pathname,error:request.failure()?.errorText});});
  page.on('pageerror',error=>network.push({event:'pageerror',name:error.name,message:error.message.slice(0,500)}));
  await context.route('**/*',route=>{const url=route.request().url();return url.startsWith('data:')||origins.has(new URL(url).origin)?route.continue():route.abort();});
  await context.addInitScript(tenant=>{localStorage.setItem('tenant_slug',tenant);localStorage.setItem('openqms_locale','zh-CN');},process.env.AGENT_BROWSER_TENANT!);
  if(!savedSession){await page.goto('/login');await page.locator('#username').fill(details.username);await page.locator('#password').fill(details.password);await page.locator('button[type=submit]').click();await expect(page).toHaveURL(/dashboard/);}
  await page.goto(`/capa/${report}`);

  async function inspectSources(kind:string,id:string,button:string){
    const pending=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith(`/sources/${kind}/${id}`));
    await page.getByRole('button',{name:button,exact:true}).click();
    const response=await pending;expect(response.status()).toBe(200);const source=await response.json();
    expect(source.sources).toHaveLength(3);
    expect(source.sources.map((s:{projection_id:string})=>s.projection_id).sort()).toEqual(['capa.d2.snapshot.v1','capa.d3.snapshot.v1','fmea.failure_cause.reference.v1']);
    expect(source.sources.every((s:{current_state:string})=>s.current_state==='current')).toBe(true);
    const external=source.sources.find((s:{kind:string})=>s.kind==='fmea_projection');
    expect(external.fmea_id).toBe(details.fmea_id);expect(external.node_id).toBe('cause-a');
    if(kind==='d4-candidate'){expect(source.proof.state).toBe('not_issued_by_confirmation');expect(source.supporting).toBeInstanceOf(Array);expect(source.opposing).toBeInstanceOf(Array);}
    else expect(source.proof).toMatchObject({state:'active',bound_to_item:true,basis_current:true});
    const card=page.locator('.ant-card').filter({has:page.getByRole('button',{name:'刷新依据',exact:true})}).last();
    for(const item of source.sources){
      await expect(card).toContainText(item.projection_id);await expect(card).toContainText(item.version);
      const read=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith(`/evidence/${item.source_id}`));
      await card.getByLabel(`重新核对来源 ${item.source_id}`,{exact:true}).click();
      const result=await read;expect(result.status()).toBe(200);expect(await result.json()).toMatchObject({source_id:item.source_id,version:item.version,current_state:'current'});
    }
    await expect(card).toContainText(details.fmea_id);await expect(card).toContainText('cause-a');
    await mkdir(artifacts,{recursive:true});await writeFile(path.join(artifacts,`sources-${kind}-${id}.json`),JSON.stringify(source),{mode:0o600});
  }
  async function clickWrite(button:string,suffix:string,expected=200){
    const pending=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith(suffix)&&r.request().method()==='POST');
    await page.getByRole('button',{name:button,exact:true}).click();const response=await pending;expect(response.status()).toBe(expected);
    // Response headers precede the complete mutation response. Navigation must
    // not cancel its body before the normal UI handler can consume it.
    expect(await response.finished()).toBeNull();await response.body();return response;
  }
  let employeeAuthorization='';
  async function advance(state:string,gate=false){
    const pending=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith(`/capa/${report}/advance`)&&r.request().method()==='POST');
    await page.locator(gate?'[data-e2e="doc-gate-advance"]':'[data-e2e="capa-advance"]').click();
    const response=await pending;expect(response.status()).toBe(200);employeeAuthorization=response.request().headers()['authorization'];expect((await response.json()).capa.status).toBe(state);
  }

  if(details.phase==='generate-d4'||details.phase==='generate-d5'){
    test.setTimeout(180000);
    const d4=details.phase==='generate-d4';
    await page.getByRole('button',{name:'以本报告创建任务',exact:true}).click();
    const sidebar=page.getByRole('dialog');await expect(sidebar).toContainText(`创建目标报告 ${report}`);
    await sidebar.getByLabel('插件安装',{exact:true}).selectOption(details.installation);
    await sidebar.getByLabel('新任务类型',{exact:true}).selectOption(d4?'d4':'d5');
    await sidebar.getByLabel('新任务模型',{exact:true}).selectOption(details.deployment);
    if(d4){await sidebar.getByLabel('D4 输入 FMEA',{exact:true}).selectOption(details.fmea_id);await sidebar.getByLabel('D4 输入原因节点',{exact:true}).selectOption('cause-a');}
    const created=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/agent/tasks'&&r.request().method()==='POST');
    await sidebar.getByRole('button',{name:d4?'开始 D4 根因分析候选任务':/^用 .+ 开始新任务（仅根据当前根因）$/}).click();
    const creation=await created;expect(creation.status()).toBe(201);const task=await creation.json();const command=creation.request().postDataJSON();
    expect(command).toMatchObject({report_id:report,installation_id:details.installation,model_deployment_id:details.deployment});
    expect(task).toMatchObject({target_capa_id:report,preferred_installation_id:details.installation,model_deployment:{deployment_id:details.deployment}});
    if(d4)expect(command.derived_source_scope).toEqual({target_report_id:report,fmea_id:details.fmea_id,cause_node_id:'cause-a'});
    else{expect(command.initial_text).toBe('deliver_d4_root_cause_candidate_v1');expect(command.derived_source_scope).toBeUndefined();}
    const entry:Record<string,any>={stage:'created',creation:{command,task},fixed_report:report,selected_deployment:details.deployment};
    const preserve=async()=>{await mkdir(artifacts,{recursive:true});await writeFile(path.join(artifacts,'task-entry.json'),JSON.stringify(entry),{mode:0o600});};await preserve();
    await expect(sidebar.getByText(`部署版本 ${details.deployment}`,{exact:true})).toBeVisible();
    let checkpoint:any;let emptyProposals:any;
    page.on('response',async response=>{const p=new URL(response.url()).pathname;if(response.status()!==200)return;
      try{
        if(p===`/api/agent/tasks/${task.task_id}/workflow`){const value=await response.json();if(value.question)checkpoint=value;}
        if(p===`/api/capa/${report}/d5-proposals`){const value=await response.json();if(value.items?.length===0)emptyProposals=value;}
      }catch{/* A cancelled background poll supplies no readiness evidence. */}
    });
    const launched=page.waitForResponse(r=>new URL(r.url()).pathname===`/api/agent/tasks/${task.task_id}/launch`&&r.request().method()==='POST',{timeout:150000});
    let launchReturned=false;void launched.then(()=>{launchReturned=true;},()=>{launchReturned=true;});
    await sidebar.getByRole('button',{name:'启动模型任务',exact:true}).click();
    if(d4){
      await expect.poll(()=>launchReturned||!!checkpoint?.question,{timeout:150000}).toBeTruthy();
      if(checkpoint?.question&&!launchReturned){
        expect(checkpoint.status).toBe('waiting');expect(checkpoint.checkpoint_id).toBeTruthy();await expect(sidebar).toContainText(checkpoint.question);
        entry.checkpoint=checkpoint;entry.stage='waiting-for-employee';await preserve();
        const continued=page.waitForResponse(r=>new URL(r.url()).pathname===`/api/agent/tasks/${task.task_id}/messages`&&r.request().method()==='POST');
        await sidebar.getByRole('button',{name:'继续（无额外资料）',exact:true}).click();const message=await continued;expect(message.status()).toBe(202);
        const body=message.request().postDataJSON();expect(JSON.parse(body.content)).toEqual({intent:'continue_d4',additional_context:'none'});
        entry.continue={command:body,result:await message.json()};await preserve();
      }
    }else{
      await expect.poll(()=>checkpoint?.question,{timeout:120000}).toBeTruthy();expect(checkpoint.checkpoint_id).toBeTruthy();
      await expect(sidebar).toContainText(checkpoint.question);await expect.poll(()=>emptyProposals?.items?.length,{timeout:20000}).toBe(0);
      entry.checkpoint=checkpoint;entry.proposals_before_continue=emptyProposals;entry.stage='waiting-for-employee';await preserve();
      const continued=page.waitForResponse(r=>new URL(r.url()).pathname===`/api/agent/tasks/${task.task_id}/messages`&&r.request().method()==='POST');
      await sidebar.getByRole('button',{name:'继续（无额外资料）',exact:true}).click();const message=await continued;expect(message.status()).toBe(202);
      const body=message.request().postDataJSON();expect(JSON.parse(body.content)).toEqual({intent:'continue_d5',additional_context:'none'});
      entry.continue={command:body,result:await message.json()};await preserve();
    }
    const response=await launched;entry.launch={status:response.status(),command:response.request().postDataJSON(),body:await response.json()};entry.stage='launch-returned';await preserve();
    expect(response.status()).toBe(200);expect(await response.finished()).toBeNull();
    if(d4)expect(command.initial_text).toBe('analyze_d4_candidate_v1');
  }else if(details.phase==='view-candidate'){
    await inspectSources('d4-candidate',details.candidate,`依据详情 ${details.candidate}`);
    await expect(page.getByLabel(`核对并确认 ${details.candidate}`,{exact:true})).toHaveCount(0);
    await expect(page.getByRole('button',{name:'确认正式根因',exact:true})).toHaveCount(0);
  }else if(details.phase==='confirm'){
    await inspectSources('d4-candidate',details.candidate,`依据详情 ${details.candidate}`);
    await page.getByLabel(`核对并确认 ${details.candidate}`,{exact:true}).click();await page.getByLabel('最终根因',{exact:true}).fill(details.final_text);
    await clickWrite('确认正式根因',`/d4-candidates/${details.candidate}/confirm`);await page.reload();
    await expect(page.getByLabel(`核对并确认 ${details.candidate}`,{exact:true})).toHaveCount(0);
  }else if(details.phase==='adopt'){
    await inspectSources('d5-proposal',details.proposal,`查看建议依据 ${details.proposal}`);
    await inspectSources('d5-proposal',details.other_proposal,`查看建议依据 ${details.other_proposal}`);
    await page.getByLabel(`最终措施 ${details.proposal}`,{exact:true}).fill(details.adopted_text);
    // The normal write commits; its successful response is lost to the UI.
    // Python replays this exact UI-issued body as the same normal colleague.
    let lost:unknown;
    await page.route(`**/api/capa/${report}/d5-proposals/${details.proposal}/adopt`,async route=>{
      const response=await route.fetch();expect(response.status()).toBe(200);
      lost={command:route.request().postDataJSON(),result:await response.json()};await route.abort('failed');
    });
    await page.getByLabel(`采纳 ${details.proposal}`,{exact:true}).click();await expect.poll(()=>!!lost).toBe(true);
    await mkdir(artifacts,{recursive:true});await writeFile(path.join(artifacts,'adoption-response-loss.json'),JSON.stringify(lost),{mode:0o600});
    await page.unroute(`**/api/capa/${report}/d5-proposals/${details.proposal}/adopt`);await page.reload();
    await expect(page.getByText(details.adopted_text,{exact:true}).first()).toBeVisible();
    await expect(page.getByLabel(`最终措施 ${details.proposal}`,{exact:true})).toHaveCount(0);
  }else if(details.phase==='manual'){
    const field=page.locator('.ant-form-item').filter({hasText:'永久纠正措施'}).locator('textarea');
    await field.fill(details.manual_text);const saved=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith(`/capa/${report}`)&&r.request().method()==='PUT');await field.press('Tab');
    const response=await saved;expect(response.status()).toBe(200);
    expect(response.request().postDataJSON()).toMatchObject({d5_correction:details.manual_text,expected_entry_epoch:details.entry_epoch});expect(response.request().postDataJSON().expected_material_version).toBeTruthy();
    await page.reload();await expect(field).toHaveValue(details.manual_text);await expect(page.getByText(details.adopted_text,{exact:true}).first()).toBeVisible();
  }else if(details.phase==='correct'){
    await page.getByLabel(`更正与历史 ${details.measure}`,{exact:true}).click();
    await inspectSources('d5-measure',details.measure,'查看正式措施依据');
    await page.getByLabel('更正后全文',{exact:true}).fill(details.final_text);
    await page.getByLabel('更正理由',{exact:true}).fill('明确既有检查的责任人与记录位置；未增加频次、阈值或文件要求。');
    await clickWrite('提交更正',`/d5-measures/${details.measure}/corrections`);await page.reload();
    await page.getByLabel(`更正与历史 ${details.measure}`,{exact:true}).click();await expect(page.getByText(details.adopted_text,{exact:true})).toBeVisible();await expect(page.getByText(/更正版本 1/)).toBeVisible();
    await inspectSources('d5-measure',details.measure,'查看正式措施依据');
  }else if(details.phase==='withdraw'){
    await page.getByRole('button',{name:'Agent 任务',exact:true}).click();await page.getByLabel('选择任务',{exact:true}).selectOption(details.task);
    await page.getByLabel('选择处理范围检查点',{exact:true}).selectOption(details.checkpoint);
    const sidebar=page.getByRole('dialog');await sidebar.getByLabel(`选择建议 ${details.withdrawn}`,{exact:true}).check();
    await sidebar.getByLabel('批量撤回原因',{exact:true}).fill('员工保留A，撤回本检查点后未采用的B。');
    const pending=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith(`/d5-checkpoints/${details.checkpoint}/proposals/withdraw`));
    await sidebar.getByRole('button',{name:'撤回选中建议',exact:true}).click();const response=await pending;expect(response.status()).toBe(200);expect(await response.json()).toEqual([{proposal_id:details.withdrawn,outcome:'withdrawn'}]);
    await expect(sidebar.getByText(`${details.withdrawn}：withdrawn`,{exact:true})).toBeVisible();
    await page.getByRole('button',{name:'关闭任务侧栏',exact:true}).click();await page.reload();
    await expect(page.getByText('已撤回',{exact:true})).toBeVisible();await expect(page.getByLabel(`最终措施 ${details.withdrawn}`,{exact:true})).toHaveCount(0);await expect(page.getByText(details.final_text,{exact:true}).first()).toBeVisible();
  }else if(details.phase==='local-close'){
    await advance('D6_VERIFICATION');const field=page.locator('.ant-form-item').filter({hasText:'效果验证'}).locator('textarea');
    await field.fill('合成员工执行既有点检及更换后，同一工艺窗口复测200件0件超差；人工核对执行记录，持续效果需后续监测。');
    const saved=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith(`/capa/${report}`)&&r.request().method()==='PUT');await field.press('Tab');expect((await saved).status()).toBe(200);await advance('D7_PREVENTION');
    await page.getByLabel('本地预防措施',{exact:true}).fill('执行现行开班定位销检查及既有磨损件更换要求，记录责任人和结果；不增加频次、阈值或文件义务。');
    await page.getByLabel('本地预防依据',{exact:true}).fill('员工核对FMEA既有控制、D2/D3、现场验证、普通D5及更正后的正式措施A。');
    await page.getByLabel('本地预防理由',{exact:true}).fill('既有控制执行遗漏，纠正执行及记录。');await clickWrite('保存本地预防','/local-prevention');
    await page.getByLabel('传播处置审阅理由',{exact:true}).fill('来源受限，本轮经验、知识、横向、供应商风险正文传播均不执行。');await clickWrite('记录本轮不执行审阅','/propagation-review');
    await page.reload();
    await expect(page.getByText('执行现行开班定位销检查及既有磨损件更换要求，记录责任人和结果；不增加频次、阈值或文件义务。',{exact:true})).toBeVisible();
    await expect(page.locator('.ant-form-item').filter({hasText:'预防复发措施'}).locator('textarea')).toBeDisabled();
    await advance('D7_COMPLETED');await page.reload();await advance('D8_GATE_PENDING');await page.reload();
    await expect(page.getByLabel(`选择受影响文档 ${details.fmea_id}`,{exact:true})).toBeVisible();await page.getByLabel('人工分析理由',{exact:true}).fill(details.impact_reason);await clickWrite('保存人工分析','/manual-doc-analysis');await page.reload();
    await expect(page.getByText('人工分析已记录；模型未运行，尚须独立门禁处置。',{exact:true})).toBeVisible();
    await expect(page.locator('[data-e2e="doc-gate-advance"]')).toHaveCount(0);
    const blocked=await context.request.post(`${process.env.AGENT_BACKEND_URL}/api/capa/${report}/advance`,{headers:{Authorization:employeeAuthorization,'X-Tenant-ID':process.env.AGENT_BROWSER_TENANT!},data:{target_state:'D8_APPROVAL_PENDING'}});expect(blocked.status()).toBe(400);
    await page.getByLabel('独立确认本轮无受影响文档',{exact:true}).check();await clickWrite('确认空清单','/doc-gate/confirm-no-affected');
    await page.getByLabel('传播处置审阅理由',{exact:true}).fill('审批前再次审阅四通道正文传播NOT_EXECUTED，MES仅ID/状态；不是零风险或已完成。');await clickWrite('记录本轮不执行审阅','/propagation-review');await page.reload();await advance('D8_APPROVAL_PENDING',true);
  }else if(details.phase==='approve'){
    const core=page.locator('[data-e2e="capa-outcome-core"]');await expect(core).toContainText(details.manual_text);
    const official=core.locator('[data-e2e="capa-outcome-d5"]');await expect(official).toContainText(details.final_text);await expect(official).toContainText(details.measure);await expect(official).not.toContainText(details.withdrawn);await expect(official).not.toContainText(details.adopted_text);
    await expect(core.getByLabel('本轮本地闭环与传播处置',{exact:true})).toContainText('NOT_EXECUTED');
    const approved=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith(`/capa/${report}/advance`)&&r.request().method()==='POST');await page.locator('[data-e2e="capa-approve"]').click();const response=await approved;expect(response.status()).toBe(200);expect(response.request().postDataJSON().expected_outcome_revision).toMatch(/^[a-f0-9]{64}$/);
    await expect(page.locator('[data-e2e="capa-outcome-binding"]')).toHaveText('已核对审核版本');
  }else if(details.phase==='closed'){
    await expect(page.locator('[data-e2e="capa-outcome-core"]')).toContainText(details.manual_text);await expect(page.getByText(details.final_text,{exact:true}).first()).toBeVisible();await expect(page.getByLabel(`最终措施 ${details.withdrawn}`,{exact:true})).toHaveCount(0);
    await page.getByLabel(`更正与历史 ${details.measure}`,{exact:true}).click();await expect(page.getByLabel('更正后全文',{exact:true})).toHaveCount(0);await expect(page.getByText(/更正版本 1/)).toBeVisible();await inspectSources('d5-measure',details.measure,'查看正式措施依据');
    const exported=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith('/ppt-export')&&r.request().method()==='POST');await page.getByRole('button',{name:/导出本地规则版 PPT（模型不运行）/}).click();const response=await exported;expect(response.status()).toBe(200);
    await mkdir(artifacts,{recursive:true});await writeFile(path.join(artifacts,'approved.pptx'),await response.body(),{mode:0o600});
  }else{expect(details.phase).toBe('empty');await expect(page.getByRole('button',{name:'确认正式根因',exact:true})).toHaveCount(0);await expect(page.getByLabel('更正后全文',{exact:true})).toHaveCount(0);}
});
