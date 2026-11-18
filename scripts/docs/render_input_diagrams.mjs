/** Print figures for docs/INPUT_LAYERS_AND_MODEL_FLOW.md.
 * Local-only renderer; source labels follow the four Mermaid diagrams.
 * From the repository root, run:
 * /home/jzhu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node scripts/docs/render_input_diagrams.mjs
 * Uses the bundled sharp module (SVG renderer); no additional installation.
 * Writes SVGs, 3x PNGs, and manifest.json under tmp/pdfs/input_layers/diagrams.
 * No application/model imports or network IO.
 */
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire('/home/jzhu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/package.json');
const sharp = require('sharp');
const root = process.cwd();
const out = path.resolve(root, 'tmp/pdfs/input_layers/diagrams');
fs.mkdirSync(out, { recursive: true });
const esc = s => String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
const palette = { native: ['#e9f1fa','#47688b'], research: ['#e9f4ef','#407b63'], cohort: ['#fff1e4','#a66d37'], external: ['#f5f5f5','#737b83'], plain: ['#ffffff','#536474'] };
function figure(width, height, key) {
  let shapes=[], links=[], captions=[];
  const nodes = {};
  function node(id,x,y,w,h,label,theme=key,opts={}) {
    const [fill,stroke]=palette[theme]; const font=opts.font||9.5;
    const lines=label.split('\n'), lh=opts.lineHeight||11.7;
    nodes[id]={x,y,w,h};
    shapes.push(`<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="5" fill="${fill}" stroke="${stroke}" stroke-width=".9"${opts.dashed?' stroke-dasharray="3 2"':''}/>`);
    const first=y+h/2-(lines.length-1)*lh/2+font*.34;
    shapes.push(`<text x="${x+w/2}" y="${first}" text-anchor="middle" font-size="${font}" fill="#17293a">${lines.map((s,i)=>`<tspan x="${x+w/2}" dy="${i?lh:0}">${esc(s)}</tspan>`).join('')}</text>`);
  }
  function line(points,dashed=false) {
    links.push(`<polyline points="${points.map(p=>p.join(',')).join(' ')}" fill="none" stroke="${dashed?'#737b83':'#344e66'}" stroke-width="1.05"${dashed?' stroke-dasharray="3 2"':''} marker-end="url(#arrow)"/>`);
  }
  function port(id, side) { const {x,y,w,h}=nodes[id]; return side==='t'?[x+w/2,y]:side==='b'?[x+w/2,y+h]:side==='l'?[x,y+h/2]:[x+w,y+h/2]; }
  function edge(a,b,sa='b',sb='t',via=[],dashed=false) { line([port(a,sa),...via,port(b,sb)],dashed); }
  function text(x,y,label,font=9.5,anchor='start',color='#33495c',bold=false) { captions.push(`<text x="${x}" y="${y}" font-size="${font}" text-anchor="${anchor}" fill="${color}"${bold?' font-weight="700"':''}>${esc(label)}</text>`); }
  function lane(y,label,color) { shapes.push(`<line x1="9" y1="${y+6}" x2="731" y2="${y+6}" stroke="${color}" stroke-width=".7"/>`); text(10,y,label,10,'start',color,true); }
  function svg() { return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><defs><marker id="arrow" markerWidth="6" markerHeight="6" refX="5.5" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L6,3 L0,6 Z" fill="#344e66"/></marker></defs><rect width="100%" height="100%" fill="white"/><g font-family="DejaVu Sans, Arial, sans-serif">${links.join('')}${shapes.join('')}${captions.join('')}</g></svg>`; }
  return {width,height,node,edge,line,text,lane,svg};
}
const figures=[];
{
  const f=figure(740,440,'native'); const {node:n,edge:e,line:l,text:t,lane}=f;
  lane(11,'NATIVE FAMILY · default, explicit Fichtl mode, older notebooks','#47688b');
  n('cli',10,25,106,28,'Native JSON /\noffline CLI');
  n('nb',10,60,106,37,'Older Fichtl\nnotebooks: base +\ncandidate + seed');
  n('dash',10,104,106,35,'Dash / Hydra\n→ Prefect flow');
  n('schema',130,26,116,40,'RootSimulationModel\nvalidated native\nparameters');
  n('run',130,83,116,42,'RootSystemSimulation\n.run()\nselect tropism_mode');
  n('legacy',260,30,116,37,'legacy (default)\nnative construction\n+ legacy gravity');
  n('fichtl',260,93,116,46,'fichtl2024 (explicit)\nsame construction +\nFichtl lateral-path\nreconstruction');
  n('tables',387,68,69,40,'Native\nnode + edge\ntables');
  n('support',470,25,144,29,'Aligned grid/core geometry\nand observation support','external',{dashed:true,font:9.3});
  n('obs',470,70,144,55,'Selected native/notebook\nobservation operator:\nscalar statistics, voxel\ngrid or core RLD');
  n('target',626,25,104,29,'Measured\ntarget values','external',{dashed:true});
  n('score',626,76,104,43,'Matching app or\nnotebook objective');
  e('cli','schema','r','l',[[123,39],[123,46]]); e('nb','schema','r','l',[[123,78.5],[123,46]]); e('dash','schema','r','l',[[123,121.5],[123,46]]);
  e('schema','run'); e('run','legacy','r','l',[[253,104],[253,48.5]]); e('run','fichtl','r','l',[[253,104],[253,116]]);
  e('legacy','tables','r','l',[[381,48.5],[381,88]]); e('fichtl','tables','r','l',[[381,116],[381,88]]);
  e('tables','obs','r','l',[[463,88],[463,97.5]]); e('obs','score','r','l'); e('support','obs','b','t',[],true); e('target','score','b','t',[],true);
  lane(163,'CONTROLLED SO4 · shared native construction, separate replay','#407b63');
  n('search',10,187,106,52,'Research notebook /\nCLI: parameters,\nroute and search\nsettings','research');
  n('initial',130,183,116,60,'construct_skeleton\nreuse native\nconstruction stages\nand record INITIAL','research');
  n('replay',260,183,116,60,'Explicit controlled\nreplay: graph\nsegments or\nconstruction steps','research');
  n('rg',387,195,69,36,'Replayed\nnode + edge\ntables','research');
  n('traits',470,191,144,44,'Geometric traits\n+ aligned profiles','research');
  n('ref',626,151,104,35,'SO4 traits/profiles\nframe + support\ncontract','external',{dashed:true,font:9.3,lineHeight:10.6});
  n('sc',626,199,104,39,'Research\ncomparison /\nsearch score','research');
  e('search','initial','r','l');e('initial','replay','r','l');e('replay','rg','r','l');e('rg','traits','r','l');e('traits','sc','r','l');e('ref','sc','b','t',[],true);
  e('sc','search','b','b',[[678,258],[63,258]]); t(370,274,'Next candidate, if search is enabled',9.3,'middle');
  lane(296,'CALVIN COHORT · separate constructor and explicit observation projection','#a66d37');
  n('cc',10,329,106,51,'Calvin cohort\ndictionary:\nglobal + per-order\nrules','cohort');
  n('cg',130,329,116,51,'CohortRootGenerator\n.generate()\nseed + older/later\nprimary counts','cohort');
  n('proj',260,316,116,34,'Root-only\nobservation projection','cohort');
  n('qual',260,361,116,30,'qualify_root_segments','cohort',{font:9.3});
  n('coregeom',387,307,78,40,'Core positions,\nradii, depths,\nmask + frame','external',{dashed:true,font:9.3,lineHeight:10.7});
  n('core',387,358,78,34,'predict_core_\nobservations','cohort',{font:9.3});
  n('full',130,400,116,33,'Full crown graph\norgan records +\ndiagnostics','cohort',{font:9.3});
  n('mass',470,396,144,38,'Whole-root material:\nrepresented axes +\nexplicit crown term','cohort');
  n('ctarget',626,307,104,41,'Measured core RLD /\nmass; explicit whole-\nroot mass definition','external',{dashed:true,font:9.3,lineHeight:10.7});
  n('local',626,361,104,38,'Caller-owned\nlocal comparison','cohort');
  e('cc','cg','r','l');e('cg','proj','r','l',[[252,354.5],[252,333]]);e('proj','qual');e('qual','core','r','l');e('coregeom','core','b','t',[],true);
  e('cg','full');e('cg','mass','r','l',[[252,354.5],[252,415]]);e('core','local','r','l',[[620,375],[620,380]]);e('mass','local','r','b',[[678,415]]);e('ctarget','local','b','t',[],true);
  figures.push({slug:'01-overall-input-flow',title:'Overall model flow: three execution routes',orientation:'landscape',figure:f});
}
{
  const f=figure(480,640,'native'); const {node:n,edge:e,text:t}=f;
  n('input',115,8,250,25,'Flat parameter dictionary');
  n('schema',115,43,250,35,'RootSimulationModel validation\noptional fields receive schema defaults');
  n('new',115,88,250,35,'Fresh RootSystemSimulation\nmatching random_seed and simulation_tag');
  n('guard',115,133,250,34,'run: reject controls that require named replay');
  n('org',115,177,250,50,'init_organs\nprimary/daughter counts, lengths, diameters\nsegment construction and branch sites');
  n('secondary',115,237,250,34,'position_secondary_roots\nattach daughter organs');
  n('primary',115,281,250,50,'position_primary_roots\nouter/inner groups or explicit primary design\noptional yaw, inclination and origin');
  n('mode',155,341,170,26,'tropism_mode');
  n('legacy',16,381,204,38,'apply_gravitropism\nlegacy heading blend');
  n('vp',260,381,204,43,'Validate primaries\ncheck optional primary initialization');
  n('vl',16,429,204,43,'Validate all orders\nreorientation attempts / invalid flags');
  n('fichtl',260,434,204,58,'apply_fichtl_tropism\nretain primary scaffold; rebuild laterals\ninsertion angles +\ncandidate heading search');
  n('vf',260,502,204,38,'Validate lateral orders\nreorientation disabled');
  n('out',115,551,250,35,'RootSystemGraph.as_df\nnode table + edge table');
  n('export',75,596,330,36,'CLI: CSVs, resolved parameters, 3D view, manifest\nor caller-selected analysis');
  for(const [a,b] of [['input','schema'],['schema','new'],['new','guard'],['guard','org'],['org','secondary'],['secondary','primary'],['primary','mode']])e(a,b);
  e('mode','legacy','b','t',[[240,374],[118,374]]);e('mode','vp','b','t',[[240,374],[362,374]]);
  t(122,365,'legacy',9.5,'middle');t(363,365,'fichtl2024',9.5,'middle');
  e('legacy','vl');e('vp','fichtl');e('fichtl','vf');e('vl','out','b','l',[[118,480],[95,480],[95,568.5]]);e('vf','out','b','r',[[362,546],[374,546],[374,568.5]]);e('out','export');
  figures.push({slug:'02-native-fichtl-construction',title:'Native and optional Fichtl construction',orientation:'portrait',figure:f});
}
{
  const f=figure(480,640,'research');const {node:n,edge:e,text:t}=f;
  n('settings',95,8,290,50,'Search configuration\nparameters_file / reference_file\nroute, objective, seeds, search space, budgets');
  n('check',95,68,290,32,'Validate route, source and input identity');
  n('propose',95,110,290,34,'Explicit candidate parameters + simulation seed');
  n('construct',95,154,290,48,'construct_skeleton\ninit_organs → position_secondary_roots\n→ position_primary_roots');
  n('initial',95,212,290,48,'INITIAL tables + construction metadata + hash\noptional declared attachment transform');
  n('route',155,270,170,28,'simulation_route');
  n('graph',10,319,220,55,'replay_arm: arm D\nheading decisions on graph segments');
  n('steps',250,319,220,55,'replay_construction_steps: arm D\ndirection stations separate\nfrom attachment cuts');
  n('boundary',95,386,290,42,'Selected replay includes\nminimum_angle_projection boundary policy');
  n('sample',95,438,290,48,'summarize_sample\ngeometric lengths + soil clipping\ntraits and normalized 10 cm profiles');
  n('ref',10,495,150,39,'Frozen reference +\ncomparison identities','external',{dashed:true});
  n('eval',185,496,255,38,'evaluate_samples\npopulation_mean or per_seed_mean');
  n('receipt',95,546,290,33,'Per-trial metrics / receipts / saved best parameters');
  n('fresh',95,589,290,42,'Separately invoked frozen-candidate evaluation\npredeclared fresh seeds');
  for(const [a,b] of [['settings','check'],['check','propose'],['propose','construct'],['construct','initial'],['initial','route']])e(a,b);
  e('route','graph','b','t',[[240,313],[120,313]]);e('route','steps','b','t',[[240,313],[360,313]]);
  t(120,308,'graph_segments_v1',9.3,'middle');t(360,308,'construction_steps_v1',9.3,'middle');
  e('graph','boundary','b','t',[[120,380],[240,380]]);e('steps','boundary','b','t',[[360,380],[240,380]]);
  e('boundary','sample');e('sample','eval','b','t',[[240,491],[312.5,491]]);e('ref','eval','r','l',[],true);e('eval','receipt','b','t',[[312.5,540],[240,540]]);e('receipt','fresh');
  e('receipt','propose','l','l',[[4,562.5],[4,127]]);t(72,281,'Search',9.3,'end');t(72,293,'continues',9.3,'end');
  figures.push({slug:'03-controlled-so4-flow',title:'Controlled SO4 search and evaluation',orientation:'portrait',figure:f});
}
{
  const f=figure(480,640,'cohort');const {node:n,edge:e,text:t}=f;
  n('config',100,8,280,32,'Nested cohort dictionary\nglobal rules + orders 1 through 5');
  n('validate',100,48,280,32,'CohortRootGenerator\ncopy and validate configuration');
  n('generate',100,88,280,25,'generate(seed, older_count, later_count)');
  n('crown',100,121,280,45,'Nonmaterial crown support\nemergence disk / depth / inclination\nolder maturity = 1; later maturity sampled');
  n('organ',100,174,280,45,'For each queued organ\nbounded length, basal/tip diameter, first branch\nmaturity scaling and parent diameter cap');
  n('branch',100,227,280,45,'Branch probability × maturity\ncount distribution; first branch and extra sites\norder 5 terminal');
  n('curve',100,280,280,43,'integrate_curve\nphysical-step correlated curvature\ndownward drift and surface reflection');
  n('material',100,331,280,55,'Cut at geometry stations, attachments, taper changes\nand fine/coarse threshold crossings\nintegrate volume; equivalent-cylinder diameters');
  n('child',100,394,280,36,'Queue daughters at parent tangent\nshared insertion_heading utility');
  n('full',100,440,280,28,'Full crown graph + organ records');
  n('proj',100,478,280,41,'Root-only projection\nremove crown connectors\none base and plant_id per primary tree');
  n('qual',100,529,280,34,'qualify_root_segments\nroot length, volume, mass and graph checks');
  n('total',10,584,220,47,'Diagnostics\nrepresented root mass\n+ explicit crown mass\n+ optional unrepresented mass','cohort',{font:9.3,lineHeight:10.7});
  n('cores',250,588,220,43,'Caller separately invokes core prediction\nwith aligned core geometry');
  for(const [a,b] of [['config','validate'],['validate','generate'],['generate','crown'],['crown','organ'],['organ','branch'],['branch','curve'],['curve','material'],['material','child'],['child','full'],['full','proj'],['proj','qual']])e(a,b);
  e('child','organ','l','l',[[74,412],[74,196.5]]);t(67,303,'More',9.3,'end');t(67,315,'organs',9.3,'end');t(388,439,'Finished',9.3);
  e('qual','total','b','t',[[240,579],[120,579]]);e('qual','cores','b','t',[[240,579],[360,579]]);
  figures.push({slug:'04-calvin-cohort-construction',title:'Calvin cohort construction and projection',orientation:'portrait',figure:f});
}
const records=[];
for(const {slug,title,orientation,figure:f} of figures) {
  const svgpath=path.join(out,slug+'.svg'), pngpath=path.join(out,slug+'.png');
  fs.writeFileSync(svgpath,f.svg());
  await sharp(Buffer.from(f.svg()), {density: 216}).png().toFile(pngpath);
  records.push({path:pngpath,svg_path:svgpath,title,orientation,width_pt:f.width,height_pt:f.height,pixel_width:f.width*3,pixel_height:f.height*3,min_font_pt:9.3});
}
fs.writeFileSync(path.join(out,'manifest.json'),JSON.stringify({source:'docs/INPUT_LAYERS_AND_MODEL_FLOW.md',rendering:'Local SVG rasterized with bundled Sharp; no remote resources.',diagrams:records},null,2)+'\n');
console.log(JSON.stringify(records.map(({path,title,width_pt,height_pt})=>({path,title,width_pt,height_pt})),null,2));
